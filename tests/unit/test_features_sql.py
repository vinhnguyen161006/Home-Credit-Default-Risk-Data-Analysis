"""Step 5 aggregation. The row count and null handling are what matter here.

Two properties carry most of the risk. A join that fans out multiplies rows and every
per-customer metric computed afterwards is wrong. A null coalesced to zero erases the
distinction between a customer who borrowed nothing and one who never borrowed, which is
the distinction this whole problem is about.

Tests run against the small fixtures through an in-memory DuckDB connection, so the real
27.3 million row table is never read.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import polars as pl
import pytest

from conftest import (
    BUREAU_ID_WITHOUT_BALANCE,
    FIRST_APPLICATION_ID,
    NO_BUREAU_HISTORY_ROWS,
    SINGLE_MONTH_BUREAU_ID,
)
from hcr.config import FeatureSpec, load_feature_spec, load_silver_rules
from hcr.features import build
from hcr.features.build import (
    AggregationError,
    BuildLayout,
    build_features,
    compute_application_ratios,
    fold_stage_one,
    register_silver_tables,
    render_aggregation_sql,
)
from hcr.features.columns import (
    DAYS_PER_MONTH,
    feature_column_name,
    own_columns,
    stage_one_columns,
    stage_two_columns,
    validate_identifier,
    window_filter,
    window_threshold,
)
from hcr.paths import configs_dir
from hcr.silver.clean_application import add_missingness_flags
from hcr.silver.clean_history import (
    derive_bureau_balance_status,
    derive_delinquency_flags,
    derive_payment_behaviour,
    derive_utilization,
)
from hcr.silver.flags import build_presence_flags

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb

APPLICATION_ROWS = 50
MATRIX_COLUMN_BUDGET = 800
APPLICATION_COLUMN_ALLOWANCE = 110
NAME_PATTERN = re.compile(r"^(APP|BURO|BB|PREV|POS|INST|CC)_[A-Z0-9_]+$")
WINDOWED_NAME_PATTERN = re.compile(r"_(3|6|12|24)M$")
CUSTOMER_WITHOUT_BUREAU = FIRST_APPLICATION_ID + min(NO_BUREAU_HISTORY_ROWS)
CUSTOMER_WITH_BARE_LOANS = FIRST_APPLICATION_ID + 3
MANIFEST_SUFFIX = ".manifest.json"
STAGE_ONE = 1
THIRD_LEVEL_TABLES = ("pos_cash_balance", "installments_payments", "credit_card_balance")
SECOND_LEVEL_TABLES = ("bureau", "previous_application")


@pytest.fixture
def feature_spec() -> FeatureSpec:
    return load_feature_spec()


def _write_silver(directory: Path, tables: dict[str, pl.DataFrame]) -> dict[str, Path]:
    paths = {}
    for name, frame in tables.items():
        paths[name] = directory / f"{name}.parquet"
        frame.write_parquet(paths[name])
    return paths


@pytest.fixture
def silver_paths(
    tmp_path: Path,
    application_frame: pl.DataFrame,
    bureau_frame: pl.DataFrame,
    bureau_balance_frame: pl.DataFrame,
    previous_application_frame: pl.DataFrame,
    pos_cash_frame: pl.DataFrame,
    installments_frame: pl.DataFrame,
    credit_card_frame: pl.DataFrame,
) -> dict[str, Path]:
    rules = load_silver_rules()
    tables = {
        "application_train": add_missingness_flags(application_frame, rules),
        "bureau": bureau_frame,
        "bureau_balance": derive_bureau_balance_status(bureau_balance_frame),
        "previous_application": previous_application_frame,
        "pos_cash_balance": derive_delinquency_flags(pos_cash_frame),
        "installments_payments": derive_payment_behaviour(installments_frame),
        "credit_card_balance": derive_delinquency_flags(derive_utilization(credit_card_frame)),
    }
    customers = {
        table: tables[table].get_column("SK_ID_CURR") for table in rules.history_presence_flags
    }
    tables["history_presence_flags"] = build_presence_flags(
        application_frame.get_column("SK_ID_CURR"), customers, rules.history_presence_flags
    )
    directory = tmp_path / "silver"
    directory.mkdir()
    return _write_silver(directory, tables)


def _layout(
    directory: Path, silver: dict[str, Path], configurations: tuple[str, ...] = ("full",)
) -> BuildLayout:
    return BuildLayout(
        silver=silver,
        matrices={name: directory / f"{name}.parquet" for name in configurations},
        manifests={name: directory / f"{name}{MANIFEST_SUFFIX}" for name in configurations},
        temp_dir=directory / "spill",
        config_path=configs_dir() / "features.yml",
    )


@pytest.fixture
def built_matrix(
    tmp_path: Path, silver_paths: dict[str, Path], feature_spec: FeatureSpec
) -> pl.DataFrame:
    layout = _layout(tmp_path / "out", silver_paths)
    build_features(layout, feature_spec, ("full",), expected_rows=APPLICATION_ROWS)
    return pl.read_parquet(layout.matrices["full"])


def _row(matrix: pl.DataFrame, customer: int) -> dict[str, object]:
    return matrix.filter(pl.col("SK_ID_CURR") == customer).row(0, named=True)


def _stage_one_by_table(feature_spec: FeatureSpec) -> dict[str, tuple[object, ...]]:
    return {
        name: stage_one_columns(name, feature_spec)
        for name, entry in feature_spec.sources.items()
        if entry["stage"] == STAGE_ONE
    }


def test_aggregation_yields_one_row_per_customer(
    built_matrix: pl.DataFrame, application_frame: pl.DataFrame
) -> None:
    assert built_matrix.height == application_frame.height
    assert built_matrix.get_column("SK_ID_CURR").is_unique().all()


def test_matrix_does_not_carry_the_label(built_matrix: pl.DataFrame) -> None:
    assert "TARGET" not in built_matrix.columns


def test_aggregation_gate_raises_when_row_count_is_wrong(
    tmp_path: Path, silver_paths: dict[str, Path], feature_spec: FeatureSpec
) -> None:
    layout = _layout(tmp_path / "out", silver_paths)

    with pytest.raises(AggregationError, match="expected"):
        build_features(layout, feature_spec, ("full",), expected_rows=APPLICATION_ROWS + 1)

    assert not layout.matrices["full"].exists()


def test_left_join_keeps_customers_without_bureau_history(built_matrix: pl.DataFrame) -> None:
    assert CUSTOMER_WITHOUT_BUREAU in built_matrix.get_column("SK_ID_CURR").to_list()


def test_missing_history_yields_null_not_zero(built_matrix: pl.DataFrame) -> None:
    row = _row(built_matrix, CUSTOMER_WITHOUT_BUREAU)
    bureau_values = [value for name, value in row.items() if name.startswith("BURO_")]

    assert bureau_values
    assert all(value is None for value in bureau_values)


def test_history_presence_flag_is_set_for_missing_history(built_matrix: pl.DataFrame) -> None:
    row = _row(built_matrix, CUSTOMER_WITHOUT_BUREAU)

    assert row["FLAG_NO_BUREAU_HISTORY"] == 1
    assert row["BURO_SK_ID_BUREAU_COUNT"] is None
    assert _row(built_matrix, FIRST_APPLICATION_ID)["FLAG_NO_BUREAU_HISTORY"] == 0


def test_count_of_key_is_zero_not_one_when_no_child_rows(
    built_matrix: pl.DataFrame, feature_spec: FeatureSpec
) -> None:
    row = _row(built_matrix, CUSTOMER_WITH_BARE_LOANS)
    columns = stage_two_columns(
        "previous_application",
        feature_spec,
        {name: stage_one_columns(name, feature_spec) for name in THIRD_LEVEL_TABLES},
    )

    assert row["PREV_SK_ID_PREV_COUNT"] == 1
    assert row["POS_MONTHS_BALANCE_COUNT_MEAN"] is None
    assert "COUNT(*)" not in render_aggregation_sql("previous_application", columns).upper()


def test_two_stage_fold_preserves_loan_without_balance_rows(built_matrix: pl.DataFrame) -> None:
    row = _row(built_matrix, CUSTOMER_WITH_BARE_LOANS)

    assert row["BURO_SK_ID_BUREAU_COUNT"] == 1
    assert row["BURO_BB_STATUS_IS_DPD_MEAN_MEAN"] is None
    assert row["BURO_AMT_CREDIT_SUM_SUM"] is not None


def test_regr_slope_is_null_for_single_observation(
    duckdb_connection: duckdb.DuckDBPyConnection,
    silver_paths: dict[str, Path],
    feature_spec: FeatureSpec,
) -> None:
    register_silver_tables(duckdb_connection, silver_paths)
    stage = fold_stage_one(duckdb_connection, "bureau_balance", feature_spec)

    slopes = dict(
        duckdb_connection.execute(
            f"SELECT SK_ID_BUREAU, BB_STATUS_IS_DPD_SLOPE FROM {stage.relation}"
        ).fetchall()
    )

    assert slopes[SINGLE_MONTH_BUREAU_ID] is None
    assert slopes[SINGLE_MONTH_BUREAU_ID - 3] is not None
    assert BUREAU_ID_WITHOUT_BALANCE not in slopes


def test_window_filter_uses_days_not_months_for_days_columns(
    duckdb_connection: duckdb.DuckDBPyConnection,
    silver_paths: dict[str, Path],
    feature_spec: FeatureSpec,
) -> None:
    assert window_filter("DAYS_INSTALMENT", 3) == f"DAYS_INSTALMENT >= -{3 * DAYS_PER_MONTH}"
    register_silver_tables(duckdb_connection, silver_paths)
    stage = fold_stage_one(duckdb_connection, "installments_payments", feature_spec)

    row = duckdb_connection.execute(
        f"SELECT INST_AMT_INSTALMENT_SUM, INST_AMT_INSTALMENT_SUM_3M FROM {stage.relation}"
    ).fetchone()

    assert row == (30_000.0, 20_000.0)


def test_window_filter_uses_months_for_months_balance(
    duckdb_connection: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    feature_spec: FeatureSpec,
) -> None:
    assert window_filter("MONTHS_BALANCE", 3) == "MONTHS_BALANCE >= -3"
    assert window_threshold("MONTHS_BALANCE", 12) == 12
    pos_cash = derive_delinquency_flags(
        pl.DataFrame(
            {
                "SK_ID_PREV": [1] * 4,
                "SK_ID_CURR": [1] * 4,
                "MONTHS_BALANCE": [0, -2, -5, -20],
                "CNT_INSTALMENT": [12.0] * 4,
                "CNT_INSTALMENT_FUTURE": [4.0, 5.0, 6.0, 7.0],
                "SK_DPD": [1] * 4,
                "SK_DPD_DEF": [0] * 4,
            }
        )
    )
    paths = _write_silver(tmp_path, {"pos_cash_balance": pos_cash})
    register_silver_tables(duckdb_connection, paths)
    stage = fold_stage_one(duckdb_connection, "pos_cash_balance", feature_spec)

    sums = duckdb_connection.execute(
        "SELECT POS_SK_DPD_SUM_3M, POS_SK_DPD_SUM_6M, POS_SK_DPD_SUM_12M, POS_SK_DPD_SUM_24M "
        f"FROM {stage.relation}"
    ).fetchone()

    assert sums == (2.0, 3.0, 3.0, 4.0)


def test_unit_of_an_unknown_time_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="unit"):
        window_threshold("SOME_OTHER_COLUMN", 3)


APPLICATION_RATIO_COLUMNS = (
    "APP_CREDIT_INCOME_RATIO",
    "APP_ANNUITY_INCOME_RATIO",
    "APP_CREDIT_GOODS_RATIO",
    "APP_CREDIT_ANNUITY_RATIO",
    "APP_EMPLOYED_BIRTH_RATIO",
    "APP_INCOME_PER_FAMILY_MEMBER",
)


def _write_silver_application(tmp_path: Path, frame: pl.DataFrame) -> Path:
    path = tmp_path / "application_train.parquet"
    frame.write_parquet(path)
    return path


def test_ratio_guards_against_zero_denominator(
    duckdb_connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    silver = _write_silver_application(
        tmp_path,
        pl.DataFrame(
            {
                "SK_ID_CURR": [1],
                "AMT_CREDIT": [100.0],
                "AMT_ANNUITY": [0.0],
                "AMT_INCOME_TOTAL": [0.0],
                "AMT_GOODS_PRICE": [0.0],
                "DAYS_EMPLOYED": [-100.0],
                "DAYS_BIRTH": [0.0],
                "CNT_FAM_MEMBERS": [0.0],
            }
        ),
    )

    row = compute_application_ratios(duckdb_connection, silver).row(0, named=True)

    assert all(row[column] is None for column in APPLICATION_RATIO_COLUMNS)


def test_employed_birth_ratio_stays_null_for_sentinel_customer(
    duckdb_connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    silver = _write_silver_application(
        tmp_path,
        pl.DataFrame(
            {
                "SK_ID_CURR": [2],
                "AMT_CREDIT": [100.0],
                "AMT_ANNUITY": [10.0],
                "AMT_INCOME_TOTAL": [50.0],
                "AMT_GOODS_PRICE": [100.0],
                "DAYS_EMPLOYED": [None],
                "DAYS_BIRTH": [-1000.0],
                "CNT_FAM_MEMBERS": [2.0],
            },
            schema_overrides={"DAYS_EMPLOYED": pl.Float64},
        ),
    )

    row = compute_application_ratios(duckdb_connection, silver).row(0, named=True)

    assert row["APP_EMPLOYED_BIRTH_RATIO"] is None
    assert row["APP_CREDIT_INCOME_RATIO"] == pytest.approx(2.0)


def test_column_names_follow_the_naming_contract(feature_spec: FeatureSpec) -> None:
    stage_ones = _stage_one_by_table(feature_spec)
    generated = [
        column
        for parent in SECOND_LEVEL_TABLES
        for column in stage_two_columns(parent, feature_spec, stage_ones)
    ]

    assert generated
    for column in generated:
        assert NAME_PATTERN.fullmatch(column.name), column.name
        windowed = column.provenance.window_months is not None
        assert bool(WINDOWED_NAME_PATTERN.search(column.name)) == windowed, column.name
    assert feature_column_name("POS", "SK_DPD_MEAN", "mean", 3) == "POS_SK_DPD_MEAN_MEAN_3M"
    assert "BURO_BB_STATUS_IS_DPD_MEAN_MEAN" in {column.name for column in generated}


def test_column_name_rejects_a_prefix_outside_the_fixed_set() -> None:
    with pytest.raises(ValueError, match="BUREAU"):
        feature_column_name("BUREAU", "AMT_CREDIT", "mean", None)


def test_identifier_with_sql_syntax_is_rejected() -> None:
    with pytest.raises(ValueError, match="identifier"):
        validate_identifier("AMT_CREDIT; DROP TABLE bureau")


def test_derived_division_without_a_guard_is_rejected(feature_spec: FeatureSpec) -> None:
    bureau = dict(feature_spec.sources["bureau"])
    bureau["derived"] = {"DEBT_CREDIT_RATIO": "AMT_CREDIT_SUM_DEBT / AMT_CREDIT_SUM"}

    with pytest.raises(ValueError, match="NULLIF"):
        list(own_columns("bureau", bureau, feature_spec, 2))


def test_generated_column_count_stays_inside_the_matrix_budget(feature_spec: FeatureSpec) -> None:
    stage_ones = _stage_one_by_table(feature_spec)
    generated = sum(
        len(stage_two_columns(parent, feature_spec, stage_ones)) for parent in SECOND_LEVEL_TABLES
    )

    total = generated + len(feature_spec.application_ratios) + APPLICATION_COLUMN_ALLOWANCE

    assert total <= MATRIX_COLUMN_BUDGET


def test_manifest_records_provenance_for_every_column(
    tmp_path: Path, silver_paths: dict[str, Path], feature_spec: FeatureSpec
) -> None:
    layout = _layout(tmp_path / "out", silver_paths)
    build_features(layout, feature_spec, ("full",), expected_rows=APPLICATION_ROWS)

    matrix_columns = list(pl.read_parquet_schema(layout.matrices["full"]))
    manifest = json.loads(layout.manifests["full"].read_text(encoding="utf-8"))
    recorded = [column["name"] for column in manifest["columns"]]

    assert matrix_columns == recorded
    assert manifest["column_count"] == len(recorded)
    assert set(manifest["source_sha256"]) == set(silver_paths)


def test_manifest_is_byte_identical_across_two_runs(
    tmp_path: Path, silver_paths: dict[str, Path], feature_spec: FeatureSpec
) -> None:
    first = _layout(tmp_path / "first", silver_paths)
    second = _layout(tmp_path / "second", silver_paths)

    build_features(first, feature_spec, ("full",), expected_rows=APPLICATION_ROWS)
    build_features(second, feature_spec, ("full",), expected_rows=APPLICATION_ROWS)

    assert first.manifests["full"].read_bytes() == second.manifests["full"].read_bytes()
    assert pl.read_parquet(first.matrices["full"]).equals(pl.read_parquet(second.matrices["full"]))


def test_no_ext_source_configuration_excludes_the_columns(
    tmp_path: Path, silver_paths: dict[str, Path], feature_spec: FeatureSpec
) -> None:
    configurations = ("full", "no_ext_source")
    layout = _layout(tmp_path / "out", silver_paths, configurations)
    build_features(layout, feature_spec, configurations, expected_rows=APPLICATION_ROWS)

    full = pl.read_parquet_schema(layout.matrices["full"])
    reduced = pl.read_parquet_schema(layout.matrices["no_ext_source"])

    assert "EXT_SOURCE_1" in full
    assert "FLAG_MISSING_EXT_SOURCE_1" in full
    assert not [name for name in reduced if "EXT_SOURCE" in name]
    excluded = feature_spec.configurations["no_ext_source"]["excluded_columns"]
    assert len(full) - len(reduced) == len(excluded)


def test_aggregation_requires_holdout_file_to_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(build, "holdout_ids_path", lambda: tmp_path / "missing.parquet")

    with pytest.raises(FileNotFoundError, match="make split"):
        build.run()

    assert not list(tmp_path.iterdir())
