from collections.abc import AsyncIterator

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from datapilot.domain import TaskStatus
from datapilot.persistence import Database, DatasetRepository, EventRepository, TaskRepository


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.initialize()
    yield database
    await database.dispose()


async def seed_dataset(repository: DatasetRepository) -> None:
    await repository.create(
        dataset_id="dataset-1",
        original_name="sales.csv",
        stored_path="data/uploads/dataset-1/source.csv",
        sha256="a" * 64,
        media_type="text/csv",
        size=128,
    )


async def test_initialize_creates_all_business_tables(database: Database) -> None:
    await database.initialize()

    async with database.engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert table_names == {
        "approvals",
        "artifacts",
        "datasets",
        "task_events",
        "tasks",
        "tool_calls",
    }


async def test_dataset_round_trip_and_hash_lookup(database: Database) -> None:
    repository = DatasetRepository(database)
    await seed_dataset(repository)

    loaded = await repository.get("dataset-1")
    duplicate = await repository.get_by_sha256("a" * 64)

    assert loaded is not None
    assert loaded.original_name == "sales.csv"
    assert duplicate == loaded


async def test_duplicate_dataset_hash_is_rejected(database: Database) -> None:
    repository = DatasetRepository(database)
    await seed_dataset(repository)

    with pytest.raises(IntegrityError):
        await repository.create(
            dataset_id="dataset-2",
            original_name="copy.csv",
            stored_path="data/uploads/dataset-2/source.csv",
            sha256="a" * 64,
            media_type="text/csv",
            size=128,
        )

    assert await repository.get("dataset-2") is None


async def test_task_requires_existing_dataset(database: Database) -> None:
    repository = TaskRepository(database)

    with pytest.raises(IntegrityError):
        await repository.create(
            task_id="task-1",
            dataset_id="missing",
            question="分析销售趋势",
        )


async def test_task_status_transition_uses_expected_state(database: Database) -> None:
    datasets = DatasetRepository(database)
    tasks = TaskRepository(database)
    await seed_dataset(datasets)
    await tasks.create(task_id="task-1", dataset_id="dataset-1", question="分析销售趋势")

    changed = await tasks.transition_status(
        "task-1",
        expected=TaskStatus.CREATED,
        target=TaskStatus.PROFILING,
    )
    stale_change = await tasks.transition_status(
        "task-1",
        expected=TaskStatus.CREATED,
        target=TaskStatus.CANCELLED,
    )

    task = await tasks.get("task-1")
    assert changed is True
    assert stale_change is False
    assert task is not None
    assert task.status == TaskStatus.PROFILING


async def test_events_are_ordered_and_support_replay_cursor(database: Database) -> None:
    datasets = DatasetRepository(database)
    tasks = TaskRepository(database)
    events = EventRepository(database)
    await seed_dataset(datasets)
    await tasks.create(task_id="task-1", dataset_id="dataset-1", question="分析销售趋势")

    await events.append(task_id="task-1", event_type="task.created")
    second = await events.append(
        task_id="task-1",
        event_type="task.status_changed",
        payload={"status": "profiling"},
    )

    replay = await events.list_after("task-1", after_sequence=1)
    assert second.sequence == 2
    assert [event.sequence for event in replay] == [2]
    assert replay[0].payload == {"status": "profiling"}
