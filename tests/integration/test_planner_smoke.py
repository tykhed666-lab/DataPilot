import os

import pytest

from datapilot.agent.planner import Planner, PlannerRequest
from datapilot.config import get_settings
from datapilot.dataset import profile_dataset
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import OpenAICompatibleModel
from datapilot.tool_runtime import ToolRegistry


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL_TESTS") != "1",
    reason="set RUN_LIVE_MODEL_TESTS=1 to spend one real model request",
)
def test_real_model_generates_a_valid_analysis_plan() -> None:
    tools = ToolRegistry(dataset_tool_definitions("data")).list_tools()
    planner = Planner(
        model=OpenAICompatibleModel.from_settings(get_settings()),
        max_steps=4,
    )

    plan = planner.create_plan(
        PlannerRequest(
            question="哪个区域的总收入最高？",
            dataset_relative_path="samples/sales_demo.csv",
            profile=profile_dataset("data/samples/sales_demo.csv"),
            tools=tools,
        )
    )

    known_tools = {tool.name for tool in tools}
    assert 1 <= len(plan.steps) <= 4
    assert all(step.tool_name in known_tools for step in plan.steps)
    assert plan.question == "哪个区域的总收入最高？"
