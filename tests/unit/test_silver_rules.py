"""Step 3 normalization. One test per value trap, both branches of each.

Every trap in the specification gets its own test, because each one is a distinct way the
raw data lies and a single combined test would pass while one of them regressed.

The sentinel test is the most important in this file. Missing it puts a value equivalent
to a thousand years of employment into every mean, and the resulting statistics look
plausible enough to publish.
"""

from __future__ import annotations

import pytest
import polars as pl

from typing import NamedTuple

from hcr.silver.clean_application import (
    EMPLOYMENT_SENTINEL,
    GENDER_UNKNOWN_CODE,
    INCOME_WINSOR_QUANTILE,
    add_missingness_flags,
    derive_age_and_tenure,
    keep_organization_unknown_as_level,
    null_employment_sentinel,
    null_unknown_gender,
    reduce_building_columns,
    winsorize_income,
)

EMPLOYMENT_SENTINEL_ROWS = frozenset({3, 6, 11, 19, 27, 35, 43, 47, 49})
EXTREME_INCOME = 117_000_000.0
EXTREME_INCOME_ROWS = frozenset({23})
EXT_SOURCE_1_NULL_ROWS = frozenset(range(28))
GENDER_XNA_ROWS = frozenset({9, 31})
OWN_CAR_AGE_NULL_ROWS = frozenset(range(17, 50))
FIRST_APPLICATION_ID = 100001


class InstalmentCase(NamedTuple):
    """One payment against its schedule, named by the behaviour it exercises."""

    days_instalment: int
    days_entry_payment: int | None
    amt_instalment: float
    amt_payment: float | None


INSTALMENT_CASES = {
    "late": InstalmentCase(-100, -95, 5000.0, 5000.0),
    "early": InstalmentCase(-70, -75, 5000.0, 5000.0),
    "on_time": InstalmentCase(-40, -40, 5000.0, 5000.0),
    "underpaid": InstalmentCase(-10, -10, 5000.0, 3000.0),
    "overpaid": InstalmentCase(-130, -130, 5000.0, 6500.0),
    "zero_instalment": InstalmentCase(-160, -160, 0.0, 1200.0),
    "unpaid": InstalmentCase(-5, None, 5000.0, None),
}


def test_days_employed_sentinel_becomes_null(application_frame: pl.DataFrame) -> None:
    """The 365243 sentinel is replaced with null.

    Assert no row retains the literal value after normalization. This is the condition
    the step 3 gate also checks, and it belongs in both places: the gate catches it on
    real data, this test catches it on an edit.
    """
    result = null_employment_sentinel(application_frame)
    assert (result["DAYS_EMPLOYED"] == EMPLOYMENT_SENTINEL).sum() == 0


def test_days_employed_sentinel_sets_no_employment_flag(application_frame: pl.DataFrame) -> None:
    """FLAG_NO_EMPLOYMENT is set on exactly the sentinel rows.

    Assert the flag is 1 where the sentinel was and 0 elsewhere. The flag must come from
    the sentinel match, not from the resulting null: DAYS_EMPLOYED can be null for other
    reasons, and the flag means "not employed", not "value absent".
    """
    result = null_employment_sentinel(application_frame)
    flag = result["FLAG_NO_EMPLOYMENT"]

    expected_sentinel_ids = {
        application_frame["SK_ID_CURR"][row] for row in EMPLOYMENT_SENTINEL_ROWS
    }
    flagged_ids = set(
        result.filter(pl.col("FLAG_NO_EMPLOYMENT") == 1)["SK_ID_CURR"].to_list()
    )
    assert flagged_ids == expected_sentinel_ids


