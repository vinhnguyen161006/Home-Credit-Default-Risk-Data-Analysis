"""Step 2 gate: assert the bronze data matches the declared contract.

Three conditions stop the pipeline here: row and column counts that disagree
with the specification, a non-unique primary key, and a missing or mistyped
column. Each is a sign the source file is not the one every downstream number
was derived from. The TARGET label of application_train is checked as well,
because a shifted label invalidates every reference figure.

This module is a gate, not a loader. It returns a verdict and raises on failure;
it never repairs a value and never writes a file. Keeping it separate is what
lets the gate run on its own in CI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import duckdb
import polars as pl
from pandera.errors import SchemaErrors

from hcr.config import load_data_contract
from hcr.contracts.measure import (
    count_target_values,
    find_duplicate_keys,
    measure_coverage,
    read_parquet_footer,
)
from hcr.contracts.schemas import build_table_schema, declared_columns, forbidden_column_check
from hcr.paths import bronze_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hcr.config import DataContract, TableContract

logger = logging.getLogger(__name__)

COVERAGE_TOLERANCE_ROWS: Final = 0
TARGET_TABLE: Final = "application_train"
TARGET_COLUMN: Final = "TARGET"
TARGET_RATE_TOLERANCE: Final = 0.0005
BUREAU_TABLE: Final = "bureau"
BUREAU_BALANCE_TABLE: Final = "bureau_balance"
EXIT_FAILURE: Final = 1
LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class ContractViolationError(Exception):
    """Raised when bronze data disagrees with configs/data_contract.yml.

    Carries the table, the condition and both the expected and observed value,
    so the message alone identifies what changed.
    """


@dataclass(frozen=True)
class TableReport:
    """Outcome of validating one table.

    Attributes:
        table: Logical table name.
        passed: True when every condition held.
        observed_rows: Rows counted in bronze, 0 when the file is absent.
        observed_columns: Columns counted in bronze, 0 when the file is absent.
        violations: One message per failed condition, empty when passed.
    """

    table: str
    passed: bool
    observed_rows: int
    observed_columns: int
    violations: tuple[str, ...]


def check_row_count(table: str, observed: int, expected: int) -> str | None:
    """Compare the observed row count against the contract.

    Exact equality: a tolerance would let a truncated download pass and silently
    change every reported metric.

    Returns:
        A violation message with the signed difference, or None when they match.
    """
    if observed == expected:
        return None
    return f"{table}: {observed} rows vs {expected} expected, {_describe_delta(observed, expected)}"


def check_column_count(table: str, observed: int, expected: int) -> str | None:
    """Compare the observed column count against the contract.

    The absent columns are named by check_required_columns; this check catches
    an extra column, which presence alone cannot.

    Returns:
        A violation message with the signed difference, or None when they match.
    """
    if observed == expected:
        return None
    delta = _describe_delta(observed, expected)
    return f"{table}: {observed} columns vs {expected} expected, {delta}"


def check_primary_key_unique(
    table: str,
    duplicate_count: int,
    sample_keys: tuple[tuple[object, ...], ...] = (),
) -> str | None:
    """Assert the primary key holds no duplicates.

    A duplicate multiplies rows through every join and breaks the step 5 gate
    that asserts the post-join row count equals the application count. Tables
    declaring no key, such as installments_payments, are never measured, so this
    is only called for keyed tables.

    Args:
        table: Logical table name.
        duplicate_count: Number of key values occurring on more than one row.
        sample_keys: A few of those values; they usually reveal the cause.

    Returns:
        A violation message, or None when the key is unique.
    """
    if duplicate_count == 0:
        return None
    examples = ", ".join(str(key) for key in sample_keys)
    return f"{table}: {duplicate_count} primary key values repeat, for example {examples}"


def check_required_columns(
    table: str,
    observed: tuple[str, ...],
    required: tuple[str, ...],
) -> str | None:
    """Assert every required column is present.

    Compared case-sensitively. The Kaggle spelling is the contract, and a
    case-insensitive match would hide a renamed column that later SQL references
    by exact name.

    Returns:
        A violation message naming every absent column, or None.
    """
    present = set(observed)
    absent = [column for column in required if column not in present]
    if not absent:
        return None
    return f"{table}: missing columns {', '.join(absent)}"


def check_forbidden_columns(
    table: str,
    observed: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> str | None:
    """Assert no forbidden column is present.

    Catches a labelled application_test, which would mean the file is not the
    unlabelled test set the contract describes.

    Returns:
        A violation message naming every forbidden column found, or None.
    """
    found = [column for column in forbidden if column in set(observed)]
    if not found:
        return None
    return f"{table}: forbidden columns present {', '.join(found)}"


def check_target_labels(invalid_count: int) -> str | None:
    """Assert TARGET holds only 0 and 1.

    A third value or a null would silently break the stratified split and the
    AUC computation.

    Returns:
        A violation message, or None when every label is 0 or 1.
    """
    if invalid_count == 0:
        return None
    return f"{TARGET_TABLE}: {invalid_count} {TARGET_COLUMN} values are null or outside 0 and 1"


def check_target_distribution(positive_count: int, total: int, expected_rate: float) -> str | None:
    """Assert the TARGET positive rate matches the published 8.07 percent.

    A shifted rate means the label column changed, which invalidates the cost
    threshold and every baseline reference number. The tolerance is a few
    hundredths of a percentage point, wide enough for the rounding of the
    published 0.0807 against the exact 24825 / 307511.

    Returns:
        A violation message, or None when the rate is within tolerance.
    """
    if total == 0:
        return f"{TARGET_TABLE}: no rows to compute the {TARGET_COLUMN} rate from"
    observed_rate = positive_count / total
    if abs(observed_rate - expected_rate) <= TARGET_RATE_TOLERANCE:
        return None
    rates = f"{observed_rate:.3%} vs {expected_rate:.3%} expected"
    return f"{TARGET_TABLE}: {TARGET_COLUMN} positive rate {rates}"


def report_coverage(observed: dict[str, int], expected: dict[str, int]) -> None:
    """Log the known coverage gaps as warnings, never as failures.

    Fewer than half of bureau loans have rows in bureau_balance, and about one
    training customer in seven has no bureau record at all. These describe the
    data; they are the reason every join is a LEFT JOIN, not defects to stop on.
    A figure that moved means the relationship between two files changed, so it
    is logged at WARNING.

    Raises:
        KeyError: If a declared figure was not measured.
    """
    unmeasured = sorted(set(expected) - set(observed))
    if unmeasured:
        raise KeyError(f"Coverage figures not measured: {', '.join(unmeasured)}")
    for name, expected_value in expected.items():
        observed_value = observed[name]
        if abs(observed_value - expected_value) > COVERAGE_TOLERANCE_ROWS:
            logger.warning("Coverage %s is %s, expected %s", name, observed_value, expected_value)
        else:
            logger.info("Coverage %s is %s as expected", name, observed_value)


def validate_table(
    table: str,
    contract: DataContract,
    parquet_path: Path,
    connection: duckdb.DuckDBPyConnection,
) -> TableReport:
    """Run every structural check for one table and collect all violations.

    Row and column counts come from the Parquet footer and dtypes from the
    Parquet schema, so only the key and label checks scan data. Every violation
    is collected before returning: a report listing all failures beats fixing
    them one run at a time.

    Args:
        table: Logical table name as keyed in the contract.
        contract: Parsed data contract.
        parquet_path: Bronze file of the table.
        connection: DuckDB connection used for the key and label scans.

    Returns:
        The report, with passed False when any check produced a violation.
    """
    if not parquet_path.is_file():
        missing = f"{table}: bronze file {parquet_path} not found, run make ingest first"
        return TableReport(table, False, 0, 0, (missing,))
    entry = contract.tables[table]
    footer = read_parquet_footer(parquet_path)
    candidates = (
        *_shape_violations(table, entry, footer.rows, footer.columns),
        *_dtype_violations(table, entry, parquet_path),
        *_key_violations(table, entry, parquet_path, connection),
        *_target_violations(table, contract, parquet_path, connection),
    )
    violations = tuple(message for message in candidates if message is not None)
    return TableReport(table, not violations, footer.rows, len(footer.columns), violations)


def run(
    contract: DataContract | None = None,
    resolve_path: Callable[[str], Path] = bronze_path,
) -> tuple[TableReport, ...]:
    """Validate all eight tables and raise if any failed.

    Every table is validated before raising, so one run surfaces every problem.

    Args:
        contract: Parsed data contract; loaded from configs when omitted.
        resolve_path: Maps a table name to its bronze file.

    Returns:
        One report per table, in contract order.

    Raises:
        ContractViolationError: If any table failed any check.
    """
    data_contract = load_data_contract() if contract is None else contract
    with duckdb.connect() as connection:
        reports = tuple(
            validate_table(table, data_contract, resolve_path(table), connection)
            for table in data_contract.tables
        )
        for report in reports:
            _log_report(report)
        _report_measured_coverage(data_contract, reports, resolve_path, connection)
    violations = [message for report in reports for message in report.violations]
    if violations:
        raise ContractViolationError("Contract check failed:\n" + "\n".join(violations))
    return reports


def main() -> None:
    """Entry point for `python -m hcr.contracts.validate_raw`.

    Exits with status 1 after logging every violation, so make and CI stop.
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        run()
    except ContractViolationError as error:
        logger.critical("%s", error)
        raise SystemExit(EXIT_FAILURE) from error


