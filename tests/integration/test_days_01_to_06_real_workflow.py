"""用真实模型串联 Day 1 到 Day 6，作为进入 LangGraph 前的综合复习。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from datapilot.agent import Planner, PlannerRequest, create_initial_state
from datapilot.config import get_settings
from datapilot.contracts import TaskStatus
from datapilot.dataset import profile_dataset, query_dataset
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import OpenAICompatibleModel
from datapilot.tool_runtime import ToolEnvelope, ToolRegistry

DATA_ROOT = Path("data")
DATASET_RELATIVE_PATH = "samples/sales_demo.csv"
DATASET_PATH = DATA_ROOT / DATASET_RELATIVE_PATH


def show_stage(day: str, title: str, content: str) -> None:
    """为学习运行输出清晰分段；断言仍负责判断测试成败。"""

    print(f"\n{'=' * 18} {day} · {title} {'=' * 18}")
    print(content)


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL_TESTS") != "1",
    reason="set RUN_LIVE_MODEL_TESTS=1 to run the real-model learning workflow",
)
def test_days_01_to_06_with_a_real_model() -> None:
    question = "哪个区域的总收入最高？请给出各区域总收入作为依据。"

    # Day 1：创建未来会交给 LangGraph 的小型 AgentState。
    state = create_initial_state(
        task_id="learning-days-01-to-06",
        dataset_id="sales-demo",
        question=question,
    )
    assert state["status"] is TaskStatus.CREATED
    show_stage("Day 1", "AgentState", str(state))

    # Day 2：读取 CSV，生成不包含完整 DataFrame 的统一画像。
    state["status"] = TaskStatus.PROFILING
    profile = profile_dataset(DATASET_PATH)
    assert profile.row_count == 5
    assert {column.name for column in profile.columns} >= {"region", "revenue"}
    show_stage("Day 2", "Dataset Profile", profile.model_dump_json(indent=2))

    # Day 3：直接调用受控 DuckDB 查询，建立一个确定性的正确答案基线。
    baseline = query_dataset(
        DATASET_PATH,
        """
        SELECT region, SUM(revenue) AS total_revenue
        FROM dataset
        GROUP BY region
        ORDER BY total_revenue DESC
        """,
        max_rows=10,
    )
    assert baseline.rows[0] == {"region": "华东", "total_revenue": 1960.0}
    show_stage("Day 3", "Safe DuckDB Baseline", baseline.model_dump_json(indent=2))

    # Day 4：将真实 Dataset 能力注册成统一、可发现、带 Guardrail 的工具。
    registry = ToolRegistry(dataset_tool_definitions(DATA_ROOT))
    tools = registry.list_tools()
    assert {tool.name for tool in tools} == {"profile_dataset", "query_dataset"}
    show_stage(
        "Day 4",
        "Discovered Tools",
        "\n".join(f"- {tool.name}: {tool.description}" for tool in tools),
    )

    # Day 5：这里明确使用真实 Adapter，而不是 FakeStructuredModel。
    model = OpenAICompatibleModel.from_settings(get_settings())
    show_stage("Day 5", "Real Model Adapter", f"model={model.model_name}")

    # Day 6：真实模型根据 Profile 与 ToolSpec 动态生成经过 Guardrail 的计划。
    state["status"] = TaskStatus.PLANNING
    planner = Planner(model=model, max_steps=4)
    plan = planner.create_plan(
        PlannerRequest(
            question=question,
            dataset_relative_path=DATASET_RELATIVE_PATH,
            profile=profile,
            tools=tools,
        )
    )
    state["plan"] = plan
    state["status"] = TaskStatus.AWAITING_APPROVAL
    assert 1 <= len(plan.steps) <= 4
    assert all(step.tool_name in {tool.name for tool in tools} for step in plan.steps)
    show_stage("Day 6", "Real Model AnalysisPlan", plan.model_dump_json(indent=2))

    # 预演未来 Executor：仍然只通过 Day 4 的 invoke interface 调用工具。
    state["status"] = TaskStatus.EXECUTING
    results: list[ToolEnvelope] = []
    for step in plan.steps:
        result = registry.invoke(step.tool_name, step.arguments)
        assert result.ok, result.error
        results.append(result)
        state["tool_result_summaries"].append(f"{step.step_id}:{step.tool_name}:ok")
        show_stage(
            "Review",
            f"Executed {step.step_id} · {step.tool_name}",
            result.model_dump_json(indent=2),
        )

    assert results
    assert len(state["tool_result_summaries"]) == len(plan.steps)
    state["status"] = TaskStatus.COMPLETED
    show_stage(
        "Complete",
        "Days 01-06 Connected",
        f"status={state['status'].value}\n"
        f"executed_steps={len(results)}\n"
        f"baseline_top_region={baseline.rows[0]['region']}",
    )
