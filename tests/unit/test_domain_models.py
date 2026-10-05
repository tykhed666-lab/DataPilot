import pytest
from pydantic import ValidationError

from datapilot.domain import (
    AnalysisPlan,
    ErrorType,
    PlanStep,
    ReviewDecision,
    TaskStatus,
    ToolCallRecord,
    ToolCallStatus,
    ToolEnvelope,
    ToolError,
)


def make_step(step_id: str = "step-1") -> PlanStep:
    return PlanStep(
        step_id=step_id,
        title="汇总区域销售额",
        objective="按区域计算总销售额",
        preferred_tool="run_readonly_sql",
        inputs=["sales"],
        expected_output="区域销售额表",
        success_criteria=["结果至少包含 region 和 revenue"],
    )


def make_plan(*steps: PlanStep) -> AnalysisPlan:
    return AnalysisPlan(
        question="哪个区域销售额最高？",
        assumptions=[],
        steps=list(steps) or [make_step()],
        final_deliverables=["关键结论"],
    )


def test_task_status_serializes_to_public_value() -> None:
    assert TaskStatus.AWAITING_APPROVAL == "awaiting_approval"


def test_analysis_plan_accepts_unique_steps() -> None:
    plan = make_plan(make_step("step-1"), make_step("step-2"))

    assert [step.step_id for step in plan.steps] == ["step-1", "step-2"]


def test_analysis_plan_rejects_duplicate_step_ids() -> None:
    with pytest.raises(ValidationError, match="step_id values must be unique"):
        make_plan(make_step("duplicate"), make_step("duplicate"))


def test_analysis_plan_rejects_more_than_eight_steps() -> None:
    with pytest.raises(ValidationError):
        make_plan(*(make_step(f"step-{index}") for index in range(9)))


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanStep(
            **make_step().model_dump(),
            unexpected="must fail",
        )


def test_failed_tool_call_requires_error_type() -> None:
    with pytest.raises(ValidationError, match="require error_type"):
        ToolCallRecord(
            call_id="call-1",
            step_id="step-1",
            tool_name="run_readonly_sql",
            arguments={"sql": "SELECT 1"},
            status=ToolCallStatus.FAILED,
        )


def test_tool_envelope_requires_error_on_failure() -> None:
    with pytest.raises(ValidationError, match="require an error"):
        ToolEnvelope[dict[str, object]](ok=False)

    envelope = ToolEnvelope[dict[str, object]](
        ok=False,
        error=ToolError(
            type=ErrorType.SQL,
            code="invalid_sql",
            message="Only SELECT is allowed",
        ),
    )
    assert envelope.error is not None
    assert envelope.error.type is ErrorType.SQL


def test_passed_review_cannot_request_retry() -> None:
    with pytest.raises(ValidationError, match="passed review"):
        ReviewDecision(
            passed=True,
            score=1,
            issues=["contradiction"],
            retryable=True,
            correction_instructions=["retry"],
        )
