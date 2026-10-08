import json
from html import unescape
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
    loaded = json.loads(unescape(rendered))

    assert len(rendered) <= 1200
    assert loaded[0]["columns"] == ["region", "revenue"]
    assert loaded[0]["row_count"] == 30
    assert loaded[0]["truncated"] is True
    assert len(loaded[0]["sample_rows"]) < 10


def test_render_budget_applies_after_xml_escaping(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    step = PlanStep(
        step_id="step-1",
        title="读取说明",
        tool_name="profile_dataset",
        arguments={"relative_path": "sales.csv"},
        expected_output="数据说明",
    )
    plan = AnalysisPlan(question="数据是什么？", steps=[step], final_deliverable="说明数据")
    result = ToolEnvelope(
        tool_name="profile_dataset",
        call_id="f" * 32,
        ok=True,
        output={"note": "<&>" * 200},
    )
    reference = artifacts.save_tool_result("f" * 32, step, result)
    packager = EvidencePackager(artifacts, max_prompt_chars=1000)

    rendered = packager.render(packager.build(plan, [reference]))

    assert len(rendered) <= 1000
    assert "<" not in rendered
    assert json.loads(unescape(rendered))[0]["artifact_id"] == "f" * 32


def test_wide_schema_truncates_columns_without_losing_total_count(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path)
    step = PlanStep(
        step_id="step-1",
        title="检查宽表",
        tool_name="query_dataset",
        arguments={"relative_path": "wide.csv", "sql": "SELECT * FROM dataset"},
        expected_output="宽表结构",
    )
    plan = AnalysisPlan(question="有哪些列？", steps=[step], final_deliverable="说明列结构")
    all_columns = [f"metric_<&>_{index}_" + "x" * 80 for index in range(500)]
    result = ToolEnvelope(
        tool_name="query_dataset",
        call_id="a" * 32,
        ok=True,
        output={
            "columns": all_columns,
            "rows": [],
            "row_count": 0,
            "truncated": False,
        },
    )
    reference = artifacts.save_tool_result("a" * 32, step, result)
    packager = EvidencePackager(artifacts, max_prompt_chars=1200)

    rendered = packager.render(packager.build(plan, [reference]))
    digest = json.loads(unescape(rendered))[0]

    assert len(rendered) <= 1200
    assert digest["column_count"] == 500
    assert digest["columns_truncated"] is True
    assert 0 < len(digest["columns"]) < 500
