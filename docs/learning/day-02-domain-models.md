# Day 2：领域枚举与 Pydantic 模型

## 今天的目标

把 Agent、API 和 MCP 之间传递的数据先定义成稳定契约。今天不连接数据库，也不调用模型。

## 阅读顺序

1. `src/datapilot/domain/enums.py`
2. `src/datapilot/domain/models.py`
3. `src/datapilot/domain/state.py`
4. `tests/unit/test_domain_models.py`

## 需要理解的四件事

### 1. 为什么使用 `StrEnum`

程序内部需要枚举保证取值有限，HTTP/JSON 又需要普通字符串。`StrEnum` 同时满足这两个要求。

### 2. 为什么设置 `extra="forbid"`

如果模型或调用方拼错字段，系统应该立即报错，而不是悄悄丢弃未知字段。对于可恢复的 Agent，
显式失败比带着错误状态继续运行更安全。

### 3. 字段校验与跨字段校验的区别

`Field` 约束单个字段，例如计划最多 8 步；`model_validator` 检查字段之间的关系，例如同一计划的
`step_id` 不能重复。

### 4. 为什么 `AgentState` 只保存引用

状态会被 LangGraph checkpoint 持久化。完整 DataFrame、图表或 SQL 大结果会让 checkpoint 和模型
上下文迅速膨胀，因此状态中只保存 `artifact_ids`、`result_ref` 等轻量引用。

## 动手练习

1. 给 `TaskStatus` 增加一个临时值并观察序列化结果。
2. 把 `AnalysisPlan.steps` 的 `max_length` 临时改成 2，运行测试观察失败。
3. 恢复修改，再运行完整质量门禁。

## 验收命令

```powershell
uv run pytest tests/unit/test_domain_models.py -q
uv run python scripts/check_quality.py
```

