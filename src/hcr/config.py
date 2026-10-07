"""Typed access to the YAML configuration files and the environment.

Configuration is data, not code. Thresholds, aggregation lists, hyperparameters
and cost assumptions live in configs/*.yml so they change without touching a
module, and so a run can record which values produced it.

Secrets and connection details come from the environment only. One variable
governs the SQL Server port, shared by docker-compose, the load script and the
Power BI connection string: a port that disagrees between those three places is
a common failure and hard to spot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

RANDOM_SEED_KEY: Final = "random_seed"

ENV_MSSQL_HOST: Final = "MSSQL_HOST"
ENV_MSSQL_PORT: Final = "MSSQL_PORT"
ENV_MSSQL_DATABASE: Final = "MSSQL_DATABASE"
ENV_MSSQL_PASSWORD: Final = "MSSQL_SA_PASSWORD"
ENV_MLFLOW_URI: Final = "MLFLOW_TRACKING_URI"
ENV_MLFLOW_EXPERIMENT: Final = "MLFLOW_EXPERIMENT_NAME"

COST_FRACTION_KEYS: Final = ("profit_margin", "loss_given_default")


class ConfigError(Exception):
    """Raised when a configuration file is missing a key or holds a bad value.

    Carries the file and the key so the message is actionable without opening
    the YAML.
    """


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
    """

    random_seed: int
    holdout_fraction: float
    target_rate_tolerance_pp: float
    n_splits: int
    lightgbm_params: dict[str, Any]
    calibration_method: str
    acceptance: dict[str, float]
    fairness_attributes: tuple[str, ...]


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


def load_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file into a plain dictionary.

    The single reader for every config file, so encoding and error handling are
    defined once.

    Args:
        path: File to read.

    Raises:
        ConfigError: If the file is absent or does not parse to a mapping.

    TODO:
        - Read with yaml.safe_load and UTF-8 encoding. Never yaml.load: a config
          file must not be able to construct arbitrary Python objects.
        - Raise ConfigError naming the path when the file is missing or when the
          parsed value is not a mapping.
    """
    raise NotImplementedError


def require_keys(data: dict[str, Any], keys: tuple[str, ...], source: Path) -> None:
    """Assert every required key is present, naming the file when one is not.

    Validation happens at load time rather than at the point of use, so a typo
    in a config file surfaces before a four-minute aggregation runs.

    Args:
        data: Parsed config mapping.
        keys: Keys that must be present.
        source: File the mapping came from, used in the message.

    Raises:
        ConfigError: If any key is absent.

    TODO:
        - Collect every missing key and raise once listing all of them. Raising
          on the first makes fixing a config an iterative guessing game.
    """
    raise NotImplementedError


def load_data_contract() -> DataContract:
    """Load and validate configs/data_contract.yml.

    TODO:
        - Build one TableContract per entry under 'tables'.
        - Map a null primary_key to None rather than an empty tuple, so an event
          table is distinguishable from a declaration mistake.
        - Default required_columns, forbidden_columns and dtypes to empty when
          absent; they are optional per table.
        - Assert the eight expected table names are all present.
    """
    raise NotImplementedError


def load_silver_rules() -> SilverRules:
    """Load and validate configs/silver_rules.yml.

    TODO:
        - Read days_columns from days_columns_sign.columns.
        - Assert the employment sentinel value is 365243 and that it declares an
          emit_flag; the flag is what preserves the signal after nulling.
        - Ignore the 'rationale' and 'note' keys: they document the file for a
          reader and carry no behaviour.
    """
    raise NotImplementedError


def load_feature_spec() -> FeatureSpec:
    """Load and validate configs/features.yml.

    TODO:
        - Assert all six mandatory application ratios are declared.
        - Assert every source declares a prefix drawn from the fixed set
          APP, BURO, BB, PREV, POS, INST, CC, and that prefixes are unique.
        - Assert every stage-1 source that declares roll_up_to also declares
          join_from, since a second fold needs a parent table to fold through.
        - Assert the declared aggregations name no column twice with the same
          function, which would generate a duplicate output column.
    """
    raise NotImplementedError


def load_model_config() -> ModelConfig:
    """Load and validate configs/model.yml.

    TODO:
        - Assert holdout_fraction lies in (0, 1) and n_splits is at least 2.
        - Assert acceptance.holdout_auc_min is below acceptance.holdout_auc_max
          and that leakage_alarm_auc exceeds holdout_auc_max.
        - Assert class_imbalance.synthetic_oversampling is "forbidden". The
          config states the rule; this check stops a silent edit from relaxing
          it, because synthetic samples destroy calibration.
        - Assert cross_validation.time_based is false, since the data carries no
          usable time axis.
    """
    raise NotImplementedError


def load_cost_config() -> CostConfig:
    """Load and validate configs/cost.yml.

    TODO:
        - Assert profit_margin and loss_given_default both lie in the open
          interval (0, 1). A cost outside that range silently produces a
          meaningless threshold rather than failing.
        - Assert the threshold grid is ordered and its step is positive.
    """
    raise NotImplementedError


def random_seed() -> int:
    """Return the one seed governing every stochastic step.

    Passed explicitly into each function that needs it. Never applied through a
    global call such as np.random.seed, which hides where randomness enters.

    TODO:
        - Read RANDOM_SEED_KEY from the model config.
    """
    raise NotImplementedError


def mssql_connection_string() -> str:
    """Build the SQL Server connection string from the environment.

    Raises:
        ConfigError: If any of host, port, database or password is absent.

    TODO:
        - Read the four ENV_MSSQL_* variables. Raise ConfigError naming the
          missing variable; never fall back to a default password or port,
          because a silent default is how a load lands in the wrong instance.
        - Let a real environment variable win over .env, so CI can override it.
        - Keep the password out of the returned value's logged form, out of
          exception messages and out of __repr__. Log host, port and database
          only.
    """
    raise NotImplementedError


def mlflow_tracking_uri() -> str:
    """Return the MLflow tracking URI, defaulting to the local mlruns directory.

    TODO:
        - Read ENV_MLFLOW_URI, defaulting to "file:./mlruns" as documented in
          .env.example.
    """
    raise NotImplementedError


def mlflow_experiment_name() -> str:
    """Return the MLflow experiment name.

    TODO:
        - Read ENV_MLFLOW_EXPERIMENT, defaulting to the experiment_name in the
          model config so the two cannot disagree.
    """
    raise NotImplementedError
