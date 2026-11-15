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

Every baseline runs on the training split only, with the same folds as the main model.
The holdout is excluded before any fold is built and is never read for its labels here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import duckdb
import mlflow
import numpy as np
import numpy.typing as npt
import polars as pl
from sklearn.base import clone
from sklearn.model_selection import cross_val_predict

from hcr.config import load_model_config, mlflow_experiment_name, mlflow_tracking_uri
from hcr.evaluation.confidence import AucInterval, auc_interval, format_auc_with_interval
from hcr.evaluation.metrics import ACCURACY_OF_ALL_ZEROS, MetricSet, compute_metrics
from hcr.features.build import compute_application_ratios
from hcr.modeling.pipeline import (
    ESTIMATOR_STEP,
    ID_COLUMN,
    LABEL_COLUMN,
    PREPROCESS_STEP,
    build_logistic_pipeline,
    categorical_columns,
    numeric_columns,
)
from hcr.modeling.train import stratified_folds
from hcr.paths import holdout_ids_path, silver_path
from hcr.split.make_holdout import (
    EXPECTED_HOLDOUT_ROWS,
    EXPECTED_TOTAL_APPLICATIONS,
    load_holdout_ids,
)

if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

Folds = tuple[tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]], ...]

CONSTANT_RATE: Final = "constant_rate"
EXT_SOURCE_ONLY: Final = "logistic_ext_source_only"
APPLICATION_AND_RATIOS: Final = "logistic_application_and_ratios"

CONSTANT_RATE_STEP: Final = 0
EXT_SOURCE_ONLY_STEP: Final = 1
APPLICATION_AND_RATIOS_STEP: Final = 2

RANDOM_GUESS_AUC: Final = 0.5
AUC_EQUALITY_TOLERANCE: Final = 1e-12
APPLICATION_TABLE: Final = "application_train"

TAG_SEQUENCE_STEP: Final = "sequence_step"
TAG_BASELINE_NAME: Final = "baseline_name"
TAG_MATCHES_EXPECTATION: Final = "matches_expectation"
PARAM_FEATURE_COUNT: Final = "feature_count"
PARAM_N_SPLITS: Final = "n_splits"
PARAM_RANDOM_SEED: Final = "random_seed"
METRIC_AUC: Final = "auc"
METRIC_AUC_CI_LOWER: Final = "auc_ci_lower"
METRIC_AUC_CI_UPPER: Final = "auc_ci_upper"
METRIC_AUC_FOLD_STD: Final = "auc_fold_std"
METRIC_PR_AUC: Final = "pr_auc"
METRIC_BRIER: Final = "brier"
METRIC_AUC_FOLD_PREFIX: Final = "auc_fold_"
DETAIL_ARTIFACT_SUFFIX: Final = "_detail.json"


@dataclass(frozen=True)
class BaselineResult:
    """Cross-validated outcome of one baseline.

    Attributes:
        name: Baseline identifier, matching its key in configs/model.yml.
        sequence_step: Position in the model sequence, 0 to 2.
        auc_mean: Mean AUC across folds, the figure reported.
        auc_std: Standard deviation across folds.
        fold_aucs: AUC of each fold in fold order.
        interval: 95 percent interval around auc_mean, built from all training cases.
        pr_auc_mean: Mean PR-AUC, more sensitive than AUC under this imbalance.
        brier_mean: Mean Brier score, uncalibrated at this stage.
        feature_count: Columns the baseline used.
        matches_expectation: Whether auc_mean lies within tolerance of its reference.
        detail: Supporting figures: coefficients for the logistic baselines, the
            all-zero accuracy for the constant baseline.
    """

    name: str
    sequence_step: int
    auc_mean: float
    auc_std: float
    fold_aucs: tuple[float, ...]
    interval: AucInterval
    pr_auc_mean: float
    brier_mean: float
    feature_count: int
    matches_expectation: bool
    detail: dict[str, float]


