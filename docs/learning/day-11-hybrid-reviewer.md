# Day 11：混合 Reviewer

## 今天解决什么

只让 LLM 判断数字是否正确并不可靠。`HybridReviewer` 先读取 Executor 保存的 `ToolEnvelope`，再用相同的受控 SQL 复算；只有确定性检查通过，才让模型判断“证据是否回答了问题”。

## 阅读顺序

1. `src/datapilot/agent/reviewer.py`
2. `tests/unit/test_reviewer.py`
3. `src/datapilot/agent/workflow.py` 的 `_review_node`

## 面试重点

- 数值正确性用程序验证，语义充分性才交给模型。
- Reviewer 只看到计划和证据摘要，完整数据仍留在 Artifact Store。
- 被篡改的结果会在模型调用前失败，因此既省 token 又更可信。

## 练习

把单元测试中的产物总收入从 200 改成 201，观察 Reviewer 如何在不调用 Fake Model 的情况下拒绝。
