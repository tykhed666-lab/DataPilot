# Day 13：MCP 2.x 工具边界

`src/datapilot/mcp_server.py` 把 Dataset Tool Registry 暴露成独立 MCP Server。它支持 stdio，也预留 Streamable HTTP；工具返回统一 `ToolEnvelope`，并要求调用方携带 `call_id`。

这里要区分两层：

- Tool Registry 是进程内业务接口，Agent 当前直接使用它。
- MCP 是进程间协议接口，外部 Agent 或后续 MCP Client Adapter 可以调用。

`tests/integration/test_mcp_server.py` 会真的启动子进程、初始化 MCP Session、发现工具并执行 SQL，不是对 Python 函数的伪测试。

MVP 没有为了“看起来用了 MCP”强迫核心图走网络；这保留了清晰的模块边界，也让 MCP 传输可以独立演进。
