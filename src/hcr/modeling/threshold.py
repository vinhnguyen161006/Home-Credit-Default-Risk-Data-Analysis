"""Choose the decision threshold from the assumed cost structure.

The default 0.5 is never used. At an 8.07 percent base rate it would approve almost
everyone, and more importantly it encodes an assumption nobody made: that a wrong
rejection and a wrong approval cost the same. They do not.

Both errors are real costs. Rejecting a good applicant loses revenue and pushes that
person toward informal lending. Approving someone who cannot repay loses the lender
money and pushes that person into bad debt. This module weighs the two
quantitatively, which is the whole purpose of the system.

The cost figures are assumptions, not measurements. Every report that cites a
threshold must say so, and must also say that the published label definition is
unknown, so the probability is the probability of this dataset's event rather than a
Basel PD convertible into realised loss.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_FORBIDDEN: Final = 0.5
PORTFOLIO_DEFAULT_RATE: Final = 0.0807
DECILE_COUNT: Final = 10


@dataclass(frozen=True)
class ThresholdPoint:
    """Expected outcome at one candidate threshold.

    Attributes:
        threshold: Calibrated probability cutoff; approve below it.
        approval_rate: Share of applicants approved.
        default_rate_approved: Realised default rate among the approved.
        false_positive_cost: Total cost of wrongly rejected applicants.
        false_negative_cost: Total cost of wrongly approved applicants.
        total_cost: Sum of both.
    """

    threshold: float
    approval_rate: float
    default_rate_approved: float
    false_positive_cost: float
    false_negative_cost: float
    total_cost: float


@dataclass(frozen=True)
class DecileRow:
    """One row of the decile table.

    Attributes:
        decile: 1 for the riskiest tenth, 10 for the safest.
        applications: Rows in this decile.
        observed_default_rate: Realised rate.
        mean_predicted_probability: Mean calibrated probability.
        cumulative_default_share: Share of all defaults captured up to here.
    """

    decile: int
    applications: int
    observed_default_rate: float
    mean_predicted_probability: float
    cumulative_default_share: float


def cost_at_threshold(
    probabilities: npt.NDArray[np.float64],
    labels: npt.NDArray[np.int64],
    credit_amounts: npt.NDArray[np.float64],
    threshold: float,
    profit_margin: float,
    loss_given_default: float,
) -> ThresholdPoint:
    """Compute the expected cost of one threshold.

    Args:
        probabilities: Calibrated default probabilities.
        labels: Realised TARGET.
        credit_amounts: AMT_CREDIT per applicant, which scales both costs.
        threshold: Cutoff under evaluation.
        profit_margin: Assumed margin lost on a wrong rejection.
        loss_given_default: Assumed loss share on a wrong approval.

    Returns:
        The cost breakdown at this threshold.

    TODO:
        - Weight each error by that applicant's AMT_CREDIT. An unweighted count
          treats a small and a large loan as equal mistakes, which is the error this
          cost structure exists to avoid.
        - Count a false positive as a rejected applicant whose TARGET is 0, and a
          false negative as an approved applicant whose TARGET is 1.
        - Return absolute currency amounts, not normalised ones. The report quotes
          expected loss, and a normalised figure cannot be stated in money.
    """
    raise NotImplementedError


def search_threshold(
    probabilities: npt.NDArray[np.float64],
    labels: npt.NDArray[np.int64],
    credit_amounts: npt.NDArray[np.float64],
    grid: dict[str, float],
    profit_margin: float,
    loss_given_default: float,
) -> tuple[ThresholdPoint, tuple[ThresholdPoint, ...]]:
    """Find the cost-minimising threshold and return the full curve.

    Returns:
        The chosen point and every evaluated point, for the loss curve plot.

    TODO:
        - Search on out-of-fold predictions, never on the holdout. Choosing the
          threshold against the holdout would make it a decision the holdout
          informed, and it would stop being an independent estimate.
        - Return the whole curve, not just the minimum. The curve shows whether the
          minimum is a sharp point or a broad plateau, and a plateau means the exact
          threshold matters less than the report would otherwise imply.
        - Assert the chosen threshold is not DEFAULT_THRESHOLD_FORBIDDEN, as a guard
          against a degenerate search silently returning the midpoint.
        - Log the approval rate and default rate at the chosen threshold next to the
          portfolio rate of 8.07 percent. That comparison is the single most useful
          line in the output.
    """
    raise NotImplementedError


def build_decile_table(
    probabilities: npt.NDArray[np.float64],
    labels: npt.NDArray[np.int64],
) -> tuple[DecileRow, ...]:
    """Build the ten-row risk decile table.

    The most readable metric for a non-technical audience, because it answers
    directly how much default is avoided by rejecting the riskiest tenth.

    Returns:
        Ten rows, decile 1 being the riskiest.

    TODO:
        - Rank by predicted probability and cut into ten equal-sized groups.
        - Assert the observed default rate falls monotonically from decile 1 to
          decile 10. That monotonicity is an acceptance condition, and a violation
          means the model does not rank reliably even if its AUC looks acceptable.
        - Report a non-monotonic table rather than hiding it. A single inversion
          between adjacent middle deciles is common and worth stating; an inversion
          at the extremes is a real problem.
        - Include the cumulative share of defaults captured, which is what turns the
          table into an answer about how much risk a given rejection rate avoids.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> ThresholdPoint:
    """Choose the threshold and write the curve and decile table.

    TODO:
        - Read out-of-fold calibrated predictions and the AMT_CREDIT column from the
          training split.
        - Write the loss curve and the decile table to the reports directory, and log
          the chosen threshold to MLflow so the serving layer and the Power BI
          what-if default both read one value.
        - State the cost assumptions in the written output, next to the numbers they
          produced, rather than only in the config file.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.modeling.threshold`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
