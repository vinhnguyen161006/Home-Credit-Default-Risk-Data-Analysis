"""The shared fixtures carry every trap they promise.

A fixture that silently loses its trap rows makes every normalization test pass without
testing anything, so the traps themselves are asserted here.
"""

from __future__ import annotations

import duckdb
import polars as pl
import pytest
from sklearn.metrics import roc_auc_score

from conftest import (
    BUREAU_ID_WITHOUT_BALANCE,
    EMPLOYMENT_SENTINEL,
    EXTREME_INCOME,
    FIRST_APPLICATION_ID,
    FIXTURE_APPLICATION_ROWS,
    MISSING_CATEGORY_CODE,
    NO_BUREAU_HISTORY_ROWS,
    NO_PREVIOUS_APPLICATION_ROWS,
    NOT_APPLICABLE_CODE,
    PREVIOUS_ID_WITHOUT_BALANCE,
    SINGLE_MONTH_BUREAU_ID,
    ScoredCase,
)
from hcr.config import load_data_contract

TARGET_RATE_LOWER_BOUND = 0.05
TARGET_RATE_UPPER_BOUND = 0.12
DELINQUENT_STATUS_CODES = {"1", "2", "3", "4", "5"}


def test_application_fixture_has_unique_ids_and_both_classes(
    application_frame: pl.DataFrame,
) -> None:
    assert application_frame.height == FIXTURE_APPLICATION_ROWS
    assert application_frame["SK_ID_CURR"].is_unique().all()
    positive_rate = application_frame["TARGET"].mean()
    assert isinstance(positive_rate, float)
    assert TARGET_RATE_LOWER_BOUND < positive_rate < TARGET_RATE_UPPER_BOUND


def test_application_fixture_declares_every_required_column(
    application_frame: pl.DataFrame,
) -> None:
    required = load_data_contract().tables["application_train"].required_columns

    assert set(required) <= set(application_frame.columns)


def test_application_fixture_carries_the_seven_value_traps(
    application_frame: pl.DataFrame,
) -> None:
    assert (application_frame["DAYS_EMPLOYED"] == EMPLOYMENT_SENTINEL).any()
    assert (application_frame["CODE_GENDER"] == MISSING_CATEGORY_CODE).any()
    assert (application_frame["ORGANIZATION_TYPE"] == MISSING_CATEGORY_CODE).any()
    assert (application_frame["AMT_INCOME_TOTAL"] == EXTREME_INCOME).any()
    assert application_frame["EXT_SOURCE_1"].null_count() > 0
    assert application_frame["OWN_CAR_AGE"].null_count() > 0
    assert (application_frame["DAYS_BIRTH"] < 0).all()


def test_application_fixture_days_are_negative_outside_the_sentinel(
    application_frame: pl.DataFrame,
) -> None:
    employed = application_frame.filter(pl.col("DAYS_EMPLOYED") != EMPLOYMENT_SENTINEL)

    assert (employed["DAYS_EMPLOYED"] < 0).all()
    assert (application_frame["DAYS_REGISTRATION"] <= 0).all()


def test_bureau_fixture_leaves_customers_without_history(bureau_frame: pl.DataFrame) -> None:
    covered = set(bureau_frame["SK_ID_CURR"])

    for row in NO_BUREAU_HISTORY_ROWS:
        assert FIRST_APPLICATION_ID + row not in covered
    assert bureau_frame["SK_ID_BUREAU"].is_unique().all()


def test_bureau_balance_fixture_covers_every_status_branch(
    bureau_frame: pl.DataFrame, bureau_balance_frame: pl.DataFrame
) -> None:
    statuses = set(bureau_balance_frame["STATUS"].drop_nulls())

    assert statuses >= DELINQUENT_STATUS_CODES | {"C", "X"}
    assert bureau_balance_frame["STATUS"].null_count() > 0
    assert set(bureau_balance_frame["SK_ID_BUREAU"]) <= set(bureau_frame["SK_ID_BUREAU"])
    assert BUREAU_ID_WITHOUT_BALANCE in set(bureau_frame["SK_ID_BUREAU"])
    assert BUREAU_ID_WITHOUT_BALANCE not in set(bureau_balance_frame["SK_ID_BUREAU"])


def test_bureau_balance_fixture_has_a_single_month_loan(
    bureau_balance_frame: pl.DataFrame,
) -> None:
    months = bureau_balance_frame.filter(pl.col("SK_ID_BUREAU") == SINGLE_MONTH_BUREAU_ID)

    assert months.height == 1


def test_previous_application_fixture_carries_history_traps(
    previous_application_frame: pl.DataFrame,
) -> None:
    text_values = set(previous_application_frame["NAME_PAYMENT_TYPE"]) | set(
        previous_application_frame["CODE_REJECT_REASON"]
    )

    assert {MISSING_CATEGORY_CODE, NOT_APPLICABLE_CODE} <= text_values
    assert (previous_application_frame["DAYS_FIRST_DRAWING"] == EMPLOYMENT_SENTINEL).any()
    for row in NO_PREVIOUS_APPLICATION_ROWS:
        assert FIRST_APPLICATION_ID + row not in set(previous_application_frame["SK_ID_CURR"])


def test_balance_fixtures_leave_a_previous_loan_without_rows(
    pos_cash_frame: pl.DataFrame, credit_card_frame: pl.DataFrame
) -> None:
    assert PREVIOUS_ID_WITHOUT_BALANCE not in set(pos_cash_frame["SK_ID_PREV"])
    assert PREVIOUS_ID_WITHOUT_BALANCE not in set(credit_card_frame["SK_ID_PREV"])
    assert (credit_card_frame["AMT_CREDIT_LIMIT_ACTUAL"] == 0).any()


def test_installments_fixture_covers_timing_and_amount_boundaries(
    installments_frame: pl.DataFrame,
) -> None:
    paid = installments_frame.drop_nulls("DAYS_ENTRY_PAYMENT")
    delay = paid["DAYS_ENTRY_PAYMENT"] - paid["DAYS_INSTALMENT"]
    shortfall = paid["AMT_PAYMENT"] - paid["AMT_INSTALMENT"]

    assert (delay > 0).any()
    assert (delay < 0).any()
    assert (delay == 0).any()
    assert (shortfall < 0).any()
    assert (shortfall > 0).any()
    assert (installments_frame["AMT_INSTALMENT"] == 0).any()


@pytest.mark.parametrize("case_name", ["separable", "random", "partial"])
def test_scored_case_expected_auc_matches_sklearn(
    predictions_and_labels: dict[str, ScoredCase], case_name: str
) -> None:
    case = predictions_and_labels[case_name]

    assert roc_auc_score(case.labels, case.probabilities) == pytest.approx(case.expected_auc)


def test_miscalibrated_case_overstates_the_base_rate(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["miscalibrated"]

    assert case.probabilities.mean() > 2 * case.labels.mean()
    assert roc_auc_score(case.labels, case.probabilities) > 0.5


def test_duckdb_connection_is_in_memory(duckdb_connection: duckdb.DuckDBPyConnection) -> None:
    result = duckdb_connection.execute("SELECT 1").fetchone()

    assert result == (1,)
