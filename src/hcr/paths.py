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
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hcr.config import DataContract

PROJECT_MARKER: Final = "pyproject.toml"

DATA_DIR_NAME: Final = "data"
CONFIGS_DIR_NAME: Final = "configs"
RAW_DIR_NAME: Final = "raw"
BRONZE_DIR_NAME: Final = "bronze"
SILVER_DIR_NAME: Final = "silver"
SPLITS_DIR_NAME: Final = "splits"
FEATURES_DIR_NAME: Final = "features"
MODELS_DIR_NAME: Final = "models"
REPORTS_DIR_NAME: Final = "reports"
FIGURES_DIR_NAME: Final = "figures"

HOLDOUT_IDS_FILENAME: Final = "holdout_ids.parquet"
PARQUET_SUFFIX: Final = ".parquet"
MANIFEST_SUFFIX: Final = ".manifest.json"

PACKAGE_DIR: Final = Path(__file__).resolve().parent


def project_root() -> Path:
    """Return the repository root, the directory holding pyproject.toml.

    Walks upward from this file rather than assuming a fixed depth, so paths
    resolve identically whether the package runs from source or installed.

    Raises:
        RuntimeError: If no ancestor directory contains the project marker.
    """
    search_start = Path(__file__).resolve()
    for candidate in search_start.parents:
        if (candidate / PROJECT_MARKER).is_file():
            return candidate
    raise RuntimeError(f"No ancestor of {search_start} contains {PROJECT_MARKER}")


def data_dir() -> Path:
    """Return the gitignored data root holding every layer directory."""
    return project_root() / DATA_DIR_NAME


def configs_dir() -> Path:
    """Return the directory holding the five YAML configuration files."""
    return project_root() / CONFIGS_DIR_NAME


def raw_dir() -> Path:
    """Return the directory holding the raw CSV files as downloaded."""
    return data_dir() / RAW_DIR_NAME


def raw_path(table: str, contract: DataContract) -> Path:
    """Resolve a logical table name to its raw CSV file.

    The raw tree is not flat: application_train, application_test and
    sample_submission sit in a nested home-credit-default-risk subdirectory
    while the six history files sit directly in raw. The mapping comes from the
    data contract, so this layout detail never leaks into callers. The filename
    is never inferred from the table name because the casing differs:
    pos_cash_balance maps to POS_CASH_balance.csv.

    The contract is passed in rather than loaded here, so resolving a path never
    reads a file behind the caller's back.

    Args:
        table: Logical table name as keyed in configs/data_contract.yml.
        contract: Parsed data contract holding the per-table file entry.

    Raises:
        KeyError: If the table is absent from the data contract.
    """
    if table not in contract.tables:
        known_tables = ", ".join(sorted(contract.tables))
        raise KeyError(f"Unknown table {table!r}; the data contract declares: {known_tables}")
    return raw_dir() / contract.tables[table].file


def bronze_path(table: str) -> Path:
    """Return the Parquet location for a table in the bronze layer."""
    return data_dir() / BRONZE_DIR_NAME / f"{table}{PARQUET_SUFFIX}"


def silver_path(table: str) -> Path:
    """Return the Parquet location for a table in the silver layer."""
    return data_dir() / SILVER_DIR_NAME / f"{table}{PARQUET_SUFFIX}"


def splits_dir() -> Path:
    """Return the directory holding the holdout identifier list and its usage log."""
    return data_dir() / SPLITS_DIR_NAME


def holdout_ids_path() -> Path:
    """Return the file holding the holdout SK_ID_CURR list.

    This list fixes the split across runs. It is written once at step 4 and
    read, never rewritten, by every later step.
    """
    return splits_dir() / HOLDOUT_IDS_FILENAME


def features_path(version: str, configuration: str) -> Path:
    """Return the feature matrix for one version and feature configuration.

    The configuration stays in the filename. The two configurations are compared
    against each other, so they must never collide on disk.

    Args:
        version: Matrix version such as "v1".
        configuration: Either "full" or "no_ext_source".
    """
    filename = f"features_{version}_{configuration}{PARQUET_SUFFIX}"
    return data_dir() / FEATURES_DIR_NAME / filename


def manifest_path(version: str, configuration: str) -> Path:
    """Return the manifest sitting beside a feature matrix.

    Without a manifest recording the column list, the aggregation that produced
    each column and the source data hash, a column such as
    BURO_AMT_CREDIT_SUM_MEAN cannot be traced back to how it was computed.
    Derived from features_path so the two can never drift apart.

    Args:
        version: Matrix version such as "v1".
        configuration: Either "full" or "no_ext_source".
    """
    return features_path(version, configuration).with_suffix(MANIFEST_SUFFIX)


def models_dir() -> Path:
    """Return the directory holding trained models and out-of-fold predictions."""
    return data_dir() / MODELS_DIR_NAME


def sql_dir() -> Path:
    """Return the directory holding the DuckDB aggregation queries.

    Resolved from the package location rather than from project_root, so the
    queries are found when the package is installed as a wheel.
    """
    return PACKAGE_DIR / "features" / "sql"


def ddl_dir() -> Path:
    """Return the directory holding the SQL Server DDL scripts.

    Resolved from the package location for the same reason as sql_dir.
    """
    return PACKAGE_DIR / "serving" / "ddl"


def figures_dir() -> Path:
    """Return the directory for the reliability diagram, decile and SHAP plots."""
    return project_root() / REPORTS_DIR_NAME / FIGURES_DIR_NAME


def ensure_parent(path: Path) -> Path:
    """Create the parent directory of a path and return the path unchanged.

    Returning the argument lets writers call this inline at the point of use.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
