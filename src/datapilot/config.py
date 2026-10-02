"""Application settings loaded from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration boundary for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    data_root: Path = Path("data")
    database_url: str = "sqlite+aiosqlite:///./data/datapilot.db"
    checkpoint_db: Path = Path("data/checkpoints.db")

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = None
    agent_model: str | None = None

    max_upload_mb: int = Field(default=50, ge=1, le=500)
    sql_max_rows: int = Field(default=1000, ge=1, le=10_000)
    python_timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_agent_retries: int = Field(default=2, ge=0, le=5)
    max_plan_steps: int = Field(default=8, ge=1, le=20)
    max_artifact_mb: int = Field(default=20, ge=1, le=200)
    sandbox_backend: str = "subprocess"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object for the process lifetime."""

    return Settings()
