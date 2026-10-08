# Day 11：确定性验证、证据压缩与语义 Reviewer

## 今天完成了什么

Day 10 的 Executor 能可靠执行计划，但“工具成功”不等于“答案正确”。今天加入混合 Reviewer，把审核拆成两个职责不同的阶段：

```text
ToolEnvelope
  → 确定性检查：结果是否真实、可复算
  → Evidence Digest：结果如何安全进入模型上下文
  → 语义审核：证据是否回答用户问题
  → GroundedReview：决定 + 答案 + 关键发现 + 注意事项
```

这里最重要的思想是：程序负责它擅长的精确验证，模型负责它擅长的语义判断。二者不能互相冒充。

## 1. 为什么“调用成功”不等于“任务成功”

假设用户问“哪个区域收入最高，原因是什么？”，Planner 却只生成：

```sql
SELECT SUM(revenue) FROM dataset
```

SQL 合法、工具执行成功、数字也可以复算，但它没有比较区域，更没有解释原因。如果系统只检查 `ok=true`，就会把错误任务当成成功任务。

因此 Reviewer 至少要回答两个不同问题：

1. Artifact 中的数据是否与重新执行得到的数据一致？
2. 这些数据是否足以完成 `final_deliverable`？

第一个问题是确定性的；第二个问题需要语义理解。

## 2. 确定性检查做什么

`HybridReviewer` 首先逐项验证：

- Artifact 数量与计划步骤数量一致；
- Artifact 文件存在并能解析成 `ToolEnvelope`；
- 保存的 `tool_name` 与计划一致；
- 工具结果必须是成功状态；
- `query_dataset` 使用相同参数重新执行后，输出必须完全一致。

如果任何一项失败，Reviewer 直接返回失败，不调用模型。这样可以避免让模型判断一个已经被证明不可信的结果。

## 3. 为什么不能只把 ArtifactRef.summary 给模型

`ArtifactRef.summary` 的职责是让 AgentState 保持轻量，例如：

```text
step=step-1 tool=query_dataset outcome=ok
```

它适合 checkpoint 和时间线，却不包含数字。模型如果只看到这个摘要，就无法判断证据是否回答问题。

但另一个极端——把完整 1000 行结果全部放进 Prompt——也会产生问题：

- token 成本不可控；
- 长上下文稀释关键证据；
- 数据中可能包含提示词注入文本；
- checkpoint 与模型上下文职责混乱。

因此今天加入 `EvidencePackager`，专门在“磁盘 Artifact”和“模型 Prompt”之间建立 seam。

## 4. Evidence Digest 包含什么

每个 `EvidenceDigest` 包含：

```text
artifact_id
step_id
tool_name
columns
column_count
columns_truncated
row_count
truncated
sample_rows
output_summary
```

其中：

- `columns` 告诉模型数据表达什么；
- `column_count` 和 `columns_truncated` 让超宽表可以只展示部分列名，同时明确原始列数；
- `row_count` 告诉模型结果规模；
- `truncated` 防止模型误以为样本是完整数据；
- `sample_rows` 对聚合结果通常就是完整的一两行；
- `artifact_id` 让答案可以追溯回原始证据；
- `output_summary` 保存非表格工具的小型结构化输出。

字符串、列表、字典、列名和样本行都有上限。预算针对最终 XML 转义后的 Prompt 片段计算，而不是转义前的 JSON，因为 `&`、`<`、`>` 转义后会膨胀。超过预算时依次减少样本行、非表格摘要和展示列名，必要时改用紧凑 JSON；总列数、行数和截断标记继续保留。

## 5. 为什么不修改 ArtifactRef.summary

如果把样本数据直接塞进 `ArtifactRef.summary`，它会进入 AgentState 和每个 checkpoint。随着步骤和重试增加，状态会持续膨胀。

当前设计保持三个层次：

```text
AgentState       小型引用和决策状态
Artifact Store   完整、可复算的工具结果
Evidence Digest  按需构造、有预算的模型上下文
```

这样既让模型看到真实证据，也不破坏 Day 9～10 建立的状态边界。

## 6. GroundedReview

通过审核时，模型必须返回：

- `answer`：直接回答用户问题；
- `key_findings`：关键发现；
- `caveats`：数据限制或解释边界；
- `evidence_artifact_ids`：由应用覆盖为真实产物 ID；
- 原有的 `passed`、`score`、`issues` 和 `retryable`。

如果 `passed=true` 却没有 `answer`，Pydantic 校验会拒绝该模型输出。失败审核则不能发布答案。

## 7. Prompt 注入边界

计划和证据都放在明确的 XML 标签中，并在系统提示里声明它们是不可信数据。这里的 XML 不是安全沙箱；真正的安全来自：

- 工具白名单；
- SQL AST Guardrail；
- 结构化输出；
- Evidence 字符预算；
- 确定性复算；
- 失败时不执行新的工具。

## 8. 测试如何证明它有效

`test_reviewer.py` 有两条关键路径：

1. 正常聚合结果中，模型 Prompt 必须真的包含列名、`row_count` 和数值 200。
2. Artifact 被篡改成 999 时，确定性层直接拒绝，并验证模型一次都没有调用。

`test_evidence.py` 使用大量长字符串、XML 特殊字符和 500 列宽表制造超预算结果，验证转义后的最终文本仍在预算内，反转义后仍是合法 JSON，并保留总列数与明确的列截断标记。

Reviewer 级测试还会检查 Evidence 没有被二次转义：`&lt;` 不能再次变成 `&amp;lt;`。

## 阅读顺序

1. `tests/unit/test_reviewer.py`
2. `tests/unit/test_evidence.py`
3. `src/datapilot/agent/evidence.py`
4. `src/datapilot/agent/reviewer.py`
5. `src/datapilot/agent/workflow.py` 的 `_review_node`

## 运行验证

```powershell
uv run pytest tests/unit/test_evidence.py tests/unit/test_reviewer.py -q
```

## 练习

### 练习 1：观察证据 Prompt

在 Reviewer 测试中打印 `model.calls[0].prompt.user`，区分计划、真实证据和确定性验证标记。

### 练习 2：制造错误计划

用户问题保持“哪个区域收入最高”，但让计划只查询总收入。思考确定性层为什么会通过、语义层为什么应该拒绝。

### 练习 3：调整预算

把 `max_prompt_chars` 从 1200 改为 3000，观察保留的样本行数量变化，并解释为什么列名和行数不应优先删除。

## 面试表达

不要说“Reviewer 用 LLM 检查数字”。更准确的说法是：

> DataPilot 先用同一受控工具复算结果，再把有预算、可追溯的证据摘要交给模型判断任务完成度，并要求通过审核时输出有证据的直接答案。

## 今天没有实现的内容

- 多模型交叉审核；
- 基于统计容差的浮点比较；
- 对图片或图表的视觉审核；
- 事实引用的逐句自动对齐。

今天的核心不是“再调用一次模型”，而是设计一条让模型真正看见证据、同时保持状态和上下文受控的审核路径。
