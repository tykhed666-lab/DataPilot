# DataPilot Agent Backend

DataPilot 是一个用于 AI Agent 后端面试的状态化数据分析智能体。项目重点不是前端页面或生产级基础设施，而是把一条可解释、可恢复、可评测的 Agent 工作流实现完整：

```text
profile → plan → human approval → execute → review → report
```

## 与 ResearchKB 的区别

ResearchKB 展示多模态 RAG、检索、引用和文档生命周期；DataPilot 进一步学习动态规划、工具选择、LangGraph 状态图、Human-in-the-loop、持久化恢复、Reviewer 自我修正、MCP、Trace 和 Agent 轨迹评测。

## 15 天目标

- Planner 生成经过 Pydantic 校验的 `AnalysisPlan`。
- LangGraph 在审批节点暂停，并支持 approve、revise、reject。
- Executor 按计划动态调用数据工具，而不是写死调用顺序。
- SQLite Checkpoint 支持程序重启后继续任务。
- Reviewer 使用确定性复算和模型审核，最多修正两次。
- 一个 Dataset MCP Server 同时展示 stdio 和 Streamable HTTP 的工具接口。
- AgentState 只保存小型上下文和产物引用，不塞入 DataFrame 或大型结果。
- Trace 记录节点、模型、工具、延迟、token、重试和最终状态。
- 12～15 个评测案例同时检查最终答案和 Agent 执行轨迹。

完整排期见 [15 天实施计划](docs/15-day-plan.md)，模块设计见 [Agent 后端架构](docs/architecture.md)。

## 技术栈

- Python 3.11、uv
- FastAPI、Pydantic
- LangGraph、SQLite Checkpoint
- DuckDB、Pandas、SQLGlot
- MCP Python SDK
- Pytest、Ruff、Pyright、GitHub Actions

## 当前阶段

当前为 Day 9：批准后的计划由 Executor 逐步动态调用 Tool Registry；完整 ToolEnvelope 保存为 JSON Artifact，AgentState 只保留短摘要和 `ArtifactRef`，失败步骤会留下证据并阻止后续执行。当天学习说明见 [Day 9：Executor、动态工具调用与 ArtifactRef](docs/learning/day-09-executor-artifacts.md)。SQLite 跨进程恢复和幂等 `call_id` 将在 Day 10 加入。

旧的生产级工程尝试保存在 GitHub 分支 `archive/pre-agent-backend-replan`，不会与新的学习主线混在一起。

## 本地运行

项目目录：`E:\DataPilot`

```powershell
uv sync --python 3.11
uv run uvicorn datapilot.api.app:app --reload
```

浏览器打开：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health/live>

运行质量门禁：

```powershell
uv run python scripts/check_quality.py
```

## 学习方式

每天只引入一个主要概念。你先阅读当天学习文档和测试，再阅读实现，完成小练习后确认是否进入下一天。尚未学习的高级模块不会提前堆入代码库。
