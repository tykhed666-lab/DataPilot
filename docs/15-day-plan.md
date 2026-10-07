# DataPilot Agent Backend：15 天实施计划

周期：2026-10-07 至 2026-10-21。目标是完成一个难度高于 ResearchKB、但学习路径清晰的 Agent 后端项目。

每天按约 40% 讲解、40% 阅读和运行代码、20% 动手练习分配。当天内容未理解前不继续堆叠下一层。

| Day | 日期 | 实现内容 | 必须掌握的知识 | 当日验收 |
|---:|---|---|---|---|
| 1 | 10/07 | 项目重置、架构、共享契约、AgentState、GitHub 计划 | State 与业务对象的区别；为什么大结果只存引用 | 健康接口、契约测试、CI 通过 |
| 2 | 10/08 | CSV/XLSX 加载和 Dataset Profile | DataFrame、字段类型、缺失值、摘要 | 两种文件得到统一 Profile |
| 3 | 10/09 | DuckDB 只读查询、行数限制、图表数据准备 | 工具输入输出；SELECT/CTE 安全规则 | 危险 SQL 被阻止，查询结果正确 |
| 4 | 10/10 | Tool Contract、Registry、Input/Output Guardrail | 动态工具发现与统一错误 | Fake 工具与真实工具走相同接口 |
| 5 | 10/11 | Fake LLM、真实模型 Adapter、结构化输出 | 为什么测试不能依赖真实模型 | 离线生成固定计划，真实模型冒烟 |
| 6 | 10/12 | Planner Prompt、AnalysisPlan 校验、预算 | 计划生成、未知工具拒绝 | 合法计划通过，非法计划失败 |
| 7 | 10/13 | LangGraph StateGraph 和条件路由 | Node、Edge、Command、状态更新 | 最小图完整运行 |
| 8 | 10/14 | interrupt、approve/revise/reject | Human-in-the-loop 和恢复语义 | 三种审批路线测试通过 |
| 9 | 10/15 | Executor 按计划逐步执行、ArtifactRef | 动态调用、上下文控制 | 计划步骤依次执行且大结果不进 State |
| 10 | 10/16 | SQLite Checkpoint、幂等 call_id、重启恢复 | Durable execution、重复执行 | 重启后继续且不重复工具副作用 |
| 11 | 10/17 | 确定性复算 + LLM Reviewer | 混合验证比纯模型审核可靠 | 错误数字被发现，正确结果通过 |
| 12 | 10/18 | 最多两次修正、错误分类、停止条件 | Agent 闭环和 retry budget | 可修复错误成功，安全错误不重试 |
| 13 | 10/19 | Dataset MCP：stdio，预留 Streamable HTTP | MCP 工具发现、结构化结果、协议 seam | MCP Client 可发现并调用工具 |
| 14 | 10/20 | Trace、故障注入、12～15 个轨迹评测 | Span、工具轨迹、确定性 grader | 能定位规划/执行/审核哪层失败 |
| 15 | 10/21 | FastAPI、CLI 演示、README、架构图、面试题、Release | 讲清设计、取舍和局限 | 冷启动成功，CI 全绿，完成演示 |

## 最终演示

1. 上传销售 CSV。
2. 提问“哪个区域利润最高，原因是什么？”
3. Planner 生成结构化计划。
4. 用户修改其中一步并批准。
5. Executor 通过 MCP 数据工具执行查询和图表准备。
6. Reviewer 复算关键数字；故意注入错误时触发一次修正。
7. 生成带工具证据和 Trace ID 的 Markdown 报告。
8. 重启进程后继续另一个暂停中的任务。

## 质量门禁

- Ruff、Pyright、Pytest、GitHub Actions 全绿。
- Agent 图路由、安全 Guardrail、Checkpoint 和 retry budget 必须有测试。
- CI 使用 Fake LLM，不消耗真实模型额度。
- 评测同时检查最终答案和执行轨迹。
- 真实密钥、上传文件、数据库、checkpoint、trace 原文和产物不得提交。

## 延期时的削减顺序

可以削减：Streamable HTTP、Plotly 美化、额外模型路由、Trace 可视化。

不得削减：Planner、审批、Executor、Reviewer、Checkpoint、MCP、Guardrail 和轨迹评测。
