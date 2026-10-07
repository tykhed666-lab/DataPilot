from pathlib import Path

from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.tool_runtime import ToolRegistry


def test_real_dataset_tools_use_the_same_registry_interface(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text(
        "region,revenue\n华东,120\n华南,80\n华东,60\n",
        encoding="utf-8",
    )
    registry = ToolRegistry(dataset_tool_definitions(tmp_path))

    profile_result = registry.invoke(
        "profile_dataset",
        {"relative_path": "sales.csv"},
    )
    query_result = registry.invoke(
        "query_dataset",
        {
            "relative_path": "sales.csv",
            "sql": """
                SELECT region, SUM(revenue) AS total_revenue
                FROM dataset
                GROUP BY region
                ORDER BY total_revenue DESC
            """,
        },
    )

    assert profile_result.ok is True
    assert profile_result.output is not None
    assert profile_result.output["row_count"] == 3
    assert query_result.ok is True
    assert query_result.output is not None
    assert query_result.output["rows"] == [
        {"region": "华东", "total_revenue": 180.0},
        {"region": "华南", "total_revenue": 80.0},
    ]


def test_dataset_tool_input_guardrail_rejects_path_traversal(tmp_path: Path) -> None:
    registry = ToolRegistry(dataset_tool_definitions(tmp_path))

    result = registry.invoke(
        "profile_dataset",
        {"relative_path": "../private.csv"},
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "invalid_tool_input"
