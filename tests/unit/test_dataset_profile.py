from pathlib import Path

import pandas as pd
import pytest

from datapilot.dataset import UnsupportedDatasetFormatError, profile_dataset


def test_profile_csv_returns_shape_columns_and_numeric_summary(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text(
        "region,revenue,orders\n华东,120.5,2\n华南,,1\n华东,79.5,3\n",
        encoding="utf-8",
    )

    profile = profile_dataset(dataset_path)

    assert profile.file_name == "sales.csv"
    assert profile.file_type == "csv"
    assert profile.row_count == 3
    assert profile.column_count == 3

    columns = {column.name: column for column in profile.columns}
    assert columns["region"].data_type == "string"
    assert columns["region"].unique_count == 2
    assert columns["revenue"].data_type == "number"
    assert columns["revenue"].missing_count == 1
    assert columns["revenue"].missing_ratio == pytest.approx(1 / 3, abs=0.0001)
    assert columns["revenue"].numeric_summary is not None
    assert columns["revenue"].numeric_summary.minimum == 79.5
    assert columns["revenue"].numeric_summary.maximum == 120.5
    assert columns["revenue"].numeric_summary.mean == 100.0
    assert columns["orders"].data_type == "integer"


def test_profile_xlsx_uses_the_same_contract_as_csv(tmp_path: Path) -> None:
    dataset_path = tmp_path / "orders.xlsx"
    pd.DataFrame(
        {
            "ordered_at": pd.to_datetime(["2026-10-01", "2026-10-02"]),
            "paid": [True, False],
            "amount": [20, 30],
        }
    ).to_excel(dataset_path, index=False)

    profile = profile_dataset(dataset_path)

    assert profile.file_type == "xlsx"
    assert profile.row_count == 2
    columns = {column.name: column for column in profile.columns}
    assert columns["ordered_at"].data_type == "datetime"
    assert columns["paid"].data_type == "boolean"
    assert columns["amount"].data_type == "integer"
    assert columns["amount"].numeric_summary is not None
    assert columns["amount"].numeric_summary.mean == 25.0


def test_profile_rejects_an_unsupported_file_format(tmp_path: Path) -> None:
    dataset_path = tmp_path / "notes.txt"
    dataset_path.write_text("not a table", encoding="utf-8")

    with pytest.raises(UnsupportedDatasetFormatError, match=r"\.txt"):
        profile_dataset(dataset_path)
