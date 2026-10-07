"""将不同表格文件转换成统一、可序列化的数据画像。"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
import sqlglot
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_integer_dtype,
    is_numeric_dtype,
)
from pydantic import Field
from sqlglot import exp

from datapilot.contracts import ContractModel

JsonScalar = str | int | float | bool | None
DatasetFileType = Literal["csv", "xlsx"]


class UnsupportedDatasetFormatError(ValueError):
    """文件扩展名不属于当前 Dataset 模块支持的格式。"""


class UnsafeQueryError(ValueError):
    """SQL 不符合 DataPilot 的只读查询规则。"""


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
    file_type: DatasetFileType
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: list[ColumnProfile]


class QueryResult(ContractModel):
    """适合进入工具结果或图表准备步骤的小型查询结果。"""

    columns: list[str]
    rows: list[dict[str, JsonScalar]]
    row_count: int = Field(ge=0)
    truncated: bool


def profile_dataset(path: str | Path) -> DatasetProfile:
    """读取一个表格文件，并返回与文件格式无关的数据画像。"""

    dataset_path = Path(path)
    file_type, frame = _load_frame(dataset_path)

    row_count = len(frame.index)
    columns = [_profile_column(series, row_count) for _, series in frame.items()]
    return DatasetProfile(
        file_name=dataset_path.name,
        file_type=file_type,
        row_count=row_count,
        column_count=len(frame.columns),
        columns=columns,
    )


def query_dataset(path: str | Path, sql: str, *, max_rows: int = 1000) -> QueryResult:
    """将一个数据文件注册为 dataset 表并执行查询。"""

    if not 1 <= max_rows <= 10_000:
        raise ValueError("max_rows must be between 1 and 10000")
    validated_sql = _validate_read_only_query(sql)
    dataset_path = Path(path)
    _, frame = _load_frame(dataset_path)

    with duckdb.connect(":memory:") as connection:
        connection.register("dataset", frame)
        bounded_sql = f"SELECT * FROM ({validated_sql}) AS datapilot_result LIMIT {max_rows + 1}"
        cursor = connection.execute(bounded_sql)
        columns = [description[0] for description in cursor.description]
        values = cursor.fetchall()

    truncated = len(values) > max_rows
    rows = [
        {column: _to_json_scalar(value) for column, value in zip(columns, row, strict=True)}
        for row in values[:max_rows]
    ]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    )


def _validate_read_only_query(sql: str) -> str:
    statements = sqlglot.parse(sql, read="duckdb")
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeQueryError("only one SELECT or WITH query is allowed")

    statement = statements[0]
    allowed_tables = {"dataset"}
    allowed_tables.update(cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE))
    for table in statement.find_all(exp.Table):
        if not table.name or table.name.lower() not in allowed_tables:
            raise UnsafeQueryError("queries may only read the dataset table or a local CTE")
    return statement.sql(dialect="duckdb")


def _load_frame(path: Path) -> tuple[DatasetFileType, pd.DataFrame]:
    if path.suffix.lower() == ".csv":
        return "csv", pd.read_csv(path)
    if path.suffix.lower() == ".xlsx":
        return "xlsx", pd.read_excel(path)
    raise UnsupportedDatasetFormatError(f"unsupported dataset format: {path.suffix or '<none>'}")


def _to_json_scalar(value: object) -> JsonScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


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
