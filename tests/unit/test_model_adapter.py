import pytest

from datapilot.contracts import ContractModel
from datapilot.model import (
    FakeStructuredModel,
    ModelConfigurationError,
    ModelOutputValidationError,
    ModelPrompt,
    OpenAICompatibleModel,
)


class SmokeAnswer(ContractModel):
    answer: str
    confidence: float


def test_fake_model_returns_a_validated_structured_response() -> None:
    model = FakeStructuredModel(responses=[{"answer": "模型接口正常", "confidence": 0.95}])
    prompt = ModelPrompt(
        system="你是一个测试助手。",
        user="返回结构化结果。",
    )

    result = model.generate_structured(prompt, SmokeAnswer)

    assert result == SmokeAnswer(answer="模型接口正常", confidence=0.95)
    assert model.calls[0].prompt == prompt
    assert model.calls[0].output_model_name == "SmokeAnswer"


def test_fake_model_normalizes_invalid_structured_output() -> None:
    model = FakeStructuredModel(responses=[{"answer": "缺少 confidence"}])
    prompt = ModelPrompt(system="测试", user="返回结构化结果")

    with pytest.raises(ModelOutputValidationError, match="SmokeAnswer"):
        model.generate_structured(prompt, SmokeAnswer)


def test_real_model_rejects_incomplete_configuration_before_network_access() -> None:
    with pytest.raises(ModelConfigurationError, match="AGENT_MODEL"):
        OpenAICompatibleModel(
            api_key="",
            base_url="https://provider.example.com/v1",
            model="",
        )
