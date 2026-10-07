# Day 5：Fake LLM、真实模型 Adapter 与结构化输出

## 今天只解决一个问题

Planner 和 Reviewer 以后都需要调用模型，但业务代码不应该知道模型来自 DashScope、OpenAI 还是测试数据。

今天建立真正有两个 Adapter 的模型 seam：

```python
generate_structured(prompt, output_model) -> output_model instance
```

- `FakeStructuredModel`：离线、确定性、不会产生费用；
- `OpenAICompatibleModel`：通过 OpenAI-compatible Chat Completions 调用真实模型。

## 五个核心知识点

### 1. 为什么现在才引入模型 seam

前四天只有“未来可能调用模型”的设想，没有第二个实现。今天 Fake 与真实模型同时存在，变化已经真实发生，因此 seam 才开始产生价值。

Planner 和 Reviewer 以后只依赖 `StructuredModel` interface，不依赖 `ChatOpenAI`。

### 2. Fake LLM 不是随便写死一个字符串

Fake Adapter 会：

- 按顺序消费预设响应；
- 使用调用者指定的 Pydantic 模型校验响应；
- 记录 Prompt 和输出模型名称；
- 响应耗尽时明确失败。

因此测试可以验证模型调用次数、Prompt 和结构化结果，而不访问网络。

### 3. Structured Output 仍然需要本地校验

调用者把 Pydantic 类型传给 Adapter。真实 Adapter 使用 function calling 请求结构化结果，Fake Adapter 直接验证预设对象。

无论提供商是否声称支持严格结构化输出，应用最终仍以自己的 Pydantic 模型为准。格式不合法时统一抛出 `ModelOutputValidationError`。

[官方 OpenAI Structured Outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs)将其定义为由 JSON Schema 约束的模型响应，并建议使用 SDK 的类型/schema helper，避免代码类型和 JSON Schema 分离。DataPilot 使用同一 Pydantic 类生成 schema 并校验结果。

### 4. OpenAI-compatible 不等于绑定 OpenAI

真实 Adapter 的配置只有：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `AGENT_MODEL`

当前本地配置使用 DashScope 和 `qwen3.5-flash`。以后更换兼容提供商时，Planner 不需要修改。

项目采用 `function_calling` 结构化方式，因为它已经在你的 ResearchKB 和当前 DashScope 模型上完成真实验证。不同兼容提供商对 `json_schema` 的支持程度可能不同，因此不盲目假设所有端点都支持相同特性。

### 5. CI 不能调用真实模型

`tests/integration/test_model_smoke.py` 默认跳过。只有显式设置下面的变量才会产生一次真实请求：

```powershell
$env:RUN_LIVE_MODEL_TESTS = "1"
uv run pytest tests/integration/test_model_smoke.py -q
```

普通质量门禁只运行 Fake，结果稳定且不消耗额度。

## 推荐阅读顺序

1. `tests/unit/test_model_adapter.py`
2. `src/datapilot/model.py` 中的 `ModelPrompt` 和 `StructuredModel`
3. `FakeStructuredModel`
4. `OpenAICompatibleModel`
5. `tests/integration/test_model_smoke.py`

第一次阅读可以暂时忽略 `Protocol` 和 `TypeVar` 的语法，先理解两种 Adapter 为什么能通过同一个方法返回指定类型。

## 运行示例

在 PyCharm Python Console 中运行：

```python
from datapilot.contracts import ContractModel
from datapilot.model import FakeStructuredModel, ModelPrompt


class DemoAnswer(ContractModel):
    answer: str
    confidence: float


model = FakeStructuredModel(responses=[{"answer": "Fake 模型正常", "confidence": 1.0}])
result = model.generate_structured(
    ModelPrompt(system="你是测试助手", user="返回结果"),
    DemoAnswer,
)
print(result)
print(model.calls)
```

## 动手练习

1. 再准备一个 Fake 响应，连续调用两次并观察响应顺序。
2. 删除 `confidence`，观察 `ModelOutputValidationError`。
3. 第三次调用耗尽的 Fake，观察 `FakeModelExhaustedError`。
4. 解释为什么单元测试不能依赖真实模型，即使 temperature 设置为 0。

## 验收命令

默认离线验收：

```powershell
uv run pytest tests/unit/test_model_adapter.py -q
uv run python scripts/check_quality.py
```

真实模型测试已经由项目实施过程执行成功，不需要反复运行和消耗额度。

理解今天的代码后，再进入 Day 6 的 Planner Prompt、AnalysisPlan 校验与计划预算。
