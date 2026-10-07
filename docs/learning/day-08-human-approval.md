# Day 8：interrupt、Command 与人工审批恢复

## 今天完成了什么

Day 7 的 `awaiting_approval` 只是一个普通终点。今天把它改成真正可暂停、可恢复的 Human-in-the-loop 工作流：

```text
start(state, thread_id=task_id)
  → profile
  → plan
  → await_approval（plan_version + 1）
  → approval
       interrupt(plan)
       ├─ approve → executing → END
       ├─ reject  → rejected  → END
       └─ revise  → plan → await_approval → interrupt(plan v2)
```

`executing` 目前只是批准后的边界状态。Day 9 才会加入真正的 Executor。

## 1. 为什么 interrupt 需要 Checkpointer

普通函数暂停后，局部变量会随调用结束而消失。LangGraph 必须先保存当前 State 和节点位置，之后才能继续。因此只要使用 `interrupt()`，编译图时就必须提供 Checkpointer：

```python
graph.compile(checkpointer=checkpointer)
```

Day 8 使用 `InMemorySaver`，便于理解暂停语义：

- 同一 Python 进程内可以恢复。
- 进程关闭后内容消失。
- Day 10 会替换成 SQLite Checkpointer，学习跨进程恢复。

## 2. task_id 为什么同时作为 thread_id

LangGraph 使用 `thread_id` 区分不同执行历史：

```python
config = {"configurable": {"thread_id": task_id}}
```

本项目让业务 `task_id` 同时作为 LangGraph `thread_id`，避免维护两套任务标识。调用 `resume()` 时，图会用它找到正确的暂停位置。

## 3. interrupt 如何暂停

审批节点把当前计划和版本作为可检查的暂停信息：

```python
decision = interrupt(
    {
        "task_id": state["task_id"],
        "plan_version": state["plan_version"],
        "plan": state["plan"],
    }
)
```

第一次运行到这里时，`interrupt()` 不会正常返回，图保存 checkpoint 并把控制权交还给调用者。因此 `start()` 得到的 State 是：

```text
status = awaiting_approval
plan_version = 1
plan = AnalysisPlan(...)
```

## 4. Command(resume=...) 如何恢复

用户提交审批后，不能把审批结果当成一个全新的 State 再次启动，而要恢复原来的 thread：

```python
graph.invoke(
    Command(resume=approval.model_dump(mode="json")),
    config={"configurable": {"thread_id": task_id}},
)
```

恢复时，`Command.resume` 的内容会成为 `interrupt()` 的返回值。审批节点随后验证 `ApprovalRequest`，再更新状态和选择路由。

## 5. 三种审批决定

### approve

```text
awaiting_approval → executing
```

计划不再修改。Day 9 的 Executor 将从这个状态开始逐步调用工具。

### reject

```text
awaiting_approval → rejected → END
```

拒绝是明确终态，不会调用 Planner，也不会执行工具。

### revise

```text
awaiting_approval
  → planning
  → Planner(revision_feedback)
  → awaiting_approval(plan_version=2)
```

用户原始问题保持不变。反馈通过独立的 `<revision_feedback>` 进入 Planner Prompt，新的计划必须再次审批。

## 6. 为什么要有 plan_version

假设用户同时打开两个页面：

1. 页面 A 显示计划 v1。
2. 页面 B 修改计划，系统生成 v2。
3. 页面 A 又批准旧的 v1。

如果没有版本检查，旧页面可能错误批准已经失效的计划。因此每个审批请求必须携带所看到的 `plan_version`；版本不等于当前 checkpoint 时抛出 `StalePlanVersionError`。未来 API 会把它映射成 HTTP 409。

## 7. interrupt 的重要重放语义

恢复时，包含 `interrupt()` 的节点会从函数开头重新执行，直到再次走到同一个 `interrupt()`，然后获得 resume 值。

因此不要这样写：

```python
def approval_node(state):
    send_email()  # 恢复时可能再次发送
    decision = interrupt(...)
```

DataPilot 的审批节点在 `interrupt()` 之前只构造小型字典，没有写数据库、调用工具或发送消息。未来若必须产生副作用，应放在独立节点，并使用幂等 `call_id`；这会在 Day 10 展开。

## 8. 恢复值仍然是不可信输入

暂停并不意味着恢复数据可信。`ApprovalRequest` 会确定性校验：

- decision 只能是 `approve`、`revise`、`reject`。
- plan_version 必须大于等于 1。
- revise 必须提供 feedback。
- 未声明字段会被拒绝。

模型不负责这些规则，LangGraph 也不会自动替我们验证业务契约。

## 阅读顺序

1. `tests/unit/test_agent_workflow.py` 中的四类审批测试
2. `src/datapilot/agent/approval.py`
3. `src/datapilot/agent/workflow.py`
4. `src/datapilot/agent/planner.py` 的 revision feedback
5. `src/datapilot/agent/state.py` 的版本和反馈字段

## 运行验证

```powershell
uv run pytest tests/unit/test_agent_workflow.py -q
uv run python scripts/check_quality.py
```

今天继续使用 `FakeStructuredModel`，审批路由测试不会访问真实模型，也不会消耗 API 额度。

## 练习

### 练习 1：跟踪 revise

在 `test_revise_replans_with_feedback_and_pauses_again` 中分别观察：

- 第一次暂停的 `plan_version`
- 第二次模型调用的 Prompt
- 第二次暂停的 `plan_version`

说明为什么 revise 不能直接进入 Executor。

### 练习 2：验证过期审批

把 `test_resume_rejects_a_stale_plan_version` 中的版本从 2 改为 1，观察测试为什么不再抛出 `StalePlanVersionError`，然后恢复原代码。

### 练习 3：理解重放

假设在 `interrupt()` 前面加入一次数据库写入，写出恢复时可能发生的错误。思考如何用唯一 `call_id` 和唯一约束使它变为幂等操作。

## 今天没有实现的内容

- Executor 和工具逐步执行：Day 9。
- SQLite 持久化与进程重启恢复：Day 10。
- HTTP 审批 API：最终 API 集成阶段。

今天的重点是理解“暂停的图不是结束的图”，以及如何用经过验证的外部决定安全地恢复同一条执行历史。
