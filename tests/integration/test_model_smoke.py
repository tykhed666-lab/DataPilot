import os
from typing import Literal

import pytest

from datapilot.config import get_settings
from datapilot.contracts import ContractModel
from datapilot.model import ModelPrompt, OpenAICompatibleModel


class LiveSmokeResult(ContractModel):
    status: Literal["ok"]
    message: str


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL_TESTS") != "1",
    reason="set RUN_LIVE_MODEL_TESTS=1 to spend one real model request",
)
def test_openai_compatible_model_returns_structured_output() -> None:
    model = OpenAICompatibleModel.from_settings(get_settings())

    result = model.generate_structured(
        ModelPrompt(
            system="你是模型接口测试助手，严格返回请求的结构。",
            user="将 status 设置为 ok，并用一句中文说明接口正常。",
        ),
        LiveSmokeResult,
    )

    assert result.status == "ok"
    assert result.message.strip()
