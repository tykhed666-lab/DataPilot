import pytest

from datapilot.contracts import ContractModel
from datapilot.tool_runtime import DuplicateToolError, ToolDefinition, ToolRegistry


class AddInput(ContractModel):
    left: int
    right: int


class AddOutput(ContractModel):
    total: int


def add_numbers(payload: AddInput) -> AddOutput:
    return AddOutput(total=payload.left + payload.right)


def test_registry_lists_tool_contracts_as_json_schema() -> None:
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="add_numbers",
                description="Add two integers.",
                input_model=AddInput,
                output_model=AddOutput,
                handler=add_numbers,
            )
        ]
    )

    tools = registry.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "add_numbers"
    assert tools[0].description == "Add two integers."
    assert tools[0].input_schema["properties"]["left"]["type"] == "integer"
    assert tools[0].output_schema["properties"]["total"]["type"] == "integer"


def test_registry_invokes_a_tool_through_one_envelope() -> None:
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="add_numbers",
                description="Add two integers.",
                input_model=AddInput,
                output_model=AddOutput,
                handler=add_numbers,
            )
        ]
    )

    result = registry.invoke("add_numbers", {"left": 2, "right": 3})

    assert result.ok is True
    assert result.tool_name == "add_numbers"
    assert result.output == {"total": 5}
    assert result.error is None


def test_registry_blocks_invalid_input_before_handler_runs() -> None:
    calls: list[AddInput] = []

    def tracked_add(payload: AddInput) -> AddOutput:
        calls.append(payload)
        return add_numbers(payload)

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="add_numbers",
                description="Add two integers.",
                input_model=AddInput,
                output_model=AddOutput,
                handler=tracked_add,
            )
        ]
    )

    result = registry.invoke("add_numbers", {"left": "not-an-integer", "right": 3})

    assert calls == []
    assert result.ok is False
    assert result.output is None
    assert result.error is not None
    assert result.error.code == "invalid_tool_input"


def test_registry_blocks_output_that_breaks_the_tool_contract() -> None:
    def broken_add(_payload: AddInput) -> dict[str, str]:
        return {"unexpected": "value"}

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="add_numbers",
                description="Add two integers.",
                input_model=AddInput,
                output_model=AddOutput,
                handler=broken_add,
            )
        ]
    )

    result = registry.invoke("add_numbers", {"left": 2, "right": 3})

    assert result.ok is False
    assert result.output is None
    assert result.error is not None
    assert result.error.code == "invalid_tool_output"


def test_registry_returns_a_stable_error_for_unknown_tools() -> None:
    registry = ToolRegistry()

    result = registry.invoke("missing_tool", {})

    assert result.ok is False
    assert result.output is None
    assert result.error is not None
    assert result.error.code == "tool_not_found"


def test_registry_does_not_leak_handler_exception_details() -> None:
    def failing_add(_payload: AddInput) -> AddOutput:
        raise RuntimeError(r"secret file: C:\private\credentials.txt")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="add_numbers",
                description="Add two integers.",
                input_model=AddInput,
                output_model=AddOutput,
                handler=failing_add,
            )
        ]
    )

    result = registry.invoke("add_numbers", {"left": 2, "right": 3})

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "tool_execution_failed"
    assert "credentials" not in result.error.message
    assert result.error.details == []


def test_registry_rejects_duplicate_tool_names() -> None:
    definition = ToolDefinition(
        name="add_numbers",
        description="Add two integers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=add_numbers,
    )

    with pytest.raises(DuplicateToolError, match="add_numbers"):
        ToolRegistry([definition, definition])
