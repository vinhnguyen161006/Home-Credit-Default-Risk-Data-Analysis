"""Baseline sequence on a small synthetic applicant table.

The table is built here rather than taken from the shared fixtures. The shared application
fixture holds four positives, too few for five stratified folds, and the baselines need a
real signal to prove they learn anything. Every expected figure is a property of the
construction, not a number copied from the real dataset.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from mlflow.tracking import MlflowClient

from hcr.evaluation.confidence import auc_interval
from hcr.modeling.baselines import (
    EXT_SOURCE_ONLY,
    TAG_BASELINE_NAME,
    BaselineResult,
    baseline_application_and_ratios,
    baseline_constant_rate,
    baseline_ext_source_only,
    exclude_holdout,
    log_baseline_to_mlflow,
)
from hcr.modeling.pipeline import ID_COLUMN, LABEL_COLUMN
from hcr.modeling.train import stratified_folds

ROW_COUNT = 400
POSITIVE_RATE = 0.1
N_SPLITS = 5
SEED = 42
EXT_SOURCE_COLUMNS = ("EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3")
RATE_TOLERANCE = 0.02
EXPECTED_AUC = 0.7
TOLERANCE = 0.05


@pytest.fixture
def applicants() -> pl.DataFrame:
    rng = np.random.default_rng(SEED)
    label = (rng.uniform(size=ROW_COUNT) < POSITIVE_RATE).astype(np.int64)
    ext_one = rng.normal(size=ROW_COUNT) - 1.5 * label
    ext_one_with_gaps = np.where(np.arange(ROW_COUNT) % 3 == 0, np.nan, ext_one)
    frame = pl.DataFrame(
        {
            ID_COLUMN: rng.permutation(ROW_COUNT).astype(np.int64) + 100_000,
            LABEL_COLUMN: label,
            "EXT_SOURCE_1": ext_one_with_gaps,
            "EXT_SOURCE_2": rng.normal(size=ROW_COUNT),
            "EXT_SOURCE_3": rng.normal(size=ROW_COUNT),
            "AMT_CREDIT": rng.uniform(1e5, 1e6, ROW_COUNT),
            "APP_CREDIT_INCOME_RATIO": rng.uniform(1.0, 6.0, ROW_COUNT),
            "ORGANIZATION_TYPE": rng.choice(["School", "Business Entity"], ROW_COUNT),
        }
    )
    return frame.sort(ID_COLUMN)


@pytest.fixture
def folds(applicants: pl.DataFrame) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    return stratified_folds(applicants[LABEL_COLUMN], N_SPLITS, SEED)


def test_constant_baseline_fold_aucs_are_exactly_half(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    result = baseline_constant_rate(
        applicants[LABEL_COLUMN], folds, expected_auc=0.5, auc_tolerance=TOLERANCE
    )

    assert result.fold_aucs == pytest.approx((0.5,) * N_SPLITS)
    assert result.matches_expectation


def test_constant_baseline_reports_the_all_zero_accuracy_it_excludes(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    result = baseline_constant_rate(
        applicants[LABEL_COLUMN], folds, expected_auc=0.5, auc_tolerance=TOLERANCE
    )

    assert result.detail["accuracy_all_zeros"] == pytest.approx(1 - applicants[LABEL_COLUMN].mean())


def test_ext_source_baseline_uses_only_the_three_score_columns(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    result = baseline_ext_source_only(
        applicants,
        applicants[LABEL_COLUMN],
        folds,
        EXT_SOURCE_COLUMNS,
        expected_auc=EXPECTED_AUC,
        auc_tolerance=TOLERANCE,
    )

    assert result.feature_count == len(EXT_SOURCE_COLUMNS)
    assert all("EXT_SOURCE" in name for name in result.detail)


def test_ext_source_baseline_learns_the_planted_signal(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    result = baseline_ext_source_only(
        applicants,
        applicants[LABEL_COLUMN],
        folds,
        EXT_SOURCE_COLUMNS,
        expected_auc=EXPECTED_AUC,
        auc_tolerance=TOLERANCE,
    )

    assert result.auc_mean > 0.6


def test_application_baseline_reports_a_coefficient_for_encoded_categories(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    result = baseline_application_and_ratios(
        applicants,
        applicants[LABEL_COLUMN],
        folds,
        expected_auc=EXPECTED_AUC,
        auc_tolerance=TOLERANCE,
    )

    assert any("ORGANIZATION_TYPE" in name for name in result.detail)
    assert result.feature_count == applicants.width - 2


def test_stratified_folds_partition_every_row_exactly_once(
    folds: tuple[tuple[np.ndarray, np.ndarray], ...],
) -> None:
    validation_rows = np.concatenate([valid for _, valid in folds])

    assert sorted(validation_rows.tolist()) == list(range(ROW_COUNT))


def test_stratified_folds_hold_the_positive_rate_in_every_fold(
    applicants: pl.DataFrame, folds: tuple[tuple[np.ndarray, np.ndarray], ...]
) -> None:
    labels = applicants[LABEL_COLUMN].to_numpy()
    overall_rate = labels.mean()

    for _, valid in folds:
        assert labels[valid].mean() == pytest.approx(overall_rate, abs=RATE_TOLERANCE)


def test_stratified_folds_repeat_exactly_under_the_same_seed(
    applicants: pl.DataFrame,
) -> None:
    first = stratified_folds(applicants[LABEL_COLUMN], N_SPLITS, SEED)
    second = stratified_folds(applicants[LABEL_COLUMN], N_SPLITS, SEED)

    for (first_train, first_valid), (second_train, second_valid) in zip(first, second, strict=True):
        assert np.array_equal(first_train, second_train)
        assert np.array_equal(first_valid, second_valid)


def test_exclude_holdout_removes_every_holdout_identifier() -> None:
    frame = pl.DataFrame({ID_COLUMN: [5, 1, 9, 3, 7], LABEL_COLUMN: [0, 1, 0, 0, 1]})
    holdout = pl.Series("anything", [3, 7])

    training = exclude_holdout(frame, holdout)

    assert training[ID_COLUMN].to_list() == [1, 5, 9]


def test_log_baseline_to_mlflow_records_tags_metrics_and_fold_aucs(tmp_path: Path) -> None:
    interval = auc_interval(0.74, 40, 360)
    result = BaselineResult(
        name=EXT_SOURCE_ONLY,
        sequence_step=1,
        auc_mean=0.74,
        auc_std=0.01,
        fold_aucs=(0.73, 0.75, 0.74, 0.74, 0.74),
        interval=interval,
        pr_auc_mean=0.2,
        brier_mean=0.08,
        feature_count=3,
        matches_expectation=True,
        detail={"numeric__EXT_SOURCE_1": -0.5},
    )
    tracking_uri = (tmp_path / "mlruns").as_uri()

    run_id = log_baseline_to_mlflow(result, tracking_uri, "baseline-test", N_SPLITS, SEED)
    run = MlflowClient(tracking_uri=tracking_uri).get_run(run_id)

    assert run.data.tags[TAG_BASELINE_NAME] == EXT_SOURCE_ONLY
    assert run.data.metrics["auc"] == pytest.approx(0.74)
    assert run.data.metrics["auc_fold_4"] == pytest.approx(0.74)
    assert run.data.metrics["auc_ci_lower"] == pytest.approx(interval.lower)
