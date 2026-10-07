"""SHAP explanations at two levels: the portfolio and the single application.

Both levels are needed and they answer different questions. A global ranking says
which factors drive risk across the book; a per-application breakdown says why this
applicant was scored as they were, which is what an adverse action explanation
requires.

Raw SHAP output over 800 columns is not readable, so values are aggregated two ways:
back to the original source variable, collapsing the window and aggregation variants
of one column, and up to the feature family, showing how much the windowed family
contributes relative to the whole-history one.

The no_ext_source configuration is the more useful one to explain. In the full model
three third-party scores dominate the ranking, which is informative once and then
crowds out every internal factor the business could act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    import polars as pl

logger = logging.getLogger(__name__)

SHAP_SAMPLE_ROWS: Final = 10000
TOP_FEATURES_REPORTED: Final = 30

FEATURE_FAMILIES: Final = (
    "application_ratio",
    "whole_history",
    "time_window",
    "trend",
)


@dataclass(frozen=True)
class FeatureContribution:
    """Mean absolute SHAP value for one column.

    Attributes:
        column: Feature name.
        mean_absolute_shap: Mean absolute contribution.
        mean_signed_shap: Mean signed contribution, showing direction.
        source_table: Table it came from, via the manifest.
        source_variable: Original variable, with aggregation and window stripped.
        family: Which of the four feature families it belongs to.
    """

    column: str
    mean_absolute_shap: float
    mean_signed_shap: float
    source_table: str
    source_variable: str
    family: str


def compute_shap_values(
    model: object,
    frame: pl.DataFrame,
    sample_rows: int,
    seed: int,
) -> npt.NDArray[np.float64]:
    """Compute SHAP values for a sample of applications.

    Args:
        model: Fitted LightGBM estimator.
        frame: Feature matrix.
        sample_rows: Rows to sample.
        seed: Seed for the sample.

    Returns:
        SHAP values, one row per sampled application.

    TODO:
        - Use TreeExplainer, which is exact for tree ensembles and fast enough that
          no approximation is needed here.
        - Sample rather than explaining all 307511 rows, and sample with the project
          seed so the published ranking is reproducible.
        - Explain the uncalibrated model. Isotonic calibration is a monotonic
          post-transform, so it changes the probability scale but not the relative
          contributions, and explaining through the calibrator adds a step that
          complicates the interpretation without changing the ranking.
        - Stratify the sample on TARGET. An 8 percent sample of a rare class gives a
          thin basis for explaining the defaults, which are the cases anyone actually
          asks about.
    """
    raise NotImplementedError


def aggregate_to_source_variable(
    contributions: tuple[FeatureContribution, ...],
) -> dict[str, float]:
    """Sum contributions of all columns derived from one original variable.

    BURO_AMT_CREDIT_SUM_MEAN, BURO_AMT_CREDIT_SUM_MAX and their windowed variants all
    describe AMT_CREDIT_SUM. Ranked separately each looks modest; summed, the variable
    may be the strongest signal in the model.

    TODO:
        - Strip the aggregation suffix and the window suffix using the manifest, not a
          regular expression over the name. The manifest knows the provenance; a
          pattern match would mis-split a column whose source name happens to end in
          MEAN.
        - Sum absolute values, not signed ones. Two variants with opposite signs do
          not cancel into irrelevance; they indicate an interaction worth noting.
    """
    raise NotImplementedError


def aggregate_to_family(
    contributions: tuple[FeatureContribution, ...],
) -> dict[str, float]:
    """Sum contributions by feature family.

    Answers whether the engineering effort paid off and where. The time-window family
    is the expensive one to build and the specification argues it holds the most
    value; this aggregation is how that claim gets checked rather than assumed.

    TODO:
        - Classify by the window and aggregation recorded in the manifest.
        - Report each family's share of total absolute contribution alongside its
          column count. A family with 250 columns contributing 20 percent is less
          efficient than one with 15 contributing 15 percent, and the per-column
          figure is what informs the next iteration.
    """
    raise NotImplementedError


def explain_single_application(
    model: object,
    row: pl.DataFrame,
    top_n: int,
) -> tuple[FeatureContribution, ...]:
    """Explain one application for an adverse action style breakdown.

    TODO:
        - Return the top_n contributions by absolute value, with signs preserved, so
          the explanation says which factors pushed the score down and which up.
        - Translate column names to readable labels through the manifest. A rejection
          reason reading "BURO_BB_STATUS_IS_DPD_MEAN_MEAN_3M" explains nothing to the
          person it concerns.
        - State that the model is not the decision. Scope excludes automated
          decisioning, so this output is a diagnostic, and presenting it as a reason
          code would overstate what the system does.
    """
    raise NotImplementedError


def run(configuration: str = "no_ext_source") -> tuple[FeatureContribution, ...]:
    """Compute and write the explanation artifacts.

    TODO:
        - Default to no_ext_source, which is the configuration that supports business
          conclusions.
        - Write the global ranking, the source-variable aggregation and the family
          aggregation to the figures directory, and log all three to MLflow.
        - Produce the ablation input: the top five features by SHAP feed the leave-one-
          out check in quality.leakage_checks, which is how a single dominant feature
          gets caught.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.evaluation.explain`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
