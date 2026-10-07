from pathlib import Path

import pytest

from datapilot.dataset import UnsafeQueryError, query_dataset


def test_query_dataset_executes_a_read_only_aggregation(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text(
        "region,revenue\n华东,120\n华南,80\n华东,60\n",
        encoding="utf-8",
    )

    result = query_dataset(
        dataset_path,
        """
        SELECT region, SUM(revenue) AS total_revenue
        FROM dataset
        GROUP BY region
        ORDER BY total_revenue DESC
        """,
    )

    assert result.columns == ["region", "total_revenue"]
    assert result.rows == [
        {"region": "华东", "total_revenue": 180.0},
        {"region": "华南", "total_revenue": 80.0},
    ]
    assert result.row_count == 2
    assert result.truncated is False


def test_query_dataset_rejects_non_select_statements(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text("region,revenue\n华东,120\n", encoding="utf-8")

    with pytest.raises(UnsafeQueryError, match="SELECT or WITH"):
        query_dataset(dataset_path, "DELETE FROM dataset")


def test_query_dataset_rejects_external_file_table_functions(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text("region,revenue\n华东,120\n", encoding="utf-8")
    private_path = tmp_path / "private.csv"
    private_path.write_text("secret\ndo-not-read\n", encoding="utf-8")
    sql_path = private_path.as_posix().replace("'", "''")

    with pytest.raises(UnsafeQueryError, match="dataset table"):
        query_dataset(dataset_path, f"SELECT * FROM read_csv_auto('{sql_path}')")


def test_query_dataset_enforces_result_limit_and_reports_truncation(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text(
        "rank,revenue\n1,100\n2,90\n3,80\n4,70\n",
        encoding="utf-8",
    )

    result = query_dataset(
        dataset_path,
        "SELECT rank, revenue FROM dataset ORDER BY rank",
        max_rows=2,
    )

    assert result.rows == [
        {"rank": 1, "revenue": 100},
        {"rank": 2, "revenue": 90},
    ]
    assert result.row_count == 2
    assert result.truncated is True


def test_query_dataset_returns_json_ready_values(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text("region,revenue\n华东,120\n", encoding="utf-8")

    result = query_dataset(
        dataset_path,
        """
        SELECT
            CAST('2026-10-01' AS DATE) AS report_date,
            CAST(12.34 AS DECIMAL(10, 2)) AS ratio
        """,
    )

    assert result.rows == [{"report_date": "2026-10-01", "ratio": 12.34}]


def test_query_dataset_allows_a_cte_built_from_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text(
        "region,revenue\n华东,120\n华南,80\n华东,60\n",
        encoding="utf-8",
    )

    result = query_dataset(
        dataset_path,
        """
        WITH regional_totals AS (
            SELECT region, SUM(revenue) AS revenue
            FROM dataset
            GROUP BY region
        )
        SELECT region, revenue
        FROM regional_totals
        ORDER BY revenue DESC
        """,
    )

    assert result.rows == [
        {"region": "华东", "revenue": 180.0},
        {"region": "华南", "revenue": 80.0},
    ]


def test_query_dataset_rejects_multiple_statements(tmp_path: Path) -> None:
    dataset_path = tmp_path / "sales.csv"
    dataset_path.write_text("region,revenue\n华东,120\n", encoding="utf-8")

    with pytest.raises(UnsafeQueryError, match="only one"):
        query_dataset(dataset_path, "SELECT * FROM dataset; DELETE FROM dataset")
