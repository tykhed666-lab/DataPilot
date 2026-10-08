# Day 14：Trace、故障注入与轨迹评测

普通测试只检查结果，Agent 评测还要检查它怎样得到结果。`TraceRecorder` 以追加式 JSONL 记录节点、模型、工具和人工决策，每个任务有连续 sequence，但不记录完整数据行。

`TrajectoryGrader` 同时检查：

- 最终状态是否符合预期；
- 必须出现的节点或工具；
- 禁止成功执行的危险工具；
- 故障注入后是否走到正确停止条件。

`evals/cases.json` 提供 14 个面试用案例目录。当前 grader 是确定性的，不消耗模型 API；真实模型的整体完成率可在本地配置密钥后单独运行。

阅读 `tests/unit/test_trace_and_evaluation.py`，理解“答案正确”和“轨迹正确”为何是两个独立维度。
