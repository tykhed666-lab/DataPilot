"""将完整工具结果保存到 State 之外，只返回小型 ArtifactRef。"""

from __future__ import annotations

import json
import re
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

    def save_tool_result(
        self,
        call_id: str,
        step: PlanStep,
        result: ToolEnvelope,
    ) -> ArtifactRef:
        """原子保存完整 ToolEnvelope，并返回不含结果正文的引用。"""

        _validate_call_id(call_id)
        if result.call_id not in (None, call_id):
            raise ValueError("ToolEnvelope call_id does not match artifact call_id")
        if result.call_id is None:
            result = result.model_copy(update={"call_id": call_id})
        payload = json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > self._max_bytes:
            raise ArtifactTooLargeError("tool result exceeds artifact size limit")

        artifact_id = call_id
        relative_path = Path("tool-results") / f"{call_id}.json"
        destination = self._root / relative_path
        temporary = destination.with_name(f".{call_id}.{uuid4().hex}.tmp")
        self._tool_results.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            existing = ToolEnvelope.model_validate_json(destination.read_text(encoding="utf-8"))
            if existing.call_id != call_id:
                raise ValueError("stored ToolEnvelope call_id does not match artifact name")
            return _artifact_reference(step, existing, artifact_id, relative_path)
        try:
            temporary.write_bytes(payload)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

        return _artifact_reference(step, result, artifact_id, relative_path)

    def find_tool_result(
        self,
        call_id: str,
        step: PlanStep,
    ) -> tuple[ArtifactRef, ToolEnvelope] | None:
        """按稳定 call_id 查找已经完成的工具调用。"""

        _validate_call_id(call_id)
        relative_path = Path("tool-results") / f"{call_id}.json"
        path = self._root / relative_path
        if not path.is_file():
            return None
        result = ToolEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        if result.call_id != call_id:
            raise ValueError("stored ToolEnvelope call_id does not match artifact name")
        return (
            _artifact_reference(step, result, call_id, relative_path),
            result,
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


def _validate_call_id(call_id: str) -> None:
    if re.fullmatch(r"[a-f0-9]{32}", call_id) is None:
        raise ValueError("call_id must be 32 lowercase hexadecimal characters")


def _artifact_reference(
    step: PlanStep,
    result: ToolEnvelope,
    artifact_id: str,
    relative_path: Path,
) -> ArtifactRef:
    outcome = "ok" if result.ok else f"error:{result.error.code if result.error else 'unknown'}"
    return ArtifactRef(
        artifact_id=artifact_id,
        kind="tool_result",
        relative_path=relative_path.as_posix(),
        summary=f"step={step.step_id} tool={result.tool_name} outcome={outcome}",
    )
