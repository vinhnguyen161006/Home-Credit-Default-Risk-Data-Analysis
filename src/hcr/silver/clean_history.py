"""Step 3 for the six history tables: normalize codes and assert sign.

The history tables need less repair than the application table but the same
discipline. XNA and XAP act as missing values here, DAYS_* and MONTHS_BALANCE
must stay non-positive, and derived behavioural columns are computed once at
silver so every aggregation reads the same definition.

Grain is preserved. These tables stay at loan, contract or event grain; folding
to customer grain is step 5. Every table is processed as a Polars lazy plan and
streamed to Parquet, so the 27.3 million row bureau_balance never has to fit in
memory.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final, TypeVar

import polars as pl
import polars.selectors as cs

from hcr.config import load_silver_rules
from hcr.paths import bronze_path, ensure_parent, silver_path
from hcr.silver.row_flags import ROW_FLAGS_BY_TABLE

if TYPE_CHECKING:
    from collections.abc import Callable

    from hcr.config import SilverRules

logger = logging.getLogger(__name__)

FrameT = TypeVar("FrameT", pl.DataFrame, pl.LazyFrame)

HISTORY_TABLES: Final = (
    "bureau",
    "bureau_balance",
    "previous_application",
    "pos_cash_balance",
    "installments_payments",
    "credit_card_balance",
)

BUREAU_DPD_STATUSES: Final = ("1", "2", "3", "4", "5")
BUREAU_CLOSED_STATUS: Final = "C"
MONTHS_COLUMN: Final = "MONTHS_BALANCE"
FLAG_DTYPE: Final = pl.Int8


def null_missing_value_codes(frame: FrameT, codes: tuple[str, ...]) -> FrameT:
    """Replace XNA and XAP with null across every string column.

    Both strings act as missing values in these tables. Left as literals they
    would become their own category in any grouping and dilute a real one.
    ORGANIZATION_TYPE lives in the application table, which this function never
    receives, so its deliberate XNA category is untouched.

    Args:
        frame: History table at its original grain.
        codes: Strings to treat as null, from the silver rules.

    Returns:
        Frame with every listed code replaced by null in string columns only.
    """
    string_columns = cs.string()
    return frame.with_columns(
        pl.when(string_columns.is_in(list(codes))).then(None).otherwise(string_columns).name.keep()
    )


def null_days_sentinels(
    frame: FrameT, columns: tuple[str, ...], sentinel: int, flag_template: str
) -> FrameT:
    """Replace the 365243 convention code with null and flag the rows it marked.

    Args:
        frame: History table holding the listed columns.
        columns: DAYS_* columns that use the sentinel.
        sentinel: The code value, shared with DAYS_EMPLOYED.
        flag_template: Flag name pattern with a column placeholder.

    Returns:
        Frame with the sentinel nulled and one flag per column.
    """
    flags = (
        pl.col(column)
        .eq(sentinel)
        .fill_null(False)
        .cast(FLAG_DTYPE)
        .alias(flag_template.format(column=column))
        for column in columns
    )
    nulled = (
        pl.when(pl.col(column) == sentinel).then(None).otherwise(pl.col(column)).alias(column)
        for column in columns
    )
    return frame.with_columns(*flags, *nulled)


def strict_days_columns(rules: SilverRules) -> tuple[str, ...]:
    """Return the offset columns that must be non-positive, MONTHS_BALANCE included.

    Columns holding legitimately forward-looking dates are excluded, as the silver rules
    explain.
    """
    exempt = set(rules.forward_looking_days_columns)
    strict = tuple(column for column in rules.days_columns if column not in exempt)
    return (*strict, MONTHS_COLUMN)


def assert_non_positive_days(frame: pl.DataFrame | pl.LazyFrame, columns: tuple[str, ...]) -> None:
    """Assert every DAYS_* and MONTHS_BALANCE value is at most zero.

    These columns are negative offsets from the application date, so they contain
    only past information. A positive value would mean a row recorded after the
    decision, which is leakage arriving through the data rather than through
    processing. It raises instead of clipping, because a positive offset means the
    source changed and clipping would hide that.

    Args:
        frame: Table to check, eager or lazy.
        columns: Candidate columns; those absent from the frame are skipped, since the
            list spans every table. Nulls are ignored.

    Raises:
        ValueError: If any value exceeds zero, naming the column and the count.
    """
    lazy = frame.lazy()
    available = lazy.collect_schema().names()
    present = [column for column in columns if column in available]
    if not present:
        return
    positives = lazy.select((pl.col(column) > 0).sum().alias(column) for column in present)
    counts = positives.collect().row(0, named=True)
    violations = {column: count for column, count in counts.items() if count}
    if violations:
        raise ValueError(f"Positive day offsets after normalization: {violations}")


def derive_bureau_balance_status(frame: FrameT) -> FrameT:
    """Turn the bureau_balance STATUS code into two boolean columns.

    STATUS is a single-character code per month. Defining the delinquency and
    closure predicates once here keeps the step 5 SQL from restating the code
    list, which is how two aggregations come to disagree about what counts as
    delinquent. Both stay null where STATUS is null, because a month with no
    record is not a month without delinquency.

    Args:
        frame: bureau_balance table with STATUS.

    Returns:
        Frame with STATUS_IS_DPD and STATUS_IS_CLOSED added.
    """
    status = pl.col("STATUS")

    def predicate(condition: pl.Expr, name: str) -> pl.Expr:
        return pl.when(status.is_null()).then(None).otherwise(condition).alias(name)

    return frame.with_columns(
        predicate(status.is_in(list(BUREAU_DPD_STATUSES)), "STATUS_IS_DPD"),
        predicate(status == BUREAU_CLOSED_STATUS, "STATUS_IS_CLOSED"),
    )


def derive_payment_behaviour(frame: FrameT) -> FrameT:
    """Add the features that measure repayment behaviour directly.

    installments_payments is an event table, not a monthly one: each row is an
    actual payment. That is what makes delay measurable per transaction, and
    these columns are the system's most direct behavioural signal. The delay
    and the ratio are both kept: one measures timing, the other amount, and a
    borrower can fail either independently.

    PAYMENT_DELAY_DAYS is positive when paid late. PAYMENT_RATIO is null where
    AMT_INSTALMENT is zero, because infinity would stop the step 6 gate.

    Args:
        frame: installments_payments table.

    Returns:
        Frame with PAYMENT_DELAY_DAYS, IS_LATE, PAYMENT_RATIO and IS_UNDERPAID.
    """
    ratio = (
        pl.when(pl.col("AMT_INSTALMENT") == 0)
        .then(None)
        .otherwise(pl.col("AMT_PAYMENT") / pl.col("AMT_INSTALMENT"))
    )
    return frame.with_columns(
        (pl.col("DAYS_ENTRY_PAYMENT") - pl.col("DAYS_INSTALMENT")).alias("PAYMENT_DELAY_DAYS"),
        ratio.alias("PAYMENT_RATIO"),
    ).with_columns(
        (pl.col("PAYMENT_DELAY_DAYS") > 0).alias("IS_LATE"),
        (pl.col("PAYMENT_RATIO") < 1).alias("IS_UNDERPAID"),
    )


def derive_utilization(frame: FrameT) -> FrameT:
    """Add credit card utilisation as balance over limit.

    Not clipped above 1: over-limit balances occur and the excess is exactly the risk
    signal. Null where the limit is zero, negative or missing.

    Args:
        frame: credit_card_balance table.

    Returns:
        Frame with UTILIZATION added.
    """
    limit = pl.col("AMT_CREDIT_LIMIT_ACTUAL")
    return frame.with_columns(
        pl.when(limit > 0).then(pl.col("AMT_BALANCE") / limit).otherwise(None).alias("UTILIZATION")
    )


def derive_delinquency_flags(frame: FrameT) -> FrameT:
    """Add IS_DPD for the tables carrying an SK_DPD day counter.

    Shared by pos_cash_balance and credit_card_balance. SK_DPD_DEF stays a
    distinct column; the tolerance-adjusted counter carries different information.

    Args:
        frame: Table with SK_DPD.

    Returns:
        Frame with IS_DPD, null where SK_DPD is null.
    """
    return frame.with_columns((pl.col("SK_DPD") > 0).alias("IS_DPD"))


TABLE_DERIVATIONS: Final[dict[str, tuple[Callable[[pl.LazyFrame], pl.LazyFrame], ...]]] = {
    "bureau_balance": (derive_bureau_balance_status,),
    "installments_payments": (derive_payment_behaviour,),
    "credit_card_balance": (derive_utilization, derive_delinquency_flags),
    "pos_cash_balance": (derive_delinquency_flags,),
}


def normalize_history_table(table: str, frame: pl.LazyFrame, rules: SilverRules) -> pl.LazyFrame:
    """Apply the shared steps and then the derivations of one history table.

    Args:
        table: Logical table name, one of HISTORY_TABLES.
        frame: Bronze table as a lazy plan.
        rules: Parsed silver rules.

    Returns:
        Lazy plan of the silver table; it adds columns and removes no row.
    """
    frame = null_days_sentinels(
        frame,
        rules.history_sentinel_columns.get(table, ()),
        rules.employment_sentinel["value"],
        rules.history_sentinel_flag_template,
    )
    frame = null_missing_value_codes(frame, rules.missing_value_codes)
    if table in ROW_FLAGS_BY_TABLE:
        frame = ROW_FLAGS_BY_TABLE[table](frame)
    for derive in TABLE_DERIVATIONS.get(table, ()):
        frame = derive(frame)
    return frame


def clean_table(table: str, rules: SilverRules) -> int:
    """Normalize one history table from bronze into silver.

    Reads bronze lazily and streams the result to a new silver file, so the step does
    not depend on available memory and never writes into the bronze directory.

    Args:
        table: Logical table name.
        rules: Parsed silver rules.

    Returns:
        Rows written.

    Raises:
        ValueError: If the table is unknown, a day offset is positive, or the output row
            count differs from the input.
    """
    if table not in HISTORY_TABLES:
        raise ValueError(f"{table} is not a history table")

    source = bronze_path(table)
    plan = normalize_history_table(table, pl.scan_parquet(source), rules)
    assert_non_positive_days(plan, strict_days_columns(rules))

    destination = silver_path(table)
    plan.sink_parquet(ensure_parent(destination))

    input_rows = pl.scan_parquet(source).select(pl.len()).collect().item()
    output_rows = pl.scan_parquet(destination).select(pl.len()).collect().item()
    if output_rows != input_rows:
        raise ValueError(f"{table}: wrote {output_rows} rows from {input_rows}")
    logger.info("Wrote %s rows to %s", output_rows, destination)
    return int(output_rows)


def run() -> dict[str, int]:
    """Normalize all six history tables.

    Tables run in HISTORY_TABLES order. Every table is checked against the rules before
    it is written, so a configuration mistake fails at the first table it affects.

    Returns:
        Table name to rows written.
    """
    rules = load_silver_rules()
    return {table: clean_table(table, rules) for table in HISTORY_TABLES}


def main() -> None:
    """Normalize every history table into silver."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()


if __name__ == "__main__":
    main()
