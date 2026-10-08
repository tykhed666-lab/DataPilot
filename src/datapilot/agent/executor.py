"""按计划动态调用工具，并把完整结果交给 Artifact Store。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from datapilot.agent.artifacts import ArtifactStore
from datapilot.contracts import ArtifactRef, PlanStep
from datapilot.tool_runtime import ToolEnvelope, ToolRegistry


@dataclass(frozen=True, slots=True)
class StepExecution:
    call_id: str
    succeeded: bool
    artifact: ArtifactRef
    summary: str
    error_code: str | None
    reused: bool


class PlanExecutor:
    """用一个 execute_step 接口隐藏工具调用和结果落盘。"""

    def __init__(self, *, tools: ToolRegistry, artifacts: ArtifactStore) -> None:
        self._tools = tools
        self._artifacts = artifacts

    def execute_step(
        self,
        *,
        task_id: str,
        plan_version: int,
        step: PlanStep,
    ) -> StepExecution:
        call_id = _stable_call_id(task_id, plan_version, step.step_id)
        cached = self._artifacts.find_tool_result(call_id, step)
        if cached is not None:
            artifact, result = cached
            return _step_execution(call_id, artifact, result, reused=True)

        result = self._tools.invoke(step.tool_name, step.arguments, call_id=call_id)
        artifact = self._artifacts.save_tool_result(call_id, step, result)
        return _step_execution(call_id, artifact, result, reused=False)


def _stable_call_id(task_id: str, plan_version: int, step_id: str) -> str:
    source = f"{task_id}\x1f{plan_version}\x1f{step_id}".encode()
    return sha256(source).hexdigest()[:32]


def _step_execution(
    call_id: str,
    artifact: ArtifactRef,
    result: ToolEnvelope,
    *,
    reused: bool,
) -> StepExecution:
    error_code = result.error.code if result.error else None
    return StepExecution(
        call_id=call_id,
        succeeded=result.ok,
        artifact=artifact,
        summary=artifact.summary,
        error_code=error_code,
        reused=reused,
    )
