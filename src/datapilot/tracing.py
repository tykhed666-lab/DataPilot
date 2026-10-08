"""追加式 JSONL Agent Trace，不记录完整工具结果。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from pydantic import Field

from datapilot.contracts import ContractModel


class TraceEvent(ContractModel):
    trace_id: str
    task_id: str
    sequence: int = Field(ge=1)
    kind: Literal["node", "model", "tool", "decision"]
    name: str
    status: Literal["started", "succeeded", "failed", "paused", "reused"]
    timestamp: str
    duration_ms: float = Field(ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class TraceRecorder:
    """用 record/read 隐藏安全文件名、序号和 JSONL 追加。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._lock = Lock()

    def record(
        self,
        *,
        task_id: str,
        kind: Literal["node", "model", "tool", "decision"],
        name: str,
        status: Literal["started", "succeeded", "failed", "paused", "reused"],
        duration_ms: float = 0,
        details: dict[str, Any] | None = None,
    ) -> TraceEvent:
        path = self._path(task_id)
        with self._lock:
            events = self._read_path(path)
            event = TraceEvent(
                trace_id=path.stem,
                task_id=task_id,
                sequence=len(events) + 1,
                kind=kind,
                name=name,
                status=status,
                timestamp=datetime.now(UTC).isoformat(),
                duration_ms=round(duration_ms, 3),
                details=details or {},
            )
            self._root.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
            return event

    def read(self, task_id: str) -> list[TraceEvent]:
        with self._lock:
            return self._read_path(self._path(task_id))

    def _path(self, task_id: str) -> Path:
        trace_id = sha256(task_id.encode()).hexdigest()[:24]
        return self._root / f"{trace_id}.jsonl"

    @staticmethod
    def _read_path(path: Path) -> list[TraceEvent]:
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            loaded = json.loads(line)
            events.append(TraceEvent.model_validate(loaded))
        return events
