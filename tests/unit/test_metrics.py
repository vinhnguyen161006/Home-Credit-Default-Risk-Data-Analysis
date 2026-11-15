"""Metric and interval tests on hand-worked cases.

Each expected figure here is either computed by hand from the fixture or taken from the
reference table in hcr.evaluation.confidence, so a regression in the formula cannot pass
by agreeing with itself.
"""

from __future__ import annotations

import pytest

from conftest import ScoredCase
from hcr.evaluation.confidence import (
    auc_interval,
    format_auc_with_interval,
    hanley_mcneil_standard_error,
)
from hcr.evaluation.metrics import MetricSet, compute_metrics

HOLDOUT_POSITIVES: int = 4964
HOLDOUT_NEGATIVES: int = 56538
HOLDOUT_AUC: float = 0.78
REFERENCE_STANDARD_ERRORS: tuple[tuple[int, int, float], ...] = (
    (2482, 28269, 0.0056),
    (4964, 56538, 0.0040),
    (7447, 84806, 0.0032),
)
SEPARABLE_BRIER: float = 0.0305
PRECISION_DIGITS: int = 4


def test_metrics_auc_matches_hand_worked_partial_case(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["partial"]

    metrics = compute_metrics(case.probabilities, case.labels)

    assert metrics.auc == pytest.approx(0.75)


def test_metrics_separable_case_ranks_perfectly(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["separable"]

    metrics = compute_metrics(case.probabilities, case.labels)

    assert metrics.auc == pytest.approx(1.0)
    assert metrics.pr_auc == pytest.approx(1.0)


def test_metrics_brier_matches_hand_calculation(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["separable"]

    metrics = compute_metrics(case.probabilities, case.labels)

    assert round(metrics.brier, PRECISION_DIGITS) == pytest.approx(SEPARABLE_BRIER)


def test_metrics_interval_contains_the_point_estimate(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["miscalibrated"]

    metrics = compute_metrics(case.probabilities, case.labels)

    assert metrics.auc_ci_lower <= metrics.auc <= metrics.auc_ci_upper


def test_metrics_counts_rows_and_positives(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["partial"]

    metrics = compute_metrics(case.probabilities, case.labels)

    assert metrics.rows == len(case.labels)
    assert metrics.positives == int(case.labels.sum())


def test_metrics_rejects_labels_holding_one_class(
    predictions_and_labels: dict[str, ScoredCase],
) -> None:
    case = predictions_and_labels["partial"]
    single_class = case.labels * 0

    with pytest.raises(ValueError, match="both classes"):
        compute_metrics(case.probabilities, single_class)


def test_metric_set_carries_no_accuracy_field() -> None:
    assert not any("accuracy" in name for name in MetricSet.__dataclass_fields__)


@pytest.mark.parametrize(("positives", "negatives", "expected"), REFERENCE_STANDARD_ERRORS)
def test_hanley_mcneil_standard_error_matches_reference_table(
    positives: int, negatives: int, expected: float
) -> None:
    standard_error = hanley_mcneil_standard_error(HOLDOUT_AUC, positives, negatives)

    assert round(standard_error, PRECISION_DIGITS) == pytest.approx(expected, abs=5e-5)


def test_auc_interval_matches_holdout_reference_bounds() -> None:
    interval = auc_interval(HOLDOUT_AUC, HOLDOUT_POSITIVES, HOLDOUT_NEGATIVES)

    assert round(interval.lower, 3) == pytest.approx(0.772)
    assert round(interval.upper, 3) == pytest.approx(0.788)


def test_auc_interval_clips_upper_bound_at_one() -> None:
    interval = auc_interval(0.99, 2, 5)

    assert interval.upper == 1.0


def test_auc_interval_records_class_counts() -> None:
    interval = auc_interval(HOLDOUT_AUC, HOLDOUT_POSITIVES, HOLDOUT_NEGATIVES)

    assert (interval.positives, interval.negatives) == (HOLDOUT_POSITIVES, HOLDOUT_NEGATIVES)


def test_standard_error_rejects_empty_class() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        hanley_mcneil_standard_error(HOLDOUT_AUC, 0, HOLDOUT_NEGATIVES)


def test_auc_interval_rejects_auc_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        auc_interval(1.2, HOLDOUT_POSITIVES, HOLDOUT_NEGATIVES)


def test_format_auc_with_interval_uses_three_decimals() -> None:
    interval = auc_interval(HOLDOUT_AUC, HOLDOUT_POSITIVES, HOLDOUT_NEGATIVES)

    assert format_auc_with_interval(interval) == "0.780 (95% CI 0.772 to 0.788)"
