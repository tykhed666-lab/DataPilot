# Day 12：有限自我修正

Reviewer 返回 `retryable=true` 时，图会清理本轮执行引用，把 correction 交回 Planner，并再次停在人工审批点。`retry_count` 的预算默认是 2。

关键规则：

- 每一版计划都要重新审批，Agent 不会自行扩大权限。
- 可修复的语义问题允许重规划；安全拒绝与不可修复错误直接结束。
- 第三次审核仍失败时返回 `review_failed:retry_exhausted`，避免无限循环和失控费用。

阅读 `tests/integration/test_reviewer_loop.py`，沿着 v1、v2、v3 三版计划观察状态、版本号和重试计数。
