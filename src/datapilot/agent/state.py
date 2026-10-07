"""LangGraph 将要持久化的最小任务状态。"""

from __future__ import annotations

from typing import TypedDict

from datapilot.contracts import AnalysisPlan, ArtifactRef, ReviewResult, TaskStatus
from datapilot.dataset import DatasetProfile


class AgentState(TypedDict):
    """节点共享状态；禁止直接放入 DataFrame 或完整工具输出。"""

    task_id: str
    dataset_id: str
    question: str
    status: TaskStatus
    profile: DatasetProfile | None
    plan: AnalysisPlan | None
    plan_version: int
    revision_feedback: str | None
    current_step_index: int
    tool_result_summaries: list[str]
    artifacts: list[ArtifactRef]
    review: ReviewResult | None
    retry_count: int
    error: str | None


def create_initial_state(*, task_id: str, dataset_id: str, question: str) -> AgentState:
    """创建一个可序列化、没有隐藏副作用的任务初始状态。"""

    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("question cannot be empty")
    return AgentState(
        task_id=task_id,
        dataset_id=dataset_id,
        question=cleaned_question,
        status=TaskStatus.CREATED,
        profile=None,
        plan=None,
        plan_version=0,
        revision_feedback=None,
        current_step_index=0,
        tool_result_summaries=[],
        artifacts=[],
        review=None,
        retry_count=0,
        error=None,
    )
