"""最小端到端演示入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datapilot.agent import AgentState, ApprovalDecision, ApprovalRequest
from datapilot.config import get_settings
from datapilot.service import open_default_task_service


def run() -> None:
    parser = argparse.ArgumentParser(description="Run a DataPilot analysis demo")
    parser.add_argument("dataset", type=Path, help="CSV or XLSX dataset")
    parser.add_argument("question", help="natural-language analysis question")
    parser.add_argument("--auto-approve", action="store_true")
    arguments = parser.parse_args()

    settings = get_settings()
    with open_default_task_service(settings) as service:
        uploaded = service.upload_dataset(
            arguments.dataset.name,
            arguments.dataset.read_bytes(),
        )
        state = service.create_task(
            dataset_id=uploaded.dataset_id,
            question=arguments.question,
        )
        print(json.dumps(_summary(state), ensure_ascii=False, indent=2))
        if arguments.auto_approve:
            state = service.approve_task(
                state["task_id"],
                ApprovalRequest(
                    decision=ApprovalDecision.APPROVE,
                    plan_version=state["plan_version"],
                ),
            )
            print(json.dumps(_summary(state), ensure_ascii=False, indent=2))


def _summary(state: AgentState) -> dict[str, object]:
    return {
        "task_id": state["task_id"],
        "status": state["status"],
        "plan_version": state["plan_version"],
        "retry_count": state["retry_count"],
        "artifacts": [item.model_dump(mode="json") for item in state["artifacts"]],
        "error": state["error"],
    }