def baseline_constant_rate(
    labels: pl.Series,
    folds: Folds,
    expected_auc: float,
    auc_tolerance: float,
) -> BaselineResult:
    """Predict the training-fold base rate for every applicant.

    The lower bound. It scores AUC 0.500 by construction, and it exists to make a second
    point: the same prediction scores about 91.93 percent accuracy. That is why accuracy
    is banned as a metric here, and showing it alongside the AUC is more convincing than
    asserting it.

    Raises:
        ValueError: If any fold's AUC is not exactly 0.5, which would mean the metric
            wiring is wrong, since a constant prediction cannot rank anyone.
    """
    label_values = labels.cast(pl.Int64).to_numpy()
    fold_metrics: list[MetricSet] = []
    for train_positions, valid_positions in folds:
        base_rate = float(label_values[train_positions].mean())
        probabilities = np.full(len(valid_positions), base_rate)
        fold_metrics.append(compute_metrics(probabilities, label_values[valid_positions]))
    _assert_random_guess(fold_metrics)
    accuracy_all_zeros = 1 - float(label_values.mean())
    logger.info(
        "Predicting all zeros scores accuracy %.4f against reference %.4f, excluded as a metric",
        accuracy_all_zeros,
        ACCURACY_OF_ALL_ZEROS,
    )
    return _summarise(
        name=CONSTANT_RATE,
        sequence_step=CONSTANT_RATE_STEP,
        fold_metrics=fold_metrics,
        feature_count=0,
        detail={"accuracy_all_zeros": accuracy_all_zeros},
        expected_auc=expected_auc,
        auc_tolerance=auc_tolerance,
    )


def baseline_ext_source_only(
    frame: pl.DataFrame,
    labels: pl.Series,
    folds: Folds,
    ext_source_features: tuple[str, ...],
    expected_auc: float,
    auc_tolerance: float,
) -> BaselineResult:
    """Logistic regression on the three external credit scores alone.

    Measures how much of the predictive power is already supplied by third parties
    before this project contributes anything. The median imputer fits inside each fold,
    and every row stays in the comparison, so the number is comparable to the other
    baselines rather than computed on an easier subset.
    """
    features = frame.select(ext_source_features)
    pipeline = build_logistic_pipeline(numeric=ext_source_features, categorical=())
    return _run_logistic_baseline(
        name=EXT_SOURCE_ONLY,
        sequence_step=EXT_SOURCE_ONLY_STEP,
        pipeline=pipeline,
        features=features,
        labels=labels,
        folds=folds,
        expected_auc=expected_auc,
        auc_tolerance=auc_tolerance,
    )


def baseline_application_and_ratios(
    frame: pl.DataFrame,
    labels: pl.Series,
    folds: Folds,
    expected_auc: float,
    auc_tolerance: float,
) -> BaselineResult:
    """Logistic regression on application columns, the six ratios and EXT_SOURCE columns.

    The explainable reference point: a model whose coefficients can be read directly and
    shown to a non-technical audience. The frame carries only application columns and the
    APP_ ratios, never aggregated history, so this baseline measures what the application
    form supports. Including the EXT_SOURCE columns keeps the comparison with the full
    model focused on aggregated history rather than on the third-party scores.

    Its value is not its accuracy but its interpretability. If the full LightGBM model
    reaches 0.785 against this baseline, the report can state what the extra points cost
    in explainability.
    """
    features = frame.drop(ID_COLUMN, LABEL_COLUMN)
    pipeline = build_logistic_pipeline(
        numeric=numeric_columns(features.schema),
        categorical=categorical_columns(features.schema),
    )
    return _run_logistic_baseline(
        name=APPLICATION_AND_RATIOS,
        sequence_step=APPLICATION_AND_RATIOS_STEP,
        pipeline=pipeline,
        features=features,
        labels=labels,
        folds=folds,
        expected_auc=expected_auc,
        auc_tolerance=auc_tolerance,
    )


