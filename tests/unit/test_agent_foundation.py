import pytest
from pydantic import ValidationError

from datapilot.agent import create_initial_state
from datapilot.contracts import AnalysisPlan, PlanStep, ReviewResult, TaskStatus


def make_step(step_id: str) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        title="按区域汇总销售额",
        tool_name="run_sql",
        arguments={"sql": "SELECT region, SUM(revenue) FROM sales GROUP BY region"},
        expected_output="区域销售额表",
    )


def test_initial_state_is_small_and_predictable() -> None:
    state = create_initial_state(
        task_id="task-1",
        dataset_id="dataset-1",
        question="  哪个区域销售额最高？  ",
    )

    assert state["question"] == "哪个区域销售额最高？"
    assert state["status"] is TaskStatus.CREATED
    assert state["plan"] is None
    assert state["tool_result_summaries"] == []
    assert state["artifacts"] == []


def test_initial_state_rejects_empty_question() -> None:
    with pytest.raises(ValueError, match="question cannot be empty"):
        create_initial_state(task_id="task-1", dataset_id="dataset-1", question="  ")


def test_plan_requires_unique_step_ids() -> None:
    with pytest.raises(ValidationError, match="step_id values must be unique"):
        AnalysisPlan(
            question="分析销售额",
            steps=[make_step("step-1"), make_step("step-1")],
            final_deliverable="分析报告",
        )


def test_retryable_review_requires_correction() -> None:
    with pytest.raises(ValidationError, match="requires correction"):
        ReviewResult(
            passed=False,
            score=0.4,
            issues=["没有回答用户问题"],
            retryable=True,
        )
