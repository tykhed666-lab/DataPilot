from pathlib import Path

import pytest
from pydantic import ValidationError

from datapilot.agent import (
    AgentWorkflow,
    ApprovalDecision,
    ApprovalRequest,
    Planner,
    StalePlanVersionError,
    create_initial_state,
)
from datapilot.contracts import TaskStatus
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
from datapilot.tool_runtime import ToolRegistry


def write_sales_csv(data_root: Path) -> None:
    (data_root / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n华东,60\n",
        encoding="utf-8",
    )


def test_workflow_pauses_for_approval_and_approve_resumes_it(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    model = FakeStructuredModel(
        responses=[
            {
                "question": "哪个区域收入最高？",
                "steps": [
                    {
                        "step_id": "step-1",
                        "title": "按区域汇总收入",
                        "tool_name": "query_dataset",
                        "arguments": {
                            "relative_path": "sales.csv",
                            "sql": (
                                "SELECT region, SUM(revenue) AS total_revenue "
                                "FROM dataset GROUP BY region"
                            ),
                        },
                        "expected_output": "区域收入汇总表",
                    }
                ],
                "final_deliverable": "说明收入最高的区域",
            }
        ]
    )
    workflow = AgentWorkflow(
        planner=Planner(model=model, max_steps=4),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    initial_state = create_initial_state(
        task_id="task-7",
        dataset_id="dataset-7",
        question="哪个区域收入最高？",
    )

    paused = workflow.start(initial_state, dataset_relative_path="sales.csv")

    assert paused["status"] is TaskStatus.AWAITING_APPROVAL
    assert paused["profile"] is not None
    assert paused["profile"].row_count == 3
    assert paused["plan"] is not None
    assert paused["plan"].steps[0].tool_name == "query_dataset"
    assert paused["plan_version"] == 1
    assert paused["error"] is None
    assert len(model.calls) == 1

    approved = workflow.resume(
        task_id="task-7",
        dataset_relative_path="sales.csv",
        approval=ApprovalRequest(
            decision=ApprovalDecision.APPROVE,
            plan_version=1,
        ),
    )

    assert approved["status"] is TaskStatus.EXECUTING
    assert approved["plan_version"] == 1


def test_workflow_routes_profile_failure_to_failed_without_calling_model(
    tmp_path: Path,
) -> None:
    model = FakeStructuredModel(responses=[])
    workflow = AgentWorkflow(
        planner=Planner(model=model),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    initial_state = create_initial_state(
        task_id="missing-dataset",
        dataset_id="dataset-missing",
        question="分析收入",
    )

    result = workflow.run(initial_state, dataset_relative_path="missing.csv")

    assert result["status"] is TaskStatus.FAILED
    assert result["profile"] is None
    assert result["plan"] is None
    assert result["error"] == "profile_failed:tool_execution_failed"
    assert model.calls == []


def test_workflow_routes_invalid_model_plan_to_failed(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    model = FakeStructuredModel(responses=[{"not": "an analysis plan"}])
    workflow = AgentWorkflow(
        planner=Planner(model=model),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    initial_state = create_initial_state(
        task_id="invalid-plan",
        dataset_id="dataset-7",
        question="分析收入",
    )

    result = workflow.run(initial_state, dataset_relative_path="sales.csv")

    assert result["status"] is TaskStatus.FAILED
    assert result["profile"] is not None
    assert result["plan"] is None
    assert result["error"] == "planning_failed:ModelOutputValidationError"
    assert len(model.calls) == 1


def test_revise_replans_with_feedback_and_pauses_again(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    first_plan = {
        "question": "分析收入",
        "steps": [
            {
                "step_id": "step-1",
                "title": "汇总全部收入",
                "tool_name": "query_dataset",
                "arguments": {
                    "relative_path": "sales.csv",
                    "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                },
                "expected_output": "总收入",
            }
        ],
        "final_deliverable": "收入总结",
    }
    revised_plan = {
        "question": "分析收入",
        "steps": [
            {
                "step_id": "step-1",
                "title": "按区域汇总收入",
                "tool_name": "query_dataset",
                "arguments": {
                    "relative_path": "sales.csv",
                    "sql": (
                        "SELECT region, SUM(revenue) AS total_revenue FROM dataset GROUP BY region"
                    ),
                },
                "expected_output": "区域收入汇总",
            }
        ],
        "final_deliverable": "分区域收入总结",
    }
    model = FakeStructuredModel(responses=[first_plan, revised_plan])
    workflow = AgentWorkflow(
        planner=Planner(model=model),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    initial_state = create_initial_state(
        task_id="revise-task",
        dataset_id="dataset-7",
        question="分析收入",
    )
    paused = workflow.start(initial_state, dataset_relative_path="sales.csv")

    revised = workflow.resume(
        task_id="revise-task",
        dataset_relative_path="sales.csv",
        approval=ApprovalRequest(
            decision=ApprovalDecision.REVISE,
            plan_version=paused["plan_version"],
            feedback="请按区域分组，不要只计算总体收入。",
        ),
    )

    assert revised["status"] is TaskStatus.AWAITING_APPROVAL
    assert revised["plan_version"] == 2
    assert revised["plan"] is not None
    assert revised["plan"].steps[0].title == "按区域汇总收入"
    assert "请按区域分组" in model.calls[1].prompt.user
    assert len(model.calls) == 2


def test_reject_ends_the_workflow_without_replanning(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    model = FakeStructuredModel(
        responses=[
            {
                "question": "分析收入",
                "steps": [
                    {
                        "step_id": "step-1",
                        "title": "汇总收入",
                        "tool_name": "query_dataset",
                        "arguments": {
                            "relative_path": "sales.csv",
                            "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                        },
                        "expected_output": "总收入",
                    }
                ],
                "final_deliverable": "收入总结",
            }
        ]
    )
    workflow = AgentWorkflow(
        planner=Planner(model=model),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    paused = workflow.start(
        create_initial_state(
            task_id="reject-task",
            dataset_id="dataset-7",
            question="分析收入",
        ),
        dataset_relative_path="sales.csv",
    )

    rejected = workflow.resume(
        task_id="reject-task",
        dataset_relative_path="sales.csv",
        approval=ApprovalRequest(
            decision=ApprovalDecision.REJECT,
            plan_version=paused["plan_version"],
            feedback="这个分析方向不再需要。",
        ),
    )

    assert rejected["status"] is TaskStatus.REJECTED
    assert rejected["revision_feedback"] == "这个分析方向不再需要。"
    assert len(model.calls) == 1


def test_resume_rejects_a_stale_plan_version(tmp_path: Path) -> None:
    write_sales_csv(tmp_path)
    model = FakeStructuredModel(
        responses=[
            {
                "question": "分析收入",
                "steps": [
                    {
                        "step_id": "step-1",
                        "title": "汇总收入",
                        "tool_name": "query_dataset",
                        "arguments": {
                            "relative_path": "sales.csv",
                            "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                        },
                        "expected_output": "总收入",
                    }
                ],
                "final_deliverable": "收入总结",
            }
        ]
    )
    workflow = AgentWorkflow(
        planner=Planner(model=model),
        tools=ToolRegistry(dataset_tool_definitions(tmp_path)),
    )
    workflow.start(
        create_initial_state(
            task_id="stale-task",
            dataset_id="dataset-7",
            question="分析收入",
        ),
        dataset_relative_path="sales.csv",
    )

    with pytest.raises(StalePlanVersionError, match="plan_version is stale"):
        workflow.resume(
            task_id="stale-task",
            dataset_relative_path="sales.csv",
            approval=ApprovalRequest(
                decision=ApprovalDecision.APPROVE,
                plan_version=2,
            ),
        )


@pytest.mark.parametrize("feedback", [None, "   "])
def test_revision_requires_feedback(feedback: str | None) -> None:
    with pytest.raises(ValidationError, match="feedback"):
        ApprovalRequest(
            decision=ApprovalDecision.REVISE,
            plan_version=1,
            feedback=feedback,
        )
