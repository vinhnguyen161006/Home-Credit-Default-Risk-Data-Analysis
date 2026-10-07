"""Step 4 gates. The two conditions that make every later number meaningful.

An overlap between training and holdout invalidates the final estimate entirely rather than
slightly: the model was partly trained on the rows used to accept it. A positive rate drift makes
the holdout a different population, so its AUC answers a different question than the
cross-validated figure it is compared against.
"""

from __future__ import annotations


def test_train_and_holdout_are_disjoint() -> None:
    """TODO The two identifier sets share no member."""
    raise NotImplementedError


def test_overlapping_sets_raise() -> None:
    """TODO A deliberately overlapping split raises.

    The failing half of the pair. Assert the message names the overlap size.
    """
    raise NotImplementedError


def test_split_covers_every_application_exactly_once() -> None:
    """TODO The union of both sets equals the full application set.

    A customer in neither set is silently dropped from the project, and nothing else would
    reveal it: both sets would still look internally consistent.
    """
    raise NotImplementedError


def test_target_rate_difference_is_within_tolerance() -> None:
    """TODO Positive rates differ by less than 0.1 percentage points."""
    raise NotImplementedError


def test_excessive_target_rate_drift_raises() -> None:
    """TODO A split with a large rate difference raises.

    Assert in percentage points, matching how the gate is specified, so a ratio-based check
    cannot pass by using different units.
    """
    raise NotImplementedError


def test_holdout_fraction_produces_expected_row_count() -> None:
    """TODO A 20 percent split of 307511 yields 61502 rows.

    The figure the confidence interval width was computed from, so a different count changes
    the reported precision.
    """
    raise NotImplementedError


def test_split_is_identical_across_two_runs_with_same_seed() -> None:
    """TODO The same seed produces the same partition twice.

    Assert on the written file, not just the returned series, which also catches an unstable sort
    order in the writer.
    """
    raise NotImplementedError


def test_split_differs_with_different_seed() -> None:
    """TODO A different seed produces a different partition.

    Confirms the seed is actually wired through. A split that ignores its seed would pass the
    determinism test perfectly.
    """
    raise NotImplementedError


def test_holdout_file_is_not_silently_overwritten() -> None:
    """TODO Rerunning the split without force does not replace an existing file.

    The realistic accident: a rerun regenerates the split, moves customers between sets, and
    compromises a holdout that earlier runs already trained around.
    """
    raise NotImplementedError


def test_split_rejects_label_values_outside_zero_and_one() -> None:
    """TODO A third label value raises before splitting.

    It would create a third stratum and quietly shrink both sets.
    """
    raise NotImplementedError


def test_feature_build_fails_without_holdout_file() -> None:
    """TODO Step 5 raises when the holdout file is absent.

    The ordering constraint, asserted from the other side. The message should name step 4, since
    the realistic cause is running the steps out of order.
    """
    raise NotImplementedError
