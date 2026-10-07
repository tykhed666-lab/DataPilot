"""Agent 节点之间共享的少量稳定契约。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """拒绝未声明字段，让模型输出或节点状态发生漂移时立即失败。"""

    model_config = ConfigDict(extra="forbid")


class TaskStatus(StrEnum):
    CREATED = "created"
    PROFILING = "profiling"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class PlanStep(ContractModel):
    """Planner 生成的一项可执行分析步骤。"""

    step_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, object] = Field(default_factory=dict)
    expected_output: str = Field(min_length=1, max_length=500)


class AnalysisPlan(ContractModel):
    """等待人工审批的结构化计划，最多包含八个步骤。"""

    question: str = Field(min_length=1, max_length=4000)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
    final_deliverable: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_step_ids(self) -> AnalysisPlan:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("plan step_id values must be unique")
        return self


class ReviewResult(ContractModel):
    """Reviewer 对本轮执行结果给出的结构化判断。"""

    passed: bool
    score: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    retryable: bool = False
    correction: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> ReviewResult:
        if self.passed and (self.issues or self.retryable):
            raise ValueError("a passed review cannot contain issues or request a retry")
        if self.retryable and not self.correction:
            raise ValueError("a retryable review requires correction guidance")
        return self


class ArtifactRef(ContractModel):
    """大结果留在磁盘，AgentState 只携带小型引用和摘要。"""

    artifact_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=50)
    relative_path: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=1000)
