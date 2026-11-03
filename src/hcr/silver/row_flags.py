"""Row-level data-quality flags for the six history tables.

Each flag marks a row whose values contradict each other or fall outside what the field
allows, such as a closed loan with no end date. The row is kept and its values are not
repaired, because a repair would hide the anomaly from the aggregation that might find it
predictive. Flags are never null: a missing input means the condition was not shown, so the
flag is 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeVar

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable

FrameT = TypeVar("FrameT", pl.DataFrame, pl.LazyFrame)

FLAG_DTYPE: Final = pl.Int8
CLOSED_STATUS: Final = "Closed"
DRAWING_CHANNEL_COLUMNS: Final = (
    "AMT_DRAWINGS_ATM_CURRENT",
    "AMT_DRAWINGS_OTHER_CURRENT",
    "AMT_DRAWINGS_POS_CURRENT",
)


def _flag(condition: pl.Expr, name: str) -> pl.Expr:
    return condition.fill_null(False).cast(FLAG_DTYPE).alias(name)


def add_bureau_flags(frame: FrameT) -> FrameT:
    """Flag closed loans without an end date, negative amounts and impossible dates."""
    return frame.with_columns(
        _flag(
            (pl.col("CREDIT_ACTIVE") == CLOSED_STATUS) & pl.col("DAYS_ENDDATE_FACT").is_null(),
            "FLAG_CLOSED_WITHOUT_END_DATE",
        ),
        _flag(pl.col("AMT_CREDIT_SUM_DEBT") < 0, "FLAG_NEGATIVE_DEBT"),
        _flag(pl.col("AMT_CREDIT_SUM_LIMIT") < 0, "FLAG_NEGATIVE_LIMIT"),
        _flag(pl.col("DAYS_ENDDATE_FACT") < pl.col("DAYS_CREDIT"), "FLAG_ACTUAL_END_BEFORE_CREDIT"),
        _flag(
            pl.col("DAYS_CREDIT_ENDDATE") < pl.col("DAYS_CREDIT"), "FLAG_PLANNED_END_BEFORE_CREDIT"
        ),
    )


def add_previous_application_flags(frame: FrameT) -> FrameT:
    """Flag previous applications with a negative down payment."""
    return frame.with_columns(_flag(pl.col("AMT_DOWN_PAYMENT") < 0, "FLAG_NEGATIVE_DOWN_PAYMENT"))


def add_pos_cash_flags(frame: FrameT) -> FrameT:
    """Flag missing remaining instalments and a remaining count above the contract total."""
    return frame.with_columns(
        _flag(pl.col("CNT_INSTALMENT_FUTURE").is_null(), "FLAG_MISSING_CNT_INSTALMENT_FUTURE"),
        _flag(
            pl.col("CNT_INSTALMENT_FUTURE") > pl.col("CNT_INSTALMENT"),
            "FLAG_FUTURE_INSTALMENTS_EXCEED_TOTAL",
        ),
    )


def add_installment_flags(frame: FrameT) -> FrameT:
    """Flag payments recorded with neither a payment date nor a payment amount."""
    return frame.with_columns(
        _flag(
            pl.col("DAYS_ENTRY_PAYMENT").is_null() & pl.col("AMT_PAYMENT").is_null(),
            "FLAG_PAYMENT_INFO_MISSING",
        )
    )


def add_credit_card_flags(frame: FrameT) -> FrameT:
    """Flag months where every drawing channel is missing or a drawing is negative."""
    return frame.with_columns(
        _flag(
            pl.all_horizontal(pl.col(column).is_null() for column in DRAWING_CHANNEL_COLUMNS),
            "FLAG_MISSING_DRAWING_CHANNELS",
        ),
        _flag(
            (pl.col("AMT_DRAWINGS_ATM_CURRENT") < 0) | (pl.col("AMT_DRAWINGS_CURRENT") < 0),
            "FLAG_NEGATIVE_DRAWINGS",
        ),
    )


ROW_FLAGS_BY_TABLE: Final[dict[str, Callable[[pl.LazyFrame], pl.LazyFrame]]] = {
    "bureau": add_bureau_flags,
    "previous_application": add_previous_application_flags,
    "pos_cash_balance": add_pos_cash_flags,
    "installments_payments": add_installment_flags,
    "credit_card_balance": add_credit_card_flags,
}
