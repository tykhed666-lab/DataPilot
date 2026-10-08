# Changelog

## 1.1.1 - 2026-10-08

- 修复真实模型通过 Reviewer 审核时可能省略 `answer`、导致任务失败的问题。
- Reviewer 的模型 JSON Schema 现在明确要求返回 `answer` 字段；审核失败时仍可返回 `null`。
- 新增 Schema 回归测试，并用 `qwen3.5-flash` 完成上传、审批、执行、审核和报告全链路验证。

## 1.1.0 - 2026-10-08

- 根路径新增 FastAPI 内嵌的原生 HTML/CSS/JavaScript 分析工作台。
- 支持数据上传、问题提交、计划审批、修改、拒绝、答案、报告和 Trace 查看。
- 使用 `localStorage` 保存最近 task_id，刷新后通过后端 checkpoint 恢复任务。
- 保留 `/docs` Swagger 入口，不引入 Node、前端构建链或外部 CDN。

## 1.0.2 - 2026-10-08

- Evidence Digest 字符预算现在针对 XML 转义后的最终 Prompt 文本计算。
- 超宽表会保留总列数和明确截断标记，并按预算逐步减少展示列，不再直接失败。
- Reviewer 直接嵌入已转义证据，避免二次转义放大长度或改变内容。

## 1.0.1 - 2026-10-08

- Reviewer 现在读取受限但真实的 Evidence Digest，而不是只读取工具成功摘要。
- 通过审核时必须生成有证据的自然语言答案、关键发现和注意事项。
- Markdown 报告展示直接答案与 `final_deliverable`，原始 JSON 降为证据附录。
- Day 11～15 学习文档扩展为完整的概念、代码、测试、练习和面试叙事。

## 1.0.0 - 2026-10-08

- 完成 Planner–Executor–Reviewer LangGraph 闭环和人工审批。
- 加入 SQLite checkpoint、稳定 call_id、Artifact Store 与重启恢复。
- 加入受控 DuckDB SQL、MCP 2.x Server 和真实子进程集成测试。
- 加入混合 Reviewer、两次重规划预算和确定性 Markdown 报告。
- 加入 JSONL Trace、14 个评测案例、FastAPI 与 CLI 演示入口。
