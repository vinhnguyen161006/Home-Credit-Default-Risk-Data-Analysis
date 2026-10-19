"""Facts the step 2 gate measures from Parquet: footer shape, key duplicates, labels, coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import polars as pl

from conftest import (
    BUREAU_STATUS_HISTORIES,
    FIRST_BUREAU_ID,
    FIXTURE_APPLICATION_ROWS,
    NO_BUREAU_HISTORY_ROWS,
    POSITIVE_TARGET_ROWS,
)
from hcr.contracts.measure import (
    count_target_values,
    find_duplicate_keys,
    measure_coverage,
    read_parquet_footer,
)

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb

BALANCE_KEY: Final = ("SK_ID_BUREAU", "MONTHS_BALANCE")
INVALID_TARGET_VALUE: Final = 2


def write(frame: pl.DataFrame, path: Path) -> Path:
    frame.write_parquet(path)
    return path


def test_footer_reports_rows_and_columns_in_file_order(
    tmp_path: Path, bureau_balance_frame: pl.DataFrame
) -> None:
    footer = read_parquet_footer(write(bureau_balance_frame, tmp_path / "balance.parquet"))

    assert footer.rows == bureau_balance_frame.height
    assert footer.columns == tuple(bureau_balance_frame.columns)


def test_unique_composite_key_has_no_duplicates(
    tmp_path: Path,
    duckdb_connection: duckdb.DuckDBPyConnection,
    bureau_balance_frame: pl.DataFrame,
) -> None:
    path = write(bureau_balance_frame, tmp_path / "balance.parquet")

    duplicates = find_duplicate_keys(duckdb_connection, path, BALANCE_KEY)

    assert duplicates.count == 0
    assert duplicates.sample == ()


def test_repeated_composite_key_is_counted_and_sampled(
    tmp_path: Path,
    duckdb_connection: duckdb.DuckDBPyConnection,
    bureau_balance_frame: pl.DataFrame,
) -> None:
    repeated = pl.concat([bureau_balance_frame, bureau_balance_frame.head(1)])
    path = write(repeated, tmp_path / "balance.parquet")

    duplicates = find_duplicate_keys(duckdb_connection, path, BALANCE_KEY)

    assert duplicates.count == 1
    assert duplicates.sample == ((FIRST_BUREAU_ID, 0),)


def test_target_counts_find_positives_and_invalid_labels(
    tmp_path: Path,
    duckdb_connection: duckdb.DuckDBPyConnection,
    application_frame: pl.DataFrame,
) -> None:
    labels = application_frame["TARGET"].to_list()
    labels[0], labels[1] = INVALID_TARGET_VALUE, None
    relabelled = application_frame.with_columns(pl.Series("TARGET", labels, dtype=pl.Int64))
    path = write(relabelled, tmp_path / "application.parquet")

    counts = count_target_values(duckdb_connection, path, "TARGET")

    assert counts.positive == len(POSITIVE_TARGET_ROWS)
    assert counts.invalid == len(labels[:2])
    assert counts.total == FIXTURE_APPLICATION_ROWS


def test_coverage_counts_parents_without_children(
    tmp_path: Path,
    duckdb_connection: duckdb.DuckDBPyConnection,
    application_frame: pl.DataFrame,
    bureau_frame: pl.DataFrame,
    bureau_balance_frame: pl.DataFrame,
) -> None:
    coverage = measure_coverage(
        duckdb_connection,
        write(bureau_frame, tmp_path / "bureau.parquet"),
        write(bureau_balance_frame, tmp_path / "balance.parquet"),
        write(application_frame, tmp_path / "application.parquet"),
    )

    assert coverage == {
        "bureau_rows_total": bureau_frame.height,
        "bureau_rows_with_balance": len(BUREAU_STATUS_HISTORIES),
        "train_customers_total": FIXTURE_APPLICATION_ROWS,
        "train_customers_with_bureau_history": FIXTURE_APPLICATION_ROWS
        - len(NO_BUREAU_HISTORY_ROWS),
    }
