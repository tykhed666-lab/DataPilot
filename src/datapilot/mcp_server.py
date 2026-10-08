"""Dataset 工具的 MCP 2.x stdio 与 Streamable HTTP Server。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.tool_runtime import ToolRegistry


def create_dataset_mcp(data_root: str | Path) -> MCPServer:
    """创建绑定到指定数据根目录的 Dataset MCP Server。"""

    registry = ToolRegistry(dataset_tool_definitions(data_root))
    server = MCPServer(
        name="datapilot-dataset",
        title="DataPilot Dataset Tools",
        description="Profile and safely query local tabular datasets.",
        version="1.0.0",
    )

    @server.tool(name="profile_dataset", structured_output=True)
    def profile_dataset_tool(relative_path: str, call_id: str) -> dict[str, Any]:
        """Inspect columns, types, missing values, and numeric summaries."""

        return registry.invoke(
            "profile_dataset",
            {"relative_path": relative_path},
            call_id=call_id,
        ).model_dump(mode="json")

    @server.tool(name="query_dataset", structured_output=True)
    def query_dataset_tool(
        relative_path: str,
        sql: str,
        call_id: str,
        max_rows: int = 1000,
    ) -> dict[str, Any]:
        """Run one guarded read-only SELECT or WITH query against the dataset table."""

        return registry.invoke(
            "query_dataset",
            {
                "relative_path": relative_path,
                "sql": sql,
                "max_rows": max_rows,
            },
            call_id=call_id,
        ).model_dump(mode="json")

    return server


def create_streamable_http_app(data_root: str | Path) -> Starlette:
    """为部署场景创建无状态 Streamable HTTP ASGI 应用。"""

    return create_dataset_mcp(data_root).streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )


def run() -> None:
    """启动 stdio 或 Streamable HTTP transport。"""

    parser = argparse.ArgumentParser(description="Run the DataPilot Dataset MCP server")
    parser.add_argument("--data-root", default="data")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    arguments = parser.parse_args()
    server = create_dataset_mcp(arguments.data_root)
    if arguments.transport == "stdio":
        server.run("stdio")
    else:
        server.run(
            "streamable-http",
            host=arguments.host,
            port=arguments.port,
            stateless_http=True,
            json_response=True,
        )


if __name__ == "__main__":
    run()
