"""Typed, immutable views of the five YAML configuration files.

Frozen so a step cannot mutate a threshold another step relies on, and typed so a
consumer never indexes a raw dictionary by a string it might misspell.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TableContract:
    """Expected shape of one raw source table.

    Attributes:
        file: Path of the CSV relative to the raw directory.
        rows: Exact row count the step 2 gate asserts.
        columns: Exact column count the step 2 gate asserts.
        primary_key: Columns that must be jointly unique, or None for an event
            table such as installments_payments which has no natural key.
        required_columns: Columns whose absence stops the pipeline.
        forbidden_columns: Columns whose presence stops the pipeline, used to
            assert application_test carries no TARGET.
        dtypes: Expected dtype per column, checked where declared.
    """

    file: str
    rows: int
    columns: int
    primary_key: tuple[str, ...] | None
    required_columns: tuple[str, ...]
    forbidden_columns: tuple[str, ...]
    dtypes: dict[str, str]


@dataclass(frozen=True)
class DataContract:
    """Parsed configs/data_contract.yml.

    Attributes:
        tables: Contract per logical table name.
        expected_coverage: Known coverage gaps, reported as warnings rather than
            stops because they describe the data and are not defects.
        target_positive_rate: Published positive rate, 0.0807.
    """

    tables: dict[str, TableContract]
    expected_coverage: dict[str, int]
    target_positive_rate: float


@dataclass(frozen=True)
class SilverRules:
    """Parsed configs/silver_rules.yml.

    Attributes:
        employment_sentinel: The 365243 code, its column and the flag it emits.
        missing_value_codes: Strings acting as nulls in the history tables.
        days_columns: Columns the step 3 gate asserts are at most zero.
        derived_columns: Name to expression for AGE_YEARS and EMPLOYMENT_YEARS.
        missingness_flags: Column to the presence flag it gets.
        history_presence_flags: Source table to its no-history flag.
        winsorize: Column to upper quantile; rows are never dropped.
    """

    employment_sentinel: dict[str, Any]
    missing_value_codes: tuple[str, ...]
    days_columns: tuple[str, ...]
    derived_columns: dict[str, str]
    missingness_flags: dict[str, str]
    history_presence_flags: dict[str, str]
    winsorize: dict[str, float]


@dataclass(frozen=True)
class FeatureSpec:
    """Parsed configs/features.yml.

    Attributes:
        windows_months: The 3, 6, 12 and 24 month windows.
        application_ratios: Ratio name to expression, all six mandatory.
        sources: Per-source aggregation declaration driving SQL generation.
        configurations: The full and no_ext_source variants.
        selection: Post-generation filter criteria, fixed before any result is
            seen and never tuned against AUC.
    """

    windows_months: tuple[int, ...]
    application_ratios: dict[str, str]
    sources: dict[str, dict[str, Any]]
    configurations: dict[str, dict[str, Any]]
    selection: dict[str, Any]


@dataclass(frozen=True)
class ModelConfig:
    """Parsed configs/model.yml.

    Attributes:
        random_seed: The one seed governing split, folds and model.
        holdout_fraction: 0.20.
        target_rate_tolerance_pp: Allowed positive-rate drift between train and
            holdout, in percentage points.
        n_splits: 5.
        lightgbm_params: Hyperparameters passed straight to the estimator.
        calibration_method: "isotonic".
        acceptance: The AUC bounds, including the 0.85 leakage alarm and the
            0.95 univariate ceiling.
        fairness_attributes: CODE_GENDER and AGE_BAND.
        mlflow_experiment_name: Experiment every run is logged under.
    """

    random_seed: int
    holdout_fraction: float
    target_rate_tolerance_pp: float
    n_splits: int
    lightgbm_params: dict[str, Any]
    calibration_method: str
    acceptance: dict[str, float]
    fairness_attributes: tuple[str, ...]
    mlflow_experiment_name: str


@dataclass(frozen=True)
class CostConfig:
    """Parsed configs/cost.yml.

    These values are assumptions, not measurements. Every report that uses them
    states so, because the published label threshold is unknown and the
    calibrated probability is therefore not a Basel PD.

    Attributes:
        profit_margin: Revenue lost per wrongly rejected applicant, as a
            fraction of AMT_CREDIT.
        loss_given_default: Loss per wrongly approved applicant, as a fraction
            of AMT_CREDIT.
        threshold_grid: Minimum, maximum and step of the threshold search.
        decile_count: 10.
    """

    profit_margin: float
    loss_given_default: float
    threshold_grid: dict[str, float]
    decile_count: int
