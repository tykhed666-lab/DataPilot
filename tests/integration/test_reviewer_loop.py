from pathlib import Path

from datapilot.agent import (
    AgentWorkflow,
    ApprovalDecision,
    ApprovalRequest,
    ArtifactStore,
    HybridReviewer,
    Planner,
    create_initial_state,
)
from datapilot.contracts import TaskStatus
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import FakeStructuredModel
from datapilot.tool_runtime import ToolRegistry
from datapilot.tracing import TraceRecorder


def plan_response() -> dict[str, object]:
    return {
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


def build_workflow(
    tmp_path: Path,
    *,
    planner_responses: list[object],
    reviewer_responses: list[object],
) -> tuple[AgentWorkflow, FakeStructuredModel, FakeStructuredModel, TraceRecorder]:
    (tmp_path / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n",
        encoding="utf-8",
    )
    tools = ToolRegistry(dataset_tool_definitions(tmp_path))
    artifacts = ArtifactStore(tmp_path / "artifacts")
    planner_model = FakeStructuredModel(planner_responses)
    reviewer_model = FakeStructuredModel(reviewer_responses)
    reviewer = HybridReviewer(model=reviewer_model, tools=tools, artifacts=artifacts)
    trace = TraceRecorder(tmp_path / "traces")
    workflow = AgentWorkflow(
        planner=Planner(model=planner_model),
        tools=tools,
        artifacts=artifacts,
        reviewer=reviewer,
        max_retries=2,
        trace=trace,
    )
    return workflow, planner_model, reviewer_model, trace


def approve(workflow: AgentWorkflow, task_id: str, plan_version: int):
    return workflow.resume(
        task_id=task_id,
        dataset_relative_path="sales.csv",
        approval=ApprovalRequest(
            decision=ApprovalDecision.APPROVE,
            plan_version=plan_version,
        ),
    )


def test_passed_hybrid_review_completes_workflow(tmp_path: Path) -> None:
    workflow, _, reviewer_model, trace = build_workflow(
        tmp_path,
        planner_responses=[plan_response()],
        reviewer_responses=[
            {
                "passed": True,
                "score": 1,
                "issues": [],
                "retryable": False,
                "answer": "总收入是 200。",
                "key_findings": ["查询结果显示总收入为 200"],
                "caveats": [],
            }
        ],
    )
    paused = workflow.start(
        create_initial_state(
            task_id="review-pass",
            dataset_id="sales",
            question="总收入是多少？",
        ),
        dataset_relative_path="sales.csv",
    )

    completed = approve(workflow, "review-pass", paused["plan_version"])

    assert completed["status"] is TaskStatus.COMPLETED
    assert completed["review"] is not None
    assert completed["review"].passed is True
    assert len(reviewer_model.calls) == 1
    assert {event.name for event in trace.read("review-pass")} >= {
        "profile",
        "plan",
        "approval",
        "query_dataset",
        "review",
    }


def test_retryable_review_replans_twice_then_stops(tmp_path: Path) -> None:
    retry = {
        "passed": False,
        "score": 0.4,
        "issues": ["回答缺少业务解释"],
        "retryable": True,
        "correction": "增加业务解释并重新生成计划",
    }
    workflow, planner_model, reviewer_model, _ = build_workflow(
        tmp_path,
        planner_responses=[plan_response(), plan_response(), plan_response()],
        reviewer_responses=[retry, retry, retry],
    )
    paused_v1 = workflow.start(
        create_initial_state(
            task_id="review-retry",
            dataset_id="sales",
            question="总收入是多少？",
        ),
        dataset_relative_path="sales.csv",
    )

    paused_v2 = approve(workflow, "review-retry", paused_v1["plan_version"])
    paused_v3 = approve(workflow, "review-retry", paused_v2["plan_version"])
    failed = approve(workflow, "review-retry", paused_v3["plan_version"])

    assert paused_v2["status"] is TaskStatus.AWAITING_APPROVAL
    assert paused_v2["plan_version"] == 2
    assert paused_v3["status"] is TaskStatus.AWAITING_APPROVAL
    assert paused_v3["plan_version"] == 3
    assert failed["status"] is TaskStatus.FAILED
    assert failed["retry_count"] == 2
    assert failed["error"] == "review_failed:retry_exhausted"
    assert len(planner_model.calls) == 3
    assert len(reviewer_model.calls) == 3
