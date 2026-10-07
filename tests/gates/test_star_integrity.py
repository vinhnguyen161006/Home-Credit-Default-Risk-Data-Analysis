"""Step 8 gates: referential integrity and the fact row count.

Both failures produce a report that renders cleanly and states something false, which is why they
are gated at the database layer rather than trusted to the build step. A blank dimension row or a
truncated fact table looks like a data finding rather than a load defect.

Tests that need a live SQL Server are marked integration so the default suite runs without
Docker.
"""

from __future__ import annotations

import pytest


def test_fact_row_count_equals_application_count() -> None:
    """TODO The fact table holds exactly 307511 rows."""
    raise NotImplementedError


def test_wrong_fact_row_count_raises() -> None:
    """TODO A truncated fact table raises and the message reports the delta.

    A silently truncated insert is the one load failure that produces a plausible report.
    """
    raise NotImplementedError


def test_every_foreign_key_exists_in_its_dimension() -> None:
    """TODO No fact foreign key is an orphan.

    Assert across all nine key columns, not a sample.
    """
    raise NotImplementedError


def test_orphan_foreign_key_raises() -> None:
    """TODO A fact row referencing a nonexistent key raises.

    Assert the message names the key column and the offending value, which usually identifies the
    category the dimension build missed.
    """
    raise NotImplementedError


def test_no_foreign_key_column_contains_null() -> None:
    """TODO Every key column is non-null.

    Combined with the unknown member at -1, this makes a null key impossible rather than merely
    unexpected. A null key renders as a blank row that a reader interprets as missing data.
    """
    raise NotImplementedError


def test_unmatched_source_value_maps_to_unknown_key() -> None:
    """TODO A null or unrecognised source value becomes key -1, not null.

    The mechanism behind the previous test, asserted directly.
    """
    raise NotImplementedError


def test_every_dimension_has_exactly_one_unknown_member() -> None:
    """TODO Each dimension holds one row at key -1.

    Zero leaves nulls possible; two would double-count in any aggregation over the dimension.
    """
    raise NotImplementedError


def test_dimension_row_counts_match_the_specification() -> None:
    """TODO Each dimension matches its expected count including the unknown member.

    A mismatch usually means a new category appeared, which is worth knowing before a chart shows
    it.
    """
    raise NotImplementedError


def test_ordered_dimensions_have_sort_order() -> None:
    """TODO Dim_AgeBand, Dim_IncomeBand, Dim_RiskBand and Dim_Education carry SortOrder.

    Without it a chart orders alphabetically, so an income band axis reads as nonsense while
    rendering without error.
    """
    raise NotImplementedError


def test_sort_order_is_unique_within_each_dimension() -> None:
    """TODO No two rows of one dimension share a SortOrder.

    Duplicate values leave the chart order undefined and therefore unstable between refreshes.
    """
    raise NotImplementedError


def test_dimension_keys_are_integers() -> None:
    """TODO No dimension uses a business string as its key.

    A long string indexes poorly and breaks on whitespace or casing differences, both of which
    occur in this data.
    """
    raise NotImplementedError


def test_is_holdout_flag_matches_the_split_file() -> None:
    """TODO IsHoldout is 1 for exactly the identifiers in the holdout file.

    The model quality page filters on this flag, so if it is wrong that page reports in-sample
    performance as out-of-sample and nothing else would reveal it.
    """
    raise NotImplementedError


def test_pd_predicted_is_stored_as_a_fraction() -> None:
    """TODO PD_Predicted values lie between 0 and 1.

    Every DAX threshold comparison is written as a fraction. A column stored as 7 rather than 0.07
    makes all of them wrong by a hundredfold while still rendering plausibly.
    """
    raise NotImplementedError


def test_string_column_lengths_are_inferred_not_maximal() -> None:
    """TODO No string column is declared at a blanket maximum length.

    NVARCHAR(4000) exceeds the 1700 byte index key limit and the column cannot be indexed.
    """
    raise NotImplementedError


@pytest.mark.integration
def test_target_table_is_never_partially_loaded() -> None:
    """TODO A failure mid-load leaves the previous target contents intact.

    The staging and single-transaction rename exist for this. Assert by forcing a failure after
    the first insert and checking the target still holds its prior rows.
    """
    raise NotImplementedError


@pytest.mark.integration
def test_constraints_exist_on_the_target_tables() -> None:
    """TODO Real primary and foreign keys are present after the load.

    Query the catalog. The integrity tests above would pass on data that happens to be clean even
    with no constraints created, so the constraints themselves need asserting.
    """
    raise NotImplementedError
