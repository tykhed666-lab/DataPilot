# Day 9：Executor、动态工具调用与 ArtifactRef

## 今天完成了什么

Day 8 的 approve 只把状态改成 `executing`。今天加入真正的 Executor：

```text
approve
  ↓
execute current_step_index
  ├─ 工具失败 → failed → END
  ├─ 还有步骤 → current_step_index + 1 → execute
  └─ 全部完成 → reviewing → END
```

完整工具结果不会放进 `AgentState`，而是保存为 JSON Artifact；State 只保存：

- `current_step_index`
- 一行短摘要
- `ArtifactRef`

`reviewing` 是 Day 11 Reviewer 的入口状态，目前图在这里结束。

## 1. Executor 为什么不能写死工具顺序

Planner 返回的是动态 `AnalysisPlan`：

```python
PlanStep(
    step_id="step-1",
    tool_name="query_dataset",
    arguments={...},
)
```

Executor 不判断“这是 SQL 还是 Profile”，只通过统一接口调用：

```python
result = registry.invoke(step.tool_name, step.arguments)
```

因此 Planner 可以改变工具和步骤顺序，而 Executor 的实现不需要跟着修改。这就是 Tool Registry 提供的动态调用能力。

Planner 负责选择工具，Tool Registry 负责参数和输出校验，Executor 负责执行顺序与结果保存。三个职责不能混在一起。

## 2. 为什么一个节点只执行一步

一种简单写法是在 Executor 节点里使用 `for step in plan.steps`。DataPilot 没有这样做，而是：

```text
execute step 0
  → 更新 current_step_index
  → 条件边
  → execute step 1
```

这样做的价值是：

- 每一步都形成独立的 LangGraph 状态更新。
- Day 10 可以在步骤之间保存 checkpoint。
- 某一步失败时，能准确知道停止位置。
- Trace 可以记录每个工具步骤，而不是只看到一个大节点。
- 恢复时不必重新执行已经完成的全部步骤。

这是一种 Agent 后端常见的 durable execution 结构。

## 3. 为什么完整结果不能进入 AgentState

一次 SQL 查询可能返回成千上万行。如果把结果直接放进 State：

- checkpoint 会快速膨胀。
- 每次状态序列化都会复制大对象。
- 后续模型可能意外接收到无关数据。
- WebSocket 或日志可能泄露整份数据。

因此工具输出采用间接引用：

```text
ToolEnvelope（完整 rows）
  ↓ ArtifactStore.save_tool_result
data/artifacts/tool-results/<artifact_id>.json
  ↓
ArtifactRef（进入 AgentState）
```

`ArtifactRef` 只有四个小字段：

```python
artifact_id
kind
relative_path
summary
```

## 4. Artifact Store 是一个深模块

调用方只需要两个接口：

```python
reference = store.save_tool_result(step, envelope)
content = store.load(reference)
```

内部隐藏了：

- JSON 编码
- UTF-8
- 20MB 默认大小限制
- UUID 文件名
- 临时文件替换的原子保存
- 根目录路径逃逸检查
- 文件不存在错误

删除这个模块后，这些复杂性会散落到 Workflow、Executor 和测试中，因此这个模块具有足够的深度。

当前只有文件系统这一种真实实现，所以没有提前创建抽象基类。等未来真正出现对象存储 Adapter 时再建立 seam。

## 5. PlanExecutor 的小型接口

```python
execution = executor.execute_step(step)
```

它隐藏两件必须始终一起完成的事情：

1. 通过 Tool Registry 动态调用工具。
2. 无论成功还是失败，都把完整 ToolEnvelope 保存为审计证据。

返回的 `StepExecution` 只包含图路由需要的信息：

- 是否成功
- ArtifactRef
- 短摘要
- 稳定错误码

## 6. 失败为什么也要保存 Artifact

假设第二步执行危险 SQL：

```sql
DROP TABLE dataset
```

Dataset Guardrail 会阻止它，Tool Runtime 返回失败 Envelope。Executor 会：

1. 保存失败 Envelope。
2. 将 `current_step_index` 更新到 2，表示前两步已经产生结果。
3. 设置 `status=failed`。
4. 设置 `error=execution_failed:tool_execution_failed`。
5. 不执行第三步。

失败证据以后可供 Reviewer、Trace 和面试演示使用，但 traceback、绝对路径和完整数据仍不会进入 State。

## 7. SQL 没有 ORDER BY 就没有顺序保证

Day 9 的第一个红灯测试暴露了一个真实数据问题：

```sql
SELECT region, SUM(revenue)
FROM dataset
GROUP BY region
```

即使华东收入最高，也不能断言第一行一定是华东。需要显式排序：

```sql
ORDER BY total_revenue DESC
```

这不是 DuckDB 的问题，而是关系数据库结果集合的通用语义。

## 阅读顺序

1. `tests/unit/test_agent_workflow.py` 的 approve 和执行失败测试
2. `tests/unit/test_artifacts.py`
3. `src/datapilot/agent/executor.py`
4. `src/datapilot/agent/artifacts.py`
5. `src/datapilot/agent/workflow.py` 的 execute 节点和条件路由

## 运行验证

```powershell
uv run pytest tests/unit/test_artifacts.py tests/unit/test_agent_workflow.py -q
uv run python scripts/check_quality.py
```

今天继续使用 `FakeStructuredModel`。Executor 调用的是真实 Dataset Tool，但不会调用真实大模型，也不会消耗模型额度。

测试产生的 Artifact 位于 pytest 临时目录，不会进入 Git 仓库。

## 练习

### 练习 1：观察 Artifact

在 approve 测试中打印：

```python
print(approved["artifacts"][0])
print(artifacts.load(approved["artifacts"][0]))
```

比较 State 中的引用和文件中的完整 rows。

### 练习 2：增加第二个成功步骤

在计划中增加 `SELECT COUNT(*) AS row_count FROM dataset`，验证：

- `current_step_index == 2`
- `len(artifacts) == 2`
- Artifact 摘要顺序和计划一致

### 练习 3：理解失败停止

阅读 `test_executor_stops_after_failed_step_and_saves_failure_evidence`，回答：

1. 为什么第三步没有 Artifact？
2. 为什么失败步骤仍然有 Artifact？
3. 为什么 State 的 error 只保存稳定错误码？

## 今天没有实现的内容

- `call_id` 和工具幂等恢复：已在 Day 10 完成，参见 `day-10-durable-execution.md`。
- SQLite Checkpoint 和进程重启：Day 10。
- Reviewer 读取 Artifact 并复算结果：Day 11。
- MCP 远程工具 Adapter：Day 13。

今天的核心是把“模型提出计划”转换成“可控、逐步、可审计的工具执行”。
