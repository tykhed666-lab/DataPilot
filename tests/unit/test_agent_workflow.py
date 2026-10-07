from pathlib import Path

from datapilot.agent import AgentWorkflow, Planner, create_initial_state
from datapilot.contracts import TaskStatus
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
from datapilot.tool_runtime import ToolRegistry


def write_sales_csv(data_root: Path) -> None:
    (data_root / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n华东,60\n",
        encoding="utf-8",
    )


def test_workflow_profiles_dataset_and_builds_plan(tmp_path: Path) -> None:
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

    result = workflow.run(initial_state, dataset_relative_path="sales.csv")

    assert result["status"] is TaskStatus.AWAITING_APPROVAL
    assert result["profile"] is not None
    assert result["profile"].row_count == 3
    assert result["plan"] is not None
    assert result["plan"].steps[0].tool_name == "query_dataset"
    assert result["error"] is None
    assert len(model.calls) == 1


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
