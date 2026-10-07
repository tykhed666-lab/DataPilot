"""SQLAlchemy row models for the six business tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from datapilot.domain.enums import TaskStatus, ToolCallStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DatasetRow(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (CheckConstraint("size >= 0", name="ck_datasets_size_nonnegative"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1000), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TaskRow(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="ck_tasks_retry_count_nonnegative"),
        CheckConstraint("plan_version >= 0", name="ck_tasks_plan_version_nonnegative"),
        Index("ix_tasks_dataset_status", "dataset_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.CREATED.value, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TaskEventRow(TimestampMixin, Base):
    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_task_events_sequence_positive"),
        Index("ux_task_events_task_sequence", "task_id", "sequence", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApprovalRow(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("plan_version >= 1", name="ck_approvals_plan_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    plan_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolCallRow(TimestampMixin, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_tool_duration"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    args_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ToolCallStatus.RUNNING.value)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ArtifactRow(TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (CheckConstraint("size >= 0", name="ck_artifacts_size_nonnegative"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1000), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
