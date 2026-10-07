"""Validated data contracts for plans, tool calls, reviews, and events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from datapilot.domain.enums import ErrorType, ToolCallStatus


class DomainModel(BaseModel):
    """Reject unexpected fields so boundary drift fails visibly."""

    model_config = ConfigDict(extra="forbid")


class PlanStep(DomainModel):
    step_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=1000)
    preferred_tool: str = Field(min_length=1, max_length=100)
    inputs: list[str] = Field(default_factory=list)
    expected_output: str = Field(min_length=1, max_length=1000)
    success_criteria: list[str] = Field(min_length=1, max_length=10)


class AnalysisPlan(DomainModel):
    question: str = Field(min_length=1, max_length=4000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
    final_deliverables: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_unique_step_ids(self) -> AnalysisPlan:
        # 重复 step_id 会破坏工具审计和恢复，因此在计划进入状态图前拒绝。
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("plan step_id values must be unique")
        return self


class ToolCallRecord(DomainModel):
    call_id: str = Field(min_length=1, max_length=64)
    step_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]
    status: ToolCallStatus
    result_ref: str | None = None
    error_type: ErrorType | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_terminal_fields(self) -> ToolCallRecord:
        if self.status is ToolCallStatus.FAILED and self.error_type is None:
            raise ValueError("failed tool calls require error_type")
        if self.status is ToolCallStatus.SUCCEEDED and self.error_type is not None:
            raise ValueError("successful tool calls cannot contain error_type")
        return self


class ReviewDecision(DomainModel):
    passed: bool
    score: float = Field(ge=0, le=1)
    verified_claims: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    retryable: bool = False
    correction_instructions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_retry_decision(self) -> ReviewDecision:
        if self.passed and (self.retryable or self.issues):
            raise ValueError("a passed review cannot be retryable or contain issues")
        if self.retryable and not self.correction_instructions:
            raise ValueError("retryable reviews require correction instructions")
        return self


class ToolError(DomainModel):
    type: ErrorType
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool = False


class ToolMeta(DomainModel):
    duration_ms: int = Field(default=0, ge=0)
    truncated: bool = False


DataT = TypeVar("DataT")


class ToolEnvelope(DomainModel, Generic[DataT]):
    ok: bool
    data: DataT | None = None
    error: ToolError | None = None
    meta: ToolMeta = Field(default_factory=ToolMeta)

    @model_validator(mode="after")
    def require_matching_payload(self) -> ToolEnvelope[DataT]:
        # 成功与失败载荷必须互斥，避免调用方猜测真实状态。
        if self.ok and self.error is not None:
            raise ValueError("successful tool envelopes cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("failed tool envelopes require an error")
        return self


class TaskEvent(DomainModel):
    event_id: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorDetail(DomainModel):
    error_type: ErrorType
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=1, max_length=64)
    details: dict[str, Any] = Field(default_factory=dict)


class DatasetRecord(DomainModel):
    id: str = Field(min_length=1, max_length=64)
    original_name: str = Field(min_length=1, max_length=255)
    stored_path: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1, max_length=100)
    size: int = Field(ge=0)
    profile: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DatasetIngestResult(DomainModel):
    """Result of storing an upload, including whether content was reused."""

    dataset: DatasetRecord
    deduplicated: bool = False


class TaskRecord(DomainModel):
    id: str = Field(min_length=1, max_length=64)
    dataset_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=4000)
    status: str
    retry_count: int = Field(default=0, ge=0)
    plan_version: int = Field(default=0, ge=0)
    plan: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EventRecord(DomainModel):
    id: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
