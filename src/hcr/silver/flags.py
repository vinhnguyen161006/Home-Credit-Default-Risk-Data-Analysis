"""History presence flags, computed once and reused by every later step.

After a LEFT JOIN a customer with no history has nulls across every column of
that source. The null is kept, because absence is a signal, and this flag records
why the null is there. That pair, null plus flag, is what lets the model separate
a thin credit file from a clean history.

About 1700 of 307511 customers have no bureau record at all, and only about 48
percent of bureau loans have monthly rows. Both are properties of the data, not
defects, so the flags are expected to be set for real customers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pandas as pd

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)

PRESENCE_FLAGS: Final = {
    "bureau": "FLAG_NO_BUREAU_HISTORY",
    "previous_application": "FLAG_NO_PREVIOUS_APPLICATION",
    "pos_cash_balance": "FLAG_NO_POS_CASH_HISTORY",
    "installments_payments": "FLAG_NO_INSTALMENT_HISTORY",
    "credit_card_balance": "FLAG_NO_CREDIT_CARD_HISTORY",
}

EXPECTED_CUSTOMERS_WITHOUT_BUREAU: Final = 1700


def customers_with_history(table: str) -> pl.Series:
    """Return the distinct SK_ID_CURR values appearing in one history table.

    Args:
        table: Logical history table name.

    Returns:
        Distinct customer identifiers present in that table.

    TODO:
        - For bureau and previous_application, read SK_ID_CURR directly.
        - For the three third-level tables, resolve SK_ID_CURR through
          previous_application on SK_ID_PREV. They carry no customer column, which
          is the same reason their features need two folds.
        - Read only the identifier columns. Scanning 27.3 million full rows to
          collect a distinct id list is wasted work.
    """
    raise NotImplementedError


def build_presence_flags(application_ids: pl.Series) -> pl.DataFrame:
    """Build one presence flag per history source for every application.

    Args:
        application_ids: All SK_ID_CURR values in application_train.

    Returns:
        One row per application, one flag column per source, flag set to 1 where
        that source holds no record for the customer.

    TODO:
        - Produce a row for every application id, including those absent from
          every history table. The flag frame joins onto the feature matrix, so a
          customer missing here would acquire a null flag, which is the one state
          the flag exists to prevent.
        - Name the flag for absence, not presence, matching PRESENCE_FLAGS. The
          polarity is stated in the name so a reader of a SHAP plot is not left
          guessing which direction means "no history".
        - Assert the bureau flag is set for roughly EXPECTED_CUSTOMERS_WITHOUT_
          BUREAU customers and warn on a large deviation, since a jump means a
          join key changed.
    """
    raise NotImplementedError


def assert_flags_complete(flags: pl.DataFrame, expected_rows: int) -> None:
    """Assert the flag frame covers every application exactly once.

    Raises:
        ValueError: If the row count differs from expected_rows or any flag is
            null.

    TODO:
        - Check the row count, the uniqueness of SK_ID_CURR, and that no flag
          column holds a null. A null flag would propagate into the model as a
          third state that means nothing.
    """
    raise NotImplementedError


def main() -> None:
    """Save one history-absence flag per source for each application."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    silver_directory = Path(__file__).resolve().parents[3] / "data" / "silver"

    application_path = silver_directory / "application_train.parquet"
    flags = pd.read_parquet(application_path, columns=["SK_ID_CURR"])

    if flags["SK_ID_CURR"].isna().any():
        raise ValueError("Missing application IDs")

    if not flags["SK_ID_CURR"].is_unique:
        raise ValueError("Duplicate application IDs")

    sources = {
        "bureau": "FLAG_NO_BUREAU_HISTORY",
        "previous_application": "FLAG_NO_PREVIOUS_APPLICATION",
        "POS_CASH_balance": "FLAG_NO_POS_CASH_HISTORY",
        "installments_payments": "FLAG_NO_INSTALMENT_HISTORY",
        "credit_card_balance": "FLAG_NO_CREDIT_CARD_HISTORY",
    }

    for table, flag_column in sources.items():
        history = pd.read_parquet(
            silver_directory / f"{table}.parquet",
            columns=["SK_ID_CURR"],
        )

        flags[flag_column] = ~flags["SK_ID_CURR"].isin(history["SK_ID_CURR"])

        logger.info(
            "%s: %s applications without history",
            table,
            flags[flag_column].sum(),
        )

        del history

    destination = silver_directory / "application_history_flags.parquet"
    flags.to_parquet(destination, index=False)

    logger.info("Saved history flags to %s", destination)


if __name__ == "__main__":
    main()
