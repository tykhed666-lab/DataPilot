"""Async SQLAlchemy engine and transaction lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from datapilot.persistence.models import Base


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    """Enable foreign-key enforcement for every SQLite connection."""

    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Own the engine and expose one commit-or-rollback session boundary."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        engine_options: dict[str, object] = {"echo": echo}
        if url.endswith(":memory:"):
            # 内存 SQLite 必须复用同一连接，否则每个会话会看到不同数据库。
            engine_options["poolclass"] = StaticPool
        self.engine: AsyncEngine = create_async_engine(url, **engine_options)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        """Create missing tables; safe to call more than once in local development."""

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Commit successful work and roll back every exception."""

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self.engine.dispose()
