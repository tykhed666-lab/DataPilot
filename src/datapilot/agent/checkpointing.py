"""LangGraph Checkpointer 的安全序列化与 SQLite 生命周期。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver


def checkpoint_serializer() -> JsonPlusSerializer:
    """只允许恢复 AgentState 中明确登记的项目类型。"""

    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("datapilot.contracts", "AnalysisPlan"),
            ("datapilot.contracts", "ArtifactRef"),
            ("datapilot.contracts", "ReviewResult"),
            ("datapilot.contracts", "TaskStatus"),
            ("datapilot.dataset", "DatasetProfile"),
        ]
    )


def memory_checkpointer() -> InMemorySaver:
    """创建适合单进程学习和单元测试的 Checkpointer。"""

    return InMemorySaver(serde=checkpoint_serializer())


@contextmanager
def open_sqlite_checkpointer(path: str | Path) -> Iterator[SqliteSaver]:
    """打开、初始化并在退出时关闭一个 SQLite Checkpointer。"""

    database_path = Path(path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        saver = SqliteSaver(connection, serde=checkpoint_serializer())
        saver.setup()
        yield saver
    finally:
        connection.close()