def _describe_delta(observed: int, expected: int) -> str:
    delta = observed - expected
    direction = "short by" if delta < 0 else "over by"
    return f"{direction} {abs(delta)}"


def _shape_violations(
    table: str, entry: TableContract, rows: int, columns: tuple[str, ...]
) -> tuple[str | None, ...]:
    return (
        check_row_count(table, rows, entry.rows),
        check_column_count(table, len(columns), entry.columns),
        check_required_columns(table, columns, declared_columns(entry)),
        check_forbidden_columns(table, columns, forbidden_column_check(entry)),
    )


def _dtype_violations(table: str, entry: TableContract, parquet_path: Path) -> tuple[str, ...]:
    try:
        build_table_schema(entry).validate(pl.scan_parquet(parquet_path), lazy=True)
    except SchemaErrors as errors:
        return tuple(
            f"{table}: column {case['column']} has dtype {case['failure_case']}, "
            f"expected {case['check']}"
            for case in errors.failure_cases.iter_rows(named=True)
        )
    return ()


def _key_violations(
    table: str,
    entry: TableContract,
    parquet_path: Path,
    connection: duckdb.DuckDBPyConnection,
) -> tuple[str | None, ...]:
    if entry.primary_key is None:
        return ()
    duplicates = find_duplicate_keys(connection, parquet_path, entry.primary_key)
    return (check_primary_key_unique(table, duplicates.count, duplicates.sample),)


