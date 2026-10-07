"""把 Dataset Profile 与 Planner 连接成第一个可执行 LangGraph。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

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

    def __init__(self, *, planner: Planner, tools: ToolRegistry) -> None:
        self._planner = planner
        self._tools = tools
        self._graph = self._build_graph()

    def run(
        self,
        state: AgentState,
        *,
        dataset_relative_path: str,
    ) -> AgentState:
        """从初始状态运行到等待审批或失败终态。"""

        result = self._graph.invoke(
            state,
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
        graph.add_edge("await_approval", END)
        return graph.compile(name="datapilot-day-07")

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
        del state
        return {"status": TaskStatus.AWAITING_APPROVAL}

    @staticmethod
    def _route_after_profile(state: AgentState) -> Literal["plan", "end"]:
        return "plan" if state["status"] is TaskStatus.PLANNING else "end"

    @staticmethod
    def _route_after_plan(state: AgentState) -> Literal["await_approval", "end"]:
        return "await_approval" if state.get("plan") is not None else "end"
