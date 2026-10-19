"""Connection details read from the environment, never from a config file.

Secrets and connection details come from the environment only, read from a .env file
that is never committed. One variable governs the SQL Server port, shared by
docker-compose, the load script and the Power BI connection string: a port that
disagrees between those three places is a common failure and hard to spot.

A variable set in the process environment wins over the .env file, so CI can override
any value.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from dotenv import dotenv_values

from hcr.config.loaders import load_model_config
from hcr.config.values import ConfigError
from hcr.paths import project_root

logger = logging.getLogger(__name__)

ENV_MSSQL_HOST: Final = "MSSQL_HOST"
ENV_MSSQL_PORT: Final = "MSSQL_PORT"
ENV_MSSQL_DATABASE: Final = "MSSQL_DATABASE"
ENV_MSSQL_PASSWORD: Final = "MSSQL_SA_PASSWORD"
ENV_MLFLOW_URI: Final = "MLFLOW_TRACKING_URI"
ENV_MLFLOW_EXPERIMENT: Final = "MLFLOW_EXPERIMENT_NAME"
ENV_FILENAME: Final = ".env"

MSSQL_ODBC_DRIVER: Final = "ODBC Driver 18 for SQL Server"
MSSQL_LOGIN: Final = "sa"
DEFAULT_MLFLOW_URI: Final = "file:./mlruns"


def mssql_connection_string(env_file: Path | None = None) -> str:
    """Build the SQL Server connection string from the environment.

    Never falls back to a default password or port, because a silent default is
    how a load lands in the wrong instance. The returned value holds the
    password, so it is never logged; only host, port and database are.

    Args:
        env_file: Override for the .env location, used by tests.

    Raises:
        ConfigError: If any of host, port, database or password is absent, or
            the port is not an integer.
    """
    environment = _read_environment(env_file)
    required_names = (ENV_MSSQL_HOST, ENV_MSSQL_PORT, ENV_MSSQL_DATABASE, ENV_MSSQL_PASSWORD)
    missing_names = [name for name in required_names if not environment.get(name)]
    if missing_names:
        raise ConfigError(f"Missing environment variables: {', '.join(missing_names)}")

    host = environment[ENV_MSSQL_HOST]
    port = environment[ENV_MSSQL_PORT]
    database = environment[ENV_MSSQL_DATABASE]
    if not port.isdigit():
        raise ConfigError(f"{ENV_MSSQL_PORT} must be an integer, got {port!r}")

    logger.info("Resolved SQL Server target %s:%s/%s", host, port, database)
    return (
        f"DRIVER={{{MSSQL_ODBC_DRIVER}}};SERVER={host},{port};DATABASE={database};"
        f"UID={MSSQL_LOGIN};PWD={environment[ENV_MSSQL_PASSWORD]};TrustServerCertificate=yes"
    )


def mlflow_tracking_uri(env_file: Path | None = None) -> str:
    """Return the MLflow tracking URI, defaulting to the local mlruns directory.

    Args:
        env_file: Override for the .env location, used by tests.
    """
    return _read_environment(env_file).get(ENV_MLFLOW_URI) or DEFAULT_MLFLOW_URI


def mlflow_experiment_name(env_file: Path | None = None) -> str:
    """Return the MLflow experiment name.

    Defaults to the experiment_name in the model config, so the environment and
    the config cannot disagree silently.

    Args:
        env_file: Override for the .env location, used by tests.
    """
    from_environment = _read_environment(env_file).get(ENV_MLFLOW_EXPERIMENT)
    return from_environment or load_model_config().mlflow_experiment_name


def _read_environment(env_file: Path | None) -> dict[str, str]:
    """Merge .env values with the process environment, the process winning.

    Reads without mutating os.environ, so a test that clears a variable is not
    refilled from a developer's .env.
    """
    dotenv_path = env_file if env_file is not None else project_root() / ENV_FILENAME
    from_file = {
        key: value for key, value in dotenv_values(dotenv_path).items() if value is not None
    }
    return {**from_file, **os.environ}
