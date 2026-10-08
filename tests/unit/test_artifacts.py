from pathlib import Path

import pytest

from datapilot.agent import ArtifactStore, ArtifactTooLargeError
from datapilot.contracts import ArtifactRef, PlanStep
from datapilot.tool_runtime import ToolEnvelope


def make_step() -> PlanStep:
    return PlanStep(
        step_id="step-1",
        title="查询收入",
        tool_name="query_dataset",
        arguments={"sql": "SELECT revenue FROM dataset"},
        expected_output="收入列表",
    )


def test_artifact_store_round_trips_full_tool_result(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    result = ToolEnvelope(
        tool_name="query_dataset",
        ok=True,
        output={"rows": [{"revenue": 120}, {"revenue": 80}]},
    )

    reference = store.save_tool_result(make_step(), result)

    assert reference.kind == "tool_result"
    assert "rows" not in reference.summary
    assert store.load(reference) == result.model_dump(mode="json")


def test_artifact_store_rejects_oversized_result_before_writing(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, max_bytes=20)
    result = ToolEnvelope(
        tool_name="query_dataset",
        ok=True,
        output={"large": "x" * 100},
    )

    with pytest.raises(ArtifactTooLargeError, match="size limit"):
        store.save_tool_result(make_step(), result)

    assert list(tmp_path.rglob("*.json")) == []


def test_artifact_store_rejects_a_reference_outside_its_root(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    escaped = ArtifactRef(
        artifact_id="escaped",
        kind="tool_result",
        relative_path="../secret.json",
        summary="invalid external reference",
    )

    with pytest.raises(ValueError, match="escaped"):
        store.load(escaped)
