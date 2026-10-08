"""把 Agent 图、上传目录和产物存储组合成应用服务。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from datapilot.agent import (
    AgentState,
    AgentWorkflow,
    ApprovalRequest,
    ArtifactNotFoundError,
    ArtifactStore,
    HybridReviewer,
    Planner,
    create_initial_state,
    open_sqlite_checkpointer,
)
from datapilot.config import Settings
from datapilot.contracts import ContractModel
from datapilot.dataset_tools import dataset_tool_definitions
from datapilot.model import OpenAICompatibleModel
from datapilot.tool_runtime import ToolRegistry
from datapilot.tracing import TraceEvent, TraceRecorder


class TaskNotFoundError(KeyError):
    """请求的任务不存在。"""


class DatasetUpload(ContractModel):
    dataset_id: str
    file_name: str
    relative_path: str
    size_bytes: int = Field(ge=1)
    sha256: str


class TaskService:
    """应用层唯一入口；API 与 CLI 不直接了解 LangGraph 细节。"""

    def __init__(
        self,
        *,
        workflow: AgentWorkflow,
        data_root: str | Path,
        artifacts: ArtifactStore,
        trace: TraceRecorder,
        max_upload_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self._workflow = workflow
        self._data_root = Path(data_root).resolve()
        self._artifacts = artifacts
        self._trace = trace
        self._max_upload_bytes = max_upload_bytes

    def upload_dataset(self, file_name: str, content: bytes) -> DatasetUpload:
        suffix = Path(file_name).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise ValueError("only .csv and .xlsx datasets are supported")
        if not content:
            raise ValueError("dataset cannot be empty")
        if len(content) > self._max_upload_bytes:
            raise ValueError("dataset exceeds upload size limit")
        digest = sha256(content).hexdigest()
        relative_path = Path("uploads") / f"{digest}{suffix}"
        destination = self._data_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file():
            temporary = destination.with_name(f".{digest}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(content)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return DatasetUpload(
            dataset_id=digest,
            file_name=Path(file_name).name,
            relative_path=relative_path.as_posix(),
            size_bytes=len(content),
            sha256=digest,
        )

    def create_task(self, *, dataset_id: str, question: str) -> AgentState:
        relative_path = self._resolve_dataset(dataset_id)
        task_id = uuid4().hex
        initial = create_initial_state(
            task_id=task_id,
            dataset_id=relative_path,
            question=question,
        )
        return self._workflow.start(initial, dataset_relative_path=relative_path)

    def approve_task(self, task_id: str, approval: ApprovalRequest) -> AgentState:
        current = self.get_task(task_id)
        return self._workflow.resume(
            task_id=task_id,
            dataset_relative_path=current["dataset_id"],
            approval=approval,
        )

    def get_task(self, task_id: str) -> AgentState:
        try:
            return self._workflow.get_state(task_id)
        except KeyError:
            raise TaskNotFoundError(task_id) from None

    def get_trace(self, task_id: str) -> list[TraceEvent]:
        self.get_task(task_id)
        return self._trace.read(task_id)

    def load_artifact(self, task_id: str, artifact_id: str) -> tuple[bytes, str]:
        state = self.get_task(task_id)
        reference = next(
            (item for item in state["artifacts"] if item.artifact_id == artifact_id),
            None,
        )
        if reference is None:
            raise ArtifactNotFoundError(artifact_id)
        return self._artifacts.load_bytes(reference)

    def _resolve_dataset(self, dataset_id: str) -> str:
        if len(dataset_id) != 64 or any(
            character not in "0123456789abcdef" for character in dataset_id
        ):
            raise ValueError("invalid dataset_id")
        uploads = self._data_root / "uploads"
        matches = [
            path for path in uploads.glob(f"{dataset_id}.*") if path.suffix in {".csv", ".xlsx"}
        ]
        if len(matches) != 1:
            raise FileNotFoundError(dataset_id)
        return matches[0].relative_to(self._data_root).as_posix()


@contextmanager
def open_default_task_service(settings: Settings) -> Iterator[TaskService]:
    """组装生产配置，并统一管理 SQLite Checkpointer 生命周期。"""

    model = OpenAICompatibleModel.from_settings(settings)
    data_root = settings.data_root.resolve()
    tools = ToolRegistry(dataset_tool_definitions(data_root))
    artifacts = ArtifactStore(data_root / "artifacts")
    trace = TraceRecorder(data_root / "traces")
    with open_sqlite_checkpointer(settings.checkpoint_db) as checkpointer:
        reviewer = HybridReviewer(
            model=model,
            tools=tools,
            artifacts=artifacts,
            max_evidence_chars=settings.max_tool_result_chars,
        )
        workflow = AgentWorkflow(
            planner=Planner(model=model, max_steps=settings.max_plan_steps),
            tools=tools,
            artifacts=artifacts,
            reviewer=reviewer,
            max_retries=settings.max_agent_retries,
            trace=trace,
            checkpointer=checkpointer,
        )
        yield TaskService(
            workflow=workflow,
            data_root=data_root,
            artifacts=artifacts,
            trace=trace,
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        )
