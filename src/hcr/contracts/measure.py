"""Read the facts the step 2 gate compares against the data contract.

Every function here only reads. Row and column counts come from the Parquet
footer, so counting the 27.3 million bureau_balance rows costs nothing. Key
duplicates, label counts and coverage need the data itself; those run as SQL in
DuckDB, which takes the Parquet path rather than a frame because it scans the
file from disk without loading it into memory. That is the technical exception
CLAUDE.md allows for hidden I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pyarrow.parquet as pq

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb

KEY_SAMPLE_SIZE: Final = 5
VALID_TARGET_VALUES: Final = (0, 1)
POSITIVE_TARGET_VALUE: Final = 1

BUREAU_COVERAGE_SQL: Final = """
WITH loans_with_balance AS (SELECT DISTINCT SK_ID_BUREAU FROM read_parquet($balance))
SELECT COUNT(*), COUNT(loans_with_balance.SK_ID_BUREAU) FROM read_parquet($bureau) AS bureau
LEFT JOIN loans_with_balance ON bureau.SK_ID_BUREAU = loans_with_balance.SK_ID_BUREAU
"""

CUSTOMER_COVERAGE_SQL: Final = """
WITH customers_with_bureau AS (SELECT DISTINCT SK_ID_CURR FROM read_parquet($bureau))
SELECT COUNT(*), COUNT(customers_with_bureau.SK_ID_CURR) FROM read_parquet($application) AS app
LEFT JOIN customers_with_bureau ON app.SK_ID_CURR = customers_with_bureau.SK_ID_CURR
"""


@dataclass(frozen=True)
class ParquetFooter:
    """Shape of a Parquet file as recorded in its footer.

    Attributes:
        rows: Row count.
        columns: Column names in file order.
    """

    rows: int
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateKeys:
    """Key values occurring on more than one row.

    Attributes:
        count: Number of distinct key values that repeat.
        sample: Up to KEY_SAMPLE_SIZE of those values, in key order.
    """

    count: int
    sample: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class TargetCounts:
    """Label counts of the training application table.

    Attributes:
        positive: Rows with TARGET equal to 1.
        invalid: Rows whose TARGET is null or outside VALID_TARGET_VALUES.
        total: All rows.
    """

    positive: int
    invalid: int
    total: int


def read_parquet_footer(path: Path) -> ParquetFooter:
    """Read the row count and column names without reading any data page."""
    parquet_file = pq.ParquetFile(path)
    return ParquetFooter(
        rows=parquet_file.metadata.num_rows,
        columns=tuple(parquet_file.schema_arrow.names),
    )


def find_duplicate_keys(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    key: tuple[str, ...],
) -> DuplicateKeys:
    """Count key values that repeat and sample a few of them.

    The sample usually shows the cause: the same id repeated once per row hints
    at a file concatenated twice.
    """
    key_list = ", ".join(_quote_identifier(column) for column in key)
    repeated_keys = (
        f"SELECT {key_list} FROM read_parquet($path) "
        f"GROUP BY {key_list} HAVING COUNT(*) > 1 ORDER BY {key_list}"
    )
    parameters = {"path": path.as_posix()}
    (count,) = _fetch_counts(connection, f"SELECT COUNT(*) FROM ({repeated_keys})", parameters)
    sample = connection.execute(f"{repeated_keys} LIMIT {KEY_SAMPLE_SIZE}", parameters).fetchall()
    return DuplicateKeys(count=count, sample=tuple(tuple(row) for row in sample))


def count_target_values(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    target_column: str,
) -> TargetCounts:
    """Count positive, invalid and total labels in one scan."""
    target = _quote_identifier(target_column)
    valid_values = ", ".join(str(value) for value in VALID_TARGET_VALUES)
    query = (
        f"SELECT COUNT(*) FILTER (WHERE {target} = {POSITIVE_TARGET_VALUE}), "
        f"COUNT(*) FILTER (WHERE {target} IS NULL OR {target} NOT IN ({valid_values})), "
        "COUNT(*) FROM read_parquet($path)"
    )
    positive, invalid, total = _fetch_counts(connection, query, {"path": path.as_posix()})
    return TargetCounts(positive=positive, invalid=invalid, total=total)


def measure_coverage(
    connection: duckdb.DuckDBPyConnection,
    bureau_path: Path,
    balance_path: Path,
    application_path: Path,
) -> dict[str, int]:
    """Measure the bureau coverage figures declared in expected_coverage.

    Both counts start from the parent table and LEFT JOIN the child, the same
    direction every feature join takes, so a parent row without children is
    counted rather than dropped.

    Returns:
        bureau_rows_total, bureau_rows_with_balance, train_customers_total and
        train_customers_with_bureau_history.
    """
    bureau_rows_total, bureau_rows_with_balance = _fetch_counts(
        connection,
        BUREAU_COVERAGE_SQL,
        {"bureau": bureau_path.as_posix(), "balance": balance_path.as_posix()},
    )
    customers_total, customers_with_bureau = _fetch_counts(
        connection,
        CUSTOMER_COVERAGE_SQL,
        {"bureau": bureau_path.as_posix(), "application": application_path.as_posix()},
    )
    return {
        "bureau_rows_total": bureau_rows_total,
        "bureau_rows_with_balance": bureau_rows_with_balance,
        "train_customers_total": customers_total,
        "train_customers_with_bureau_history": customers_with_bureau,
    }


def _quote_identifier(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _fetch_counts(
    connection: duckdb.DuckDBPyConnection, query: str, parameters: dict[str, str]
) -> tuple[int, ...]:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise RuntimeError(f"Query returned no row: {query}")
    return tuple(int(value) for value in row)
