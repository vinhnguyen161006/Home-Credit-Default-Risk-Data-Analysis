"""The three mandatory baselines, in increasing order of information.

Steps 0 through 2 of the model sequence. They are required to run and required to
report: without them the final number has no frame of reference, and 0.785 reads
as either good or mediocre depending on what it is compared against.

Expected results, which double as a sanity check on the pipeline:
    0  constant at the base rate                      AUC 0.500
    1  logistic on EXT_SOURCE_1/2/3 only              AUC about 0.70
    2  logistic on application columns plus ratios     AUC about 0.74

The gap between step 1 and the full model is the question the whole feature
engineering effort answers. If three third-party scores reach 0.70 and 800
engineered columns reach 0.785, that difference is the project's actual output and
the report should say so plainly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)

EXT_SOURCE_COLUMNS: Final = ("EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3")

EXPECTED_AUC_CONSTANT: Final = 0.500
EXPECTED_AUC_EXT_SOURCE: Final = 0.70
EXPECTED_AUC_APPLICATION: Final = 0.74
EXPECTED_AUC_TOLERANCE: Final = 0.03


@dataclass(frozen=True)
class BaselineResult:
    """Cross-validated outcome of one baseline.

    Attributes:
        name: Baseline identifier.
        auc_mean: Mean AUC across folds.
        auc_std: Standard deviation across folds.
        pr_auc_mean: Mean PR-AUC, more sensitive than AUC under this imbalance.
        brier_mean: Mean Brier score, uncalibrated at this stage.
        feature_count: Columns the baseline used.
        matches_expectation: Whether the AUC landed near its reference value.
    """

    name: str
    auc_mean: float
    auc_std: float
    pr_auc_mean: float
    brier_mean: float
    feature_count: int
    matches_expectation: bool


def baseline_constant_rate(labels: pl.Series) -> BaselineResult:
    """Predict the base rate for every applicant.

    The lower bound. It scores AUC 0.500 by construction, and it exists to make a
    second point: the same prediction scores 91.93 percent accuracy. That is why
    accuracy is banned as a metric here, and showing it alongside the AUC is more
    convincing than asserting it.

    TODO:
        - Predict the training-fold positive rate as a constant probability.
        - Compute AUC, which must be 0.500 exactly; assert it and raise if not,
          since any other value means the metric wiring is wrong.
        - Compute accuracy as well and record it in the result detail, as the
          concrete demonstration of why accuracy is excluded.
    """
    raise NotImplementedError


def baseline_ext_source_only(frame: pl.DataFrame, labels: pl.Series) -> BaselineResult:
    """Logistic regression on the three external credit scores alone.

    Measures how much of the predictive power is already supplied by third parties
    before this project contributes anything. Expected around 0.70.

    These columns are legitimate because they exist at application time, but they
    dominate the model, which is why the system also trains a configuration without
    them.

    TODO:
        - Fit on EXT_SOURCE_COLUMNS only, through the logistic pipeline so the
          median imputer fits inside each fold.
        - EXT_SOURCE_1 is absent for about 56 percent of rows. Report the AUC on
          the full set with imputation, not on the complete-cases subset: the subset
          is a different, easier population and the number would not be comparable
          to the other baselines.
        - Warn if the result lands far from EXPECTED_AUC_EXT_SOURCE. These three
          columns are well characterised, so a large deviation means a pipeline
          defect rather than a discovery.
    """
    raise NotImplementedError


def baseline_application_and_ratios(
    frame: pl.DataFrame,
    labels: pl.Series,
) -> BaselineResult:
    """Logistic regression on application columns plus the six ratios.

    The explainable reference point: a model whose coefficients can be read directly
    and shown to a non-technical audience. Expected around 0.74.

    Its value is not its accuracy but its interpretability. If the full LightGBM
    model reaches 0.785 against this 0.74, the report can state what the extra 0.045
    cost in explainability.

    TODO:
        - Use the application columns and the APP_ ratio family only. No aggregated
          history: this baseline is about what the application form alone supports.
        - Include the EXT_SOURCE columns, so the comparison against the full model
          isolates the contribution of aggregated history rather than conflating it
          with the third-party scores.
        - Report the coefficients alongside the AUC. An explainable baseline whose
          coefficients are never shown provides none of its value.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> tuple[BaselineResult, ...]:
    """Run all three baselines and log them to MLflow.

    Returns:
        One result per baseline, in sequence order.

    TODO:
        - Use the same folds and seed as the main model, so every AUC in the
          sequence table is comparable.
        - Train on the training split only. The holdout is not read here.
        - Log each baseline as its own MLflow run, tagged with its sequence number,
          so the result document can read the table straight out of MLflow.
        - Warn when a baseline misses its expected value by more than
          EXPECTED_AUC_TOLERANCE, naming both figures.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.modeling.baselines`.

    TODO:
        - Configure logging, call run, print nothing: log the table at INFO and let
          the report generator read MLflow.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
