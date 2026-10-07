"""Step 2 gate. Every gate gets a passing and a failing case.

A gate tested only on valid data proves nothing: it would pass equally if its body were
`return True`. Each test here therefore comes in a pair, and the failing half is the one that
matters.
"""

from __future__ import annotations


def test_matching_row_count_passes() -> None:
    """TODO A table whose row count matches the contract passes."""
    raise NotImplementedError


def test_wrong_row_count_stops_the_pipeline() -> None:
    """TODO A row count one short of the contract raises.

    Exact equality, no tolerance. A truncated download is the realistic cause, and a tolerance
    would let it through to silently change every reported metric.
    """
    raise NotImplementedError


def test_wrong_column_count_stops_the_pipeline() -> None:
    """TODO A missing column raises and the message names it.

    Assert the column name appears in the message. A bare count difference sends the reader
    back to the YAML to work out which column vanished.
    """
    raise NotImplementedError


def test_duplicate_primary_key_stops_the_pipeline() -> None:
    """TODO A duplicated SK_ID_CURR raises.

    A duplicate multiplies rows through every join and would surface as a step 5 failure far
    from its cause.
    """
    raise NotImplementedError


def test_missing_primary_key_declaration_skips_uniqueness_check() -> None:
    """TODO A table declaring no primary key passes without a uniqueness check.

    installments_payments is an event table with no natural key. Asserting one would fail on
    entirely valid data, so the null declaration must be honoured rather than treated as an
    omission.
    """
    raise NotImplementedError


def test_forbidden_target_column_in_test_set_stops_the_pipeline() -> None:
    """TODO A TARGET column in application_test raises.

    Its presence would mean the file is not the unlabelled test set the contract describes, and
    every statement about measuring on a self-made holdout would be wrong.
    """
    raise NotImplementedError


def test_target_outside_zero_and_one_stops_the_pipeline() -> None:
    """TODO A TARGET value of 2 raises.

    A third label value breaks the stratified split and the AUC computation, both quietly.
    """
    raise NotImplementedError


def test_shifted_target_rate_stops_the_pipeline() -> None:
    """TODO A positive rate far from 8.07 percent raises.

    A shifted rate means the label column changed, which invalidates the cost threshold and every
    baseline reference figure.
    """
    raise NotImplementedError


def test_coverage_gap_is_reported_as_warning_not_failure() -> None:
    """TODO The known bureau coverage gap logs a warning and does not raise.

    Only 48 percent of bureau loans have monthly rows. That is a property of the data and the
    reason every join is a LEFT JOIN; treating it as a failure would block every valid run.
    """
    raise NotImplementedError


def test_all_violations_are_reported_in_one_run() -> None:
    """TODO A table failing three conditions reports all three.

    Assert the message names each. Raising on the first turns fixing a contract into an
    iterative guessing game.
    """
    raise NotImplementedError


def test_gate_runs_without_loading_full_frames() -> None:
    """TODO Row counts come from Parquet metadata, not from a full read.

    Parquet carries the count in its footer. Reading 27.3 million rows to count them would make
    the gate too slow to run routinely, which is how a gate stops being run.
    """
    raise NotImplementedError
