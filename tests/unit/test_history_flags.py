"""History absence flags and row-level quality flags.

The flag polarity is the point of these tests: 1 means no record. A customer missing from
every history table must still get a row, with every flag set, because a null flag would
reach the model as a third state that means nothing.
"""

from __future__ import annotations

import polars as pl
import pytest

from conftest import (
    FIRST_APPLICATION_ID,
    FIXTURE_APPLICATION_ROWS,
    NO_BUREAU_HISTORY_ROWS,
    NO_PREVIOUS_APPLICATION_ROWS,
)
from hcr.config import load_silver_rules
from hcr.silver.flags import (
    CUSTOMER_KEY,
    assert_flags_complete,
    build_presence_flags,
    extract_customer_ids,
)
from hcr.silver.row_flags import (
    add_bureau_flags,
    add_credit_card_flags,
    add_installment_flags,
    add_pos_cash_flags,
)

BUREAU_FLAG = "FLAG_NO_BUREAU_HISTORY"
PREVIOUS_FLAG = "FLAG_NO_PREVIOUS_APPLICATION"


def _application_ids() -> pl.Series:
    return pl.Series(
        CUSTOMER_KEY, [FIRST_APPLICATION_ID + row for row in range(FIXTURE_APPLICATION_ROWS)]
    )


def _flag_frame(flag_values: list[int | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            CUSTOMER_KEY: list(range(len(flag_values))),
            BUREAU_FLAG: pl.Series(flag_values, dtype=pl.Int8),
        }
    )


def test_customer_ids_are_read_directly_when_the_table_carries_them(
    bureau_frame: pl.DataFrame,
) -> None:
    ids = extract_customer_ids(bureau_frame.lazy(), None, None)

    assert set(ids.to_list()) == set(bureau_frame[CUSTOMER_KEY].to_list())
    assert ids.n_unique() == len(ids)


def test_customer_ids_resolve_through_the_parent_when_the_table_lacks_them(
    bureau_balance_frame: pl.DataFrame, bureau_frame: pl.DataFrame
) -> None:
    ids = extract_customer_ids(bureau_balance_frame.lazy(), bureau_frame.lazy(), "SK_ID_BUREAU")

    with_balance = set(bureau_balance_frame["SK_ID_BUREAU"].to_list())
    expected = bureau_frame.filter(pl.col("SK_ID_BUREAU").is_in(with_balance))[CUSTOMER_KEY]
    assert set(ids.to_list()) == set(expected.to_list())


def test_customer_ids_without_key_or_parent_raise(bureau_balance_frame: pl.DataFrame) -> None:
    with pytest.raises(ValueError, match=CUSTOMER_KEY):
        extract_customer_ids(bureau_balance_frame.lazy(), None, None)


def test_presence_flags_mark_exactly_the_customers_without_history(
    bureau_frame: pl.DataFrame, previous_application_frame: pl.DataFrame
) -> None:
    customers = {
        "bureau": bureau_frame[CUSTOMER_KEY].unique(),
        "previous_application": previous_application_frame[CUSTOMER_KEY].unique(),
    }
    names = {"bureau": BUREAU_FLAG, "previous_application": PREVIOUS_FLAG}

    flags = build_presence_flags(_application_ids(), customers, names)

    no_bureau = set(flags.filter(pl.col(BUREAU_FLAG) == 1)[CUSTOMER_KEY].to_list())
    assert no_bureau == {FIRST_APPLICATION_ID + row for row in NO_BUREAU_HISTORY_ROWS}
    no_previous = set(flags.filter(pl.col(PREVIOUS_FLAG) == 1)[CUSTOMER_KEY].to_list())
    assert {FIRST_APPLICATION_ID + row for row in NO_PREVIOUS_APPLICATION_ROWS} <= no_previous


def test_presence_flags_keep_a_row_for_a_customer_absent_from_every_table() -> None:
    flags = build_presence_flags(
        _application_ids(),
        {"bureau": pl.Series(CUSTOMER_KEY, [], dtype=pl.Int64)},
        {"bureau": BUREAU_FLAG},
    )

    assert len(flags) == FIXTURE_APPLICATION_ROWS
    assert (flags[BUREAU_FLAG] == 1).all()
    assert_flags_complete(flags, FIXTURE_APPLICATION_ROWS)