def _target_violations(
    table: str,
    contract: DataContract,
    parquet_path: Path,
    connection: duckdb.DuckDBPyConnection,
) -> tuple[str | None, ...]:
    if table != TARGET_TABLE:
        return ()
    counts = count_target_values(connection, parquet_path, TARGET_COLUMN)
    return (
        check_target_labels(counts.invalid),
        check_target_distribution(counts.positive, counts.total, contract.target_positive_rate),
    )


def _report_measured_coverage(
    contract: DataContract,
    reports: tuple[TableReport, ...],
    resolve_path: Callable[[str], Path],
    connection: duckdb.DuckDBPyConnection,
) -> None:
    tables = (BUREAU_TABLE, BUREAU_BALANCE_TABLE, TARGET_TABLE)
    passed_tables = {report.table for report in reports if report.passed}
    if not passed_tables.issuperset(tables):
        logger.warning("Coverage not measured: %s did not all pass", ", ".join(tables))
        return
    bureau, balance, application = (resolve_path(table) for table in tables)
    report_coverage(
        measure_coverage(connection, bureau, balance, application), contract.expected_coverage
    )


def _log_report(report: TableReport) -> None:
    if not report.passed:
        logger.error("%s failed %s checks", report.table, len(report.violations))
        return
    rows, columns = report.observed_rows, report.observed_columns
    logger.info("%s passed: %s rows, %s columns", report.table, rows, columns)


if __name__ == "__main__":
    main()