def exclude_holdout(frame: pl.DataFrame, holdout_ids: pl.Series) -> pl.DataFrame:
    """Return the training rows, sorted by SK_ID_CURR so folds ignore file row order.

    An anti-join on the identifier list, not a row index or a fraction. A positional
    filter would silently include holdout customers the moment the row order changes.
    """
    holdout_keys = holdout_ids.alias(ID_COLUMN).to_frame()
    return frame.join(holdout_keys, on=ID_COLUMN, how="anti").sort(ID_COLUMN)


def log_baseline_to_mlflow(
    result: BaselineResult,
    tracking_uri: str,
    experiment_name: str,
    n_splits: int,
    random_seed: int,
) -> str:
    """Record one baseline as its own MLflow run and return the run id.

    The tag, metric and parameter names are module constants, so the report generator
    reads the sequence table straight out of MLflow without guessing at keys.
    """
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=result.name) as active_run:
        mlflow.set_tags(
            {
                TAG_SEQUENCE_STEP: str(result.sequence_step),
                TAG_BASELINE_NAME: result.name,
                TAG_MATCHES_EXPECTATION: str(result.matches_expectation),
            }
        )
        mlflow.log_params(
            {
                PARAM_FEATURE_COUNT: result.feature_count,
                PARAM_N_SPLITS: n_splits,
                PARAM_RANDOM_SEED: random_seed,
            }
        )
        mlflow.log_metrics(_metric_values(result))
        mlflow.log_dict(result.detail, f"{result.name}{DETAIL_ARTIFACT_SUFFIX}")
    return str(active_run.info.run_id)


def run() -> tuple[BaselineResult, ...]:
    """Run all three baselines on the training split and log each to MLflow.

    Returns:
        One result per baseline, in sequence order.

    Raises:
        ValueError: If the training row count is not the expected total minus the holdout.
    """
    config = load_model_config()
    baseline_settings = config.baselines
    application = pl.read_parquet(silver_path(APPLICATION_TABLE))
    with duckdb.connect(database=":memory:") as connection:
        ratios = compute_application_ratios(connection, silver_path(APPLICATION_TABLE))
    holdout_ids = load_holdout_ids(holdout_ids_path())
    training = exclude_holdout(application.join(ratios, on=ID_COLUMN, how="left"), holdout_ids)
    _assert_training_row_count(training)

    labels = training[LABEL_COLUMN]
    folds = stratified_folds(labels, config.n_splits, config.random_seed)
    results = (
        baseline_constant_rate(
            labels,
            folds,
            baseline_settings.expected_auc[CONSTANT_RATE],
            baseline_settings.auc_tolerance,
        ),
        baseline_ext_source_only(
            training,
            labels,
            folds,
            baseline_settings.ext_source_features,
            baseline_settings.expected_auc[EXT_SOURCE_ONLY],
            baseline_settings.auc_tolerance,
        ),
        baseline_application_and_ratios(
            training,
            labels,
            folds,
            baseline_settings.expected_auc[APPLICATION_AND_RATIOS],
            baseline_settings.auc_tolerance,
        ),
    )
    for result in results:
        run_id = log_baseline_to_mlflow(
            result,
            mlflow_tracking_uri(),
            mlflow_experiment_name(),
            config.n_splits,
            config.random_seed,
        )
        logger.info("Logged %s to MLflow run %s", result.name, run_id)
    return results


