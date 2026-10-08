# Day 13：MCP 2.x、工具发现与协议 Adapter

## 今天完成了什么

前十二天的 Tool Registry 是进程内模块。今天用 MCP Python SDK 2.x 把相同 Dataset 能力暴露成独立进程协议：

```text
MCP Client
  → initialize
  → list_tools
  → call_tool(call_id, arguments)
  → MCP Server
  → Tool Registry
  → Dataset Module
  → ToolEnvelope
```

支持两种传输：

- stdio：本地 Agent 启动子进程，通过标准输入输出通信；
- Streamable HTTP：为远程或长生命周期部署预留的应用入口。

## 1. MCP 解决什么问题

没有 MCP 时，每个 Agent 框架都要直接 import 工具代码，并自行理解参数、返回值和错误。MCP 把这些信息变成可发现的协议契约：

- 工具名称；
- 工具描述；
- 输入 Schema；
- 结构化输出；
- 会话初始化与传输方式。

它解决的是工具互操作，不会自动解决业务安全、幂等、权限和数据质量。

## 2. Registry 与 MCP 的关系

DataPilot 没有在 MCP Server 中复制查询逻辑，而是复用 Day 4 的 Tool Registry：

```text
Dataset Module        真实业务能力
Tool Registry         进程内统一调用接口
MCP Server Adapter    协议转换
```

删除 MCP Adapter 后，复杂度不会散落到 Dataset Module；它只是一个必要但保持很薄的协议 Adapter。SQL Guardrail 仍在 Dataset 层生效。

## 3. 为什么核心 Workflow 仍直接调用 Registry

当前 Agent 与 Dataset 工具在同一应用内。强迫它先启动本地 Server、再经过协议调用，会增加进程管理和故障面，却不会增加真实隔离。

因此 v1.0 的选择是：

- 核心 Workflow 使用进程内 Registry；
- 独立 MCP Server 通过真实集成测试证明可用；
- 未来需要远程工具时，再增加满足同一工具接口的 MCP Client Adapter。

这不是“假装用了 MCP”，而是区分业务接口和传输接口。

## 4. MCPServer 2.x

项目使用 SDK 2.x 的 `MCPServer`，而不是旧教程常见的 `FastMCP`。Server 启动时注册两个工具：

- `profile_dataset`
- `query_dataset`

每个 MCP 调用都接收 `call_id`，并返回完整 `ToolEnvelope`。调用者不需要从自然语言错误中猜测成功与否。

## 5. call_id 为什么穿过协议

MCP 只是传输层，不能丢掉 Day 10 的幂等语义。稳定 `call_id` 让服务端和调用方可以建立共同的调用身份。

当前 Dataset 工具是只读的，因此重复调用风险较低；如果未来增加写工具，服务端必须用该 ID 建立幂等 ledger，而不是只依赖客户端 Artifact。

## 6. stdio 的注意事项

stdio Server 的标准输出属于协议通道。随意 `print()` 调试可能破坏 MCP 消息，所以日志应写入标准错误或结构化日志系统。

客户端负责启动和关闭子进程。进程退出、初始化失败、工具不存在都应被视为协议层错误，不能伪装成成功 `ToolEnvelope`。

## 7. Streamable HTTP 的边界

`create_streamable_http_app()` 创建 HTTP 应用，但 v1.0 没有加入：

- 身份认证；
- 多租户隔离；
- TLS 终止；
- 限流；
- 容器部署配置。

所以它是开发接口，不是可以直接暴露公网的生产服务。

## 8. 为什么必须做真实子进程测试

如果测试只调用 `create_dataset_mcp()` 返回的 Python 对象，下面问题都发现不了：

- 模块入口错误；
- stdio 被日志污染；
- SDK 初始化顺序不对；
- Schema 没有正确发布；
- 子进程编码或关闭异常。

`test_mcp_server.py` 使用真实 `stdio_client`：

1. 启动新的 Python 子进程；
2. 创建 `ClientSession`；
3. initialize；
4. list_tools；
5. call_tool；
6. 验证结构化结果和 call_id。

## 9. ToolEnvelope 跨协议保持一致

无论调用来自 Workflow 还是 MCP，结果都采用：

```text
tool_name
call_id
ok
output
error
```

这让上层不需要维护“本地错误格式”和“MCP 错误格式”两套业务判断。

## 阅读顺序

1. `tests/integration/test_mcp_server.py`
2. `src/datapilot/mcp_server.py`
3. `src/datapilot/tool_runtime.py`
4. `src/datapilot/dataset_tools.py`
5. `pyproject.toml` 的 `datapilot-mcp` 命令

## 运行验证

```powershell
uv run pytest tests/integration/test_mcp_server.py -q
uv run datapilot-mcp --data-root ./data
```

第二条命令会进入 stdio 协议循环，不会显示普通交互菜单，可按 Ctrl+C 结束。

## 练习

### 练习 1：观察工具发现

在集成测试中查看 `discovered.tools`，对应 Tool Registry 的输入 Schema。

### 练习 2：制造非法 SQL

通过 MCP 调用 `DELETE FROM dataset`，观察它如何经过协议后仍被 Dataset Guardrail 拒绝。

### 练习 3：区分三类错误

分别说明：工具不存在、输入 Schema 错误、工具执行失败应该在哪一层产生。

## 面试表达

> MCP 是工具协议 Adapter，不替代业务 Guardrail。DataPilot 复用同一 Registry 契约，并用真实子进程测试验证 stdio，而不是把普通函数换个 MCP 名字。

## 今天没有实现的内容

- Workflow 的远程 MCP Client Adapter；
- OAuth 或 API Token；
- 远程工具健康检查；
- 多 Server 路由和动态权限。

今天的核心是理解 MCP 放在哪里，以及哪些责任绝不能推给协议层。
