# DataPilot 面试讲解指南

## 60 秒项目介绍

DataPilot 是一个可恢复、可审批、可评测的数据分析 Agent 后端。用户上传 CSV/XLSX 并提出问题后，Planner 基于数据画像和工具 Schema 生成结构化计划；LangGraph 在执行前暂停等待人工批准；Executor 用受控 DuckDB SQL 执行；Reviewer 先确定性复算，再读取有预算的 Evidence Digest 做语义审核并生成直接答案，最多重规划两次；最终报告把自然语言结论放在正文，把原始证据放在附录。SQLite Checkpoint、稳定 call_id、ArtifactRef 和 JSONL Trace 分别解决恢复、幂等、上下文膨胀和可观测性问题。

## 高频问题

### 1. 为什么不用一个 Prompt 直接完成？

直接调用难以审批、恢复和定位错误。分成 Planner、Executor、Reviewer 后，每一层有结构化输入输出，可以独立测试和设定权限。

### 2. 为什么 Reviewer 不能只用 LLM？

模型适合判断答案是否充分，不适合充当计算器。关键 SQL 结果由相同安全工具复算；随后 Evidence Packager 提供列名、行数、截断状态和有限样本，模型据此判断任务完成度并生成有证据的答案。

### 3. 如何避免无限自我修正？

状态里有 `retry_count`，默认最多两次；每次新计划仍须人工批准，预算耗尽进入明确失败终态。

### 4. interrupt 和普通 API 等待有什么不同？

LangGraph 把暂停点和状态写进 checkpoint。进程重启后可按同一个 `task_id/thread_id` 恢复，而不是依赖内存中的协程。

### 5. call_id 如何保证幂等？

它由 task_id、plan_version 和 step_id 稳定计算。恢复时先查 Artifact Store，已有成功结果就复用。它是单机幂等，不宣称实现分布式 exactly-once。

### 6. 为什么 State 不保存完整结果？

大结果会放大 checkpoint、模型上下文和序列化风险。State 只存摘要和 ArtifactRef，完整 ToolEnvelope 留在磁盘。

### 7. SQL 安全如何实现？

SQLGlot 解析 AST，只允许单条 SELECT/CTE；DuckDB 只暴露名为 `dataset` 的关系，并强制最大返回行数。字符串关键词过滤不是主要安全边界。

### 8. MCP 在项目中承担什么角色？

Dataset 工具有统一的进程内契约，同时由独立 MCP 2.x Server 暴露。核心图当前直接调用 Registry；MCP 集成测试通过真实子进程证明协议可用，未来可加 Client Adapter 而不改 Planner。

### 9. Agent 如何评测？

除了终态，还检查轨迹中必须出现和禁止出现的工具，并支持稳定故障注入。CI 使用 Fake Model，因此可重复且不消耗 API。

### 10. 当前最大局限是什么？

它是单用户学习型 MVP：SQLite 和本地文件适合单机演示，不含认证、任务队列、多租户和分布式锁；报告提供可读答案和可追溯证据，但不是 BI 产品。

## 建议演示顺序

1. 跑 API 集成测试，展示完整闭环。
2. 打开 Workflow 路由，解释审批和重试边。
3. 修改保存后的数字，展示确定性 Reviewer 拒绝。
4. 展示重启恢复测试和稳定 call_id。
5. 启动 MCP 测试，证明它不是普通函数别名。
6. 展示 Trace 与轨迹 grader，最后主动说明系统边界。
