"""Step 3 normalization. One test per value trap, both branches of each.

Every trap in the specification gets its own test, because each one is a distinct way the
raw data lies and a single combined test would pass while one of them regressed.

The sentinel test is the most important in this file. Missing it puts a value equivalent
to a thousand years of employment into every mean, and the resulting statistics look
plausible enough to publish.
"""

from __future__ import annotations


def test_days_employed_sentinel_becomes_null() -> None:
    """TODO The 365243 sentinel is replaced with null.

    Assert no row retains the literal value after normalization. This is the condition
    the step 3 gate also checks, and it belongs in both places: the gate catches it on
    real data, this test catches it on an edit.
    """
    raise NotImplementedError


def test_days_employed_sentinel_sets_no_employment_flag() -> None:
    """TODO FLAG_NO_EMPLOYMENT is set on exactly the sentinel rows.

    Assert the flag is 1 where the sentinel was and 0 elsewhere. The flag must come from
    the sentinel match, not from the resulting null: DAYS_EMPLOYED can be null for other
    reasons, and the flag means "not employed", not "value absent".
    """
    raise NotImplementedError


def test_employment_years_is_null_for_sentinel_rows() -> None:
    """TODO EMPLOYMENT_YEARS is null where the sentinel applied.

    Guards the ordering between nulling and deriving. If the derived column is computed
    first, the sentinel becomes a thousand years of tenure and nothing downstream notices.
    """
    raise NotImplementedError


def test_days_columns_remain_non_positive() -> None:
    """TODO Every DAYS_* value is at most zero after normalization.

    These are negative offsets from the application date, so a positive value would be a
    record dated after the decision. Assert across all DAYS_* columns present, not just
    one.
    """
    raise NotImplementedError


def test_age_years_is_positive_and_plausible() -> None:
    """TODO AGE_YEARS is positive and falls in a human range.

    Assert the sign flip happened and the result lies between about 18 and 100. A sign
    error here produces negative ages, which an age band cut would silently bucket into
    the unknown member.
    """
    raise NotImplementedError


def test_unknown_gender_becomes_null_without_replacement() -> None:
    """TODO CODE_GENDER XNA becomes null and no value is substituted.

    Assert the XNA rows are null and that the distribution of the remaining values is
    unchanged. Imputing a protected attribute on four rows would fabricate data the
    fairness report then measures.
    """
    raise NotImplementedError


def test_organization_type_unknown_is_kept_as_category() -> None:
    """TODO ORGANIZATION_TYPE XNA survives normalization as a value.

    The inverse of the gender test, and deliberately so. About 18 percent of rows,
    overlapping the retired population, so it is not missing at random and nulling it would
    discard a real group.
    """
    raise NotImplementedError


def test_income_outlier_is_capped_not_dropped() -> None:
    """TODO The income outlier is winsorized and its row survives.

    Assert the row count is unchanged and the maximum fell to the quantile. Dropping the
    row would bias the sample; the value needs containing, not the applicant.
    """
    raise NotImplementedError


def test_missing_ext_source_keeps_null_and_gains_flag() -> None:
    """TODO EXT_SOURCE_1 nulls survive and the missingness flag is set.

    Assert the column still holds nulls afterwards. Filling it would destroy a signal for
    56 percent of applicants and defeat the reason LightGBM was chosen.
    """
    raise NotImplementedError


def test_own_car_age_null_is_not_filled_with_zero() -> None:
    """TODO OWN_CAR_AGE nulls are not replaced by zero.

    The null means no car; zero would mean a new car. Assert no null became zero, which is
    the single most tempting wrong repair in this dataset.
    """
    raise NotImplementedError


def test_xna_and_xap_become_null_in_history_tables() -> None:
    """TODO Both codes are nulled across the history tables.

    Assert on a string column of a history fixture. Left as literals they become their own
    category in a grouping and dilute a real one.
    """
    raise NotImplementedError


def test_payment_delay_is_positive_when_paid_late() -> None:
    """TODO PAYMENT_DELAY_DAYS is positive for a late payment.

    Assert the sign convention on a known late row. The subtraction order is easy to invert
    and an inverted delay column still produces a plausible model, so the sign needs
    pinning by test rather than by review.
    """
    raise NotImplementedError


def test_payment_ratio_is_null_when_instalment_is_zero() -> None:
    """TODO A zero instalment yields a null ratio, never infinity.

    Assert the guard holds. An infinity reaching the feature matrix stops the step 6 gate,
    which is the right outcome but a worse place to discover it.
    """
    raise NotImplementedError


def test_normalization_preserves_row_count() -> None:
    """TODO Silver output has the same row count as its input.

    Step 3 repairs values and adds columns; it removes no row. Assert for both the
    application and a history table.
    """
    raise NotImplementedError


def test_normalization_does_not_write_into_bronze() -> None:
    """TODO The bronze input file is unchanged after normalization.

    Assert by content hash before and after. No step may overwrite its own input, and this
    is the cheapest place to verify it.
    """
    raise NotImplementedError
