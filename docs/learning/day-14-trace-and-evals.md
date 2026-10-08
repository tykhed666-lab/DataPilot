# Day 14：Agent Trace、故障注入与轨迹评测

## 今天完成了什么

传统接口测试通常只关心输入和最终输出，但 Agent 可能“答案碰巧正确，过程却不安全”。今天增加两类能力：

```text
运行时：TraceRecorder 记录实际发生了什么
评测时：TrajectoryGrader 判断这条路径是否允许
```

再配合 `FaultInjectingToolRegistry`，可以稳定重现工具失败，而不是等待真实服务偶然出错。

## 1. 为什么只评答案不够

下面两个 Agent 都可能回答“总收入是 200”：

```text
Agent A：受控 SELECT → 复算 → 审核 → 答案
Agent B：读取不该访问的文件 → 猜测 → 答案
```

如果评测只比较答案，两者得分相同。Agent 后端还需要验证：

- 是否经过审批；
- 调用了哪些工具；
- 是否触发危险工具；
- 是否发生重试；
- 在哪里失败；
- 是否生成报告。

## 2. TraceEvent 契约

每条事件包含：

```text
trace_id
task_id
sequence
kind
name
status
timestamp
duration_ms
details
```

`kind` 区分 node、model、tool 和 decision；`status` 区分 started、succeeded、failed、paused 和 reused。

Trace 不保存完整工具行和模型密钥，details 只保留定位问题需要的小型元数据。

## 3. sequence 与断线恢复

每个任务的事件从 1 递增。`TraceRecorder` 重建后会读取现有 JSONL，再继续下一个序号。

这让调用方可以表达“给我 sequence 10 之后的事件”，也能发现事件缺口。它不是全局时间顺序，只在同一 task 内有意义。

## 4. 为什么使用追加式 JSONL

学习型单机项目使用 JSONL 有几个优点：

- 每条事件独立可读；
- 追加操作简单；
- 不需要引入数据库 Schema；
- 测试可以直接重建 Recorder；
- 文件损坏范围比重写完整 JSON 更小。

它不适合高并发、多进程或大规模检索，生产系统通常会使用 OpenTelemetry 和集中式存储。

## 5. 轨迹评测检查什么

`EvaluationCase` 可以声明：

- 期望终态；
- 必须出现的 trace name；
- 禁止成功或复用的工具。

`TrajectoryGrader` 不调用模型，使用确定性规则给出通过或失败理由。因此同一轨迹在 CI 中结果稳定。

## 6. 14 个案例如何分组

`evals/cases.json` 覆盖：

- 正常聚合：总收入、区域、产品和趋势；
- 人工交互：revise、reject；
- 安全：危险删除、外部文件路径；
- 故障：工具失败、可修复审核、重试耗尽；
- 持久化：重启恢复、Artifact 复用。

案例目录描述评测意图；其中关键路径由 Pytest 实现确定性执行，真实模型整体评测仍需要本地模型配置。

## 7. 故障注入为什么不能靠随机

随机让 10% 工具调用失败会产生不稳定测试。`FaultInjectingToolRegistry` 按工具名返回固定的 `injected_failure`：

```text
configured failure tool?
  yes → stable ToolEnvelope error
  no  → delegate to real registry
```

这保留真实输入校验和其他工具行为，同时让目标失败每次都出现。

## 8. Trace 放在哪些节点

Workflow 记录：

- profile 成功或失败；
- plan 模型调用；
- approval 暂停和决策；
- 每个工具调用及 reused；
- review 结果；
- report 生成。

如果 Trace 只包在 API 层，只能看到“请求成功”，无法知道 Agent 内部停在哪个节点。

## 9. Trace 与业务状态的区别

AgentState 决定下一步做什么；Trace 解释过去发生了什么。

不能通过重放 Trace 恢复任务，恢复必须使用 Checkpoint；也不能把所有 Trace 塞进 State，否则每运行一步都会让 checkpoint 变大。

## 10. 测试如何验证

`test_trace_and_evaluation.py` 验证：

1. Recorder 重建后 sequence 连续；
2. 评测案例数量和 Schema 合法；
3. 已知安全轨迹能够通过 grader。

`test_reviewer_loop.py` 和 `test_task_api.py` 则验证真实 Workflow 会产生 profile、plan、approval、tool、review 和 report 事件。

## 阅读顺序

1. `tests/unit/test_trace_and_evaluation.py`
2. `src/datapilot/tracing.py`
3. `src/datapilot/evaluation.py`
4. `evals/cases.json`
5. `src/datapilot/agent/workflow.py` 的 `_record`

## 运行验证

```powershell
uv run pytest tests/unit/test_trace_and_evaluation.py tests/integration/test_reviewer_loop.py -q
```

## 练习

### 练习 1：区分答案评测与轨迹评测

构造一个最终状态正确、但缺少 approval 事件的轨迹，解释为什么它应该失败。

### 练习 2：禁止工具

给 EvaluationCase 增加一个禁止成功的工具名，观察 grader 返回的失败理由。

### 练习 3：故障定位

让 `query_dataset` 注入失败，根据 Trace 判断失败发生在 Planner、Executor 还是 Reviewer。

## 面试表达

> Agent 评测既看结果，也看过程。DataPilot 用追加式 Trace 保存可观察轨迹，用确定性 grader 检查必须节点和禁止工具，并通过故障注入稳定覆盖失败路径。

## 今天没有实现的内容

- OpenTelemetry exporter；
- token 和费用统计；
- Web Trace 可视化；
- 大规模真实模型评测运行器；
- 多进程安全写入。

今天的核心是把“Agent 为什么得到这个结果”变成可测试的数据，而不是只留下最终字符串。
