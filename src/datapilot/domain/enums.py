"""Finite state and error vocabularies used across DataPilot."""

from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "created"
    PROFILING = "profiling"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorType(StrEnum):
    VALIDATION = "validation"
    DATA = "data"
    SQL = "sql"
    PYTHON = "python"
    TIMEOUT = "timeout"
    SECURITY = "security"
    MODEL = "model"
    SYSTEM = "system"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
