"""Step 3 for the six history tables: normalize codes and assert sign.

The history tables need less repair than the application table but the same
discipline. XNA and XAP act as missing values here, DAYS_* and MONTHS_BALANCE
must stay non-positive, and derived behavioural columns are computed once at
silver so every aggregation reads the same definition.

Grain is preserved. These tables stay at loan, contract or event grain; folding
to customer grain is step 5.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import polars as pl

    from hcr.config import SilverRules

logger = logging.getLogger(__name__)

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


def null_missing_value_codes(
    frame: pl.DataFrame,
    codes: tuple[str, ...],
) -> pl.DataFrame:
    """Replace XNA and XAP with null across every string column.

    Both strings act as missing values in these tables. Left as literals they
    would become their own category in any grouping and dilute a real one.

    Args:
        frame: History table at its original grain.
        codes: Strings to treat as null, from the silver rules.

    TODO:
        - Apply to string columns only. A numeric column holding the literal
          "XNA" would already have failed the step 2 dtype check.
        - Do not touch ORGANIZATION_TYPE, which keeps XNA as a deliberate
          category. That column lives in the application table, so this function
          never sees it, but assert the exclusion if the tables are ever merged.
    """
    raise NotImplementedError


def assert_non_positive_days(frame: pl.DataFrame, columns: tuple[str, ...]) -> None:
    """Assert every DAYS_* and MONTHS_BALANCE value is at most zero.

    These columns are negative offsets from the application date, so they contain
    only past information. A positive value would mean a row recorded after the
    decision, which is leakage arriving through the data rather than through
    processing.

    Raises:
        ValueError: If any value exceeds zero, naming the column and the count.

    TODO:
        - Check only the columns present in this frame; the list spans all
          tables.
        - Ignore nulls, which are legitimate for DAYS_CREDIT_ENDDATE on a loan
          with no recorded end.
        - Raise rather than repair. A positive offset means the source changed
          and silently clipping it would hide that.
    """
    raise NotImplementedError


def derive_bureau_balance_status(frame: pl.DataFrame) -> pl.DataFrame:
    """Turn the bureau_balance STATUS code into two boolean columns.

    STATUS is a single-character code per month. Defining the delinquency and
    closure predicates once here keeps the step 5 SQL from restating the code
    list, which is how two aggregations come to disagree about what counts as
    delinquent.

    TODO:
        - Add STATUS_IS_DPD as STATUS in BUREAU_DPD_STATUSES.
        - Add STATUS_IS_CLOSED as STATUS equals BUREAU_CLOSED_STATUS.
        - Leave both null where STATUS is null, rather than defaulting to false.
          A month with no record is not a month without delinquency.
    """
    raise NotImplementedError


def derive_payment_behaviour(frame: pl.DataFrame) -> pl.DataFrame:
    """Add the two features that measure repayment behaviour directly.

    installments_payments is an event table, not a monthly one: each row is an
    actual payment. That is what makes delay measurable per transaction, and
    these two columns are the system's most direct behavioural signal, with no
    intermediate variable between them and the outcome.

    TODO:
        - Add PAYMENT_DELAY_DAYS as DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT, where
          positive means paid late.
        - Add IS_LATE as PAYMENT_DELAY_DAYS greater than zero.
        - Add PAYMENT_RATIO as AMT_PAYMENT / AMT_INSTALMENT, below 1 meaning
          underpaid, and IS_UNDERPAID from the same comparison.
        - Null PAYMENT_RATIO where AMT_INSTALMENT is zero. Dividing by zero would
          produce infinity and the step 6 gate stops on any infinite value.
        - Keep both the delay and the ratio. One measures timing, the other
          measures amount, and a borrower can fail either way independently.
    """
    raise NotImplementedError


def derive_utilization(frame: pl.DataFrame) -> pl.DataFrame:
    """Add credit card utilisation as balance over limit.

    TODO:
        - Add UTILIZATION as AMT_BALANCE / AMT_CREDIT_LIMIT_ACTUAL, null where
          the limit is zero or null.
        - Do not clip above 1. Over-limit balances occur and the excess is
          exactly the risk signal.
    """
    raise NotImplementedError


def derive_delinquency_flags(frame: pl.DataFrame) -> pl.DataFrame:
    """Add IS_DPD for the tables carrying an SK_DPD day counter.

    Shared by pos_cash_balance and credit_card_balance.

    TODO:
        - Add IS_DPD as SK_DPD greater than zero, null where SK_DPD is null.
        - Keep SK_DPD_DEF distinct from SK_DPD rather than merging them; the
          tolerance-adjusted counter carries different information.
    """
    raise NotImplementedError


def clean_table(table: str, rules: SilverRules) -> int:
    """Normalize one history table from bronze into silver.

    Args:
        table: Logical table name.
        rules: Parsed silver rules.

    Returns:
        Rows written.

    TODO:
        - Dispatch the table-specific derivations by name: bureau_balance gets
          the status predicates, installments_payments the payment behaviour,
          credit_card_balance utilisation and delinquency, pos_cash_balance
          delinquency only.
        - Apply the shared steps to every table: null the missing value codes,
          then assert non-positive days.
        - Assert the output row count equals the input. This step adds columns and
          nulls values; it removes no row.
        - For bureau_balance at 27.3 million rows, process through DuckDB or a
          Polars lazy scan rather than a materialised frame, so the step does not
          depend on available RAM.
    """
    raise NotImplementedError


def run() -> dict[str, int]:
    """Normalize all six history tables.

    Returns:
        Table name to rows written.

    TODO:
        - Process the tables in HISTORY_TABLES order, smallest first, so a
          configuration mistake fails before the largest table runs.
        - Never write into the bronze directory.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.silver.clean_history`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
