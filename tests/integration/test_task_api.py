from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from datapilot.agent import AgentWorkflow, ArtifactStore, HybridReviewer, Planner
from datapilot.api.app import create_app
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
from datapilot.service import TaskService
from datapilot.tool_runtime import ToolRegistry
from datapilot.tracing import TraceRecorder


def test_upload_approve_review_report_flow(tmp_path: Path) -> None:
    content = "region,revenue\n华东,120\n华南,80\n".encode()
    relative_path = f"uploads/{sha256(content).hexdigest()}.csv"
    planner_model = FakeStructuredModel(
        [
            {
                "question": "总收入是多少？",
                "steps": [
                    {
                        "step_id": "step-1",
                        "title": "计算总收入",
                        "tool_name": "query_dataset",
                        "arguments": {
                            "relative_path": relative_path,
                            "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                        },
                        "expected_output": "总收入",
                    }
                ],
                "final_deliverable": "回答总收入",
            }
        ]
    )
    reviewer_model = FakeStructuredModel(
        [{"passed": True, "score": 1, "issues": [], "retryable": False}]
    )
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    trace = TraceRecorder(tmp_path / "traces")
    workflow = AgentWorkflow(
        planner=Planner(model=planner_model),
        tools=tools,
        artifacts=artifacts,
        reviewer=HybridReviewer(model=reviewer_model, tools=tools, artifacts=artifacts),
        trace=trace,
    )
    service = TaskService(
        workflow=workflow,
        data_root=tmp_path,
        artifacts=artifacts,
        trace=trace,
    )

    with TestClient(create_app(service)) as client:
        uploaded = client.post(
            "/api/datasets",
            files={"file": ("sales.csv", content, "text/csv")},
        )
        assert uploaded.status_code == 201

        created = client.post(
            "/api/tasks",
            json={
                "dataset_id": uploaded.json()["dataset_id"],
                "question": "总收入是多少？",
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "awaiting_approval"

        task_id = created.json()["task_id"]
        completed = client.post(
            f"/api/tasks/{task_id}/approval",
            json={"decision": "approve", "plan_version": created.json()["plan_version"]},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        report = next(
            item for item in completed.json()["artifacts"] if item["kind"] == "markdown_report"
        )

        trace_response = client.get(f"/api/tasks/{task_id}/trace")
        assert trace_response.status_code == 200
        assert {event["name"] for event in trace_response.json()} >= {
            "profile",
            "plan",
            "approval",
            "query_dataset",
            "review",
            "report",
        }

        report_response = client.get(f"/api/tasks/{task_id}/artifacts/{report['artifact_id']}")
        assert report_response.status_code == 200
        assert "DataPilot 分析报告" in report_response.text


def test_stale_approval_uses_standard_error_shape(tmp_path: Path) -> None:
    # Missing tasks fail before checking a plan version and exercise the shared API envelope.
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    trace = TraceRecorder(tmp_path / "traces")
    workflow = AgentWorkflow(
        planner=Planner(model=FakeStructuredModel([])),
        tools=tools,
        artifacts=artifacts,
    )
    service = TaskService(
        workflow=workflow,
        data_root=tmp_path,
        artifacts=artifacts,
        trace=trace,
    )
    with TestClient(create_app(service)) as client:
        response = client.get("/api/tasks/missing")
        validation = client.post("/api/tasks", json={"dataset_id": "short", "question": ""})
    assert response.status_code == 404
    assert set(response.json()) == {"error_type", "code", "message", "request_id", "details"}
    assert validation.status_code == 422
    assert validation.json()["code"] == "request_validation_failed"
