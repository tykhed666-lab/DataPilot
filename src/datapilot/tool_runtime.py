"""工具发现、校验与调用的统一运行时。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, ValidationError

from datapilot.contracts import ContractModel

InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)


class DuplicateToolError(ValueError):
    """两个工具尝试注册同一个名称。"""


@dataclass(frozen=True, slots=True)
class ToolDefinition(Generic[InputModel, OutputModel]):
    """注册工具时需要提供的实现和契约。"""

    name: str
    description: str
    input_model: type[InputModel]
    output_model: type[OutputModel]
    handler: Callable[[InputModel], OutputModel]


class ToolSpec(ContractModel):
    """Planner 或 MCP Client 可发现的工具说明。"""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolError(ContractModel):
    """不暴露 traceback 的稳定工具错误。"""

    code: str
    message: str
    details: list[str] = Field(default_factory=list)


class ToolEnvelope(ContractModel):
    """所有工具调用共用的成功或失败外壳。"""

    tool_name: str
    call_id: str | None = Field(default=None, min_length=1, max_length=64)
    ok: bool
    output: dict[str, Any] | None = None
    error: ToolError | None = None


class ToolRegistry:
    """用 list_tools 和 invoke 隐藏工具实现差异。"""

    def __init__(
        self,
        definitions: Iterable[ToolDefinition[Any, Any]] = (),
    ) -> None:
        self._definitions: dict[str, ToolDefinition[Any, Any]] = {}
        for definition in definitions:
            if definition.name in self._definitions:
                raise DuplicateToolError(f"duplicate tool name: {definition.name}")
            self._definitions[definition.name] = definition

    def list_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=definition.name,
                description=definition.description,
                input_schema=definition.input_model.model_json_schema(),
                output_schema=definition.output_model.model_json_schema(),
            )
            for definition in sorted(self._definitions.values(), key=lambda item: item.name)
        ]

    def invoke(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        call_id: str | None = None,
    ) -> ToolEnvelope:
        definition = self._definitions.get(name)
        if definition is None:
            return ToolEnvelope(
                tool_name=name,
                call_id=call_id,
                ok=False,
                error=ToolError(
                    code="tool_not_found",
                    message="requested tool is not registered",
                ),
            )
        try:
            validated_input = definition.input_model.model_validate(arguments)
        except ValidationError as error:
            return ToolEnvelope(
                tool_name=name,
                call_id=call_id,
                ok=False,
                error=ToolError(
                    code="invalid_tool_input",
                    message="tool arguments failed validation",
                    details=_validation_messages(error),
                ),
            )
        try:
            raw_output = definition.handler(validated_input)
        except Exception:
            return ToolEnvelope(
                tool_name=name,
                call_id=call_id,
                ok=False,
                error=ToolError(
                    code="tool_execution_failed",
                    message="tool execution failed",
                ),
            )
        try:
            validated_output = definition.output_model.model_validate(raw_output)
        except ValidationError as error:
            return ToolEnvelope(
                tool_name=name,
                call_id=call_id,
                ok=False,
                error=ToolError(
                    code="invalid_tool_output",
                    message="tool result failed validation",
                    details=_validation_messages(error),
                ),
            )
        return ToolEnvelope(
            tool_name=name,
            call_id=call_id,
            ok=True,
            output=validated_output.model_dump(mode="json"),
        )


def _validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"])
        messages.append(f"{location}: {item['msg']}")
    return messages
