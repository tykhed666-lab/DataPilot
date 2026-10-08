# Changelog

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
