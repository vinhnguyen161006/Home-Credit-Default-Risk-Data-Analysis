"""Step 5 aggregation. The row count and null handling are what matter here.

Two properties carry most of the risk. A join that fans out multiplies rows and every
per-customer metric computed afterwards is wrong. A null coalesced to zero erases the
distinction between a customer who borrowed nothing and one who never borrowed, which is
the distinction this whole problem is about.

Tests run against the small fixtures through an in-memory DuckDB connection, so the real
27.3 million row table is never read.
"""

from __future__ import annotations


def test_aggregation_yields_one_row_per_customer() -> None:
    """TODO The assembled matrix has exactly one row per application id.

    Assert the row count equals the fixture application count and that SK_ID_CURR is
    unique. This is the step 5 gate, and a fan-out is the defect it exists to catch.
    """
    raise NotImplementedError


def test_left_join_keeps_customers_without_bureau_history() -> None:
    """TODO A customer with no bureau row survives the join.

    The fixture includes such a customer deliberately. An INNER JOIN would drop them, and on
    the real data it would drop more than half the external loan history.
    """
    raise NotImplementedError


def test_missing_history_yields_null_not_zero() -> None:
    """TODO Aggregates are null, not zero, for a customer with no history.

    The central rule of the whole system. Assert on a BURO_ column for the customer the
    fixture leaves out of bureau. A zero here would claim they borrowed nothing.
    """
    raise NotImplementedError


def test_history_presence_flag_is_set_for_missing_history() -> None:
    """TODO FLAG_NO_BUREAU_HISTORY is 1 for that same customer.

    The null and the flag are a pair: the null carries the absence into the model, the flag
    records why. Assert both together, since either alone is incomplete.
    """
    raise NotImplementedError


def test_count_of_key_is_zero_not_one_when_no_child_rows() -> None:
    """TODO A count over the key yields zero for a customer with no child rows.

    COUNT(*) after a LEFT JOIN returns one for a non-matching row, which silently claims one
    loan where there are none. Assert the count column uses the key.
    """
    raise NotImplementedError


def test_two_stage_fold_preserves_loan_without_balance_rows() -> None:
    """TODO A bureau loan with no monthly rows survives the stage one join.

    Mirrors the real 48 percent coverage. Assert the loan appears in the stage two output
    with null balance aggregates rather than being dropped.
    """
    raise NotImplementedError


def test_regr_slope_is_null_for_single_observation() -> None:
    """TODO A trend over one point is null, not zero.

    A slope needs two points. Zero would assert a flat trajectory where none is measurable,
    and a model would read that as a real signal.
    """
    raise NotImplementedError


def test_window_filter_uses_days_not_months_for_days_columns() -> None:
    """TODO A three-month window on a DAYS_ column spans 90 days.

    The unit confusion that produces a window thirty times too wide while the resulting
    column still looks entirely plausible. Assert against a fixture row that falls inside
    90 days but outside 3.
    """
    raise NotImplementedError


def test_window_filter_uses_months_for_months_balance() -> None:
    """TODO A three-month window on MONTHS_BALANCE spans 3 units.

    The other half of the same confusion. Assert both directions so neither convention can
    drift into the other.
    """
    raise NotImplementedError


def test_ratio_guards_against_zero_denominator() -> None:
    """TODO Every application ratio yields null, not infinity, on a zero denominator.

    Assert for each of the six ratios. The step 6 gate stops on infinity, so a missing guard
    here fails the pipeline later and further from its cause.
    """
    raise NotImplementedError


def test_column_names_follow_the_naming_contract() -> None:
    """TODO Generated names match PREFIX_COLUMN_AGG and the windowed variant.

    Assert the prefix is from the fixed set and the window suffix is present where expected.
    With 500 to 800 columns, a naming drift is invisible by inspection and breaks the
    manifest aggregation that explanations depend on.
    """
    raise NotImplementedError


def test_manifest_records_provenance_for_every_column() -> None:
    """TODO Every matrix column has a manifest entry naming its source and aggregation.

    Assert the column sets match exactly, both directions. A column without provenance
    cannot be interpreted, and a manifest entry without a column means the generator and the
    record disagree.
    """
    raise NotImplementedError


def test_manifest_is_byte_identical_across_two_runs() -> None:
    """TODO Two runs on identical inputs produce an identical manifest.

    Underpins the reproducibility acceptance criterion. Assert equality of the written bytes,
    which catches unsorted keys and embedded timestamps.
    """
    raise NotImplementedError


def test_no_ext_source_configuration_excludes_the_columns() -> None:
    """TODO The no_ext_source matrix contains no EXT_SOURCE column or flag.

    Assert both the value columns and their missingness flags are absent. A leftover flag
    still leaks which applicants had a score, which is part of what the configuration is
    measuring the absence of.
    """
    raise NotImplementedError


def test_aggregation_requires_holdout_file_to_exist() -> None:
    """TODO Building features without a holdout file raises.

    The ordering guard. Aggregating before the split is the primary leakage source, and the
    check is one line, so assert it is actually there.
    """
    raise NotImplementedError