def main() -> None:
    """Entry point for `python -m hcr.modeling.baselines`.

    Logs the sequence table at INFO. The report generator reads MLflow, so nothing is
    printed.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    for result in run():
        logger.info(
            "%s (step %d): AUC %s",
            result.name,
            result.sequence_step,
            format_auc_with_interval(result.interval),
        )


def _run_logistic_baseline(
    name: str,
    sequence_step: int,
    pipeline: Pipeline,
    features: pl.DataFrame,
    labels: pl.Series,
    folds: Folds,
    expected_auc: float,
    auc_tolerance: float,
) -> BaselineResult:
    label_values = labels.cast(pl.Int64).to_numpy()
    feature_values = features.to_pandas()
    probabilities = cross_val_predict(
        pipeline, feature_values, label_values, cv=folds, method="predict_proba"
    )[:, 1]
    fold_metrics = [
        compute_metrics(probabilities[valid_positions], label_values[valid_positions])
        for _, valid_positions in folds
    ]
    fitted = clone(pipeline).fit(feature_values, label_values)
    return _summarise(
        name=name,
        sequence_step=sequence_step,
        fold_metrics=fold_metrics,
        feature_count=features.width,
        detail=_logistic_coefficients(fitted),
        expected_auc=expected_auc,
        auc_tolerance=auc_tolerance,
    )


def _summarise(
    name: str,
    sequence_step: int,
    fold_metrics: list[MetricSet],
    feature_count: int,
    detail: dict[str, float],
    expected_auc: float,
    auc_tolerance: float,
) -> BaselineResult:
    fold_aucs = tuple(metrics.auc for metrics in fold_metrics)
    auc_mean = _mean(fold_aucs)
    positives = sum(metrics.positives for metrics in fold_metrics)
    negatives = sum(metrics.rows for metrics in fold_metrics) - positives
    matches_expectation = abs(auc_mean - expected_auc) <= auc_tolerance
    if not matches_expectation:
        logger.warning(
            "Baseline %s AUC %.3f is outside tolerance %.3f of its expected %.3f",
            name,
            auc_mean,
            auc_tolerance,
            expected_auc,
        )
    return BaselineResult(
        name=name,
        sequence_step=sequence_step,
        auc_mean=auc_mean,
        auc_std=_standard_deviation(fold_aucs),
        fold_aucs=fold_aucs,
        interval=auc_interval(auc_mean, positives, negatives),
        pr_auc_mean=_mean(tuple(metrics.pr_auc for metrics in fold_metrics)),
        brier_mean=_mean(tuple(metrics.brier for metrics in fold_metrics)),
        feature_count=feature_count,
        matches_expectation=matches_expectation,
        detail=detail,
    )


def _assert_random_guess(fold_metrics: list[MetricSet]) -> None:
    for index, metrics in enumerate(fold_metrics):
        if abs(metrics.auc - RANDOM_GUESS_AUC) > AUC_EQUALITY_TOLERANCE:
            raise ValueError(
                f"Constant baseline fold {index} AUC is {metrics.auc}, expected exactly "
                f"{RANDOM_GUESS_AUC}; the metric wiring is wrong"
            )


def _assert_training_row_count(training: pl.DataFrame) -> None:
    expected = EXPECTED_TOTAL_APPLICATIONS - EXPECTED_HOLDOUT_ROWS
    if training.height != expected:
        raise ValueError(f"Training split has {training.height} rows, expected {expected}")


def _logistic_coefficients(fitted: Pipeline) -> dict[str, float]:
    feature_names = fitted.named_steps[PREPROCESS_STEP].get_feature_names_out()
    coefficients = fitted.named_steps[ESTIMATOR_STEP].coef_[0]
    return {
        str(name): float(value) for name, value in zip(feature_names, coefficients, strict=True)
    }


def _metric_values(result: BaselineResult) -> dict[str, float]:
    metrics = {
        METRIC_AUC: result.auc_mean,
        METRIC_AUC_CI_LOWER: result.interval.lower,
        METRIC_AUC_CI_UPPER: result.interval.upper,
        METRIC_AUC_FOLD_STD: result.auc_std,
        METRIC_PR_AUC: result.pr_auc_mean,
        METRIC_BRIER: result.brier_mean,
    }
    metrics.update(
        {f"{METRIC_AUC_FOLD_PREFIX}{index}": auc for index, auc in enumerate(result.fold_aucs)}
    )
    return metrics


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)


def _standard_deviation(values: tuple[float, ...]) -> float:
    mean = _mean(values)
    return float((sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5)


if __name__ == "__main__":
    main()
