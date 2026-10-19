"""Typed access to the YAML configuration files and the environment.

The package is split by responsibility: values reads YAML and checks types, models holds
the frozen dataclasses, rules holds the business rules a config must satisfy, loaders
reads each of the five files, and environment reads connection details. Callers import
from hcr.config and never from a submodule, so the split stays an internal detail.
"""

from hcr.config.environment import (
    DEFAULT_MLFLOW_URI,
    ENV_MLFLOW_EXPERIMENT,
    ENV_MLFLOW_URI,
    ENV_MSSQL_DATABASE,
    ENV_MSSQL_HOST,
    ENV_MSSQL_PASSWORD,
    ENV_MSSQL_PORT,
    mlflow_experiment_name,
    mlflow_tracking_uri,
    mssql_connection_string,
)
from hcr.config.loaders import (
    EXPECTED_TABLES,
    RANDOM_SEED_KEY,
    load_cost_config,
    load_data_contract,
    load_feature_spec,
    load_model_config,
    load_silver_rules,
    random_seed,
)
from hcr.config.models import (
    CostConfig,
    DataContract,
    FeatureSpec,
    ModelConfig,
    SilverRules,
    TableContract,
)
from hcr.config.values import ConfigError, load_yaml, require_keys

__all__ = [
    "DEFAULT_MLFLOW_URI",
    "ENV_MLFLOW_EXPERIMENT",
    "ENV_MLFLOW_URI",
    "ENV_MSSQL_DATABASE",
    "ENV_MSSQL_HOST",
    "ENV_MSSQL_PASSWORD",
    "ENV_MSSQL_PORT",
    "EXPECTED_TABLES",
    "RANDOM_SEED_KEY",
    "ConfigError",
    "CostConfig",
    "DataContract",
    "FeatureSpec",
    "ModelConfig",
    "SilverRules",
    "TableContract",
    "load_cost_config",
    "load_data_contract",
    "load_feature_spec",
    "load_model_config",
    "load_silver_rules",
    "load_yaml",
    "mlflow_experiment_name",
    "mlflow_tracking_uri",
    "mssql_connection_string",
    "random_seed",
    "require_keys",
]