def test_presence_flag_names_come_from_the_silver_rules() -> None:
    rules = load_silver_rules()

    assert rules.history_presence_flags["bureau"] == BUREAU_FLAG
    assert all(name.startswith("FLAG_NO_") for name in rules.history_presence_flags.values())


def test_flag_gate_rejects_a_missing_row() -> None:
    with pytest.raises(ValueError, match="rows"):
        assert_flags_complete(_flag_frame([0, 1]), expected_rows=3)


def test_flag_gate_rejects_a_repeated_customer() -> None:
    repeated = _flag_frame([0, 1]).with_columns(pl.lit(1).alias(CUSTOMER_KEY))

    with pytest.raises(ValueError, match="repeats"):
        assert_flags_complete(repeated, expected_rows=2)


def test_flag_gate_rejects_a_null_flag() -> None:
    with pytest.raises(ValueError, match="nulls"):
        assert_flags_complete(_flag_frame([0, None]), expected_rows=2)


def test_flag_gate_accepts_a_complete_frame() -> None:
    assert_flags_complete(_flag_frame([0, 1]), expected_rows=2)


def test_closed_bureau_loan_without_end_date_is_flagged() -> None:
    frame = pl.DataFrame(
        {
            "CREDIT_ACTIVE": ["Closed", "Closed", "Active"],
            "DAYS_ENDDATE_FACT": [None, -10.0, None],
            "DAYS_CREDIT": [-100.0, -100.0, -100.0],
            "DAYS_CREDIT_ENDDATE": [-50.0, -200.0, None],
            "AMT_CREDIT_SUM_DEBT": [10.0, -5.0, None],
            "AMT_CREDIT_SUM_LIMIT": [0.0, 0.0, -1.0],
        }
    )

    result = add_bureau_flags(frame)

    assert result["FLAG_CLOSED_WITHOUT_END_DATE"].to_list() == [1, 0, 0]
    assert result["FLAG_NEGATIVE_DEBT"].to_list() == [0, 1, 0]
    assert result["FLAG_NEGATIVE_LIMIT"].to_list() == [0, 0, 1]
    assert result["FLAG_PLANNED_END_BEFORE_CREDIT"].to_list() == [0, 1, 0]
    assert result["FLAG_ACTUAL_END_BEFORE_CREDIT"].to_list() == [0, 0, 0]


def test_pos_cash_remaining_instalments_above_total_are_flagged(
    pos_cash_frame: pl.DataFrame,
) -> None:
    widened = pos_cash_frame.with_columns(
        pl.when(pl.col("MONTHS_BALANCE") == -2)
        .then(pl.col("CNT_INSTALMENT") + 1)
        .otherwise(pl.col("CNT_INSTALMENT_FUTURE"))
        .alias("CNT_INSTALMENT_FUTURE")
    )

    result = add_pos_cash_flags(widened)

    exceeding = result.filter(pl.col("MONTHS_BALANCE") == -2)
    assert exceeding["FLAG_FUTURE_INSTALMENTS_EXCEED_TOTAL"].item() == 1
    missing = result.filter(pl.col("CNT_INSTALMENT_FUTURE").is_null())
    assert (missing["FLAG_MISSING_CNT_INSTALMENT_FUTURE"] == 1).all()


def test_installment_with_no_date_and_no_amount_is_flagged(
    installments_frame: pl.DataFrame,
) -> None:
    result = add_installment_flags(installments_frame)

    assert result["FLAG_PAYMENT_INFO_MISSING"].sum() == 1


def test_credit_card_channels_and_negative_drawings_are_flagged() -> None:
    frame = pl.DataFrame(
        {
            "AMT_DRAWINGS_ATM_CURRENT": [None, -5.0, 10.0],
            "AMT_DRAWINGS_OTHER_CURRENT": [None, 0.0, 0.0],
            "AMT_DRAWINGS_POS_CURRENT": [None, 0.0, 0.0],
            "AMT_DRAWINGS_CURRENT": [0.0, -5.0, 10.0],
        }
    )

    result = add_credit_card_flags(frame)

    assert result["FLAG_MISSING_DRAWING_CHANNELS"].to_list() == [1, 0, 0]
    assert result["FLAG_NEGATIVE_DRAWINGS"].to_list() == [0, 1, 0]
