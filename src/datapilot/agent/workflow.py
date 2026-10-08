"""连接 Profile、Planner、人工审批和逐步执行的 LangGraph。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from datapilot.agent.approval import ApprovalDecision, ApprovalRequest, StalePlanVersionError
from datapilot.agent.artifacts import ArtifactStore
from datapilot.agent.checkpointing import memory_checkpointer
from datapilot.agent.executor import PlanExecutor
from datapilot.agent.planner import Planner, PlannerRequest
from datapilot.agent.reviewer import HybridReviewer
from datapilot.agent.state import AgentState
from datapilot.contracts import TaskStatus
from datapilot.dataset import DatasetProfile
from datapilot.tool_runtime import ToolRegistry
from datapilot.tracing import TraceRecorder


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    """单次图运行需要、但不属于可持久化任务状态的上下文。"""

    dataset_relative_path: str


class AgentWorkflow:
    """隐藏节点、边和路由细节，只暴露一次完整图运行。"""

    def __init__(
        self,
        *,
        planner: Planner,
        tools: ToolRegistry,
        artifacts: ArtifactStore,
        reviewer: HybridReviewer | None = None,
        max_retries: int = 2,
        trace: TraceRecorder | None = None,
        checkpointer: BaseCheckpointSaver[str] | None = None,
    ) -> None:
        if not 0 <= max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")
        self._planner = planner
        self._tools = tools
        self._artifacts = artifacts
        self._executor = PlanExecutor(tools=tools, artifacts=artifacts)
        self._reviewer = reviewer
        self._max_retries = max_retries
        self._trace = trace
        self._checkpointer = checkpointer or memory_checkpointer()
        self._graph = self._build_graph()

    def start(
        self,
        state: AgentState,
        *,
        dataset_relative_path: str,
    ) -> AgentState:
        """从初始状态运行到等待审批或失败终态。"""

        result = self._graph.invoke(
            state,
            config=self._config(state["task_id"]),
            context=WorkflowContext(dataset_relative_path=dataset_relative_path),
        )
        return cast(AgentState, result)

    def get_state(self, task_id: str) -> AgentState:
        """读取持久化任务状态，不推进图。"""

        snapshot = self._graph.get_state(self._config(task_id))
        if not snapshot.values:
            raise KeyError(task_id)
        return cast(AgentState, snapshot.values)

    def run(
        self,
        state: AgentState,
        *,
        dataset_relative_path: str,
    ) -> AgentState:
        """Day 7 的兼容入口；等价于 start。"""

        return self.start(state, dataset_relative_path=dataset_relative_path)

    def resume(
        self,
        *,
        task_id: str,
        dataset_relative_path: str,
        approval: ApprovalRequest,
    ) -> AgentState:
        """用人工审批结果恢复指定 task_id 的暂停图。"""

        config = self._config(task_id)
        snapshot = self._graph.get_state(config)
        current = cast(AgentState, snapshot.values)
        if current.get("plan_version") != approval.plan_version:
            raise StalePlanVersionError("approval plan_version is stale")
        result = self._graph.invoke(
            Command(resume=approval.model_dump(mode="json")),
            config=config,
            context=WorkflowContext(dataset_relative_path=dataset_relative_path),
        )
        return cast(AgentState, result)

    def _build_graph(
        self,
    ) -> CompiledStateGraph[AgentState, WorkflowContext, AgentState, AgentState]:
        graph = StateGraph(AgentState, context_schema=WorkflowContext)
        graph.add_node("profile", self._profile_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("await_approval", self._await_approval_node)
        graph.add_node("approval", self._approval_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("review", self._review_node)
        graph.add_node("report", self._report_node)
        graph.add_edge(START, "profile")
        graph.add_conditional_edges(
            "profile",
            self._route_after_profile,
            {"plan": "plan", "end": END},
        )
        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"await_approval": "await_approval", "end": END},
        )
        graph.add_edge("await_approval", "approval")
        graph.add_conditional_edges(
            "approval",
            self._route_after_approval,
            {"execute": "execute", "replan": "plan", "end": END},
        )
        graph.add_conditional_edges(
            "execute",
            self._route_after_execution,
            {"continue": "execute", "review": "review", "end": END},
        )
        graph.add_conditional_edges(
            "review",
            self._route_after_review,
            {"replan": "plan", "report": "report", "end": END},
        )
        graph.add_edge("report", END)
        return graph.compile(checkpointer=self._checkpointer, name="datapilot-day-09")

    def _profile_node(
        self,
        state: AgentState,
        runtime: Runtime[WorkflowContext],
    ) -> dict[str, object]:
        started = perf_counter()
        result = self._tools.invoke(
            "profile_dataset",
            {"relative_path": runtime.context.dataset_relative_path},
        )
        if not result.ok or result.output is None:
            error_code = result.error.code if result.error else "unknown_tool_error"
            self._record(
                state["task_id"],
                "node",
                "profile",
                "failed",
                started,
                {"error_code": error_code},
            )
            return {
                "status": TaskStatus.FAILED,
                "error": f"profile_failed:{error_code}",
            }
        profile = DatasetProfile.model_validate(result.output)
        self._record(
            state["task_id"],
            "node",
            "profile",
            "succeeded",
            started,
            {"row_count": profile.row_count, "column_count": profile.column_count},
        )
        return {
            "status": TaskStatus.PLANNING,
            "profile": profile,
            "error": None,
        }

    def _plan_node(
        self,
        state: AgentState,
        runtime: Runtime[WorkflowContext],
    ) -> dict[str, object]:
        started = perf_counter()
        profile = state.get("profile")
        if profile is None:
            self._record(state["task_id"], "model", "plan", "failed", started)
            return {"status": TaskStatus.FAILED, "error": "planning_failed:missing_profile"}
        try:
            plan = self._planner.create_plan(
                PlannerRequest(
                    question=state["question"],
                    dataset_relative_path=runtime.context.dataset_relative_path,
                    profile=profile,
                    tools=self._tools.list_tools(),
                    revision_feedback=state.get("revision_feedback"),
                )
            )
        except Exception as error:
            self._record(
                state["task_id"],
                "model",
                "plan",
                "failed",
                started,
                {"error_type": type(error).__name__},
            )
            return {
                "status": TaskStatus.FAILED,
                "error": f"planning_failed:{type(error).__name__}",
            }
        self._record(
            state["task_id"],
            "model",
            "plan",
            "succeeded",
            started,
            {"step_count": len(plan.steps)},
        )
        return {"plan": plan, "error": None}

    def _await_approval_node(self, state: AgentState) -> dict[str, object]:
        self._record(
            state["task_id"],
            "decision",
            "approval",
            "paused",
            perf_counter(),
            {"plan_version": state["plan_version"] + 1},
        )
        return {
            "status": TaskStatus.AWAITING_APPROVAL,
            "plan_version": state["plan_version"] + 1,
        }

    def _approval_node(self, state: AgentState) -> dict[str, object]:
        started = perf_counter()
        decision = ApprovalRequest.model_validate(
            interrupt(
                {
                    "task_id": state["task_id"],
                    "plan_version": state["plan_version"],
                    "plan": state["plan"].model_dump(mode="json") if state["plan"] else None,
                }
            )
        )
        self._record(
            state["task_id"],
            "decision",
            "approval",
            "succeeded",
            started,
            {"decision": decision.decision.value, "plan_version": decision.plan_version},
        )
        if decision.decision is ApprovalDecision.APPROVE:
            return {"status": TaskStatus.EXECUTING, "revision_feedback": None}
        if decision.decision is ApprovalDecision.REJECT:
            return {"status": TaskStatus.REJECTED, "revision_feedback": decision.feedback}
        return {
            "status": TaskStatus.PLANNING,
            "plan": None,
            "revision_feedback": decision.feedback,
        }

    def _execute_node(self, state: AgentState) -> dict[str, object]:
        started = perf_counter()
        plan = state.get("plan")
        index = state["current_step_index"]
        if plan is None or index >= len(plan.steps):
            return {"status": TaskStatus.FAILED, "error": "execution_failed:missing_step"}

        execution = self._executor.execute_step(
            task_id=state["task_id"],
            plan_version=state["plan_version"],
            step=plan.steps[index],
        )
        execution_status: Literal["succeeded", "failed", "reused"]
        if execution.reused:
            execution_status = "reused"
        elif execution.succeeded:
            execution_status = "succeeded"
        else:
            execution_status = "failed"
        self._record(
            state["task_id"],
            "tool",
            plan.steps[index].tool_name,
            execution_status,
            started,
            {"call_id": execution.call_id, "step_id": plan.steps[index].step_id},
        )
        next_index = index + 1
        updates: dict[str, object] = {
            "current_step_index": next_index,
            "artifacts": [*state["artifacts"], execution.artifact],
            "tool_result_summaries": [
                *state["tool_result_summaries"],
                execution.summary,
            ],
        }
        if not execution.succeeded:
            updates.update(
                status=TaskStatus.FAILED,
                error=f"execution_failed:{execution.error_code or 'unknown_tool_error'}",
            )
        elif next_index == len(plan.steps):
            updates.update(status=TaskStatus.REVIEWING, error=None)
        else:
            updates.update(status=TaskStatus.EXECUTING, error=None)
        return updates

    def _review_node(self, state: AgentState) -> dict[str, object]:
        started = perf_counter()
        plan = state.get("plan")
        if self._reviewer is None or plan is None:
            return {"status": TaskStatus.FAILED, "error": "review_failed:not_configured"}
        try:
            review = self._reviewer.review(
                plan=plan,
                artifact_refs=state["artifacts"],
            )
        except Exception as error:
            self._record(
                state["task_id"],
                "node",
                "review",
                "failed",
                started,
                {"error_type": type(error).__name__},
            )
            return {
                "status": TaskStatus.FAILED,
                "error": f"review_failed:{type(error).__name__}",
            }

        self._record(
            state["task_id"],
            "node",
            "review",
            "succeeded" if review.passed else "failed",
            started,
            {"score": review.score, "retryable": review.retryable},
        )
        if review.passed:
            return {
                "status": TaskStatus.COMPLETED,
                "review": review,
                "error": None,
            }
        if review.retryable and state["retry_count"] < self._max_retries:
            return {
                "status": TaskStatus.PLANNING,
                "plan": None,
                "review": review,
                "retry_count": state["retry_count"] + 1,
                "revision_feedback": review.correction,
                "current_step_index": 0,
                "tool_result_summaries": [],
                "artifacts": [],
                "error": None,
            }
        reason = "retry_exhausted" if review.retryable else "non_retryable"
        return {
            "status": TaskStatus.FAILED,
            "review": review,
            "error": f"review_failed:{reason}",
        }

    def _report_node(self, state: AgentState) -> dict[str, object]:
        started = perf_counter()
        plan = state.get("plan")
        review = state.get("review")
        if plan is None or review is None or not review.passed:
            return {"status": TaskStatus.FAILED, "error": "report_failed:unverified_evidence"}
        evidence_blocks = []
        for reference in state["artifacts"]:
            payload = self._artifacts.load(reference)
            evidence_blocks.append(
                f"### {reference.summary}\n\n```json\n"
                f"{json.dumps(payload.get('output'), ensure_ascii=False, indent=2)}\n```"
            )
        evidence = "\n\n".join(evidence_blocks)
        markdown = (
            f"# DataPilot 分析报告\n\n"
            f"## 问题\n\n{state['question']}\n\n"
            f"## 执行计划\n\n"
            + "\n".join(f"{index}. {step.title}" for index, step in enumerate(plan.steps, 1))
            + f"\n\n## 证据\n\n{evidence}\n\n"
            f"## 审核结论\n\n通过，可信度评分：{review.score:.2f}\n"
        )
        reference = self._artifacts.save_report(state["task_id"], markdown)
        self._record(state["task_id"], "node", "report", "succeeded", started)
        return {
            "status": TaskStatus.COMPLETED,
            "artifacts": [*state["artifacts"], reference],
            "error": None,
        }

    @staticmethod
    def _route_after_profile(state: AgentState) -> Literal["plan", "end"]:
        return "plan" if state["status"] is TaskStatus.PLANNING else "end"

    @staticmethod
    def _route_after_plan(state: AgentState) -> Literal["await_approval", "end"]:
        return "await_approval" if state.get("plan") is not None else "end"

    @staticmethod
    def _route_after_approval(state: AgentState) -> Literal["execute", "replan", "end"]:
        if state["status"] is TaskStatus.EXECUTING:
            return "execute"
        if state["status"] is TaskStatus.PLANNING:
            return "replan"
        return "end"

    def _route_after_execution(self, state: AgentState) -> Literal["continue", "review", "end"]:
        if state["status"] is TaskStatus.EXECUTING:
            return "continue"
        if state["status"] is TaskStatus.REVIEWING and self._reviewer is not None:
            return "review"
        return "end"

    @staticmethod
    def _route_after_review(state: AgentState) -> Literal["replan", "report", "end"]:
        if state["status"] is TaskStatus.PLANNING:
            return "replan"
        if state["status"] is TaskStatus.COMPLETED:
            return "report"
        return "end"

    @staticmethod
    def _config(task_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": task_id}}

    def _record(
        self,
        task_id: str,
        kind: Literal["node", "model", "tool", "decision"],
        name: str,
        status: Literal["started", "succeeded", "failed", "paused", "reused"],
        started: float,
        details: dict[str, object] | None = None,
    ) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            kind=kind,
            name=name,
            status=status,
            duration_ms=(perf_counter() - started) * 1000,
            details=details,
        )
