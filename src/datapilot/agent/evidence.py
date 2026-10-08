"""把磁盘中的完整工具结果转换成有预算的语义审核证据。"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from pydantic import Field

from datapilot.agent.artifacts import ArtifactStore
from datapilot.contracts import AnalysisPlan, ArtifactRef, ContractModel
from datapilot.tool_runtime import ToolEnvelope


class EvidenceDigest(ContractModel):
    """允许进入模型上下文的最小、可追溯证据。"""

    artifact_id: str
    step_id: str
    tool_name: str
    columns: list[str] = Field(default_factory=list)
    column_count: int = Field(ge=0)
    columns_truncated: bool = False
    row_count: int | None = Field(default=None, ge=0)
    truncated: bool | None = None
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    output_summary: dict[str, Any] = Field(default_factory=dict)


class EvidencePackager:
    """隐藏 Artifact 加载、字段裁剪、行采样和全局字符预算。"""

    def __init__(
        self,
        artifacts: ArtifactStore,
        *,
        max_rows_per_artifact: int = 10,
        max_columns_per_artifact: int = 100,
        max_prompt_chars: int = 12_000,
    ) -> None:
        if max_rows_per_artifact < 1 or max_columns_per_artifact < 1 or max_prompt_chars < 1000:
            raise ValueError("evidence budgets are too small")
        self._artifacts = artifacts
        self._max_rows = max_rows_per_artifact
        self._max_columns = max_columns_per_artifact
        self._max_chars = max_prompt_chars

    def build(
        self,
        plan: AnalysisPlan,
        artifact_refs: list[ArtifactRef],
    ) -> list[EvidenceDigest]:
        digests = []
        for step, reference in zip(plan.steps, artifact_refs, strict=True):
            envelope = ToolEnvelope.model_validate(self._artifacts.load(reference))
            output = envelope.output or {}
            raw_rows = output.get("rows", [])
            rows = raw_rows if isinstance(raw_rows, list) else []
            raw_columns = output.get("columns", [])
            all_columns = raw_columns if isinstance(raw_columns, list) else []
            columns = [_compact_column(item) for item in all_columns[: self._max_columns]]
            row_count = output.get("row_count")
            truncated = output.get("truncated")
            remainder = {
                key: _compact(value)
                for key, value in output.items()
                if key not in {"rows", "columns", "row_count", "truncated"}
            }
            digests.append(
                EvidenceDigest(
                    artifact_id=reference.artifact_id,
                    step_id=step.step_id,
                    tool_name=envelope.tool_name,
                    columns=columns,
                    column_count=len(all_columns),
                    columns_truncated=len(all_columns) > len(columns),
                    row_count=row_count if isinstance(row_count, int) else None,
                    truncated=truncated if isinstance(truncated, bool) else None,
                    sample_rows=[
                        _compact(row) for row in rows[: self._max_rows] if isinstance(row, dict)
                    ],
                    output_summary=remainder,
                )
            )
        return digests

    def render(self, digests: list[EvidenceDigest]) -> str:
        """生成已经 XML 转义、保持合法 JSON 语义且不超预算的 Prompt 片段。"""

        compacted = [digest.model_copy(deep=True) for digest in digests]
        rendered = _render_for_prompt(compacted)
        while len(rendered) > self._max_chars and any(item.sample_rows for item in compacted):
            largest = max(compacted, key=lambda item: len(item.sample_rows))
            largest.sample_rows.pop()
            rendered = _render_for_prompt(compacted)
        if len(rendered) > self._max_chars and any(item.output_summary for item in compacted):
            for item in compacted:
                if item.output_summary:
                    item.output_summary = {"notice": "omitted by evidence character budget"}
            rendered = _render_for_prompt(compacted)
        while len(rendered) > self._max_chars and any(len(item.columns) > 1 for item in compacted):
            widest = max(compacted, key=lambda item: len(item.columns))
            widest.columns.pop()
            widest.columns_truncated = True
            rendered = _render_for_prompt(compacted)
        if len(rendered) > self._max_chars:
            rendered = _render_for_prompt(compacted, compact=True)
        if len(rendered) > self._max_chars:
            raise ValueError("essential evidence metadata exceeds prompt character budget")
        return rendered


def _render_for_prompt(digests: list[EvidenceDigest], *, compact: bool = False) -> str:
    raw_json = json.dumps(
        [item.model_dump(mode="json") for item in digests],
        ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    )
    return escape(raw_json, quote=False)


def _compact(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 300 else f"{value[:297]}..."
    if isinstance(value, dict):
        return {str(key): _compact(item) for key, item in list(value.items())[:30]}
    if isinstance(value, list):
        return [_compact(item) for item in value[:20]]
    return value


def _compact_column(value: Any) -> str:
    rendered = str(value)
    return rendered if len(rendered) <= 120 else f"{rendered[:117]}..."
