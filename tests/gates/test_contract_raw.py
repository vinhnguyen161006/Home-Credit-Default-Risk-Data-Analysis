"""Step 2 gate. Every gate gets a passing and a failing case.

A gate tested only on valid data proves nothing: it would pass equally if its body were
`return True`. Each test here therefore comes in a pair, and the failing half is the one that
matters. Each test writes small Parquet files and derives the contract from the very frame it
writes, so exactly one property is broken at a time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

import polars as pl
import pyarrow.parquet as pq
import pytest

from conftest import (
    BUREAU_STATUS_HISTORIES,
    FIRST_APPLICATION_ID,
    FIXTURE_APPLICATION_ROWS,
    NO_BUREAU_HISTORY_ROWS,
    POSITIVE_TARGET_ROWS,
)
from hcr.config import DataContract, TableContract
from hcr.contracts import validate_raw
from hcr.contracts.validate_raw import ContractViolationError, TableReport

if TYPE_CHECKING:
    from pathlib import Path

POLARS_DTYPE_ALIASES: Final = {pl.Int64: "int", pl.Float64: "float", pl.String: "str"}
FIXTURE_POSITIVE_RATE: Final = len(POSITIVE_TARGET_ROWS) / FIXTURE_APPLICATION_ROWS
SHIFTED_POSITIVE_RATE: Final = 0.2
INVALID_TARGET_VALUE: Final = 2
APPLICATION_KEY: Final = ("SK_ID_CURR",)
BUREAU_KEY: Final = ("SK_ID_BUREAU",)
BALANCE_KEY: Final = ("SK_ID_BUREAU", "MONTHS_BALANCE")


def table_contract(
    frame: pl.DataFrame,
    primary_key: tuple[str, ...] | None,
    forbidden_columns: tuple[str, ...] = (),
) -> TableContract:
    return TableContract(
        file="unused.csv",
        rows=frame.height,
        columns=frame.width,
        primary_key=primary_key,
        required_columns=(),
        forbidden_columns=forbidden_columns,
        dtypes={name: POLARS_DTYPE_ALIASES[dtype] for name, dtype in frame.schema.items()},
    )


def data_contract(
    tables: dict[str, TableContract],
    positive_rate: float = FIXTURE_POSITIVE_RATE,
    coverage: dict[str, int] | None = None,
) -> DataContract:
    return DataContract(
        tables=tables,
        expected_coverage={} if coverage is None else coverage,
        target_positive_rate=positive_rate,
    )


def write_tables(directory: Path, frames: dict[str, pl.DataFrame]) -> None:
    for table, frame in frames.items():
        frame.write_parquet(directory / f"{table}.parquet")


def run_in(directory: Path, contract: DataContract) -> tuple[TableReport, ...]:
    return validate_raw.run(contract, lambda table: directory / f"{table}.parquet")


def violation_message(directory: Path, contract: DataContract) -> str:
    with pytest.raises(ContractViolationError) as raised:
        run_in(directory, contract)
    return str(raised.value)


def test_matching_row_count_passes(tmp_path: Path, application_frame: pl.DataFrame) -> None:
    write_tables(tmp_path, {"application_train": application_frame})
    contract = data_contract(
        {"application_train": table_contract(application_frame, APPLICATION_KEY)}
    )

    (report,) = run_in(tmp_path, contract)

    assert report.passed
    assert report.observed_rows == FIXTURE_APPLICATION_ROWS


def test_wrong_row_count_stops_the_pipeline(tmp_path: Path, bureau_frame: pl.DataFrame) -> None:
    """A row count one short of the contract raises.

    Exact equality, no tolerance. A truncated download is the realistic cause, and a tolerance
    would let it through to silently change every reported metric.
    """
    write_tables(tmp_path, {"bureau": bureau_frame.head(bureau_frame.height - 1)})
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    message = violation_message(tmp_path, contract)

    assert (
        f"{bureau_frame.height - 1} rows vs {bureau_frame.height} expected, short by 1" in message
    )


def test_wrong_column_count_stops_the_pipeline(tmp_path: Path, bureau_frame: pl.DataFrame) -> None:
    """A missing column raises and the message names it.

    A bare count difference sends the reader back to the YAML to work out which column vanished.
    """
    write_tables(tmp_path, {"bureau": bureau_frame.drop("CREDIT_TYPE")})
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    message = violation_message(tmp_path, contract)

    assert "short by 1" in message
    assert "missing columns CREDIT_TYPE" in message


def test_duplicate_primary_key_stops_the_pipeline(
    tmp_path: Path, application_frame: pl.DataFrame
) -> None:
    """A duplicated SK_ID_CURR raises.

    A duplicate multiplies rows through every join and would surface as a step 5 failure far
    from its cause.
    """
    duplicated = application_frame.with_columns(
        pl.when(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID + 1)
        .then(FIRST_APPLICATION_ID)
        .otherwise(pl.col("SK_ID_CURR"))
        .alias("SK_ID_CURR")
    )
    write_tables(tmp_path, {"application_train": duplicated})
    contract = data_contract(
        {"application_train": table_contract(application_frame, APPLICATION_KEY)}
    )

    message = violation_message(tmp_path, contract)

    assert f"1 primary key values repeat, for example ({FIRST_APPLICATION_ID},)" in message


def test_missing_primary_key_declaration_skips_uniqueness_check(
    tmp_path: Path, installments_frame: pl.DataFrame
) -> None:
    """A table declaring no primary key passes without a uniqueness check.

    installments_payments is an event table with no natural key. Asserting one would fail on
    entirely valid data, so the null declaration must be honoured rather than treated as an
    omission.
    """
    assert installments_frame["SK_ID_PREV"].is_duplicated().any()
    write_tables(tmp_path, {"installments_payments": installments_frame})
    contract = data_contract({"installments_payments": table_contract(installments_frame, None)})

    (report,) = run_in(tmp_path, contract)

    assert report.passed


def test_forbidden_target_column_in_test_set_stops_the_pipeline(
    tmp_path: Path, application_frame: pl.DataFrame
) -> None:
    """A TARGET column in application_test raises.

    Its presence would mean the file is not the unlabelled test set the contract describes, and
    every statement about measuring on a self-made holdout would be wrong.
    """
    write_tables(tmp_path, {"application_test": application_frame})
    test_contract = table_contract(
        application_frame, APPLICATION_KEY, forbidden_columns=("TARGET",)
    )
    contract = data_contract({"application_test": test_contract})

    message = violation_message(tmp_path, contract)

    assert "application_test: forbidden columns present TARGET" in message


def test_target_outside_zero_and_one_stops_the_pipeline(
    tmp_path: Path, application_frame: pl.DataFrame
) -> None:
    """A TARGET value of 2 raises.

    A third label value breaks the stratified split and the AUC computation, both quietly.
    """
    relabelled = application_frame.with_columns(
        pl.when(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID)
        .then(INVALID_TARGET_VALUE)
        .otherwise(pl.col("TARGET"))
        .alias("TARGET")
    )
    write_tables(tmp_path, {"application_train": relabelled})
    contract = data_contract(
        {"application_train": table_contract(application_frame, APPLICATION_KEY)}
    )

    message = violation_message(tmp_path, contract)

    assert "1 TARGET values are null or outside 0 and 1" in message


def test_shifted_target_rate_stops_the_pipeline(
    tmp_path: Path, application_frame: pl.DataFrame
) -> None:
    """A positive rate far from 8.07 percent raises.

    A shifted rate means the label column changed, which invalidates the cost threshold and every
    baseline reference figure.
    """
    write_tables(tmp_path, {"application_train": application_frame})
    contract = data_contract(
        {"application_train": table_contract(application_frame, APPLICATION_KEY)},
        positive_rate=SHIFTED_POSITIVE_RATE,
    )

    message = violation_message(tmp_path, contract)

    assert "TARGET positive rate 8.000% vs 20.000% expected" in message


def test_coverage_gap_is_reported_as_warning_not_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    application_frame: pl.DataFrame,
    bureau_frame: pl.DataFrame,
    bureau_balance_frame: pl.DataFrame,
) -> None:
    """A coverage figure that moved logs a warning and does not raise.

    Fewer than half of bureau loans have monthly rows. That is a property of the data and the
    reason every join is a LEFT JOIN; treating a change in it as a failure would block every
    valid run.
    """
    frames = {
        "application_train": application_frame,
        "bureau": bureau_frame,
        "bureau_balance": bureau_balance_frame,
    }
    write_tables(tmp_path, frames)
    keys = {
        "application_train": APPLICATION_KEY,
        "bureau": BUREAU_KEY,
        "bureau_balance": BALANCE_KEY,
    }
    coverage = {
        "bureau_rows_total": bureau_frame.height,
        "bureau_rows_with_balance": len(BUREAU_STATUS_HISTORIES) + 1,
        "train_customers_total": FIXTURE_APPLICATION_ROWS,
        "train_customers_with_bureau_history": FIXTURE_APPLICATION_ROWS
        - len(NO_BUREAU_HISTORY_ROWS),
    }
    contract = data_contract(
        {table: table_contract(frame, keys[table]) for table, frame in frames.items()},
        coverage=coverage,
    )

    with caplog.at_level(logging.INFO):
        reports = run_in(tmp_path, contract)

    assert all(report.passed for report in reports)
    warnings = [
        record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert warnings == [
        f"Coverage bureau_rows_with_balance is {len(BUREAU_STATUS_HISTORIES)}, "
        f"expected {len(BUREAU_STATUS_HISTORIES) + 1}"
    ]


def test_all_violations_are_reported_in_one_run(tmp_path: Path, bureau_frame: pl.DataFrame) -> None:
    """A table failing three conditions reports all three.

    Raising on the first turns fixing a contract into an iterative guessing game.
    """
    broken = pl.concat([bureau_frame, bureau_frame.head(1)]).drop("CREDIT_TYPE")
    write_tables(tmp_path, {"bureau": broken})
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    message = violation_message(tmp_path, contract)

    assert "rows vs" in message
    assert "missing columns CREDIT_TYPE" in message
    assert "primary key values repeat" in message


def test_gate_runs_without_loading_full_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bureau_frame: pl.DataFrame
) -> None:
    """Row counts and dtypes come from Parquet metadata, not from a full read.

    Parquet carries the count in its footer. Reading 27.3 million rows to count them would make
    the gate too slow to run routinely, which is how a gate stops being run.
    """

    def refuse_full_read(*_: object, **__: object) -> None:
        raise AssertionError("the gate loaded a full frame")

    monkeypatch.setattr(pq, "read_table", refuse_full_read)
    monkeypatch.setattr(pq.ParquetFile, "read", refuse_full_read)
    monkeypatch.setattr(pl, "read_parquet", refuse_full_read)
    monkeypatch.setattr(pl.LazyFrame, "collect", refuse_full_read)
    write_tables(tmp_path, {"bureau": bureau_frame})
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    (report,) = run_in(tmp_path, contract)

    assert report.passed
    assert report.observed_rows == bureau_frame.height


def test_absent_bronze_file_stops_the_pipeline(tmp_path: Path, bureau_frame: pl.DataFrame) -> None:
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    message = violation_message(tmp_path, contract)

    assert "bureau: bronze file" in message
    assert "run make ingest first" in message


def test_wrong_dtype_stops_the_pipeline(tmp_path: Path, bureau_frame: pl.DataFrame) -> None:
    write_tables(
        tmp_path, {"bureau": bureau_frame.with_columns(pl.col("AMT_ANNUITY").cast(pl.String))}
    )
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})

    message = violation_message(tmp_path, contract)

    assert "bureau: column AMT_ANNUITY has dtype String, expected dtype('Float64')" in message


def test_repeated_run_gives_the_same_reports_and_writes_nothing(
    tmp_path: Path, bureau_frame: pl.DataFrame
) -> None:
    write_tables(tmp_path, {"bureau": bureau_frame})
    contract = data_contract({"bureau": table_contract(bureau_frame, BUREAU_KEY)})
    files_before = {path: path.stat().st_mtime_ns for path in tmp_path.iterdir()}

    first = run_in(tmp_path, contract)
    second = run_in(tmp_path, contract)

    assert first == second
    assert {path: path.stat().st_mtime_ns for path in tmp_path.iterdir()} == files_before


def test_main_exits_with_failure_status_on_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise ContractViolationError("bureau: 1 rows vs 2 expected, short by 1")

    monkeypatch.setattr(validate_raw, "run", fail)

    with pytest.raises(SystemExit) as raised:
        validate_raw.main()

    assert raised.value.code == validate_raw.EXIT_FAILURE


def test_main_returns_normally_when_every_table_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate_raw, "run", tuple)

    validate_raw.main()
