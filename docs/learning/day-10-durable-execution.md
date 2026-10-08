# Day 10：SQLite Checkpoint、call_id 与重启恢复

## 今天完成了什么

Day 8～9 使用 `InMemorySaver`，Python 进程关闭后暂停状态就会消失。今天替换为可注入的 SQLite Checkpointer，并让工具步骤具有稳定 `call_id`：

```text
进程 A
  start(task_id)
  → plan
  → interrupt
  → SQLite checkpoint
  → 进程退出

进程 B
  打开同一个 checkpoints.db
  → resume(task_id, approval)
  → 恢复原计划
  → execute(call_id)
  → Artifact
```

新的 Workflow 不会重新 Profile 或调用 Planner，而是从同一个 `thread_id` 的 checkpoint 继续。

## 1. Checkpoint 保存什么

LangGraph Checkpointer 保存：

- 当前 `AgentState`
- 下一批待执行节点
- interrupt 信息
- thread 内的 checkpoint 历史和版本

它不保存：

- CSV/XLSX 原文件
- 完整 SQL rows
- Artifact 文件正文
- 模型 API Key

完整工具结果仍由 Artifact Store 管理，checkpoint 中只有 `ArtifactRef`。SQLite 和 Artifact 是两类不同的持久化数据，不能混为一谈。

## 2. task_id 与 thread_id

每次调用图都使用：

```python
{"configurable": {"thread_id": task_id}}
```

SQLite Checkpointer 通过 `thread_id` 找回执行历史。DataPilot 直接复用业务 `task_id`，因此恢复接口不需要额外暴露一套 LangGraph 标识。

同一个 `task_id` 必须始终指向同一个任务；不同任务不能共用它。

## 3. SQLite 生命周期为什么使用 context manager

使用方式：

```python
with open_sqlite_checkpointer("data/checkpoints.db") as checkpointer:
    workflow = AgentWorkflow(
        planner=planner,
        tools=tools,
        artifacts=artifacts,
        checkpointer=checkpointer,
    )
```

`open_sqlite_checkpointer()` 隐藏了：

- 创建父目录
- 打开和关闭连接
- 建立 LangGraph 表
- WAL 日志模式
- synchronous 配置
- 5 秒 busy timeout
- 安全序列化白名单

连接所有权很明确：离开 `with` 后连接关闭，新的进程重新打开同一个数据库文件。

## 4. 为什么不直接序列化任意 Python 对象

Checkpoint 反序列化属于安全边界。项目只允许恢复 State 中明确存在的类型：

```text
AnalysisPlan
ArtifactRef
TaskStatus
DatasetProfile
```

这比允许任意模块和类型更容易审计。Day 11 新增 Reviewer 类型时，也必须显式加入白名单。

## 5. stable call_id

每个执行步骤使用下面三个值生成稳定 ID：

```text
task_id + plan_version + step_id
  → SHA-256
  → 前 32 个十六进制字符
```

三个字段分别解决：

- `task_id`：不同任务不能互相复用结果。
- `plan_version`：修改后的计划不能复用旧计划步骤。
- `step_id`：同一计划的不同步骤必须区分。

相同输入在不同进程中得到相同 `call_id`；随机 UUID 不具备这个性质。

## 6. Executor 如何避免重复工具调用

执行步骤前先查询 Artifact Store：

```text
derive call_id
  ↓
Artifact 已存在？
  ├─ 是 → 读取已验证的 ToolEnvelope，不调用工具
  └─ 否 → 调用工具 → 保存 ToolEnvelope
```

Artifact 文件名就是稳定 `call_id`：

```text
tool-results/<call_id>.json
```

文件内的 `ToolEnvelope.call_id` 必须与文件名一致。这样可以发现文件错配或错误引用。

## 7. idempotency、at-least-once 与 exactly-once

这是面试中非常重要的区别。

当前实现可以保证：

- 已经成功保存 Artifact 的调用不会再次执行。
- Workflow 或 Executor 重建后仍能复用结果。
- 修改后的计划使用新的 call_id。

但下面这个极小窗口仍然存在：

```text
外部工具副作用已完成
  → 进程突然崩溃
  → Artifact 尚未保存
```

重启后本地无法证明副作用是否完成。想获得端到端幂等，外部工具本身也必须接收 `call_id`，并用唯一约束记录处理结果。例如支付、发邮件、写远程数据库都需要下游参与。

DataPilot 当前 Dataset Tool 是只读查询，没有写入副作用；Day 13 的 MCP Adapter 会继续携带 `call_id`。项目不虚假宣称分布式 exactly-once，而是实现可解释的 effectively-once 行为。

## 8. 为什么仍要逐步执行

LangGraph 在每个节点后保存 checkpoint。Day 9 把每个 PlanStep 设计为一个独立 `execute` 节点，因此执行历史可以准确记录：

```text
current_step_index = 0
  → execute step 0
  → checkpoint index 1
  → execute step 1
  → checkpoint index 2
```

如果所有步骤都藏在一个普通 `for` 循环里，LangGraph 只能看到循环前和循环后的状态，无法在步骤之间提供 durable execution。

## 9. 两类测试

### SQLite 集成测试

`test_checkpoint_recovery.py`：

1. Workflow A 生成计划并暂停。
2. 关闭 SQLite 连接，模拟进程退出。
3. Workflow B 使用新的模型对象和新连接。
4. 根据 task_id 恢复并批准。
5. 验证 Planner 没有再次调用。

### Executor 幂等测试

`test_executor.py` 使用一个可观察的计数工具：

1. 第一次执行产生副作用和 Artifact。
2. 重建 Executor。
3. 用相同 task、版本和步骤再次执行。
4. 验证工具仍只调用一次，第二次结果标记为 `reused=True`。
5. 改为 plan version 2 后，验证生成新 call_id 并重新执行。

## 阅读顺序

1. `tests/integration/test_checkpoint_recovery.py`
2. `tests/unit/test_executor.py`
3. `src/datapilot/agent/checkpointing.py`
4. `src/datapilot/agent/executor.py`
5. `src/datapilot/agent/artifacts.py`
6. `src/datapilot/agent/workflow.py`

## 运行验证

```powershell
uv run pytest tests/integration/test_checkpoint_recovery.py tests/unit/test_executor.py -q
uv run python scripts/check_quality.py
```

这些测试全部使用 Fake Model，不访问真实模型 API。

## 练习

### 练习 1：观察 SQLite 文件

运行恢复测试时，在第一个 `with` 结束后设置断点，观察：

```text
checkpoints.db
checkpoints.db-wal（是否存在取决于 SQLite checkpoint 时机）
checkpoints.db-shm
```

不要手工修改数据库内容。

### 练习 2：验证 plan_version

把 Executor 幂等测试的第二次调用改成 `plan_version=2`，解释为什么计数工具会再次执行，然后恢复代码。

### 练习 3：分析崩溃窗口

写出以下三个崩溃位置的恢复结果：

1. 工具调用前崩溃。
2. 工具返回后、Artifact 保存前崩溃。
3. Artifact 保存后、LangGraph checkpoint 前崩溃。

重点解释第 2 种情况为什么需要下游工具支持 idempotency key。

## 今天没有实现的内容

- 多进程高并发写 SQLite。
- 分布式锁或消息队列。
- 外部工具端的 idempotency ledger。
- Reviewer：Day 11。

今天的核心不是“把状态写入数据库”，而是理解可恢复 Agent 的状态、外部结果和副作用必须怎样协同。
