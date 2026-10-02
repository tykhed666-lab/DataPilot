"""FastAPI application entry point."""

from fastapi import FastAPI

from datapilot import __version__
from datapilot.config import get_settings


def create_app() -> FastAPI:
    """Build the application without performing filesystem or network side effects."""

    settings = get_settings()
    application = FastAPI(
        title="DataPilot API",
        version=__version__,
        description="Safe and auditable data-analysis agent API.",
    )

    @application.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "datapilot",
            "version": __version__,
        }

    @application.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, str]:
        # Day 1 只验证配置可以加载；后续再加入 DB、MCP 和模型依赖检查。
        return {
            "status": "ready",
            "environment": settings.app_env,
        }

    return application


app = create_app()


def run() -> None:
    """Run the development server through the project console script."""

    import uvicorn

    uvicorn.run("datapilot.api.app:app", host="127.0.0.1", port=8000, reload=True)
