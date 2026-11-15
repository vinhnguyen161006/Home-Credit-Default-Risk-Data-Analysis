"""Confidence intervals for AUC, by the Hanley-McNeil method.

Every AUC figure in the result document carries an interval. The reason is concrete:
at this holdout size the 95 percent interval is about 0.016 wide, so two models
0.005 apart are indistinguishable, and reporting the bare numbers invites a model
choice made on noise.

Reference figures at AUC 0.78, which also justify the 20 percent holdout:

    holdout   rows     positives   SE       95 percent interval
    10%       30751    2482        0.0056   0.769 to 0.791
    20%       61502    4964        0.0040   0.772 to 0.788
    30%       92253    7447        0.0032   0.774 to 0.786

Twenty percent is the choice: narrow enough to resolve a 0.01 difference, while
leaving 80 percent for cross-validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

CONFIDENCE_LEVEL: Final = 0.95
Z_SCORE_95: Final = 1.959964
BOOTSTRAP_RESAMPLES: Final = 2000
AUC_LOWER_BOUND: Final = 0.0
AUC_UPPER_BOUND: Final = 1.0
AUC_DECIMAL_PLACES: Final = 3


@dataclass(frozen=True)
class AucInterval:
    """An AUC estimate with its uncertainty.

    Attributes:
        auc: Point estimate.
        standard_error: Standard error of the estimate.
        lower: Lower bound of the interval.
        upper: Upper bound.
        method: Either "hanley_mcneil" or "bootstrap".
        positives: Positive cases, which drive the width far more than total rows.
        negatives: Negative cases.
    """

    auc: float
    standard_error: float
    lower: float
    upper: float
    method: str
    positives: int
    negatives: int


def hanley_mcneil_standard_error(auc: float, positives: int, negatives: int) -> float:
    """Compute the AUC standard error analytically.

    The formula assumes an exponential score distribution. That assumption is approximate
    but close enough at these sample sizes, and it is what the reference figures in this
    module were computed with.

    Args:
        auc: Point estimate.
        positives: Positive case count.
        negatives: Negative case count.

    Returns:
        The standard error.

    Raises:
        ValueError: If either class count is zero. An interval over an empty class is
            undefined, and returning infinity would publish an unbounded figure.
    """
    if positives == 0 or negatives == 0:
        raise ValueError(
            f"Both classes need at least one case, got {positives} positives "
            f"and {negatives} negatives"
        )
    q1 = auc / (2 - auc)
    q2 = 2 * auc**2 / (1 + auc)
    variance_numerator = (
        auc * (1 - auc) + (positives - 1) * (q1 - auc**2) + (negatives - 1) * (q2 - auc**2)
    )
    return float((variance_numerator / (positives * negatives)) ** 0.5)


def auc_interval(auc: float, positives: int, negatives: int) -> AucInterval:
    """Build the 95 percent interval around an AUC estimate.

    The bounds are clipped to [0, 1]. An upper bound above 1 is arithmetically correct
    and visibly wrong in a report.

    Args:
        auc: Point estimate.
        positives: Positive case count, recorded so a reader can judge the interval.
        negatives: Negative case count.

    Raises:
        ValueError: If the class counts are zero, or the AUC lies outside [0, 1].
    """
    if not AUC_LOWER_BOUND <= auc <= AUC_UPPER_BOUND:
        raise ValueError(f"AUC must lie in [0, 1], got {auc}")
    standard_error = hanley_mcneil_standard_error(auc, positives, negatives)
    half_width = Z_SCORE_95 * standard_error
    return AucInterval(
        auc=auc,
        standard_error=standard_error,
        lower=max(AUC_LOWER_BOUND, auc - half_width),
        upper=min(AUC_UPPER_BOUND, auc + half_width),
        method="hanley_mcneil",
        positives=positives,
        negatives=negatives,
    )


def bootstrap_auc_interval(
    probabilities: object,
    labels: object,
    resamples: int,
    seed: int,
) -> AucInterval:
    """Build the interval by stratified bootstrap instead of the analytic formula.

    Used where the analytic assumption is doubtful: small fairness subgroups, or a
    comparison of two models on the same rows where the estimates are correlated.

    TODO:
        - Resample positives and negatives separately, so every resample preserves
          the class balance. An unstratified bootstrap at 8 percent positives
          occasionally draws a sample with too few positives and widens the interval
          for the wrong reason.
        - Take the percentile interval, and pass the project seed so the published
          bounds are reproducible.
        - For comparing two models, bootstrap the paired difference rather than each
          AUC separately. Two overlapping intervals do not establish that two models
          are indistinguishable when the estimates are correlated, and the paired
          interval answers the question that was actually asked.
    """
    raise NotImplementedError


def format_auc_with_interval(interval: AucInterval) -> str:
    """Format an AUC and its interval for a document.

    Three decimal places, because more implies precision the interval denies. This is
    the only formatter the report generator should use, so no bare AUC reaches the
    document by another path.

    Returns:
        A string such as "0.785 (95% CI 0.777 to 0.793)".
    """
    return (
        f"{interval.auc:.{AUC_DECIMAL_PLACES}f} "
        f"(95% CI {interval.lower:.{AUC_DECIMAL_PLACES}f} "
        f"to {interval.upper:.{AUC_DECIMAL_PLACES}f})"
    )
