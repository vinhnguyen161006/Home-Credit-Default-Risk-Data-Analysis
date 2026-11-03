"""History presence flags, computed once and reused by every later step.

After a LEFT JOIN a customer with no history has nulls across every column of
that source. The null is kept, because absence is a signal, and this flag records
why the null is there. That pair, null plus flag, is what lets the model separate
a thin credit file from a clean history.

About 44020 of 307511 customers (14.3 percent) have no bureau record at all, and
only about 45 percent of bureau loans have monthly rows. Both are properties of the data, not
defects, so the flags are expected to be set for real customers.

Customer resolution never assumes a table carries SK_ID_CURR. A table with the column is
read directly; bureau_balance carries only SK_ID_BUREAU and resolves through bureau. The
three SK_ID_PREV tables do carry SK_ID_CURR in the source, and it agrees with
previous_application wherever both exist. Joining through previous_application instead
would lose the customers of every SK_ID_PREV that table does not list, which measured
340561 POS, 1250826 instalment and 1082816 credit card rows, and would wrongly flag
those customers as having no history.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

import polars as pl

from hcr.config import load_data_contract, load_silver_rules
from hcr.paths import ensure_parent, silver_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hcr.config import DataContract

logger = logging.getLogger(__name__)

CUSTOMER_KEY: Final = "SK_ID_CURR"
APPLICATION_TABLE: Final = "application_train"
FLAGS_TABLE: Final = "history_presence_flags"
FLAG_DTYPE: Final = pl.Int8
BUREAU_COVERAGE_TOLERANCE: Final = 0.05

PARENT_ROUTES: Final = {
    "bureau_balance": ("bureau", "SK_ID_BUREAU"),
    "pos_cash_balance": ("previous_application", "SK_ID_PREV"),
    "installments_payments": ("previous_application", "SK_ID_PREV"),
    "credit_card_balance": ("previous_application", "SK_ID_PREV"),
}


def extract_customer_ids(
    history: pl.LazyFrame, parent: pl.LazyFrame | None, parent_key: str | None
) -> pl.Series:
    """Return the distinct SK_ID_CURR values present in one history table.

    Only identifier columns are read. Scanning 27.3 million full rows to collect a
    distinct id list would be wasted work.

    Args:
        history: History table as a lazy plan.
        parent: Parent table to resolve through, used only when history lacks SK_ID_CURR.
        parent_key: Column joining history to parent.

    Returns:
        Distinct, non-null customer identifiers.

    Raises:
        ValueError: If history lacks SK_ID_CURR and no parent route is supplied.
    """
    if CUSTOMER_KEY in history.collect_schema().names():
        ids = history.select(CUSTOMER_KEY)
    elif parent is not None and parent_key is not None:
        ids = (
            history.select(parent_key)
            .unique()
            .join(parent.select(parent_key, CUSTOMER_KEY), on=parent_key, how="inner")
        )
    else:
        raise ValueError(f"History table has no {CUSTOMER_KEY} and no parent route")
    return ids.select(CUSTOMER_KEY).drop_nulls().unique().collect().get_column(CUSTOMER_KEY)


def customers_with_history(table: str) -> pl.Series:
    """Read one silver history table and return the customers that appear in it.

    This function reads Parquet because the identifier scan is column-pruned and lazy; it
    is the one place that touches the silver files for this step.

    Args:
        table: Logical history table name.

    Returns:
        Distinct customer identifiers present in that table.
    """
    route = PARENT_ROUTES.get(table)
    parent = pl.scan_parquet(silver_path(route[0])) if route else None
    return extract_customer_ids(
        pl.scan_parquet(silver_path(table)), parent, route[1] if route else None
    )


def build_presence_flags(
    application_ids: pl.Series,
    customers_by_table: Mapping[str, pl.Series],
    flag_names: Mapping[str, str],
) -> pl.DataFrame:
    """Build one absence flag per history source for every application.

    The flag is named for absence: 1 means the customer has no record in that source.
    The polarity sits in the name so a reader of a SHAP plot is not left guessing which
    direction means "no history".

    Args:
        application_ids: All SK_ID_CURR values in application_train.
        customers_by_table: Customers present in each source table.
        flag_names: Source table to the name of its absence flag.

    Returns:
        One row per application, including those absent from every history table, so the
        frame joins onto the feature matrix without introducing a null flag.
    """
    absence = (
        (~application_ids.is_in(customers_by_table[table])).cast(FLAG_DTYPE).alias(flag)
        for table, flag in flag_names.items()
    )
    return pl.DataFrame({CUSTOMER_KEY: application_ids}).with_columns(*absence)


def assert_flags_complete(flags: pl.DataFrame, expected_rows: int) -> None:
    """Assert the flag frame covers every application exactly once.

    A null flag would propagate into the model as a third state that means nothing.

    Raises:
        ValueError: If the row count differs from expected_rows, SK_ID_CURR repeats, or
            any flag is null.
    """
    if len(flags) != expected_rows:
        raise ValueError(f"Flag frame has {len(flags)} rows, expected {expected_rows}")
    if flags[CUSTOMER_KEY].n_unique() != len(flags):
        raise ValueError(f"{CUSTOMER_KEY} repeats in the flag frame")
    null_counts = flags.null_count().row(0, named=True)
    nulls = {column: count for column, count in null_counts.items() if count}
    if nulls:
        raise ValueError(f"Flag frame holds nulls: {nulls}")


def warn_on_bureau_coverage_shift(
    flags: pl.DataFrame, bureau_flag: str, contract: DataContract
) -> None:
    """Warn when the share of customers without bureau history departs from the contract.

    A jump means a join key changed, not that customers changed.
    """
    coverage = contract.expected_coverage
    expected = coverage["train_customers_total"] - coverage["train_customers_with_bureau_history"]
    observed = int(flags[bureau_flag].sum())
    if abs(observed - expected) > expected * BUREAU_COVERAGE_TOLERANCE:
        logger.warning(
            "%s set for %s customers, contract expects %s", bureau_flag, observed, expected
        )


def build_history_flags() -> int:
    """Write the absence flags for every application into the silver layer.

    Returns:
        Rows written.
    """
    rules = load_silver_rules()
    contract = load_data_contract()
    application_ids = (
        pl.scan_parquet(silver_path(APPLICATION_TABLE))
        .select(CUSTOMER_KEY)
        .collect()
        .get_column(CUSTOMER_KEY)
    )
    flag_names = rules.history_presence_flags
    customers = {table: customers_with_history(table) for table in flag_names}

    flags = build_presence_flags(application_ids, customers, flag_names)
    assert_flags_complete(flags, expected_rows=len(application_ids))
    warn_on_bureau_coverage_shift(flags, flag_names["bureau"], contract)

    flags.write_parquet(ensure_parent(silver_path(FLAGS_TABLE)))
    logger.info("Wrote %s rows to %s", len(flags), silver_path(FLAGS_TABLE))
    return len(flags)


def main() -> None:
    """Save one history-absence flag per source for each application."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_history_flags()


if __name__ == "__main__":
    main()
