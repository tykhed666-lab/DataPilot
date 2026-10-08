from pathlib import Path

from datapilot.contracts import TaskStatus
from datapilot.evaluation import TrajectoryGrader, load_evaluation_cases
from datapilot.tracing import TraceEvent, TraceRecorder


def test_trace_recorder_keeps_sequence_across_recreation(tmp_path: Path) -> None:
    first = TraceRecorder(tmp_path)
    first.record(
        task_id="trace-task",
        kind="node",
        name="plan",
        status="succeeded",
        duration_ms=12.5,
        details={"step_count": 1},
    )
    second = TraceRecorder(tmp_path)
    second.record(
        task_id="trace-task",
        kind="tool",
        name="query_dataset",
        status="reused",
        details={"call_id": "abc"},
    )

    events = second.read("trace-task")

    assert [event.sequence for event in events] == [1, 2]
    assert events[1].details == {"call_id": "abc"}


def test_evaluation_catalog_and_trajectory_grader() -> None:
    cases = load_evaluation_cases(Path("evals/cases.json"))

    assert 12 <= len(cases) <= 15
    case = next(item for item in cases if item.case_id == "sales-total")
    trace = [
        TraceEvent(
            trace_id="trace",
            task_id="task",
            sequence=index,
            kind=kind,
            name=name,
            status="succeeded",
            timestamp="2026-10-08T00:00:00+00:00",
            duration_ms=1,
        )
        for index, (kind, name) in enumerate(
            [("model", "plan"), ("tool", "query_dataset"), ("model", "review")],
            start=1,
        )
    ]

    result = TrajectoryGrader().grade(
        case,
        final_status=TaskStatus.COMPLETED,
        events=trace,
    )

    assert result.passed is True
    assert result.issues == []
