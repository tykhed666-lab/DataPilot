from pathlib import Path

from datapilot.agent import (
    AgentWorkflow,
    ApprovalDecision,
    ApprovalRequest,
    ArtifactStore,
    Planner,
    create_initial_state,
    open_sqlite_checkpointer,
)
from datapilot.contracts import TaskStatus
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
from datapilot.tool_runtime import ToolRegistry


def test_new_workflow_resumes_paused_task_from_sqlite(tmp_path: Path) -> None:
    (tmp_path / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n",
        encoding="utf-8",
    )
    checkpoint_path = tmp_path / "checkpoints.db"
    artifacts = ArtifactStore(tmp_path / "artifacts")
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    first_model = FakeStructuredModel(
        responses=[
            {
                "question": "总收入是多少？",
                "steps": [
                    {
                        "step_id": "step-1",
                        "title": "计算总收入",
                        "tool_name": "query_dataset",
                        "arguments": {
                            "relative_path": "sales.csv",
                            "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                        },
                        "expected_output": "总收入",
                    }
                ],
                "final_deliverable": "回答总收入",
            }
        ]
    )

    with open_sqlite_checkpointer(checkpoint_path) as first_checkpointer:
        first_process = AgentWorkflow(
            planner=Planner(model=first_model),
            tools=tools,
            artifacts=artifacts,
            checkpointer=first_checkpointer,
        )
        paused = first_process.start(
            create_initial_state(
                task_id="restart-task",
                dataset_id="sales-dataset",
                question="总收入是多少？",
            ),
            dataset_relative_path="sales.csv",
        )
        assert paused["status"] is TaskStatus.AWAITING_APPROVAL

    second_model = FakeStructuredModel(responses=[])
    with open_sqlite_checkpointer(checkpoint_path) as second_checkpointer:
        second_process = AgentWorkflow(
            planner=Planner(model=second_model),
            tools=tools,
            artifacts=artifacts,
            checkpointer=second_checkpointer,
        )
        recovered = second_process.resume(
            task_id="restart-task",
            dataset_relative_path="sales.csv",
            approval=ApprovalRequest(
                decision=ApprovalDecision.APPROVE,
                plan_version=paused["plan_version"],
            ),
        )

    assert recovered["status"] is TaskStatus.REVIEWING
    assert recovered["current_step_index"] == 1
    assert len(recovered["artifacts"]) == 1
    assert second_model.calls == []
    saved = artifacts.load(recovered["artifacts"][0])
    assert saved["call_id"] == recovered["artifacts"][0].artifact_id
    assert saved["output"]["rows"] == [{"total_revenue": 200}]
