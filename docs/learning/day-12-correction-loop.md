# Day 12：有限自我修正、错误分类与停止条件

## 今天完成了什么

Day 11 能判断执行结果是否合格，今天把失败判断接回 Planner，形成受控闭环：

```text
review passed
  → report

review failed + retryable + retry_count < 2
  → correction
  → replan
  → human approval
  → execute
  → review

review failed + non-retryable / budget exhausted
  → failed
```

Agent 的“自我修正”不是无限自主，而是带预算、带人工审批、带明确终态的状态机。

## 1. 为什么不能简单 while retry

普通 `while not success` 隐藏了几个重要问题：

- 重试了几次？
- 为什么重试？
- 新计划是否扩大了权限？
- 程序重启后预算是否丢失？
- 什么错误永远不应该重试？

DataPilot 把 `retry_count`、`revision_feedback`、计划版本和审批状态都保存在 AgentState，由 LangGraph 路由显式决定下一步。

## 2. retryable 的含义

`retryable=true` 表示：改变计划或工具参数后，有合理机会完成同一个用户目标。例如：

- 查询缺少分组字段；
- 证据不足以支持原因分析；
- 计划遗漏必要步骤；
- 输出格式合法但交付内容不完整。

下面情况通常不可重试：

- 用户请求被安全策略拒绝；
- 数据文件不存在或不可解析；
- 要求使用未注册工具；
- 证据无法建立可信来源；
- 重试预算已经耗尽。

重复相同操作不会改变结果时，重试只会增加成本。

## 3. correction 如何回到 Planner

Reviewer 的 `correction` 写入 `revision_feedback`，下一次 Planner Prompt 会包含它：

```text
原问题
+ 数据画像
+ 可用工具
+ 上一轮修正建议
→ 新 AnalysisPlan
```

修正建议是上下文，不是更高优先级指令。Planner 仍必须遵守工具白名单、SQL 安全约束、路径约束和最大步骤数。

## 4. 为什么每次重规划都重新审批

Reviewer 可以建议改变计划，但不能替用户授予权限。重规划后图再次到达 `await_approval`：

```text
plan_version 1 → 用户批准 → 执行失败
plan_version 2 → 用户再次审阅 → 批准或拒绝
```

这避免 Agent 在用户只批准了一条聚合查询后，自行增加另一项更敏感的操作。

## 5. retry_count 与 plan_version 不同

- `retry_count`：Reviewer 触发了多少次自动修正。
- `plan_version`：产生并等待审批了多少个计划版本。

用户主动选择 revise 也会产生新计划版本，但不一定消耗 Reviewer 的自动修正预算。两个数字不能合并。

## 6. 清理上一轮状态

进入重规划时必须清理：

- `plan`
- `current_step_index`
- `tool_result_summaries`
- `artifacts`
- 上一轮错误

同时保留：

- task 和 dataset 标识；
- 原始问题；
- 数据画像；
- Reviewer 结果；
- retry_count；
- revision_feedback。

如果不清理执行引用，新旧计划的证据会混在一起；如果清理原始问题和画像，Planner 又会失去任务上下文。

## 7. 稳定 call_id 与新计划

`call_id` 包含 `plan_version`。新版本计划即使复用了相同 `step_id`，也会生成新的调用 ID：

```text
task-A / plan-1 / step-1 → call X
task-A / plan-2 / step-1 → call Y
```

这是必要的，因为修正后的步骤语义或参数可能已经改变，不能误用上一轮 Artifact。

## 8. 停止条件

默认最多允许两次 Reviewer 重规划：

```text
第一次失败 → retry_count 1
第二次失败 → retry_count 2
第三次失败 → review_failed:retry_exhausted
```

预算保存在 checkpoint 中，进程重启不会重新获得次数。

## 9. 测试如何覆盖闭环

`test_reviewer_loop.py` 构造三个连续失败的语义审核结果：

1. v1 批准后审核失败，回到 v2 审批；
2. v2 批准后仍失败，回到 v3 审批；
3. v3 再失败，进入明确失败终态。

测试同时断言 Planner 和 Reviewer 各调用三次，最终 `retry_count == 2`，防止边界出现 off-by-one。

## 阅读顺序

1. `tests/integration/test_reviewer_loop.py`
2. `src/datapilot/agent/workflow.py` 的 `_review_node`
3. `_route_after_review`
4. `src/datapilot/agent/state.py`
5. `src/datapilot/agent/planner.py` 的 `revision_feedback`

## 运行验证

```powershell
uv run pytest tests/integration/test_reviewer_loop.py -q
```

## 练习

### 练习 1：画状态变化

写出三次审核期间 `status`、`plan_version`、`retry_count` 和 `current_step_index` 的变化表。

### 练习 2：不可重试错误

让 Reviewer 返回 `retryable=false`，验证图立即失败，并解释为什么不应再次调用 Planner。

### 练习 3：人工 revise

在第一次审批时选择 revise，比较它与 Reviewer 自动 replan 对 `retry_count` 的影响。

## 面试表达

> 自我修正不是让 Agent 无限循环，而是把错误分类、修正反馈、预算和人工授权都编码进持久化状态机。

## 今天没有实现的内容

- 根据错误类型配置不同预算；
- 指数退避或 API 限流重试；
- 多 Agent 辩论；
- 跨任务共享历史修正经验。

今天的核心是理解“能重试”必须同时回答：为什么重试、谁批准、最多几次、何时停止。
