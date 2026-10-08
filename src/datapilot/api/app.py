"""DataPilot HTTP API：上传、任务、审批、轨迹与产物。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from datapilot import __version__
from datapilot.agent import ApprovalRequest, ArtifactNotFoundError, StalePlanVersionError
from datapilot.config import get_settings
from datapilot.contracts import ContractModel
from datapilot.service import TaskNotFoundError, TaskService, open_default_task_service

STATIC_ROOT = Path(__file__).with_name("static")


class CreateTaskRequest(ContractModel):
    dataset_id: str = Field(min_length=64, max_length=64)
    question: str = Field(min_length=1, max_length=4000)


def create_app(service: TaskService | None = None) -> FastAPI:
    """构建应用；测试可注入离线 TaskService。"""

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            application.state.task_service = service
            yield
            return
        configured = all([settings.openai_api_key, settings.openai_base_url, settings.agent_model])
        if not configured:
            application.state.task_service = None
            yield
            return
        with open_default_task_service(settings) as default_service:
            application.state.task_service = default_service
            yield

    application = FastAPI(
        title="DataPilot Agent Backend",
        version=__version__,
        description="Durable Planner-Executor-Reviewer data-analysis agent.",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @application.get("/", include_in_schema=False)
    async def workbench() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")

    @application.exception_handler(TaskNotFoundError)
    async def task_not_found(request: Request, error: TaskNotFoundError) -> JSONResponse:
        return _error(request, 404, "not_found", "task_not_found", "task does not exist")

    @application.exception_handler(ArtifactNotFoundError)
    async def artifact_not_found(request: Request, error: ArtifactNotFoundError) -> JSONResponse:
        return _error(request, 404, "not_found", "artifact_not_found", "artifact does not exist")

    @application.exception_handler(StalePlanVersionError)
    async def stale_plan(request: Request, error: StalePlanVersionError) -> JSONResponse:
        return _error(request, 409, "conflict", "stale_plan_version", str(error))

    @application.exception_handler(FileNotFoundError)
    async def dataset_not_found(request: Request, error: FileNotFoundError) -> JSONResponse:
        return _error(request, 404, "not_found", "dataset_not_found", "dataset does not exist")

    @application.exception_handler(ValueError)
    async def invalid_request(request: Request, error: ValueError) -> JSONResponse:
        return _error(request, 400, "validation_error", "invalid_request", str(error))

    @application.exception_handler(RequestValidationError)
    async def request_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        return _error(
            request,
            422,
            "validation_error",
            "request_validation_failed",
            "request failed validation",
            details=[
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors()
            ],
        )

    @application.exception_handler(RuntimeError)
    async def service_unavailable(request: Request, error: RuntimeError) -> JSONResponse:
        return _error(request, 503, "service_unavailable", "model_not_configured", str(error))

    @application.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "datapilot",
            "version": __version__,
            "focus": "agent-backend",
        }

    @application.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, str]:
        return {"status": "ready", "environment": settings.app_env}

    @application.post("/api/datasets", status_code=201, tags=["datasets"])
    async def upload_dataset(request: Request, file: Annotated[UploadFile, File()]) -> object:
        active = _service(request)
        content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            return _error(
                request,
                413,
                "validation_error",
                "upload_too_large",
                "dataset exceeds upload size limit",
            )
        return active.upload_dataset(file.filename or "dataset.csv", content)

    @application.post("/api/tasks", status_code=201, tags=["tasks"])
    async def create_task(request: Request, payload: CreateTaskRequest) -> object:
        return _service(request).create_task(
            dataset_id=payload.dataset_id,
            question=payload.question,
        )

    @application.get("/api/tasks/{task_id}", tags=["tasks"])
    async def get_task(request: Request, task_id: str) -> object:
        return _service(request).get_task(task_id)

    @application.post("/api/tasks/{task_id}/approval", tags=["tasks"])
    async def approve_task(request: Request, task_id: str, payload: ApprovalRequest) -> object:
        return _service(request).approve_task(task_id, payload)

    @application.get("/api/tasks/{task_id}/trace", tags=["observability"])
    async def get_trace(request: Request, task_id: str) -> object:
        return _service(request).get_trace(task_id)

    @application.get("/api/tasks/{task_id}/artifacts/{artifact_id}", tags=["artifacts"])
    async def get_artifact(request: Request, task_id: str, artifact_id: str) -> Response:
        content, media_type = _service(request).load_artifact(task_id, artifact_id)
        return Response(content=content, media_type=media_type)

    return application


def _service(request: Request) -> TaskService:
    active = getattr(request.app.state, "task_service", None)
    if active is None:
        raise RuntimeError(
            "model configuration is incomplete; configure .env before creating tasks"
        )
    return active


def _error(
    request: Request,
    status_code: int,
    error_type: str,
    code: str,
    message: str,
    details: list[str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_type": error_type,
            "code": code,
            "message": message,
            "request_id": request.headers.get("x-request-id", uuid4().hex),
            "details": details or [],
        },
    )


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("datapilot.api.app:app", host="127.0.0.1", port=8000, reload=True)
