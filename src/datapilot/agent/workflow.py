"""连接 Profile、Planner、人工审批和逐步执行的 LangGraph。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from datapilot.agent.approval import ApprovalDecision, ApprovalRequest, StalePlanVersionError
from datapilot.agent.artifacts import ArtifactStore
from datapilot.agent.executor import PlanExecutor
from datapilot.agent.planner import Planner, PlannerRequest
from datapilot.agent.state import AgentState
from datapilot.contracts import TaskStatus
from datapilot.dataset import DatasetProfile
from datapilot.tool_runtime import ToolRegistry


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
        checkpointer: BaseCheckpointSaver[str] | None = None,
    ) -> None:
        self._planner = planner
        self._tools = tools
        self._executor = PlanExecutor(tools=tools, artifacts=artifacts)
        self._checkpointer = checkpointer or _memory_checkpointer()
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
            {"continue": "execute", "end": END},
        )
        return graph.compile(checkpointer=self._checkpointer, name="datapilot-day-09")

    def _profile_node(
        self,
        state: AgentState,
        runtime: Runtime[WorkflowContext],
    ) -> dict[str, object]:
        del state
        result = self._tools.invoke(
            "profile_dataset",
            {"relative_path": runtime.context.dataset_relative_path},
        )
        if not result.ok or result.output is None:
            error_code = result.error.code if result.error else "unknown_tool_error"
            return {
                "status": TaskStatus.FAILED,
                "error": f"profile_failed:{error_code}",
            }
        return {
            "status": TaskStatus.PLANNING,
            "profile": DatasetProfile.model_validate(result.output),
            "error": None,
        }

    def _plan_node(
        self,
        state: AgentState,
        runtime: Runtime[WorkflowContext],
    ) -> dict[str, object]:
        profile = state.get("profile")
        if profile is None:
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
            return {
                "status": TaskStatus.FAILED,
                "error": f"planning_failed:{type(error).__name__}",
            }
        return {"plan": plan, "error": None}

    @staticmethod
    def _await_approval_node(state: AgentState) -> dict[str, object]:
        return {
            "status": TaskStatus.AWAITING_APPROVAL,
            "plan_version": state["plan_version"] + 1,
        }

    @staticmethod
    def _approval_node(state: AgentState) -> dict[str, object]:
        decision = ApprovalRequest.model_validate(
            interrupt(
                {
                    "task_id": state["task_id"],
                    "plan_version": state["plan_version"],
                    "plan": state["plan"].model_dump(mode="json") if state["plan"] else None,
                }
            )
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
        plan = state.get("plan")
        index = state["current_step_index"]
        if plan is None or index >= len(plan.steps):
            return {"status": TaskStatus.FAILED, "error": "execution_failed:missing_step"}

        execution = self._executor.execute_step(plan.steps[index])
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

    @staticmethod
    def _route_after_execution(state: AgentState) -> Literal["continue", "end"]:
        return "continue" if state["status"] is TaskStatus.EXECUTING else "end"

    @staticmethod
    def _config(task_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": task_id}}


def _memory_checkpointer() -> InMemorySaver:
    """只允许恢复 AgentState 中明确登记的项目类型。"""

    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("datapilot.contracts", "AnalysisPlan"),
            ("datapilot.contracts", "ArtifactRef"),
            ("datapilot.contracts", "TaskStatus"),
            ("datapilot.dataset", "DatasetProfile"),
        ]
    )
    return InMemorySaver(serde=serializer)
