"""Step 3 normalization. One test per value trap, both branches of each.

Every trap in the specification gets its own test, because each one is a distinct way the
raw data lies and a single combined test would pass while one of them regressed.

The sentinel test is the most important in this file. Missing it puts a value equivalent
to a thousand years of employment into every mean, and the resulting statistics look
plausible enough to publish.

The agreed rules this file pins: XNA gender becomes the label Unknown, the income keeps its
original value and gains an outlier flag, and a missing occupation becomes Unknown only
after its missingness flag is set.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import polars as pl
import pytest

from conftest import (
    EMPLOYMENT_SENTINEL,
    EMPLOYMENT_SENTINEL_ROWS,
    EXT_SOURCE_1_NULL_ROWS,
    EXTREME_INCOME,
    FIRST_APPLICATION_ID,
    GENDER_XNA_ROWS,
    INSTALMENT_CASES,
    ORGANIZATION_XNA_ROWS,
    OWN_CAR_AGE_NULL_ROWS,
)
from hcr.config import load_silver_rules
from hcr.silver.clean_application import (
    BUILDING_COMPLETE_FLAG,
    add_missingness_flags,
    assert_application_clean,
    clean_application,
    derive_age_and_tenure,
    flag_income_outliers,
    normalize_application,
    null_employment_sentinel,
    reduce_building_columns,
    replace_unknown_categories,
)
from hcr.silver.clean_history import (
    assert_non_positive_days,
    derive_bureau_balance_status,
    derive_delinquency_flags,
    derive_payment_behaviour,
    derive_utilization,
    normalize_history_table,
    null_days_sentinels,
    null_missing_value_codes,
    strict_days_columns,
)

if TYPE_CHECKING:
    from pathlib import Path

HISTORY_CODES = ("XNA", "XAP")
INCOME_OUTLIER_BASE_ROWS = 1000
MINIMUM_ADULT_AGE = 17.9
MAXIMUM_AGE = 100


def _ids(frame: pl.DataFrame, rows: frozenset[int]) -> list[int]:
    return [FIRST_APPLICATION_ID + row for row in rows if row < len(frame)]


def test_days_employed_sentinel_becomes_null(application_frame: pl.DataFrame) -> None:
    result = null_employment_sentinel(application_frame, load_silver_rules())

    assert (result["DAYS_EMPLOYED"] == EMPLOYMENT_SENTINEL).sum() == 0
    assert result["DAYS_EMPLOYED"].null_count() == len(EMPLOYMENT_SENTINEL_ROWS)


def test_days_employed_sentinel_sets_no_employment_flag(application_frame: pl.DataFrame) -> None:
    result = null_employment_sentinel(application_frame, load_silver_rules())

    flagged = set(result.filter(pl.col("FLAG_NO_EMPLOYMENT") == 1)["SK_ID_CURR"].to_list())
    assert flagged == set(_ids(application_frame, EMPLOYMENT_SENTINEL_ROWS))


def test_no_employment_flag_is_zero_when_days_employed_is_null_for_another_reason(
    application_frame: pl.DataFrame,
) -> None:
    row = 0
    blanked = application_frame.with_columns(
        pl.when(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID + row)
        .then(None)
        .otherwise(pl.col("DAYS_EMPLOYED"))
        .alias("DAYS_EMPLOYED")
    )

    result = null_employment_sentinel(blanked, load_silver_rules())

    assert (
        result.filter(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID + row)[
            "FLAG_NO_EMPLOYMENT"
        ].item()
        == 0
    )


def test_employment_years_is_null_for_sentinel_rows(application_frame: pl.DataFrame) -> None:
    after_sentinel = null_employment_sentinel(application_frame, load_silver_rules())
    result = derive_age_and_tenure(after_sentinel)

    sentinel_rows = result.filter(
        pl.col("SK_ID_CURR").is_in(_ids(application_frame, EMPLOYMENT_SENTINEL_ROWS))
    )
    assert sentinel_rows["EMPLOYMENT_YEARS"].is_null().all()
    assert (result["EMPLOYMENT_YEARS"].drop_nulls() >= 0).all()


def test_days_columns_remain_non_positive(application_frame: pl.DataFrame) -> None:
    rules = load_silver_rules()
    result = normalize_application(application_frame, rules)

    days_columns = [column for column in result.columns if column.startswith("DAYS_")]
    assert days_columns
    for column in days_columns:
        assert (result[column].drop_nulls() <= 0).all(), column


def test_age_years_is_positive_and_plausible(application_frame: pl.DataFrame) -> None:
    result = derive_age_and_tenure(null_employment_sentinel(application_frame, load_silver_rules()))
    age = result["AGE_YEARS"]

    assert (age > MINIMUM_ADULT_AGE).all()
    assert (age < MAXIMUM_AGE).all()


def test_unknown_gender_becomes_unknown_label(application_frame: pl.DataFrame) -> None:
    rules = load_silver_rules()
    result = replace_unknown_categories(application_frame, rules)

    xna_rows = result.filter(pl.col("SK_ID_CURR").is_in(_ids(application_frame, GENDER_XNA_ROWS)))
    assert (xna_rows["CODE_GENDER"] == rules.unknown_label).all()
    assert (result["CODE_GENDER"] == "XNA").sum() == 0
    assert result["CODE_GENDER"].null_count() == 0


def test_known_gender_values_are_unchanged(application_frame: pl.DataFrame) -> None:
    result = replace_unknown_categories(application_frame, load_silver_rules())

    known = ~pl.col("SK_ID_CURR").is_in(_ids(application_frame, GENDER_XNA_ROWS))
    assert result.filter(known)["CODE_GENDER"].to_list() == (
        application_frame.filter(known)["CODE_GENDER"].to_list()
    )


def test_missing_occupation_becomes_unknown_and_keeps_its_flag(
    application_frame: pl.DataFrame,
) -> None:
    rules = load_silver_rules()
    flagged = add_missingness_flags(application_frame, rules)
    result = replace_unknown_categories(flagged, rules)

    null_ids = _ids(application_frame, EMPLOYMENT_SENTINEL_ROWS)
    null_rows = result.filter(pl.col("SK_ID_CURR").is_in(null_ids))
    assert (null_rows["OCCUPATION_TYPE"] == rules.unknown_label).all()
    assert (null_rows["FLAG_MISSING_OCCUPATION"] == 1).all()
    assert (
        result.filter(~pl.col("SK_ID_CURR").is_in(null_ids))["FLAG_MISSING_OCCUPATION"] == 0
    ).all()
    assert result["OCCUPATION_TYPE"].null_count() == 0


def test_organization_type_unknown_is_kept_as_category(application_frame: pl.DataFrame) -> None:
    result = normalize_application(application_frame, load_silver_rules())

    xna_before = (application_frame["ORGANIZATION_TYPE"] == "XNA").sum()
    assert xna_before == len(ORGANIZATION_XNA_ROWS)
    assert (result["ORGANIZATION_TYPE"] == "XNA").sum() == xna_before


def test_income_keeps_original_value_and_outlier_is_flagged() -> None:
    rules = load_silver_rules()
    incomes = [float(value) for value in range(INCOME_OUTLIER_BASE_ROWS)] + [EXTREME_INCOME]
    frame = pl.DataFrame({"SK_ID_CURR": list(range(len(incomes))), "AMT_INCOME_TOTAL": incomes})

    result = flag_income_outliers(frame, rules)

    assert result["AMT_INCOME_TOTAL"].to_list() == incomes
    flag = rules.outlier_flags["AMT_INCOME_TOTAL"].flag
    assert result.filter(pl.col(flag) == 1)["AMT_INCOME_TOTAL"].to_list() == [EXTREME_INCOME]


def test_income_outlier_row_survives(application_frame: pl.DataFrame) -> None:
    result = normalize_application(application_frame, load_silver_rules())

    assert len(result) == len(application_frame)
    assert result["AMT_INCOME_TOTAL"].max() == EXTREME_INCOME


def test_missing_ext_source_keeps_null_and_gains_flag(application_frame: pl.DataFrame) -> None:
    result = add_missingness_flags(application_frame, load_silver_rules())

    null_ids = _ids(application_frame, EXT_SOURCE_1_NULL_ROWS)
    null_rows = result.filter(pl.col("SK_ID_CURR").is_in(null_ids))
    assert null_rows["EXT_SOURCE_1"].is_null().all()
    assert (null_rows["FLAG_MISSING_EXT_SOURCE_1"] == 1).all()
    others = result.filter(~pl.col("SK_ID_CURR").is_in(null_ids))
    assert (others["FLAG_MISSING_EXT_SOURCE_1"] == 0).all()


def test_own_car_age_null_is_not_filled_with_zero(application_frame: pl.DataFrame) -> None:
    result = normalize_application(application_frame, load_silver_rules())

    null_rows = result.filter(
        pl.col("SK_ID_CURR").is_in(_ids(application_frame, OWN_CAR_AGE_NULL_ROWS))
    )
    assert null_rows["OWN_CAR_AGE"].is_null().all()
    assert (null_rows["FLAG_MISSING_OWN_CAR_AGE"] == 1).all()


def test_building_columns_reduced_to_avg_only(application_frame: pl.DataFrame) -> None:
    frame = application_frame.with_columns(
        pl.lit(0.5).alias("APARTMENTS_AVG"),
        pl.lit(0.5).alias("APARTMENTS_MODE"),
        pl.lit(0.5).alias("APARTMENTS_MEDI"),
        pl.lit("block").alias("HOUSETYPE_MODE"),
    )

    result = reduce_building_columns(frame)

    assert "APARTMENTS_AVG" in result.columns
    assert "APARTMENTS_MODE" not in result.columns
    assert "APARTMENTS_MEDI" not in result.columns
    assert "HOUSETYPE_MODE" in result.columns
    assert (result[BUILDING_COMPLETE_FLAG] == 1).all()


def test_building_completeness_flag_is_zero_when_an_average_is_null(
    application_frame: pl.DataFrame,
) -> None:
    frame = application_frame.with_columns(
        pl.when(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID)
        .then(None)
        .otherwise(0.5)
        .alias("APARTMENTS_AVG")
    )

    result = reduce_building_columns(frame)

    assert (
        result.filter(pl.col("SK_ID_CURR") == FIRST_APPLICATION_ID)[BUILDING_COMPLETE_FLAG].item()
        == 0
    )


def test_normalization_preserves_row_count_and_adds_no_null_flag(
    application_frame: pl.DataFrame,
) -> None:
    rules = load_silver_rules()
    result = normalize_application(application_frame, rules)

    assert len(result) == len(application_frame)
    flag_columns = [column for column in result.columns if column.startswith("FLAG_")]
    assert flag_columns
    assert all(result[column].null_count() == 0 for column in flag_columns)


def test_normalization_does_not_mutate_its_input(application_frame: pl.DataFrame) -> None:
    before = application_frame.clone()

    normalize_application(application_frame, load_silver_rules())

    assert application_frame.equals(before)


def test_application_gate_rejects_a_surviving_sentinel(application_frame: pl.DataFrame) -> None:
    with pytest.raises(ValueError, match="sentinel"):
        assert_application_clean(application_frame, load_silver_rules(), len(application_frame))


def test_application_gate_rejects_a_lost_row(application_frame: pl.DataFrame) -> None:
    rules = load_silver_rules()
    silver = normalize_application(application_frame, rules)

    with pytest.raises(ValueError, match="row count"):
        assert_application_clean(silver.head(10), rules, len(application_frame))


def test_application_gate_accepts_a_normalized_table(application_frame: pl.DataFrame) -> None:
    rules = load_silver_rules()
    silver = normalize_application(application_frame, rules)

    assert_application_clean(silver, rules, len(application_frame))


def test_clean_application_refuses_to_overwrite_its_input(
    application_frame: pl.DataFrame, tmp_path: Path
) -> None:
    source = tmp_path / "application_train.parquet"
    application_frame.write_parquet(source)

    with pytest.raises(ValueError, match="overwrite"):
        clean_application(source, source, load_silver_rules())


def test_clean_application_twice_gives_byte_identical_output(
    application_frame: pl.DataFrame, tmp_path: Path
) -> None:
    source = tmp_path / "bronze.parquet"
    application_frame.write_parquet(source)
    rules = load_silver_rules()

    clean_application(source, tmp_path / "first.parquet", rules)
    clean_application(source, tmp_path / "second.parquet", rules)

    assert (tmp_path / "first.parquet").read_bytes() == (tmp_path / "second.parquet").read_bytes()
    assert pl.read_parquet(source).equals(application_frame)


def test_xna_and_xap_become_null_in_history_tables(
    previous_application_frame: pl.DataFrame,
) -> None:
    result = null_missing_value_codes(previous_application_frame, HISTORY_CODES)

    for column in result.select(pl.col(pl.String)).columns:
        for code in HISTORY_CODES:
            assert (result[column] == code).sum() == 0, (column, code)
    assert result["NAME_PAYMENT_TYPE"].null_count() > 0
    assert result["CODE_REJECT_REASON"].null_count() > 0


def test_missing_codes_are_nulled_identically_on_a_lazy_frame(
    previous_application_frame: pl.DataFrame,
) -> None:
    eager = null_missing_value_codes(previous_application_frame, HISTORY_CODES)
    lazy = null_missing_value_codes(previous_application_frame.lazy(), HISTORY_CODES).collect()

    assert eager.equals(lazy)


def test_missing_code_nulling_leaves_numeric_columns_untouched(
    previous_application_frame: pl.DataFrame,
) -> None:
    result = null_missing_value_codes(previous_application_frame, HISTORY_CODES)

    assert result["AMT_CREDIT"].to_list() == previous_application_frame["AMT_CREDIT"].to_list()


def test_history_day_sentinel_becomes_null_and_flagged(
    previous_application_frame: pl.DataFrame,
) -> None:
    columns = ("DAYS_FIRST_DRAWING", "DAYS_TERMINATION")
    result = null_days_sentinels(
        previous_application_frame, columns, EMPLOYMENT_SENTINEL, "FLAG_SENTINEL_{column}"
    )

    for column in columns:
        assert (result[column] == EMPLOYMENT_SENTINEL).sum() == 0
        flagged = result[f"FLAG_SENTINEL_{column}"].sum()
        assert flagged == (previous_application_frame[column] == EMPLOYMENT_SENTINEL).sum()
        assert result[column].null_count() == flagged


def test_non_positive_gate_raises_on_a_positive_offset() -> None:
    frame = pl.DataFrame({"DAYS_CREDIT": [-5, 3], "MONTHS_BALANCE": [0, -1]})

    with pytest.raises(ValueError, match="DAYS_CREDIT"):
        assert_non_positive_days(frame, ("DAYS_CREDIT", "MONTHS_BALANCE"))


def test_non_positive_gate_ignores_nulls_and_absent_columns() -> None:
    frame = pl.DataFrame({"DAYS_CREDIT": [-5, None]})

    assert_non_positive_days(frame, ("DAYS_CREDIT", "DAYS_NOT_IN_THIS_TABLE"))


def test_strict_day_columns_exclude_forward_looking_dates_and_include_months() -> None:
    rules = load_silver_rules()
    strict = strict_days_columns(rules)

    assert "DAYS_CREDIT_ENDDATE" not in strict
    assert "DAYS_LAST_DUE_1ST_VERSION" not in strict
    assert "DAYS_CREDIT" in strict
    assert "MONTHS_BALANCE" in strict


def test_bureau_balance_status_predicates_cover_each_branch(
    bureau_balance_frame: pl.DataFrame,
) -> None:
    result = derive_bureau_balance_status(bureau_balance_frame)

    by_status = {
        row["STATUS"]: (row["STATUS_IS_DPD"], row["STATUS_IS_CLOSED"])
        for row in result.unique("STATUS").to_dicts()
    }
    for status in ("1", "2", "3", "4", "5"):
        assert by_status[status] == (True, False)
    assert by_status["C"] == (False, True)
    assert by_status["0"] == (False, False)
    assert by_status["X"] == (False, False)
    assert by_status[None] == (None, None)


def test_payment_delay_is_positive_when_paid_late(installments_frame: pl.DataFrame) -> None:
    result = derive_payment_behaviour(installments_frame)

    late = INSTALMENT_CASES["late"]
    row = result.filter(pl.col("DAYS_INSTALMENT") == late.days_instalment)
    assert row["PAYMENT_DELAY_DAYS"].item() == late.days_entry_payment - late.days_instalment
    assert row["IS_LATE"].item() is True


def test_early_and_on_time_payments_are_not_late(installments_frame: pl.DataFrame) -> None:
    result = derive_payment_behaviour(installments_frame)

    for name in ("early", "on_time"):
        row = result.filter(pl.col("DAYS_INSTALMENT") == INSTALMENT_CASES[name].days_instalment)
        assert row["IS_LATE"].item() is False


def test_unpaid_instalment_has_null_behaviour(installments_frame: pl.DataFrame) -> None:
    result = derive_payment_behaviour(installments_frame)

    row = result.filter(pl.col("DAYS_INSTALMENT") == INSTALMENT_CASES["unpaid"].days_instalment)
    assert row["PAYMENT_DELAY_DAYS"].item() is None
    assert row["IS_LATE"].item() is None
    assert row["PAYMENT_RATIO"].item() is None


def test_payment_ratio_is_null_when_instalment_is_zero(installments_frame: pl.DataFrame) -> None:
    result = derive_payment_behaviour(installments_frame)

    row = result.filter(
        pl.col("DAYS_INSTALMENT") == INSTALMENT_CASES["zero_instalment"].days_instalment
    )
    assert row["PAYMENT_RATIO"].item() is None
    assert result["PAYMENT_RATIO"].is_infinite().sum() == 0


def test_underpaid_and_overpaid_ratios_sit_on_either_side_of_one(
    installments_frame: pl.DataFrame,
) -> None:
    result = derive_payment_behaviour(installments_frame)

    under = result.filter(
        pl.col("DAYS_INSTALMENT") == INSTALMENT_CASES["underpaid"].days_instalment
    )
    over = result.filter(pl.col("DAYS_INSTALMENT") == INSTALMENT_CASES["overpaid"].days_instalment)
    assert under["IS_UNDERPAID"].item() is True
    assert under["PAYMENT_RATIO"].item() < 1
    assert over["IS_UNDERPAID"].item() is False
    assert over["PAYMENT_RATIO"].item() > 1


def test_utilization_is_null_when_limit_is_zero_and_not_clipped(
    credit_card_frame: pl.DataFrame,
) -> None:
    over_limit = credit_card_frame.with_columns(
        pl.when(pl.col("SK_ID_PREV") == credit_card_frame["SK_ID_PREV"].max())
        .then(pl.col("AMT_CREDIT_LIMIT_ACTUAL") / 2)
        .otherwise(pl.col("AMT_CREDIT_LIMIT_ACTUAL"))
        .alias("AMT_CREDIT_LIMIT_ACTUAL")
    )

    result = derive_utilization(over_limit)

    assert result["UTILIZATION"].is_infinite().sum() == 0
    assert result.filter(pl.col("AMT_CREDIT_LIMIT_ACTUAL") == 0)["UTILIZATION"].is_null().all()
    assert result["UTILIZATION"].max() > 1


def test_delinquency_flag_follows_sk_dpd(pos_cash_frame: pl.DataFrame) -> None:
    result = derive_delinquency_flags(pos_cash_frame)

    assert result.filter(pl.col("SK_DPD") > 0)["IS_DPD"].all()
    assert not result.filter(pl.col("SK_DPD") == 0)["IS_DPD"].any()


@pytest.mark.parametrize(
    ("table", "fixture_name"),
    [
        ("bureau", "bureau_frame"),
        ("bureau_balance", "bureau_balance_frame"),
        ("pos_cash_balance", "pos_cash_frame"),
        ("installments_payments", "installments_frame"),
    ],
)
def test_history_normalization_preserves_row_count(
    table: str, fixture_name: str, request: pytest.FixtureRequest
) -> None:
    frame: pl.DataFrame = request.getfixturevalue(fixture_name)

    result = normalize_history_table(table, frame.lazy(), load_silver_rules()).collect()

    assert len(result) == len(frame)
    flags = [column for column in result.columns if column.startswith("FLAG_")]
    assert all(result[column].null_count() == 0 for column in flags)


def test_previous_application_normalization_nulls_sentinels_and_codes(
    previous_application_frame: pl.DataFrame,
) -> None:
    rules = replace(
        load_silver_rules(),
        history_sentinel_columns={
            "previous_application": ("DAYS_FIRST_DRAWING", "DAYS_TERMINATION")
        },
    )

    result = normalize_history_table(
        "previous_application", previous_application_frame.lazy(), rules
    ).collect()

    assert len(result) == len(previous_application_frame)
    assert (result["DAYS_FIRST_DRAWING"] == EMPLOYMENT_SENTINEL).sum() == 0
    assert (result["NAME_PAYMENT_TYPE"] == "XNA").sum() == 0
    assert "FLAG_NEGATIVE_DOWN_PAYMENT" in result.columns
