# Day 4：Tool Contract、Registry 与 Guardrail

## 今天只解决一个问题

Planner 以后会动态选择工具。如果每个工具都有不同调用方式、异常类型和返回结构，Executor 会迅速变成大量 `if/else`。

今天建立一个 Tool Runtime module，对外只有两个主要方法：

```python
registry.list_tools()
registry.invoke(name, arguments)
```

Fake 工具、Dataset 工具以及未来的 MCP 工具，都要通过这个 interface 被发现和调用。

## 五个核心知识点

### 1. ToolDefinition 是注册契约

一个工具需要声明：

- `name`：稳定且唯一的工具名；
- `description`：让 Planner 理解何时使用；
- `input_model`：Pydantic 输入模型；
- `output_model`：Pydantic 输出模型；
- `handler`：真正执行工作的函数。

Registry 会拒绝重复工具名，避免“发现的是一个工具，运行的却是另一个实现”。

### 2. ToolSpec 用于动态发现

`list_tools()` 不会暴露 Python 处理函数，而是将输入和输出模型转换为 JSON Schema。将来 Planner 和 MCP Client 都可以用相同信息理解工具能力。

### 3. ToolEnvelope 统一成功与失败

调用者永远获得同一种外壳：

```text
ToolEnvelope
├── tool_name
├── ok
├── output
└── error
    ├── code
    ├── message
    └── details
```

当前错误码：

| 错误码 | 含义 |
|---|---|
| `tool_not_found` | 工具未注册 |
| `invalid_tool_input` | 输入不符合 Pydantic 契约 |
| `tool_execution_failed` | 处理函数执行失败 |
| `invalid_tool_output` | 输出不符合声明的契约 |

处理函数异常不会把 traceback、绝对路径或内部异常消息放入公开 Envelope。

### 4. Guardrail 包围工具执行

调用顺序是：

```text
查找工具
→ Input Model 校验
→ Handler 执行
→ Output Model 校验
→ ToolEnvelope
```

输入失败时 Handler 不会运行；输出失败时错误结果不会继续进入 Executor。

### 5. Adapter 让真实工具进入同一 seam

`dataset_tools.py` 是 Dataset module 到 Tool Runtime seam 的 adapter。它负责：

- 声明 `profile_dataset` 和 `query_dataset` 的工具契约；
- 将相对路径解析到指定数据根目录；
- 拒绝绝对路径和 `..` 路径穿越；
- 调用 Day 2、Day 3 已完成的 Dataset interface。

Dataset 的实现没有为了 Tool Runtime 而改写，Fake 工具和真实工具也不需要两套 Executor 逻辑。

## 推荐阅读顺序

1. `tests/unit/test_tool_runtime.py`
2. `src/datapilot/tool_runtime.py` 中的四个公开类型
3. `ToolRegistry.list_tools`
4. `ToolRegistry.invoke`
5. `tests/unit/test_dataset_tools.py`
6. `src/datapilot/dataset_tools.py`

## 运行示例

在 PyCharm Python Console 中运行：

```python
from pathlib import Path

from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.tool_runtime import ToolRegistry

registry = ToolRegistry(dataset_tool_definitions(Path("data")))
print([tool.name for tool in registry.list_tools()])

result = registry.invoke(
    "query_dataset",
    {
        "relative_path": "samples/sales_demo.csv",
        "sql": """
            SELECT region, SUM(revenue) AS total_revenue
            FROM dataset
            GROUP BY region
            ORDER BY total_revenue DESC
        """,
    },
)
print(result.model_dump_json(indent=2))
```

## 动手练习

1. 给 Fake `add_numbers` 工具传入字符串，观察 `invalid_tool_input`。
2. 调用一个不存在的工具，观察 `tool_not_found`。
3. 把真实工具路径改成 `../secret.csv`，确认 Handler 不会运行。
4. 阅读输出校验测试，思考为什么不能只信任 Handler 的类型注解。

思考题：如果没有 Tool Runtime module，Planner、Executor、MCP Server 和测试分别要重复哪些逻辑？

## 验收命令

```powershell
uv run pytest tests/unit/test_tool_runtime.py tests/unit/test_dataset_tools.py -q
uv run python scripts/check_quality.py
```

理解今天的代码后，再进入 Day 5 的 Fake LLM、真实模型 Adapter 与结构化输出。
