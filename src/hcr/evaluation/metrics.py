"""The metrics this system reports, and the one it does not.

AUC ROC is the headline comparison metric, but it measures ranking only: a model can
rank perfectly and still produce probabilities on the wrong scale, which is useless
for a cost-based decision. PR-AUC is more sensitive under an 11.4 to 1 imbalance.
The Brier score and the reliability diagram are the probability checks and both are
mandatory after calibration.

Accuracy is not reported. Predicting all zeros scores 91.93 percent while catching no
default, so the number is actively misleading rather than merely uninformative. The
constant baseline computes it once, to demonstrate exactly that.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

ACCURACY_OF_ALL_ZEROS: Final = 0.9193


@dataclass(frozen=True)
class MetricSet:
    """The metrics reported for one model on one dataset.

    Attributes:
        auc: ROC AUC, ranking quality.
        auc_ci_lower: Lower bound of the 95 percent interval.
        auc_ci_upper: Upper bound.
        pr_auc: Average precision, more sensitive on the minority class.
        brier: Brier score, probability accuracy.
        log_loss: Cross entropy, reported alongside Brier as a second proper score.
        rows: Rows evaluated.
        positives: Positive cases among them.
    """

    auc: float
    auc_ci_lower: float
    auc_ci_upper: float
    pr_auc: float
    brier: float
    log_loss: float
    rows: int
    positives: int


def compute_metrics(probabilities: np.ndarray, labels: np.ndarray) -> MetricSet:
    """Compute every reported metric for one set of predictions.

    Args:
        probabilities: Calibrated default probabilities.
        labels: Realised TARGET.

    Returns:
        The metric set, with the AUC confidence interval attached.

    Raises:
        ValueError: If labels hold a single class, which makes AUC undefined.

    TODO:
        - Attach the confidence interval here rather than leaving it to the caller.
          Every AUC figure in the result document must carry one, and the way to
          guarantee that is to make the bare number unavailable.
        - Raise on a single-class input rather than returning 0.5. A silent 0.5 from
          a degenerate slice would read as a real measurement in a fairness table.
        - Do not compute accuracy. A caller that needs it can justify the need in
          its own docstring; this function does not offer it.
    """
    raise NotImplementedError


def decile_lift(
    probabilities: np.ndarray,
    labels: np.ndarray,
    deciles: int = 10,
) -> np.ndarray:
    """Return the observed default rate per predicted-risk decile.

    TODO:
        - Rank descending so decile 1 is the riskiest, matching the report.
        - Return the rates only; the full table with cumulative shares belongs to
          modeling.threshold, which owns the decile acceptance condition.
    """
    raise NotImplementedError


def calibration_gap(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Return mean predicted probability minus observed default rate.

    The single number that says whether the model over- or under-states risk on a
    slice. Positive means overstated. Sliced by gender and age band, this same
    quantity performs the third fairness check.

    TODO:
        - Return a signed value in probability units; the direction is the point.
        - Let the caller convert to percentage points for display. Mixing units
          between computation and presentation is how a 0.07 ends up labelled as
          7 percentage points.
    """
    raise NotImplementedError
