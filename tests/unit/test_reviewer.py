from pathlib import Path

from datapilot.agent import ArtifactStore, HybridReviewer, PlanExecutor
from datapilot.contracts import AnalysisPlan, PlanStep
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
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
        responses=[{"passed": True, "score": 0.95, "issues": [], "retryable": False}]
    )
    reviewer = HybridReviewer(model=model, tools=tools, artifacts=artifacts)

    result = reviewer.review(plan=plan, artifact_refs=[execution.artifact])

    assert result.passed is True
    assert len(model.calls) == 1
    assert "deterministic_checks=passed" in model.calls[0].prompt.user
    assert '"rows"' not in model.calls[0].prompt.user


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
