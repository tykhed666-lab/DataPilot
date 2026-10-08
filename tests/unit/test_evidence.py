import json
from pathlib import Path

from datapilot.agent import ArtifactStore
from datapilot.agent.evidence import EvidencePackager
from datapilot.contracts import AnalysisPlan, PlanStep
from datapilot.tool_runtime import ToolEnvelope


def test_evidence_packager_preserves_metadata_and_stays_within_budget(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    step = PlanStep(
        step_id="step-1",
        title="读取收入",
        tool_name="query_dataset",
        arguments={"relative_path": "sales.csv", "sql": "SELECT * FROM dataset"},
        expected_output="收入样本",
    )
    plan = AnalysisPlan(
        question="收入是多少？",
        steps=[step],
        final_deliverable="给出收入结论",
    )
    result = ToolEnvelope(
        tool_name="query_dataset",
        call_id="e" * 32,
        ok=True,
        output={
            "columns": ["region", "revenue"],
            "rows": [
                {"region": f"区域-{index}-" + "很长" * 200, "revenue": index} for index in range(30)
            ],
            "row_count": 30,
            "truncated": True,
        },
    )
    reference = artifacts.save_tool_result("e" * 32, step, result)
    packager = EvidencePackager(artifacts, max_rows_per_artifact=10, max_prompt_chars=1200)

    rendered = packager.render(packager.build(plan, [reference]))
    loaded = json.loads(rendered)

    assert len(rendered) <= 1200
    assert loaded[0]["columns"] == ["region", "revenue"]
    assert loaded[0]["row_count"] == 30
    assert loaded[0]["truncated"] is True
    assert len(loaded[0]["sample_rows"]) < 10
