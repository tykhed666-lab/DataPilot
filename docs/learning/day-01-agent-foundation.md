# Day 1：Agent 后端基础地图

## 今天只需要理解三个概念

### 1. Contract

Contract 是节点之间约定的数据形状。例如 Planner 必须返回 `AnalysisPlan`，Reviewer 必须返回 `ReviewResult`。Pydantic 会拒绝缺少字段、多余字段和不合法取值。

今天阅读：`src/datapilot/contracts.py`。

### 2. AgentState

AgentState 是一项任务在 LangGraph 中流动的“工作记忆”。它保存当前计划、执行进度、Reviewer 判断和重试次数。

State 不是数据库，也不是文件仓库。DataFrame、完整 SQL 结果和图表不能直接放进去，只保存摘要和 `ArtifactRef`。

今天阅读：`src/datapilot/agent/state.py`。

### 3. 节点尚未实现

今天没有 Planner、Executor 或 Reviewer。这是有意的：先明确它们交换什么数据，再逐个实现行为。

## 推荐阅读顺序

1. `README.md`
2. `docs/architecture.md`
3. `src/datapilot/contracts.py`
4. `src/datapilot/agent/state.py`
5. `tests/unit/test_agent_foundation.py`
6. `docs/15-day-plan.md`

## 动手练习

在 PyCharm 的 Python Console 中运行：

```python
from datapilot.agent import create_initial_state

state = create_initial_state(
    task_id="task-demo",
    dataset_id="sales-demo",
    question="哪个区域销售额最高？",
)
print(state)
```

然后回答三个问题：

1. 为什么 `question` 需要去掉首尾空格？
2. 为什么 State 中只有 `artifacts` 引用，而不是完整文件？
3. 如果 `retry_count` 没有上限，可能发生什么？

## 验收命令

```powershell
uv run pytest tests/unit/test_agent_foundation.py tests/test_health.py -q
uv run python scripts/check_quality.py
```

完成阅读和练习后，再进入 Day 2 的 Dataset Profile。
