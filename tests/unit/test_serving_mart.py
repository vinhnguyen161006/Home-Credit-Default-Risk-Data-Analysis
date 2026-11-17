"""Serving mart construction and SQL Server column sizing."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest

from hcr.serving.build_star import build_mart
from hcr.serving.dimensions import EDUCATION_ORDER, build_dimension_frame
from hcr.serving.load_sqlserver import NON_NULL_COLUMNS, infer_string_column_length


def _write_source_tables(directory: Path) -> dict[str, Path]:
    tables = {
        "application_train": pl.DataFrame(
            {
                "SK_ID_CURR": [100, 101, 102],
                "TARGET": [0, 1, 0],
                "CODE_GENDER": ["F", "M", None],
                "FLAG_OWN_CAR": ["Y", "N", "N"],
                "FLAG_OWN_REALTY": ["Y", "Y", "N"],
                "OCCUPATION_TYPE": ["Managers", "Unknown", "Sales staff"],
                "ORGANIZATION_TYPE": ["Business Entity Type 3", "XNA", None],
                "NAME_EDUCATION_TYPE": [
                    "Higher education",
                    "Secondary / secondary special",
                    None,
                ],
                "NAME_CONTRACT_TYPE": ["Cash loans", "Revolving loans", "Cash loans"],
                "NAME_HOUSING_TYPE": ["House / apartment", "Rented apartment", None],
                "NAME_FAMILY_STATUS": ["Married", "Single / not married", None],
                "AGE_YEARS": [30.0, 42.0, None],
                "AMT_INCOME_TOTAL": [100000.0, 0.0, None],
                "AMT_CREDIT": [200000.0, 150000.0, 80000.0],
                "AMT_ANNUITY": [10000.0, 5000.0, 3000.0],
                "AMT_GOODS_PRICE": [180000.0, 140000.0, 75000.0],
            }
        ),
        "bureau": pl.DataFrame(
            {
                "SK_ID_CURR": [100, 101],
                "SK_ID_BUREAU": [501, 502],
                "CREDIT_ACTIVE": ["Active", "Closed"],
                "CREDIT_TYPE": ["Consumer credit", "Credit card"],
                "DAYS_CREDIT": [-100, -200],
                "CREDIT_DAY_OVERDUE": [0, 2],
                "AMT_CREDIT_SUM": [10000.0, 20000.0],
                "AMT_CREDIT_SUM_DEBT": [5000.0, 0.0],
                "AMT_CREDIT_SUM_OVERDUE": [0.0, 10.0],
                "CNT_CREDIT_PROLONG": [0, 1],
                "FLAG_CLOSED_WITHOUT_END_DATE": [0, 0],
                "FLAG_NEGATIVE_DEBT": [0, 0],
            }
        ),
        "bureau_balance": pl.DataFrame(
            {
                "SK_ID_BUREAU": [501, 501, 503],
                "MONTHS_BALANCE": [-1, -2, -1],
                "STATUS_IS_DPD": [False, True, True],
                "STATUS_IS_CLOSED": [False, False, True],
            }
        ),
        "previous_application": pl.DataFrame(
            {
                "SK_ID_PREV": [701],
                "SK_ID_CURR": [100],
                "NAME_CONTRACT_TYPE": ["Cash loans"],
                "NAME_CONTRACT_STATUS": ["Approved"],
                "NAME_CLIENT_TYPE": ["Repeater"],
                "AMT_APPLICATION": [12000.0],
                "AMT_CREDIT": [10000.0],
                "AMT_ANNUITY": [1000.0],
                "AMT_DOWN_PAYMENT": [2000.0],
                "DAYS_DECISION": [-30],
            }
        ),
        "pos_cash_balance": pl.DataFrame(
            {
                "SK_ID_PREV": [701, 702],
                "SK_ID_CURR": [100, 102],
                "MONTHS_BALANCE": [-1, -2],
                "SK_DPD": [0, 3],
                "CNT_INSTALMENT_FUTURE": [4.0, 2.0],
                "IS_DPD": [False, True],
            }
        ),
        "installments_payments": pl.DataFrame(
            {
                "SK_ID_PREV": [701, 702],
                "SK_ID_CURR": [100, 102],
                "AMT_PAYMENT": [1000.0, 500.0],
                "PAYMENT_DELAY_DAYS": [0.0, 3.0],
                "IS_LATE": [False, True],
                "PAYMENT_RATIO": [1.0, 0.5],
                "IS_UNDERPAID": [False, True],
            }
        ),
        "credit_card_balance": pl.DataFrame(
            {
                "SK_ID_PREV": [701, 703],
                "SK_ID_CURR": [100, 101],
                "AMT_BALANCE": [100.0, 500.0],
                "UTILIZATION": [0.1, 0.5],
                "SK_DPD": [0, 2],
            }
        ),
    }
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for table, frame in tables.items():
        path = directory / f"{table}.parquet"
        frame.write_parquet(path)
        paths[table] = path
    return paths


def test_dimension_keys_and_natural_sort_order_are_stable() -> None:
    dimension = build_dimension_frame(
        ["Secondary / secondary special", "Higher education", "Unknown"],
        "EducationKey",
        "NAME_EDUCATION_TYPE",
        EDUCATION_ORDER,
    )

    assert dimension["EducationKey"].to_list() == [-1, 1, 2]
    assert dimension["SortOrder"].to_list() == [0, 2, 4]
    assert dimension["NAME_EDUCATION_TYPE"][0] == "Unknown"


def test_string_column_length_uses_observed_characters() -> None:
    values = pl.Series("category", ["a", "Long label", None], dtype=pl.String)

    assert infer_string_column_length(values) == 12
    assert infer_string_column_length(pl.Series("empty", [None], dtype=pl.String)) == 1


def test_string_column_length_rejects_non_string_data() -> None:
    with pytest.raises(TypeError, match="string series"):
        infer_string_column_length(pl.Series("amount", [1, 2]))


def test_loader_marks_keys_non_nullable_and_model_fields_nullable() -> None:
    assert ("Dim_Customer", "CustomerKey") in NON_NULL_COLUMNS
    assert ("Fact_Application", "CustomerKey") in NON_NULL_COLUMNS
    assert ("Fact_Application", "Model_Version") not in NON_NULL_COLUMNS


def test_mart_preserves_child_only_and_balance_only_keys(tmp_path: Path) -> None:
    source_paths = _write_source_tables(tmp_path / "silver")
    output_dir = tmp_path / "mart"

    row_counts = build_mart(source_paths, output_dir, expected_application_rows=None)

    assert row_counts["Fact_Application"] == 3
    assert row_counts["Fact_BureauLoan"] == 3
    assert row_counts["Fact_PreviousApplication"] == 3
    assert row_counts["Dim_RiskBand"] == 1

    connection = duckdb.connect()
    try:
        bureau_rows = connection.execute(
            "SELECT SK_ID_BUREAU, CustomerKey, FLAG_NO_BUREAU_BALANCE, BB_MONTH_COUNT "
            "FROM read_parquet(?) ORDER BY SK_ID_BUREAU",
            [str(output_dir / "Fact_BureauLoan.parquet")],
        ).fetchall()
        previous_keys = connection.execute(
            "SELECT SK_ID_PREV FROM read_parquet(?) ORDER BY SK_ID_PREV",
            [str(output_dir / "Fact_PreviousApplication.parquet")],
        ).fetchall()
        app_model_values = connection.execute(
            "SELECT PD_Predicted, CreditScore, Model_Version, IsHoldout " "FROM read_parquet(?)",
            [str(output_dir / "Fact_Application.parquet")],
        ).fetchall()
        app_ratios = connection.execute(
            "SELECT CREDIT_INCOME_RATIO FROM read_parquet(?) ORDER BY SK_ID_CURR",
            [str(output_dir / "Fact_Application.parquet")],
        ).fetchall()
    finally:
        connection.close()

    assert bureau_rows[0] == (501, 1, 0, 2)
    assert bureau_rows[1] == (502, 2, 1, None)
    assert bureau_rows[2][0] == 503
    assert bureau_rows[2][1] == -1
    assert [row[0] for row in previous_keys] == [701, 702, 703]
    assert all(value is None for row in app_model_values for value in row)
    assert app_ratios[0][0] == pytest.approx(2.0)
    assert app_ratios[1][0] is None
