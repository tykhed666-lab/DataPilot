# Day 7：LangGraph StateGraph 与条件路由

## 今天完成了什么

前六天的模块原本需要人工按顺序调用。今天使用 LangGraph 把它们连接成第一个可执行状态图：

```text
START
  ↓
profile ──失败──→ END
  ↓成功
plan ─────失败──→ END
  ↓成功
await_approval
  ↓
END
```

成功时，图的最终状态是 `awaiting_approval`。这里只表示“计划已经准备好”；Day 8 才会加入真正的 `interrupt` 以及 approve、revise、reject 恢复语义。

## 五个核心概念

### 1. State

`AgentState` 是所有节点共同读写的小型任务状态。今天新增了 `profile`：

```python
class AgentState(TypedDict):
    task_id: str
    dataset_id: str
    question: str
    status: TaskStatus
    profile: DatasetProfile | None
    plan: AnalysisPlan | None
    # ...
```

节点不返回一份手工复制的完整 State，只返回自己负责更新的字段。LangGraph 将这些字段合并回当前状态。

### 2. Node

Node 是一个接收 State、返回状态更新的函数：

```python
def await_approval_node(state: AgentState) -> dict[str, object]:
    return {"status": TaskStatus.AWAITING_APPROVAL}
```

本项目当前有三个节点：

- `profile`：通过 Tool Registry 调用 `profile_dataset`。
- `plan`：把 Profile 和动态工具列表交给 Planner。
- `await_approval`：把任务标记为等待审批。

### 3. Edge

普通 Edge 表示无条件的下一步：

```python
graph.add_edge(START, "profile")
graph.add_edge("await_approval", END)
```

### 4. Conditional Edge

条件边根据当前 State 选择下一节点。Profile 成功才允许进入 Planner：

```python
graph.add_conditional_edges(
    "profile",
    route_after_profile,
    {"plan": "plan", "end": END},
)
```

这样失败不是靠抛出异常让整个程序崩溃，而是变成可观察的业务状态：

```text
status = failed
error = profile_failed:tool_execution_failed
```

### 5. Runtime Context

`dataset_relative_path` 是本次运行所需的依赖参数，但它不是 Agent 的推理记忆，因此通过 `WorkflowContext` 传入：

```python
workflow.run(state, dataset_relative_path="samples/sales_demo.csv")
```

可以用这个问题判断数据放在哪里：

- 后续节点需要记住、Checkpoint 恢复时仍需存在：放入 State。
- 只属于本次运行环境或依赖注入：放入 Runtime Context。
- 大型查询结果和图表：保存为 Artifact，State 只放引用。

## 深模块接口

外部代码只需要认识 `AgentWorkflow.run()`：

```python
workflow = AgentWorkflow(planner=planner, tools=registry)
result = workflow.run(
    initial_state,
    dataset_relative_path="samples/sales_demo.csv",
)
```

节点名称、路由函数和图编译都隐藏在 `AgentWorkflow` 内部。图在构造 Workflow 时编译一次，而不是每经过一个节点重新编译。

## 阅读顺序

1. `tests/unit/test_agent_workflow.py`
2. `src/datapilot/agent/workflow.py`
3. `src/datapilot/agent/state.py`
4. 回看 `planner.py`、`dataset_tools.py` 和 `tool_runtime.py`

先从测试理解可观察行为，再阅读节点与边的实现。

## 运行验证

只运行 Day 7：

```powershell
uv run pytest tests/unit/test_agent_workflow.py -q
```

运行全部质量检查：

```powershell
uv run python scripts/check_quality.py
```

Day 7 使用 `FakeStructuredModel`，不会调用真实模型、不会消耗 API 额度。这里测试的是图的确定性路由，而不是再次测试模型能力。

## 练习

### 练习 1：画出失败路径

阅读两个 `_route_after_*` 函数，回答：

1. CSV 不存在时，为什么 Planner 不会被调用？
2. 模型返回非法计划时，为什么不会进入 `await_approval`？

可用测试中的 `model.calls` 验证答案。

### 练习 2：增加一个只读节点

尝试在 `plan` 和 `await_approval` 之间加入 `summarize_plan` 节点，只向 State 新增一条短摘要。不要执行 SQL，也不要修改原计划。

### 练习 3：区分 State 与 Context

判断以下内容应该放在 State、Runtime Context 还是 Artifact：

- 用户原始问题
- 本机数据根目录
- 20 万行 SQL 结果
- 已审批的 AnalysisPlan
- 当前重试次数

参考答案：State、Context、Artifact、State、State。

## 今天暂时没有加入的内容

- 没有 `interrupt()`：Day 8 学习。
- 没有 approve、revise、reject：Day 8 学习。
- 没有 SQLite Checkpoint：Day 10 学习。
- 没有 Executor：Day 9 学习。

今天只建立可解释的图结构和确定性路由，为后面三个能力提供稳定骨架。
