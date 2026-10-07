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

import logging
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

CONFIDENCE_LEVEL: Final = 0.95
Z_SCORE_95: Final = 1.959964
BOOTSTRAP_RESAMPLES: Final = 2000


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

    Args:
        auc: Point estimate.
        positives: Positive case count.
        negatives: Negative case count.

    Returns:
        The standard error.

    Raises:
        ValueError: If either class count is zero.

    TODO:
        - Implement the standard formula with the two intermediate quantities
          Q1 = auc / (2 - auc) and Q2 = 2 * auc ** 2 / (1 + auc).
        - Note in the implementation that this assumes an exponential score
          distribution, which is approximate but close enough at these sample sizes
          and is what the quoted reference figures were computed with.
        - Raise on a zero class count rather than returning infinity, so a degenerate
          fairness subgroup fails loudly instead of producing an unbounded interval
          in a published table.
    """
    raise NotImplementedError


def auc_interval(auc: float, positives: int, negatives: int) -> AucInterval:
    """Build the 95 percent interval around an AUC estimate.

    TODO:
        - Use Z_SCORE_95 times the standard error, clipped to [0, 1]. An interval
          whose upper bound exceeds 1 is arithmetically correct and visibly wrong in
          a report.
        - Record the positive and negative counts in the result. A reader checking
          whether an interval is plausible needs the counts, and a fairness subgroup
          with 300 positives deserves visibly wider bounds.
    """
    raise NotImplementedError


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

    Returns:
        A string such as "0.785 (95% CI 0.777 to 0.793)".

    TODO:
        - Render three decimal places. More implies precision the interval denies.
        - Make this the only formatter used in the report generator, so no bare AUC
          can reach the document by a different path.
    """
    raise NotImplementedError
