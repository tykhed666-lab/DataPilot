"""轨迹评测契约、grader 与可控工具故障注入。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from datapilot.contracts import ContractModel, TaskStatus
from datapilot.tool_runtime import ToolEnvelope, ToolError, ToolRegistry, ToolSpec
from datapilot.tracing import TraceEvent


class EvaluationCase(ContractModel):
    case_id: str
    question: str
    expected_status: TaskStatus
    required_trace_names: list[str] = Field(default_factory=list)
    forbidden_tool_names: list[str] = Field(default_factory=list)
    category: str


class EvaluationResult(ContractModel):
    case_id: str
    passed: bool
    issues: list[str] = Field(default_factory=list)


def load_evaluation_cases(path: str | Path) -> list[EvaluationCase]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError("evaluation case file must contain a JSON array")
    cases = [EvaluationCase.model_validate(item) for item in loaded]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("evaluation case_id values must be unique")
    return cases


class TrajectoryGrader:
    """同时检查最终状态和 Agent 执行轨迹。"""

    def grade(
        self,
        case: EvaluationCase,
        *,
        final_status: TaskStatus,
        events: list[TraceEvent],
    ) -> EvaluationResult:
        issues: list[str] = []
        if final_status is not case.expected_status:
            issues.append(f"expected status {case.expected_status.value}, got {final_status.value}")
        trace_names = {event.name for event in events}
        for required in case.required_trace_names:
            if required not in trace_names:
                issues.append(f"missing trace event: {required}")
        used_tools = {
            event.name
            for event in events
            if event.kind == "tool" and event.status in {"succeeded", "reused"}
        }
        for forbidden in case.forbidden_tool_names:
            if forbidden in used_tools:
                issues.append(f"forbidden tool was used: {forbidden}")
        return EvaluationResult(case_id=case.case_id, passed=not issues, issues=issues)


class FaultInjectingToolRegistry(ToolRegistry):
    """测试 Adapter：保留工具发现，但让指定工具返回稳定故障。"""

    def __init__(self, wrapped: ToolRegistry, *, fail_tools: set[str]) -> None:
        super().__init__()
        self._wrapped = wrapped
        self._fail_tools = fail_tools

    def list_tools(self) -> list[ToolSpec]:
        return self._wrapped.list_tools()

    def invoke(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        call_id: str | None = None,
    ) -> ToolEnvelope:
        if name in self._fail_tools:
            return ToolEnvelope(
                tool_name=name,
                call_id=call_id,
                ok=False,
                error=ToolError(
                    code="injected_failure",
                    message="tool failure injected by evaluation harness",
                ),
            )
        return self._wrapped.invoke(name, arguments, call_id=call_id)
