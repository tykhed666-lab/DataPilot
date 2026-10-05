"""LangGraph state shape; large values are stored externally and referenced by ID."""

from typing import Any, TypedDict

from datapilot.domain.models import AnalysisPlan, ReviewDecision, ToolCallRecord


class AgentState(TypedDict, total=False):
    task_id: str
    dataset_id: str
    question: str
    dataset_profile: dict[str, Any]
    plan: AnalysisPlan
    plan_version: int
    approval_feedback: str
    current_step_index: int
    tool_calls: list[ToolCallRecord]
    step_results: dict[str, str]
    review: ReviewDecision
    retry_count: int
    artifact_ids: list[str]
    error: dict[str, Any] | None
