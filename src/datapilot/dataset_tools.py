"""将 Dataset 模块适配到统一 Tool Runtime。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import Field, field_validator

from datapilot.contracts import ContractModel
from datapilot.dataset import (
    DatasetProfile,
    QueryResult,
    profile_dataset,
    query_dataset,
)
from datapilot.tool_runtime import ToolDefinition


class ProfileDatasetInput(ContractModel):
    """数据画像工具只接受数据根目录内的相对路径。"""

    relative_path: str = Field(min_length=1, max_length=500)

    @field_validator("relative_path")
    @classmethod
    def reject_unsafe_paths(cls, value: str) -> str:
        windows_path = PureWindowsPath(value)
        posix_path = PurePosixPath(value)
        if windows_path.is_absolute() or posix_path.is_absolute():
            raise ValueError("relative_path must be relative")
        if ".." in windows_path.parts or ".." in posix_path.parts:
            raise ValueError("relative_path cannot contain parent traversal")
        return value


class QueryDatasetInput(ProfileDatasetInput):
    """安全查询工具的结构化输入。"""

    sql: str = Field(min_length=1, max_length=20_000)
    max_rows: int = Field(default=1000, ge=1, le=10_000)


def dataset_tool_definitions(
    data_root: str | Path,
) -> list[ToolDefinition[Any, Any]]:
    """创建绑定到指定数据根目录的两个 Dataset 工具适配器。"""

    root = Path(data_root).resolve()

    def resolve_path(relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("dataset path escaped the configured data root")
        return candidate

    def handle_profile(payload: ProfileDatasetInput) -> DatasetProfile:
        return profile_dataset(resolve_path(payload.relative_path))

    def handle_query(payload: QueryDatasetInput) -> QueryResult:
        return query_dataset(
            resolve_path(payload.relative_path),
            payload.sql,
            max_rows=payload.max_rows,
        )

    return [
        ToolDefinition(
            name="profile_dataset",
            description="Inspect columns, types, missing values, and numeric summaries.",
            input_model=ProfileDatasetInput,
            output_model=DatasetProfile,
            handler=handle_profile,
        ),
        ToolDefinition(
            name="query_dataset",
            description="Run one read-only SELECT or WITH query against the dataset table.",
            input_model=QueryDatasetInput,
            output_model=QueryResult,
            handler=handle_query,
        ),
    ]