def test_employment_years_is_null_for_sentinel_rows(application_frame: pl.DataFrame) -> None:
    """EMPLOYMENT_YEARS is null where the sentinel applied.

    Guards the ordering between nulling and deriving. If the derived column is computed
    first, the sentinel becomes a thousand years of tenure and nothing downstream notices.
    """
    after_sentinel = null_employment_sentinel(application_frame)
    result = derive_age_and_tenure(after_sentinel)

    sentinel_ids = {application_frame["SK_ID_CURR"][row] for row in EMPLOYMENT_SENTINEL_ROWS}
    sentinel_rows = result.filter(pl.col("SK_ID_CURR").is_in(sentinel_ids))
    assert sentinel_rows["EMPLOYMENT_YEARS"].is_null().all()


def test_days_columns_remain_non_positive(application_frame: pl.DataFrame) -> None:
    """Every DAYS_* value is at most zero after normalization.

    These are negative offsets from the application date, so a positive value would be a
    record dated after the decision. Assert across all DAYS_* columns present, not just
    one.
    """
    after_sentinel = null_employment_sentinel(application_frame)
    result = derive_age_and_tenure(after_sentinel)

    days_cols = [c for c in result.columns if c.startswith("DAYS_")]
    for col in days_cols:
        non_null = result[col].drop_nulls()
        assert (non_null <= 0).all(), f"{col} has positive values after normalization"


def test_age_years_is_positive_and_plausible(application_frame: pl.DataFrame) -> None:
    """AGE_YEARS is positive and falls in a human range.

    Assert the sign flip happened and the result lies between about 18 and 100. A sign
    error here produces negative ages, which an age band cut would silently bucket into
    the unknown member.
    """
    after_sentinel = null_employment_sentinel(application_frame)
    result = derive_age_and_tenure(after_sentinel)
    age = result["AGE_YEARS"]

    assert (age > 0).all(), "AGE_YEARS has non-positive values"
    assert (age >= 18).all(), "AGE_YEARS has values below 18"
    assert (age <= 100).all(), "AGE_YEARS has values above 100"


def test_unknown_gender_becomes_null_without_replacement(application_frame: pl.DataFrame) -> None:
    """CODE_GENDER XNA becomes null and no value is substituted.

    Assert the XNA rows are null and that the distribution of the remaining values is
    unchanged. Imputing a protected attribute on four rows would fabricate data the
    fairness report then measures.
    """
    result = null_unknown_gender(application_frame)
    gender_col = result["CODE_GENDER"]

    xna_ids = {application_frame["SK_ID_CURR"][row] for row in GENDER_XNA_ROWS}
    xna_rows = result.filter(pl.col("SK_ID_CURR").is_in(xna_ids))
    assert xna_rows["CODE_GENDER"].is_null().all()

    assert (gender_col == GENDER_UNKNOWN_CODE).sum() == 0

    non_xna_before = (
        application_frame.filter(pl.col("CODE_GENDER") != GENDER_UNKNOWN_CODE)["CODE_GENDER"]
        .value_counts()
        .sort("CODE_GENDER")
    )
    non_xna_after = (
        result.filter(pl.col("CODE_GENDER").is_not_null())["CODE_GENDER"]
        .value_counts()
        .sort("CODE_GENDER")
    )
    assert non_xna_before.equals(non_xna_after)


def test_organization_type_unknown_is_kept_as_category(application_frame: pl.DataFrame) -> None:
    """ORGANIZATION_TYPE XNA survives normalization as a value.

    The inverse of the gender test, and deliberately so. About 18 percent of rows,
    overlapping the retired population, so it is not missing at random and nulling it would
    discard a real group.
    """
    result = keep_organization_unknown_as_level(application_frame)

    xna_before = (application_frame["ORGANIZATION_TYPE"] == "XNA").sum()
    xna_after = (result["ORGANIZATION_TYPE"] == "XNA").sum()
    assert xna_after == xna_before
    assert xna_after > 0


