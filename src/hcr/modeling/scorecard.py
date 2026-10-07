"""Convert calibrated probabilities to an industry-style credit score.

The standard transform:

    Score = Offset - Factor * ln(p / (1 - p))

Parameters are chosen so the odds double every 20 points, anchored at 600. The
resulting score is then cut into five bands, A to E, which populate Dim_RiskBand.

The score adds no information: it is a monotonic transform of the probability, so it
cannot rank better than the probability it came from. Its value is communication. A
decision-maker reads 640 more readily than 0.043, and a band reads more readily
still.

Because it is monotonic, the cost threshold stays defined on the probability, not on
the score. Translating the threshold into a score for display is fine; deciding on
the score would add a rounding step between the cost structure and the decision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = logging.getLogger(__name__)

ANCHOR_SCORE: Final = 600
ANCHOR_ODDS: Final = 19.0
POINTS_TO_DOUBLE_ODDS: Final = 20

BAND_LABELS: Final = ("A", "B", "C", "D", "E")
UNKNOWN_BAND_KEY: Final = -1


@dataclass(frozen=True)
class ScorecardParameters:
    """The two constants of the score transform.

    Attributes:
        factor: Points per unit of log odds, POINTS_TO_DOUBLE_ODDS / ln(2).
        offset: Constant placing ANCHOR_ODDS at ANCHOR_SCORE.
    """

    factor: float
    offset: float


@dataclass(frozen=True)
class RiskBand:
    """One row of Dim_RiskBand.

    Attributes:
        key: Surrogate key, a generated integer.
        label: A through E.
        min_score: Lower bound, inclusive; None for the lowest band.
        max_score: Upper bound, exclusive; None for the highest band.
        sort_order: Display order, since alphabetical ordering would be wrong for
            a band set with natural sequence.
    """

    key: int
    label: str
    min_score: int | None
    max_score: int | None
    sort_order: int


def derive_parameters(
    anchor_score: int,
    anchor_odds: float,
    points_to_double: int,
) -> ScorecardParameters:
    """Derive factor and offset from the anchor and the doubling interval.

    Args:
        anchor_score: Score assigned to the anchor odds, 600.
        anchor_odds: Odds of non-default at the anchor, 19 to 1.
        points_to_double: Points over which odds double, 20.

    Returns:
        The two constants.

    TODO:
        - Compute factor as points_to_double / ln(2), and offset as
          anchor_score - factor * ln(anchor_odds).
        - Assert the round trip: feeding anchor_odds back through the transform must
          return anchor_score within floating point tolerance. An off-by-one in the
          sign here shifts every score by a constant and nothing downstream notices.
    """
    raise NotImplementedError


def probability_to_score(
    probabilities: npt.NDArray[np.float64],
    parameters: ScorecardParameters,
) -> npt.NDArray[np.float64]:
    """Apply the score transform to calibrated default probabilities.

    Returns:
        Scores, higher meaning lower risk.

    TODO:
        - Clip probabilities away from exactly 0 and 1 before taking log odds, since
          both produce infinite scores. Clip to something like 1e-6, and note that
          an isotonic calibrator does produce exact 0 and 1 at the extremes, so this
          is a real case rather than a defensive one.
        - Confirm the direction: a higher probability of default must yield a lower
          score. The minus sign in the formula does this, and an inverted score is
          the kind of mistake that survives review because the distribution still
          looks plausible.
        - Round to integers for display only. Keep the unrounded value for any
          comparison, so a band boundary does not shift by rounding.
    """
    raise NotImplementedError


def assign_bands(
    scores: npt.NDArray[np.float64], bands: tuple[RiskBand, ...]
) -> npt.NDArray[np.float64]:
    """Assign each score to a risk band key.

    Returns:
        Band keys aligned to the input scores.

    TODO:
        - Assign UNKNOWN_BAND_KEY where the score is null, so the fact table never
          holds a null foreign key and the report never renders an empty row.
        - Use half-open intervals so a score on a boundary lands in exactly one band.
        - Assert every score received a key, then assert no band is empty. An empty
          band means the cutoffs do not match the actual score distribution, which
          makes the dimension misleading even though it is technically valid.
    """
    raise NotImplementedError


def build_risk_band_dimension() -> tuple[RiskBand, ...]:
    """Build the six rows of Dim_RiskBand, five bands plus unknown.

    TODO:
        - Generate integer surrogate keys; never use the band letter as the key.
        - Include the unknown row at key UNKNOWN_BAND_KEY.
        - Set sort_order explicitly. Without it a chart orders A to E alphabetically,
          which happens to be correct here but would break the moment a band is
          renamed, and the same column is required for the age, income and education
          dimensions where alphabetical order is simply wrong.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> tuple[RiskBand, ...]:
    """Score the full population and persist scores and bands.

    TODO:
        - Score every application, holdout included. The score is a display
          transform, so computing it for all rows leaks nothing; what matters is
          that the model was not fitted on the holdout.
        - Log the score distribution and the band populations, so an empty or
          overfull band is visible before Power BI renders it.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.modeling.scorecard`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
