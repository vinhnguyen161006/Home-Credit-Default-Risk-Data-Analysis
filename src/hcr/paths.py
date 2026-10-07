"""Canonical filesystem locations for every pipeline artifact.

Single source of truth for paths. No module builds a path by string
concatenation and no module hardcodes a directory name, so moving a layer
touches this file only.

Layer boundaries are contract boundaries. Bronze is a faithful copy of raw,
silver is normalized at the original grain, features is the wide training matrix
at customer grain. A step reads one layer and writes the next; it never writes
into the layer it read from.

Importing this module has no side effects. Directories are created on demand by
ensure_parent, never at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

PROJECT_MARKER: Final = "pyproject.toml"

RAW_DIR_NAME: Final = "raw"
BRONZE_DIR_NAME: Final = "bronze"
SILVER_DIR_NAME: Final = "silver"
SPLITS_DIR_NAME: Final = "splits"
FEATURES_DIR_NAME: Final = "features"

HOLDOUT_IDS_FILENAME: Final = "holdout_ids.parquet"


def project_root() -> Path:
    """Return the repository root, the directory holding pyproject.toml.

    Walks upward from this file rather than assuming a fixed depth, so paths
    resolve identically whether the package runs from source or installed.

    Raises:
        RuntimeError: If no ancestor directory contains the project marker.

    TODO:
        - Walk Path(__file__).resolve().parents until PROJECT_MARKER is found.
        - Raise RuntimeError naming the search start when nothing is found;
          returning a wrong root silently writes data outside the repository.
    """
    raise NotImplementedError


def data_dir() -> Path:
    """Return the gitignored data root holding every layer directory.

    TODO:
        - Return project_root() / "data".
    """
    raise NotImplementedError


def configs_dir() -> Path:
    """Return the directory holding the five YAML configuration files.

    TODO:
        - Return project_root() / "configs".
    """
    raise NotImplementedError


def raw_dir() -> Path:
    """Return the directory holding the raw CSV files as downloaded.

    TODO:
        - Return data_dir() / RAW_DIR_NAME.
    """
    raise NotImplementedError


def raw_path(table: str) -> Path:
    """Resolve a logical table name to its raw CSV file.

    The raw tree is not flat: application_train, application_test and
    sample_submission sit in a nested home-credit-default-risk subdirectory
    while the six history files sit directly in raw. The mapping comes from the
    data contract, so this layout detail never leaks into callers.

    Args:
        table: Logical table name as keyed in configs/data_contract.yml.

    Raises:
        KeyError: If the table is absent from the data contract.

    TODO:
        - Read the per-table 'file' entry from the data contract and join it
          onto raw_dir(). Do not infer the filename from the table name: the
          casing differs (pos_cash_balance maps to POS_CASH_balance.csv).
        - Raise KeyError naming the table and listing the known names, so a
          typo is diagnosable without opening the YAML.
    """
    raise NotImplementedError


def bronze_path(table: str) -> Path:
    """Return the Parquet location for a table in the bronze layer.

    TODO:
        - Return data_dir() / BRONZE_DIR_NAME / f"{table}.parquet".
    """
    raise NotImplementedError


def silver_path(table: str) -> Path:
    """Return the Parquet location for a table in the silver layer.

    TODO:
        - Return data_dir() / SILVER_DIR_NAME / f"{table}.parquet".
    """
    raise NotImplementedError


def holdout_ids_path() -> Path:
    """Return the file holding the holdout SK_ID_CURR list.

    This list fixes the split across runs. It is written once at step 4 and
    read, never rewritten, by every later step.

    TODO:
        - Return data_dir() / SPLITS_DIR_NAME / HOLDOUT_IDS_FILENAME.
    """
    raise NotImplementedError


def features_path(version: str, configuration: str) -> Path:
    """Return the feature matrix for one version and feature configuration.

    Args:
        version: Matrix version such as "v1".
        configuration: Either "full" or "no_ext_source".

    TODO:
        - Return data_dir() / FEATURES_DIR_NAME /
          f"features_{version}_{configuration}.parquet".
        - Keep the configuration in the filename. The two configurations are
          compared against each other, so they must never collide on disk.
    """
    raise NotImplementedError


def manifest_path(version: str, configuration: str) -> Path:
    """Return the manifest sitting beside a feature matrix.

    Without a manifest recording the column list, the aggregation that produced
    each column and the source data hash, a column such as
    BURO_AMT_CREDIT_SUM_MEAN cannot be traced back to how it was computed.

    TODO:
        - Return the features_path sibling with suffix ".manifest.json".
        - Derive it from features_path so the two can never drift apart.
    """
    raise NotImplementedError


def sql_dir() -> Path:
    """Return the directory holding the DuckDB aggregation queries.

    TODO:
        - Return the package directory / "features" / "sql".
        - Resolve it from __file__, not from project_root(), so the queries are
          found when the package is installed as a wheel.
    """
    raise NotImplementedError


def ddl_dir() -> Path:
    """Return the directory holding the SQL Server DDL scripts.

    TODO:
        - Return the package directory / "serving" / "ddl", resolved from
          __file__ for the same reason as sql_dir.
    """
    raise NotImplementedError


def figures_dir() -> Path:
    """Return the directory for the reliability diagram, decile and SHAP plots.

    TODO:
        - Return project_root() / "reports" / "figures".
    """
    raise NotImplementedError


def ensure_parent(path: Path) -> Path:
    """Create the parent directory of a path and return the path unchanged.

    Returning the argument lets writers call this inline at the point of use.

    TODO:
        - Call path.parent.mkdir(parents=True, exist_ok=True) and return path.
    """
    raise NotImplementedError