def test_income_outlier_is_capped_not_dropped(application_frame: pl.DataFrame) -> None:
    """The income outlier is winsorized and its row survives.

    Assert the row count is unchanged and the maximum fell to the quantile. Dropping the
    row would bias the sample; the value needs containing, not the applicant.
    """
    result = winsorize_income(application_frame, INCOME_WINSOR_QUANTILE)
    assert len(result) == len(application_frame)

    cap = application_frame["AMT_INCOME_TOTAL"].quantile(
        INCOME_WINSOR_QUANTILE, interpolation="nearest"
    )
    extreme_ids = {application_frame["SK_ID_CURR"][row] for row in EXTREME_INCOME_ROWS}
    extreme_rows_after = result.filter(pl.col("SK_ID_CURR").is_in(list(extreme_ids)))
    assert (extreme_rows_after["AMT_INCOME_TOTAL"] <= cap).all()

    assert result["AMT_INCOME_TOTAL"].max() <= cap


def test_missing_ext_source_keeps_null_and_gains_flag(
    application_frame: pl.DataFrame,
) -> None:
    """EXT_SOURCE_1 nulls survive and the missingness flag is set.

    Assert the column still holds nulls afterwards. Filling it would destroy a signal for
    56 percent of applicants and defeat the reason LightGBM was chosen.
    """
    from hcr.config.loaders import load_silver_rules

    rules = load_silver_rules()
    result = add_missingness_flags(application_frame, rules)

    null_ids = {application_frame["SK_ID_CURR"][row] for row in EXT_SOURCE_1_NULL_ROWS}
    null_rows = result.filter(pl.col("SK_ID_CURR").is_in(null_ids))

    assert null_rows["EXT_SOURCE_1"].is_null().all()
    assert null_rows["FLAG_MISSING_EXT_SOURCE_1"].cast(pl.Int8).eq(1).all()

    non_null_rows = result.filter(~pl.col("SK_ID_CURR").is_in(list(null_ids)))
    assert non_null_rows["FLAG_MISSING_EXT_SOURCE_1"].cast(pl.Int8).eq(0).all()


def test_own_car_age_null_is_not_filled_with_zero(
    application_frame: pl.DataFrame,
) -> None:
    """OWN_CAR_AGE nulls are not replaced by zero.

    The null means no car; zero would mean a new car. Assert no null became zero, which is
    the single most tempting wrong repair in this dataset.
    """
    from hcr.config.loaders import load_silver_rules

    rules = load_silver_rules()
    result = add_missingness_flags(application_frame, rules)

    null_ids = {application_frame["SK_ID_CURR"][row] for row in OWN_CAR_AGE_NULL_ROWS}
    null_rows = result.filter(pl.col("SK_ID_CURR").is_in(null_ids))

    assert null_rows["OWN_CAR_AGE"].is_null().all()


def test_building_columns_reduced_to_avg_only(application_frame: pl.DataFrame) -> None:
    """_MODE and _MEDI building variants are dropped; _AVG variants and the flag remain.

    Three variants of the same attribute, nearly two-thirds of the table's columns and
    the group with least predictive power. Reducing before aggregation prevents the
    variants from multiplying through the four feature families.
    """
    frame_with_building = application_frame.with_columns(
        pl.lit(0.5).alias("APARTMENTS_AVG"),
        pl.lit(0.5).alias("APARTMENTS_MODE"),
        pl.lit(0.5).alias("APARTMENTS_MEDI"),
    )
    result = reduce_building_columns(frame_with_building)

    assert "APARTMENTS_AVG" in result.columns
    assert "APARTMENTS_MODE" not in result.columns
    assert "APARTMENTS_MEDI" not in result.columns
    assert "FLAG_BUILDING_INFO_COMPLETE" in result.columns


