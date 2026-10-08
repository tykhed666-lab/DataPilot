from pathlib import Path

from pydantic import BaseModel

from datapilot.agent import ArtifactStore, PlanExecutor
from datapilot.contracts import PlanStep
from datapilot.tool_runtime import ToolDefinition, ToolRegistry


class CounterInput(BaseModel):
    amount: int


class CounterOutput(BaseModel):
    value: int


def test_recreated_executor_reuses_result_for_the_same_call_id(tmp_path: Path) -> None:
    invocations: list[int] = []

    def increment(payload: CounterInput) -> CounterOutput:
        invocations.append(payload.amount)
        return CounterOutput(value=sum(invocations))

    tools = ToolRegistry(
        [
            ToolDefinition(
                name="increment_counter",
                description="A visible side effect for idempotency testing.",
                input_model=CounterInput,
                output_model=CounterOutput,
                handler=increment,
            )
        ]
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    step = PlanStep(
        step_id="step-1",
        title="增加计数",
        tool_name="increment_counter",
        arguments={"amount": 1},
        expected_output="计数结果",
    )

    first = PlanExecutor(tools=tools, artifacts=artifacts).execute_step(
        task_id="durable-task",
        plan_version=1,
        step=step,
    )
    after_restart = PlanExecutor(tools=tools, artifacts=artifacts).execute_step(
        task_id="durable-task",
        plan_version=1,
        step=step,
    )
    revised_plan = PlanExecutor(tools=tools, artifacts=artifacts).execute_step(
        task_id="durable-task",
        plan_version=2,
        step=step,
    )

    assert invocations == [1, 1]
    assert first.call_id == after_restart.call_id
    assert revised_plan.call_id != first.call_id
    assert first.artifact == after_restart.artifact
    assert first.reused is False
    assert after_restart.reused is True
    assert revised_plan.reused is False
    assert artifacts.load(first.artifact)["call_id"] == first.call_id
