"""Loaders for the five YAML configuration files.

Configuration is data, not code. Thresholds, aggregation lists, hyperparameters and cost
assumptions live in configs/*.yml so they change without touching a module, and so a run
can record which values produced it.

Every loader validates at load time and never falls back to a default for a missing key.
Each accepts an optional path so a test can load a modified copy of the real file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from hcr.config.models import CostConfig, DataContract, FeatureSpec, ModelConfig, SilverRules
from hcr.config.rules import (
    parse_acceptance,
    parse_baselines,
    parse_employment_sentinel,
    parse_table_contract,
    validate_cost_fractions,
    validate_model_rules,
    validate_prefixes,
    validate_source_entry,
    validate_split_policy,
    validate_threshold_grid,
)
from hcr.config.values import (
    load_yaml,
    parse_nested_field,
    parse_string_mapping,
    require_int,
    require_keys,
    require_list,
    require_mapping,
    require_number,
    require_section,
    require_string,
    require_string_tuple,
    strip_annotations,
)
from hcr.paths import configs_dir

RANDOM_SEED_KEY: Final = "random_seed"

DATA_CONTRACT_FILENAME: Final = "data_contract.yml"
SILVER_RULES_FILENAME: Final = "silver_rules.yml"
FEATURES_FILENAME: Final = "features.yml"
MODEL_FILENAME: Final = "model.yml"
COST_FILENAME: Final = "cost.yml"

EXPECTED_TABLES: Final = (
    "application_train",
    "application_test",
    "bureau",
    "bureau_balance",
    "previous_application",
    "pos_cash_balance",
    "installments_payments",
    "credit_card_balance",
)

SILVER_RULES_KEYS: Final = (
    "employment_sentinel",
    "missing_value_codes",
    "days_columns_sign",
    "derived_columns",
    "missingness_flags",
    "history_presence_flags",
    "winsorize",
)

FEATURE_SPEC_KEYS: Final = (
    "windows_months",
    "application_ratios",
    "sources",
    "configurations",
    "selection",
)

MANDATORY_APPLICATION_RATIOS: Final = (
    "CREDIT_INCOME_RATIO",
    "ANNUITY_INCOME_RATIO",
    "CREDIT_GOODS_RATIO",
    "CREDIT_ANNUITY_RATIO",
    "EMPLOYED_BIRTH_RATIO",
    "INCOME_PER_FAMILY_MEMBER",
)

MODEL_CONFIG_KEYS: Final = (
    RANDOM_SEED_KEY,
    "split",
    "cross_validation",
    "class_imbalance",
    "baselines",
    "lightgbm",
    "calibration",
    "acceptance",
    "fairness",
    "mlflow",
)

COST_FRACTION_KEYS: Final = ("profit_margin", "loss_given_default")
THRESHOLD_GRID_KEYS: Final = ("min", "max", "step")


def load_data_contract(path: Path | None = None) -> DataContract:
    """Load and validate configs/data_contract.yml.

    Args:
        path: Override for the file location, used by tests.

    Raises:
        ConfigError: If a key is missing, a value has the wrong type, or one of
            the eight source tables is not declared.
    """
    source = _resolve_config_path(path, DATA_CONTRACT_FILENAME)
    data = load_yaml(source)
    require_keys(data, ("tables", "expected_coverage", "target"), source)

    tables_section = require_mapping(data["tables"], "tables", source)
    require_keys(tables_section, EXPECTED_TABLES, source)
    coverage_section = strip_annotations(
        require_mapping(data["expected_coverage"], "expected_coverage", source)
    )
    target_section = require_section(data, "target", ("positive_rate",), source)

    return DataContract(
        tables={
            name: parse_table_contract(name, entry, source)
            for name, entry in tables_section.items()
        },
        expected_coverage={
            key: require_int(value, f"expected_coverage.{key}", source)
            for key, value in coverage_section.items()
        },
        target_positive_rate=require_number(
            target_section["positive_rate"], "target.positive_rate", source
        ),
    )


def load_silver_rules(path: Path | None = None) -> SilverRules:
    """Load and validate configs/silver_rules.yml.

    Args:
        path: Override for the file location, used by tests.

    Raises:
        ConfigError: If a key is missing or the sentinel declaration is wrong.
    """
    source = _resolve_config_path(path, SILVER_RULES_FILENAME)
    data = load_yaml(source)
    require_keys(data, SILVER_RULES_KEYS, source)
    missing_codes = require_section(data, "missing_value_codes", ("codes",), source)
    days_section = require_section(data, "days_columns_sign", ("columns",), source)
    winsorize = parse_nested_field(data["winsorize"], "winsorize", "upper_quantile", source)

    return SilverRules(
        employment_sentinel=parse_employment_sentinel(data["employment_sentinel"], source),
        missing_value_codes=require_string_tuple(
            missing_codes["codes"], "missing_value_codes.codes", source
        ),
        days_columns=require_string_tuple(
            days_section["columns"], "days_columns_sign.columns", source
        ),
        derived_columns=parse_nested_field(
            data["derived_columns"], "derived_columns", "expression", source
        ),
        missingness_flags=parse_string_mapping(
            data["missingness_flags"], "missingness_flags", source
        ),
        history_presence_flags=parse_string_mapping(
            data["history_presence_flags"], "history_presence_flags", source
        ),
        winsorize={
            column: require_number(quantile, f"winsorize.{column}.upper_quantile", source)
            for column, quantile in winsorize.items()
        },
    )


def load_feature_spec(path: Path | None = None) -> FeatureSpec:
    """Load and validate configs/features.yml.

    Args:
        path: Override for the file location, used by tests.

    Raises:
        ConfigError: If a mandatory ratio is missing, a prefix is outside the
            fixed set or repeated, a rolled-up source has no parent to fold
            through, or an aggregation is declared twice for one column.
    """
    source = _resolve_config_path(path, FEATURES_FILENAME)
    data = load_yaml(source)
    require_keys(data, FEATURE_SPEC_KEYS, source)

    ratios_section = require_section(data, "application_ratios", ("prefix", "ratios"), source)
    ratios = parse_string_mapping(ratios_section["ratios"], "application_ratios.ratios", source)
    require_keys(ratios, MANDATORY_APPLICATION_RATIOS, source)

    sources = {
        name: require_mapping(entry, f"sources.{name}", source)
        for name, entry in require_mapping(data["sources"], "sources", source).items()
    }
    validate_prefixes(ratios_section["prefix"], sources, source)
    for name, entry in sources.items():
        validate_source_entry(name, entry, source)

    configurations = strip_annotations(
        require_mapping(data["configurations"], "configurations", source)
    )
    return FeatureSpec(
        windows_months=tuple(
            require_int(window, "windows_months", source)
            for window in require_list(data["windows_months"], "windows_months", source)
        ),
        application_ratios=ratios,
        sources=sources,
        configurations={
            name: require_mapping(entry, f"configurations.{name}", source)
            for name, entry in configurations.items()
        },
        selection=strip_annotations(require_mapping(data["selection"], "selection", source)),
    )


def load_model_config(path: Path | None = None) -> ModelConfig:
    """Load and validate configs/model.yml.

    Beyond key presence, this asserts the two rules a silent edit could relax:
    synthetic oversampling stays forbidden and validation stays non-temporal.

    Args:
        path: Override for the file location, used by tests.

    Raises:
        ConfigError: If a key is missing, a bound is out of order, or either
            rule above is relaxed.
    """
    source = _resolve_config_path(path, MODEL_FILENAME)
    data = load_yaml(source)
    require_keys(data, MODEL_CONFIG_KEYS, source)

    split = require_section(data, "split", ("holdout_fraction", "target_rate_tolerance_pp"), source)
    cross_validation = require_section(data, "cross_validation", ("n_splits", "time_based"), source)
    holdout_fraction = require_number(split["holdout_fraction"], "split.holdout_fraction", source)
    n_splits = require_int(cross_validation["n_splits"], "cross_validation.n_splits", source)
    validate_split_policy(holdout_fraction, n_splits, source)
    validate_model_rules(data["class_imbalance"], cross_validation, source)

    return ModelConfig(
        random_seed=require_int(data[RANDOM_SEED_KEY], RANDOM_SEED_KEY, source),
        holdout_fraction=holdout_fraction,
        target_rate_tolerance_pp=require_number(
            split["target_rate_tolerance_pp"], "split.target_rate_tolerance_pp", source
        ),
        n_splits=n_splits,
        lightgbm_params=strip_annotations(require_mapping(data["lightgbm"], "lightgbm", source)),
        calibration_method=require_string(
            require_section(data, "calibration", ("method",), source)["method"],
            "calibration.method",
            source,
        ),
        acceptance=parse_acceptance(data["acceptance"], source),
        fairness_attributes=require_string_tuple(
            require_section(data, "fairness", ("attributes",), source)["attributes"],
            "fairness.attributes",
            source,
        ),
        baselines=parse_baselines(data["baselines"], source),
        mlflow_experiment_name=require_string(
            require_section(data, "mlflow", ("experiment_name",), source)["experiment_name"],
            "mlflow.experiment_name",
            source,
        ),
    )


def load_cost_config(path: Path | None = None) -> CostConfig:
    """Load and validate configs/cost.yml.

    Args:
        path: Override for the file location, used by tests.

    Raises:
        ConfigError: If a key is missing, a fraction is out of range, or the
            threshold grid is unordered or has a non-positive step.
    """
    source = _resolve_config_path(path, COST_FILENAME)
    data = load_yaml(source)
    require_keys(data, (*COST_FRACTION_KEYS, "threshold_search", "reporting"), source)

    fractions = {key: require_number(data[key], key, source) for key in COST_FRACTION_KEYS}
    validate_cost_fractions(fractions, source)
    search = require_section(data, "threshold_search", THRESHOLD_GRID_KEYS, source)
    threshold_grid = {
        key: require_number(search[key], f"threshold_search.{key}", source)
        for key in THRESHOLD_GRID_KEYS
    }
    validate_threshold_grid(threshold_grid, source)
    reporting = require_section(data, "reporting", ("decile_count",), source)

    return CostConfig(
        profit_margin=fractions["profit_margin"],
        loss_given_default=fractions["loss_given_default"],
        threshold_grid=threshold_grid,
        decile_count=require_int(reporting["decile_count"], "reporting.decile_count", source),
    )


def random_seed() -> int:
    """Return the one seed governing every stochastic step.

    Passed explicitly into each function that needs it. Never applied through a
    global call such as np.random.seed, which hides where randomness enters.
    """
    return load_model_config().random_seed


def _resolve_config_path(path: Path | None, filename: str) -> Path:
    return path if path is not None else configs_dir() / filename
