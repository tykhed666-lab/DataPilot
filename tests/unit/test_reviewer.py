from pathlib import Path

import pytest

from datapilot.agent import ArtifactStore, HybridReviewer, PlanExecutor
from datapilot.contracts import AnalysisPlan, PlanStep
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel, ModelOutputValidationError
from datapilot.tool_runtime import ToolEnvelope, ToolRegistry


def make_plan() -> AnalysisPlan:
    return AnalysisPlan(
        question="总收入是多少？",
        steps=[
            PlanStep(
                step_id="step-1",
                title="计算总收入",
                tool_name="query_dataset",
                arguments={
                    "relative_path": "sales.csv",
                    "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                },
                expected_output="总收入",
            )
        ],
        final_deliverable="回答总收入",
    )


def write_sales_csv(root: Path) -> None:
    (root / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n",
        encoding="utf-8",
    )


def test_hybrid_reviewer_recomputes_numbers_before_llm_review(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    plan = make_plan()
    execution = PlanExecutor(tools=tools, artifacts=artifacts).execute_step(
        task_id="review-task",
        plan_version=1,
        step=plan.steps[0],
    )
    model = FakeStructuredModel(
        responses=[
            {
                "passed": True,
                "score": 0.95,
                "issues": [],
                "retryable": False,
                "answer": "总收入是 200。",
                "key_findings": ["两条记录的收入合计为 200"],
                "caveats": [],
                "evidence_artifact_ids": [execution.artifact.artifact_id],
            }
        ]
    )
    reviewer = HybridReviewer(model=model, tools=tools, artifacts=artifacts)

    result = reviewer.review(plan=plan, artifact_refs=[execution.artifact])

    assert result.passed is True
    assert len(model.calls) == 1
    assert "deterministic_checks=passed" in model.calls[0].prompt.user
    assert '"columns": [\n      "total_revenue"' in model.calls[0].prompt.user
    assert '"row_count": 1' in model.calls[0].prompt.user
    assert '"total_revenue": 200' in model.calls[0].prompt.user
    assert result.answer == "总收入是 200。"


def test_hybrid_reviewer_blocks_tampered_numbers_without_calling_llm(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    plan = make_plan()
    tampered = ToolEnvelope(
        tool_name="query_dataset",
        call_id="d" * 32,
        ok=True,
        output={
            "columns": ["total_revenue"],
            "rows": [{"total_revenue": 999}],
            "row_count": 1,
            "truncated": False,
        },
    )
    reference = artifacts.save_tool_result("d" * 32, plan.steps[0], tampered)
    model = FakeStructuredModel(responses=[])
    reviewer = HybridReviewer(model=model, tools=tools, artifacts=artifacts)

    result = reviewer.review(plan=plan, artifact_refs=[reference])

    assert result.passed is False
    assert result.retryable is True
    assert result.score == 0
    assert result.correction is not None
    assert "step-1" in result.correction
    assert model.calls == []


def test_hybrid_reviewer_rejects_passed_decision_without_answer(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    plan = make_plan()
    execution = PlanExecutor(tools=tools, artifacts=artifacts).execute_step(
        task_id="missing-answer",
        plan_version=1,
        step=plan.steps[0],
    )
    reviewer = HybridReviewer(
        model=FakeStructuredModel(
            responses=[{"passed": True, "score": 1, "issues": [], "retryable": False}]
        ),
        tools=tools,
        artifacts=artifacts,
    )

    with pytest.raises(ModelOutputValidationError):
        reviewer.review(plan=plan, artifact_refs=[execution.artifact])


def test_reviewer_embeds_budgeted_evidence_without_double_escaping(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    step = PlanStep(
        step_id="step-1",
        title="检查字段",
        tool_name="profile_dataset",
        arguments={"relative_path": "sales.csv"},
        expected_output="字段说明",
    )
    plan = AnalysisPlan(
        question="有哪些字段？",
        steps=[step],
        final_deliverable="说明字段",
    )
    envelope = ToolEnvelope(
        tool_name="profile_dataset",
        call_id="b" * 32,
        ok=True,
        output={"columns": [f"field_<&>_{index}" for index in range(300)]},
    )
    reference = artifacts.save_tool_result("b" * 32, step, envelope)
    model = FakeStructuredModel(
        responses=[
            {
                "passed": True,
                "score": 1,
                "issues": [],
                "retryable": False,
                "answer": "数据包含一组已截断展示的字段。",
            }
        ]
    )
    reviewer = HybridReviewer(
        model=model,
        tools=tools,
        artifacts=artifacts,
        max_evidence_chars=1000,
    )

    reviewer.review(plan=plan, artifact_refs=[reference])
    prompt = model.calls[0].prompt.user
    bounded = prompt.split("<bounded_evidence>\n", 1)[1].split("\n</bounded_evidence>", 1)[0]

    assert len(bounded) <= 1000
    assert "&lt;" in bounded
    assert "&amp;lt;" not in bounded
