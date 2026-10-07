"""将不同表格文件转换成统一、可序列化的数据画像。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_integer_dtype,
    is_numeric_dtype,
)
from pydantic import Field

from datapilot.contracts import ContractModel


class UnsupportedDatasetFormatError(ValueError):
    """文件扩展名不属于当前 Dataset 模块支持的格式。"""


class NumericSummary(ContractModel):
    """数值字段的最小统计摘要。"""

    minimum: float
    maximum: float
    mean: float


class ColumnProfile(ContractModel):
    """一个字段中对后续 Planner 有用的信息。"""

    name: str
    data_type: Literal["string", "integer", "number", "boolean", "datetime"]
    missing_count: int = Field(ge=0)
    missing_ratio: float = Field(ge=0, le=1)
    unique_count: int = Field(ge=0)
    numeric_summary: NumericSummary | None = None


class DatasetProfile(ContractModel):
    """CSV 和 XLSX 共用的数据画像契约。"""

    file_name: str
    file_type: Literal["csv", "xlsx"]
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: list[ColumnProfile]


def profile_dataset(path: str | Path) -> DatasetProfile:
    """读取一个表格文件，并返回与文件格式无关的数据画像。"""

    dataset_path = Path(path)
    file_type: Literal["csv", "xlsx"]
    if dataset_path.suffix.lower() == ".csv":
        file_type = "csv"
        frame = pd.read_csv(dataset_path)
    elif dataset_path.suffix.lower() == ".xlsx":
        file_type = "xlsx"
        frame = pd.read_excel(dataset_path)
    else:
        raise UnsupportedDatasetFormatError(
            f"unsupported dataset format: {dataset_path.suffix or '<none>'}"
        )

    row_count = len(frame.index)
    columns = [_profile_column(series, row_count) for _, series in frame.items()]
    return DatasetProfile(
        file_name=dataset_path.name,
        file_type=file_type,
        row_count=row_count,
        column_count=len(frame.columns),
        columns=columns,
    )


def _profile_column(series: pd.Series, row_count: int) -> ColumnProfile:
    missing_count = int(series.isna().sum())
    missing_ratio = missing_count / row_count if row_count else 0.0
    data_type = _classify_dtype(series)
    numeric_summary = None

    if data_type in {"integer", "number"}:
        values = series.dropna()
        if not values.empty:
            numeric_summary = NumericSummary(
                minimum=float(values.min()),
                maximum=float(values.max()),
                mean=float(values.mean()),
            )

    return ColumnProfile(
        name=str(series.name),
        data_type=data_type,
        missing_count=missing_count,
        missing_ratio=missing_ratio,
        unique_count=int(series.nunique(dropna=True)),
        numeric_summary=numeric_summary,
    )


def _classify_dtype(
    series: pd.Series,
) -> Literal["string", "integer", "number", "boolean", "datetime"]:
    if is_bool_dtype(series.dtype):
        return "boolean"
    if is_integer_dtype(series.dtype):
        return "integer"
    if is_numeric_dtype(series.dtype):
        return "number"
    if is_datetime64_any_dtype(series.dtype):
        return "datetime"
    return "string"
