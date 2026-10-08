"""将完整工具结果保存到 State 之外，只返回小型 ArtifactRef。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from datapilot.contracts import ArtifactRef, PlanStep
from datapilot.tool_runtime import ToolEnvelope


class ArtifactTooLargeError(ValueError):
    """单个工具结果超过 Artifact Store 的大小上限。"""


class ArtifactNotFoundError(FileNotFoundError):
    """ArtifactRef 指向的文件不存在。"""


class ArtifactStore:
    """隐藏 JSON 编码、原子写入、大小限制和安全路径解析。"""

    def __init__(self, root: str | Path, *, max_bytes: int = 20 * 1024 * 1024) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._root = Path(root).resolve()
        self._tool_results = self._root / "tool-results"
        self._max_bytes = max_bytes

    def save_tool_result(self, step: PlanStep, result: ToolEnvelope) -> ArtifactRef:
        """原子保存完整 ToolEnvelope，并返回不含结果正文的引用。"""

        payload = json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > self._max_bytes:
            raise ArtifactTooLargeError("tool result exceeds artifact size limit")

        artifact_id = uuid4().hex
        relative_path = Path("tool-results") / f"{artifact_id}.json"
        destination = self._root / relative_path
        temporary = destination.with_suffix(".tmp")
        self._tool_results.mkdir(parents=True, exist_ok=True)
        try:
            temporary.write_bytes(payload)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

        outcome = "ok" if result.ok else f"error:{result.error.code if result.error else 'unknown'}"
        return ArtifactRef(
            artifact_id=artifact_id,
            kind="tool_result",
            relative_path=relative_path.as_posix(),
            summary=f"step={step.step_id} tool={result.tool_name} outcome={outcome}",
        )

    def load(self, reference: ArtifactRef) -> dict[str, Any]:
        """通过安全相对路径读取一个 JSON Artifact。"""

        path = (self._root / reference.relative_path).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("artifact path escaped the configured root")
        if not path.is_file():
            raise ArtifactNotFoundError(reference.artifact_id)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("artifact content must be a JSON object")
        return loaded
