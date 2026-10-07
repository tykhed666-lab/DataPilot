"""Small repositories that translate SQLAlchemy rows into domain records."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update

from datapilot.domain.enums import TaskStatus
from datapilot.domain.models import DatasetRecord, EventRecord, TaskRecord
from datapilot.persistence.database import Database
from datapilot.persistence.models import DatasetRow, TaskEventRow, TaskRow


def _dataset_record(row: DatasetRow) -> DatasetRecord:
    return DatasetRecord(
        id=row.id,
        original_name=row.original_name,
        stored_path=row.stored_path,
        sha256=row.sha256,
        media_type=row.media_type,
        size=row.size,
        profile=row.profile_json,
        created_at=row.created_at,
    )


def _task_record(row: TaskRow) -> TaskRecord:
    return TaskRecord(
        id=row.id,
        dataset_id=row.dataset_id,
        question=row.question,
        status=row.status,
        retry_count=row.retry_count,
        plan_version=row.plan_version,
        plan=row.plan_json,
        review=row.review_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_record(row: TaskEventRow) -> EventRecord:
    return EventRecord(
        id=row.id,
        task_id=row.task_id,
        sequence=row.sequence,
        event_type=row.event_type,
        payload=row.payload_json,
        created_at=row.created_at,
    )


class DatasetRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        *,
        dataset_id: str,
        original_name: str,
        stored_path: str,
        sha256: str,
        media_type: str,
        size: int,
    ) -> DatasetRecord:
        row = DatasetRow(
            id=dataset_id,
            original_name=original_name,
            stored_path=stored_path,
            sha256=sha256,
            media_type=media_type,
            size=size,
        )
        async with self.database.session() as session:
            session.add(row)
            await session.flush()
            return _dataset_record(row)

    async def get(self, dataset_id: str) -> DatasetRecord | None:
        async with self.database.session() as session:
            row = await session.get(DatasetRow, dataset_id)
            return _dataset_record(row) if row else None

    async def get_by_sha256(self, sha256: str) -> DatasetRecord | None:
        async with self.database.session() as session:
            row = await session.scalar(select(DatasetRow).where(DatasetRow.sha256 == sha256))
            return _dataset_record(row) if row else None


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, *, task_id: str, dataset_id: str, question: str) -> TaskRecord:
        row = TaskRow(id=task_id, dataset_id=dataset_id, question=question)
        async with self.database.session() as session:
            session.add(row)
            await session.flush()
            return _task_record(row)

    async def get(self, task_id: str) -> TaskRecord | None:
        async with self.database.session() as session:
            row = await session.get(TaskRow, task_id)
            return _task_record(row) if row else None

    async def transition_status(
        self,
        task_id: str,
        *,
        expected: TaskStatus,
        target: TaskStatus,
    ) -> bool:
        async with self.database.session() as session:
            result = await session.execute(
                update(TaskRow)
                .where(TaskRow.id == task_id, TaskRow.status == expected.value)
                .values(status=target.value)
            )
            # 比较并更新同一条 SQL 完成，避免两个请求同时推进同一任务。
            return result.rowcount == 1  # type: ignore[attr-defined]


class EventRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def append(
        self,
        *,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> EventRecord:
        async with self.database.session() as session:
            last_sequence = await session.scalar(
                select(func.max(TaskEventRow.sequence)).where(TaskEventRow.task_id == task_id)
            )
            row = TaskEventRow(
                id=f"evt_{uuid4().hex}",
                task_id=task_id,
                sequence=(last_sequence or 0) + 1,
                event_type=event_type,
                payload_json=payload or {},
            )
            session.add(row)
            await session.flush()
            return _event_record(row)

    async def list_after(self, task_id: str, *, after_sequence: int = 0) -> list[EventRecord]:
        async with self.database.session() as session:
            rows = (
                await session.scalars(
                    select(TaskEventRow)
                    .where(
                        TaskEventRow.task_id == task_id,
                        TaskEventRow.sequence > after_sequence,
                    )
                    .order_by(TaskEventRow.sequence)
                )
            ).all()
            return [_event_record(row) for row in rows]
