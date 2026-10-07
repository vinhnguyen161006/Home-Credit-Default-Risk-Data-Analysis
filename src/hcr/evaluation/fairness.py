"""Three fairness measurements by gender and age band, computed on the holdout.

The data carries CODE_GENDER and DAYS_BIRTH, and consumer lending is legally
constrained on gender and age discrimination in many markets. All three measures are
mandatory.

    approval rate by group    who is refused more often at the same threshold
    AUC by group              is the model equally accurate across groups
    calibration by group      does predicted PD match the realised rate per group

The third matters most. If the model overstates one group's risk, that group is
systematically priced against while carrying equivalent real risk. That is an
unfairness measurable in numbers rather than argued about, and it is invisible to the
first two measures: a model can approve both groups at the same rate, rank equally
well within each, and still be miscalibrated between them.

Scope stops at measuring and reporting. Bias remediation is out of scope, but the
results are published even when unfavourable. A measurement taken and withheld is
worse than one never taken, because the withholding is itself a finding about the
process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import polars as pl

logger = logging.getLogger(__name__)

PROTECTED_ATTRIBUTES: Final = ("CODE_GENDER", "AGE_BAND")
MIN_GROUP_SIZE: Final = 500
MIN_GROUP_POSITIVES: Final = 50


@dataclass(frozen=True)
class GroupMeasurement:
    """All three measures for one group of one attribute.

    Attributes:
        attribute: Protected attribute name.
        group: Group value, or "unknown" for the null group.
        rows: Applicants in this group.
        positives: Realised defaults among them.
        approval_rate: Share approved at the chosen threshold.
        auc: AUC within this group.
        auc_ci_lower: Lower interval bound.
        auc_ci_upper: Upper bound.
        mean_predicted: Mean predicted probability.
        observed_rate: Realised default rate.
        calibration_gap: Mean predicted minus observed, positive meaning overstated.
        reliable: Whether the group is large enough for the numbers to mean anything.
    """

    attribute: str
    group: str
    rows: int
    positives: int
    approval_rate: float
    auc: float
    auc_ci_lower: float
    auc_ci_upper: float
    mean_predicted: float
    observed_rate: float
    calibration_gap: float
    reliable: bool


def build_age_bands(ages: pl.Series) -> pl.Series:
    """Cut AGE_YEARS into the seven bands used by Dim_AgeBand.

    TODO:
        - Use the same boundaries as the BI dimension, read from one place. Two
          definitions of "young" between the fairness report and the dashboard would
          produce two different published numbers for the same question.
        - Put nulls in an explicit unknown band rather than dropping them, so the
          group counts reconcile with the holdout row count.
    """
    raise NotImplementedError


def measure_group(
    probabilities: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    attribute: str,
    group: str,
) -> GroupMeasurement:
    """Compute all three measures for one group.

    TODO:
        - Compute the approval rate at the given threshold, the within-group AUC with
          its interval, and the calibration gap.
        - Mark reliable False below MIN_GROUP_SIZE rows or MIN_GROUP_POSITIVES
          positives, and still report the group. Suppressing a small group hides the
          group; flagging it keeps it visible while warning against reading too much
          into the figure.
        - Use the bootstrap interval for small groups, where the analytic formula is
          least trustworthy.
        - Report the four XNA gender rows as their own unknown group, not merged into
          another. Four rows carry no statistical weight, and the point of showing
          them is that the count is visible rather than quietly absorbed.
    """
    raise NotImplementedError


def measure_attribute(
    frame: pl.DataFrame,
    probabilities: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    attribute: str,
) -> tuple[GroupMeasurement, ...]:
    """Measure every group of one protected attribute.

    TODO:
        - Return the groups in a stable order, largest first, so two runs produce
          comparable tables.
        - Compute the maximum pairwise gap for each of the three measures across
          groups and log it. The gap is the number a reviewer asks for, and deriving
          it from the table by eye invites arithmetic mistakes.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> tuple[GroupMeasurement, ...]:
    """Measure fairness on the holdout and write the report.

    TODO:
        - Measure on the holdout, which is the only data the model never saw.
          Measuring on training predictions would understate every gap.
        - Coordinate with holdout_report so the holdout is opened once for both. Two
          independent reads are two decisions informed by it.
        - Write the full table, every group and every measure, including the
          unfavourable rows. The acceptance criterion is that the measurements were
          published, not that they were good.
        - State in the output that the probability is not a Basel PD, since a
          calibration table invites exactly that reading.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.evaluation.fairness`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
