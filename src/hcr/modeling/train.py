"""Steps 3 and 4 of the sequence: LightGBM with and without the external scores.

Stratified 5-fold cross-validation on the 80 percent training split, logged to
MLflow. The holdout is never touched here.

Two configurations are trained, and the second is not optional. The full model
performs best; the one without EXT_SOURCE measures how much signal the internal
data carries on its own, and only that second model supports a statement about which
applicant attributes relate to risk.

Expected: 0.78 to 0.79 with the external scores, about 0.74 without. The plausible
range for this dataset is 0.74 to 0.80. A result above 0.85 is a leakage alarm to
investigate and report, not a success.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import polars as pl
    from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

N_SPLITS: Final = 5
FOLD_AUC_SPREAD_WARNING: Final = 0.02
PLAUSIBLE_AUC_MIN: Final = 0.74
PLAUSIBLE_AUC_MAX: Final = 0.80
LEAKAGE_ALARM_AUC: Final = 0.85


class LeakageAlarmError(Exception):
    """Raised when cross-validated AUC exceeds the leakage alarm threshold.

    Deliberately an exception rather than a warning. A number above 0.85 on this
    dataset is far more likely to be a defect than a breakthrough, and a result
    that good is hard to re-examine objectively once it has been written down.
    """


@dataclass(frozen=True)
class FoldResult:
    """Outcome of one cross-validation fold.

    Attributes:
        fold_index: Zero-based fold number.
        auc: Validation AUC for this fold.
        pr_auc: Validation PR-AUC.
        brier: Validation Brier score, before calibration.
        best_iteration: Boosting round early stopping selected.
        train_rows: Rows trained on.
        valid_rows: Rows validated on.
    """

    fold_index: int
    auc: float
    pr_auc: float
    brier: float
    best_iteration: int
    train_rows: int
    valid_rows: int


@dataclass(frozen=True)
class TrainingResult:
    """Outcome of one full cross-validated training run.

    Attributes:
        configuration: Either "full" or "no_ext_source".
        folds: Per-fold results.
        auc_mean: Mean validation AUC.
        auc_std: Standard deviation across folds.
        auc_spread: Max minus min fold AUC.
        oof_predictions: Out-of-fold probabilities, aligned to the training rows.
        feature_importance: Feature name to gain importance.
        mlflow_run_id: Run that recorded this result.
    """

    configuration: str
    folds: tuple[FoldResult, ...]
    auc_mean: float
    auc_std: float
    auc_spread: float
    oof_predictions: np.ndarray
    feature_importance: dict[str, float]
    mlflow_run_id: str


def load_training_split(configuration: str) -> tuple[pl.DataFrame, pl.Series]:
    """Load the training rows of a feature matrix, excluding the holdout.

    Returns:
        Feature frame and label series.

    Raises:
        FileNotFoundError: If the holdout identifier list is absent.

    TODO:
        - Read the holdout ids and exclude them with an anti-join. Filtering by a
          row index or a fraction instead would silently include holdout customers
          the moment the matrix row order changes.
        - Assert the resulting row count is the expected 246009, so an exclusion
          that quietly matched nothing fails here rather than at the final
          comparison.
        - Drop SK_ID_CURR from the feature frame but keep it aligned separately, so
          out-of-fold predictions can be joined back by id rather than by position.
    """
    raise NotImplementedError


def train_single_fold(
    pipeline: Pipeline,
    train_frame: pl.DataFrame,
    train_labels: pl.Series,
    valid_frame: pl.DataFrame,
    valid_labels: pl.Series,
    fold_index: int,
) -> tuple[FoldResult, np.ndarray]:
    """Fit one fold and return its metrics and validation predictions.

    Returns:
        The fold result and the predicted probabilities for the validation rows.

    TODO:
        - Fit the whole pipeline on the training portion, so every transform inside
          it fits on this fold only.
        - Compute scale_pos_weight from this fold's training labels, not from the
          full training set.
        - Use early stopping on the validation fold, and record the chosen
          iteration. A wildly varying best iteration across folds is a sign of an
          unstable feature, worth seeing in the log.
        - Return probabilities, not classes. No threshold is applied anywhere in
          this module; thresholding is a separate decision made against a cost
          structure.
    """
    raise NotImplementedError


def cross_validate(configuration: str) -> TrainingResult:
    """Run stratified 5-fold cross-validation for one configuration.

    Returns:
        The aggregated training result.

    Raises:
        LeakageAlarmError: If mean AUC exceeds LEAKAGE_ALARM_AUC.

    TODO:
        - Stratify folds on TARGET with the project seed, so the 8.07 percent
          positive rate holds in every fold.
        - Do not use time-based splitting. The data has no date column, and
          SK_ID_CURR is not guaranteed to increase with submission time; using the
          id as a time proxy is an unverifiable assumption whose failure would be
          invisible. The result document must state this.
        - Collect out-of-fold predictions for every training row. They are what the
          threshold search and the calibration fold both consume, and they are the
          only honest in-sample estimate available.
        - Warn when auc_spread exceeds FOLD_AUC_SPREAD_WARNING. A spread that wide
          means one fold saw a different distribution, and the mean then hides more
          than it reports.
        - Raise LeakageAlarmError above the alarm threshold, before logging the run as a
          success. The point is to stop the number from being recorded as a result.
        - Log parameters, metrics, the feature manifest and the fold table to
          MLflow. The result document reads from MLflow, so anything not logged
          cannot appear in it.
    """
    raise NotImplementedError


def run() -> tuple[TrainingResult, TrainingResult]:
    """Train both configurations.

    Returns:
        Full and no_ext_source results, in that order.

    TODO:
        - Train full first, then no_ext_source, and log the AUC difference between
          them explicitly as its own metric. That difference is the answer to the
          question the two configurations exist to ask.
        - Keep the folds identical across configurations so the comparison is of
          features and not of partitions.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.modeling.train`.

    TODO:
        - Configure logging, call run, exit 1 on LeakageAlarmError with the AUC in the
          message.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
