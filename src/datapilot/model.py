"""结构化模型 seam 及其离线 Fake Adapter。"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr, ValidationError

from datapilot.config import Settings
from datapilot.contracts import ContractModel

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class ModelPrompt(ContractModel):
    """一次结构化模型调用所需的最小提示词。"""

    system: str = Field(min_length=1, max_length=20_000)
    user: str = Field(min_length=1, max_length=100_000)


class StructuredModel(Protocol):
    """Fake 与真实模型共同满足的 interface。"""

    def generate_structured(
        self,
        prompt: ModelPrompt,
        output_model: type[StructuredOutput],
    ) -> StructuredOutput: ...


@dataclass(frozen=True, slots=True)
class ModelCall:
    """Fake Adapter 记录的一次调用，便于轨迹测试。"""

    prompt: ModelPrompt
    output_model_name: str


class FakeModelExhaustedError(RuntimeError):
    """测试预设响应数量少于实际模型调用次数。"""


class ModelOutputValidationError(ValueError):
    """模型响应无法转换成请求的 Pydantic 类型。"""


class ModelConfigurationError(ValueError):
    """真实模型 Adapter 缺少 Key、Base URL 或模型名称。"""


class FakeStructuredModel:
    """不访问网络、按顺序返回预设结果的模型 Adapter。"""

    def __init__(self, responses: Iterable[object]) -> None:
        self._responses = deque(responses)
        self.calls: list[ModelCall] = []

    def generate_structured(
        self,
        prompt: ModelPrompt,
        output_model: type[StructuredOutput],
    ) -> StructuredOutput:
        if not self._responses:
            raise FakeModelExhaustedError("no fake model response remains")

        self.calls.append(
            ModelCall(
                prompt=prompt,
                output_model_name=output_model.__name__,
            )
        )
        try:
            return output_model.model_validate(self._responses.popleft())
        except ValidationError:
            raise ModelOutputValidationError(
                f"model output failed {output_model.__name__} validation"
            ) from None


class OpenAICompatibleModel:
    """通过 OpenAI-compatible Chat Completions 调用真实模型。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60,
        max_retries: int = 2,
    ) -> None:
        if not api_key.strip() or not base_url.strip() or not model.strip():
            raise ModelConfigurationError(
                "OPENAI_API_KEY, OPENAI_BASE_URL, and AGENT_MODEL are required"
            )
        self.model_name = model.strip()
        self._model = ChatOpenAI(
            model=self.model_name,
            api_key=SecretStr(api_key),
            base_url=base_url,
            temperature=0,
            timeout=timeout,
            max_retries=max_retries,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleModel:
        return cls(
            api_key=settings.openai_api_key or "",
            base_url=settings.openai_base_url or "",
            model=settings.agent_model or "",
        )

    def generate_structured(
        self,
        prompt: ModelPrompt,
        output_model: type[StructuredOutput],
    ) -> StructuredOutput:
        structured_model = self._model.with_structured_output(
            output_model,
            method="function_calling",
        )
        raw_output = structured_model.invoke(
            [
                SystemMessage(content=prompt.system),
                HumanMessage(content=prompt.user),
            ]
        )
        if isinstance(raw_output, output_model):
            return raw_output
        try:
            return output_model.model_validate(raw_output)
        except ValidationError:
            raise ModelOutputValidationError(
                f"model output failed {output_model.__name__} validation"
            ) from None
