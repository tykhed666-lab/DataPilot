import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client


async def test_stdio_mcp_client_discovers_and_calls_dataset_tools(tmp_path: Path) -> None:
    (tmp_path / "sales.csv").write_text(
        "region,revenue\n华东,120\n华南,80\n",
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "datapilot.mcp_server",
            "--data-root",
            str(tmp_path),
        ],
        encoding="utf-8",
    )

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        discovered = await session.list_tools()
        assert {tool.name for tool in discovered.tools} == {
            "profile_dataset",
            "query_dataset",
        }

        result = await session.call_tool(
            "query_dataset",
            {
                "relative_path": "sales.csv",
                "sql": "SELECT SUM(revenue) AS total_revenue FROM dataset",
                "call_id": "mcp-day-13-call",
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["ok"] is True
    assert result.structured_content["call_id"] == "mcp-day-13-call"
    assert result.structured_content["output"]["rows"] == [{"total_revenue": 200}]
