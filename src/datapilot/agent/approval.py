"""Human-in-the-loop 审批请求的稳定契约。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from datapilot.contracts import ContractModel


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class ApprovalRequest(ContractModel):
    """恢复暂停图所需的审批决定。"""

    decision: ApprovalDecision
    plan_version: int = Field(ge=1)
    feedback: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("feedback cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def require_feedback_for_revision(self) -> ApprovalRequest:
        if self.decision is ApprovalDecision.REVISE and not self.feedback:
            raise ValueError("revise decision requires feedback")
        return self


class StalePlanVersionError(ValueError):
    """审批请求针对的不是当前等待审批的计划版本。"""