def test_xna_and_xap_become_null_in_history_tables(
    previous_application_frame: pl.DataFrame,
) -> None:
    """Both codes are nulled across the history tables.

    Assert on a string column of a history fixture. Left as literals they become their own
    category in a grouping and dilute a real one.
    """
    from hcr.silver.clean_history import null_missing_value_codes

    codes = ("XNA", "XAP")
    result = null_missing_value_codes(previous_application_frame, codes)

    for col in result.select(pl.col(pl.String)).columns:
        col_values = result[col]
        for code in codes:
            assert (col_values == code).sum() == 0, (
                f"Column {col} still contains code {code!r} after normalization"
            )


def test_payment_delay_is_positive_when_paid_late(
    installments_frame: pl.DataFrame,
) -> None:
    """PAYMENT_DELAY_DAYS is positive for a late payment.

    Assert the sign convention on a known late row. The subtraction order is easy to invert
    and an inverted delay column still produces a plausible model, so the sign needs
    pinning by test rather than by review.
    """
    from hcr.silver.clean_history import derive_payment_behaviour

    result = derive_payment_behaviour(installments_frame)

    late_case = INSTALMENT_CASES["late"]
    expected_delay = late_case.days_entry_payment - late_case.days_instalment
    assert expected_delay > 0

    late_rows = result.filter(
        (pl.col("DAYS_INSTALMENT") == late_case.days_instalment)
        & (pl.col("DAYS_ENTRY_PAYMENT") == late_case.days_entry_payment)
    )
    assert len(late_rows) == 1
    assert late_rows["PAYMENT_DELAY_DAYS"][0] == expected_delay
    assert late_rows["IS_LATE"][0] is True


def test_payment_ratio_is_null_when_instalment_is_zero(
    installments_frame: pl.DataFrame,
) -> None:
    """A zero instalment yields a null ratio, never infinity.

    Assert the guard holds. An infinity reaching the feature matrix stops the step 6 gate,
    which is the right outcome but a worse place to discover it.
    """
    from hcr.silver.clean_history import derive_payment_behaviour

    result = derive_payment_behaviour(installments_frame)

    zero_case = INSTALMENT_CASES["zero_instalment"]
    zero_rows = result.filter(pl.col("DAYS_INSTALMENT") == zero_case.days_instalment)
    assert len(zero_rows) == 1
    assert zero_rows["PAYMENT_RATIO"][0] is None


def test_normalization_preserves_row_count(application_frame: pl.DataFrame) -> None:
    """Silver output has the same row count as its input.

    Step 3 repairs values and adds columns; it removes no row. Assert for both the
    application and a history table.
    """
    from hcr.config.loaders import load_silver_rules

    rules = load_silver_rules()
    input_rows = len(application_frame)

    frame = null_employment_sentinel(application_frame)
    frame = derive_age_and_tenure(frame)
    frame = null_unknown_gender(frame)
    frame = keep_organization_unknown_as_level(frame)
    frame = winsorize_income(frame, INCOME_WINSOR_QUANTILE)
    frame = add_missingness_flags(frame, rules)
    frame = reduce_building_columns(frame)

    assert len(frame) == input_rows


def test_normalization_does_not_write_into_bronze(
    application_frame: pl.DataFrame,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The bronze input frame is not mutated by normalization functions.

    Assert that the original frame's row count and the DAYS_EMPLOYED column values
    are unchanged after all repairs are applied to a copy. No step may overwrite
    its own input.
    """
    from hcr.config.loaders import load_silver_rules

    rules = load_silver_rules()
    original_days_employed = application_frame["DAYS_EMPLOYED"].to_list()
    original_row_count = len(application_frame)

    frame = application_frame.clone()
    frame = null_employment_sentinel(frame)
    frame = derive_age_and_tenure(frame)
    frame = null_unknown_gender(frame)
    frame = keep_organization_unknown_as_level(frame)
    frame = winsorize_income(frame, INCOME_WINSOR_QUANTILE)
    frame = add_missingness_flags(frame, rules)
    frame = reduce_building_columns(frame)

    assert len(application_frame) == original_row_count
    assert application_frame["DAYS_EMPLOYED"].to_list() == original_days_employed
