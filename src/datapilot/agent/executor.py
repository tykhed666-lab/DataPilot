"""按计划动态调用工具，并把完整结果交给 Artifact Store。"""

from __future__ import annotations

from dataclasses import dataclass

from datapilot.agent.artifacts import ArtifactStore
from datapilot.contracts import ArtifactRef, PlanStep
from datapilot.tool_runtime import ToolRegistry


@dataclass(frozen=True, slots=True)
class StepExecution:
    succeeded: bool
    artifact: ArtifactRef
    summary: str
    error_code: str | None


class PlanExecutor:
    """用一个 execute_step 接口隐藏工具调用和结果落盘。"""

    def __init__(self, *, tools: ToolRegistry, artifacts: ArtifactStore) -> None:
        self._tools = tools
        self._artifacts = artifacts

    def execute_step(self, step: PlanStep) -> StepExecution:
        result = self._tools.invoke(step.tool_name, step.arguments)
        artifact = self._artifacts.save_tool_result(step, result)
        error_code = result.error.code if result.error else None
        return StepExecution(
            succeeded=result.ok,
            artifact=artifact,
            summary=artifact.summary,
            error_code=error_code,
        )
