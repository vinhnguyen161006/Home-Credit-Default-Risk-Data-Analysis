"""Path resolution. Every artifact location comes from hcr.paths and nowhere else."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcr import paths
from hcr.config import load_data_contract


def test_project_root_holds_the_project_marker() -> None:
    assert (paths.project_root() / paths.PROJECT_MARKER).is_file()


def test_layer_directories_sit_under_the_data_root() -> None:
    data_root = paths.data_dir()

    assert paths.raw_dir().parent == data_root
    assert paths.bronze_path("bureau").parent.parent == data_root
    assert paths.silver_path("bureau").parent.parent == data_root
    assert paths.holdout_ids_path().parent == paths.splits_dir()
    assert paths.models_dir().parent == data_root


def test_raw_path_resolves_nested_application_files() -> None:
    contract = load_data_contract()

    resolved = paths.raw_path("application_train", contract)

    assert resolved == paths.raw_dir() / "home-credit-default-risk" / "application_train.csv"


def test_raw_path_keeps_source_file_casing() -> None:
    contract = load_data_contract()

    assert paths.raw_path("pos_cash_balance", contract).name == "POS_CASH_balance.csv"


def test_raw_path_unknown_table_names_known_tables() -> None:
    contract = load_data_contract()

    with pytest.raises(KeyError, match="bureau_balance"):
        paths.raw_path("bureau_balanse", contract)


def test_feature_configurations_never_collide_on_disk() -> None:
    assert paths.features_path("v1", "full") != paths.features_path("v1", "no_ext_source")


def test_manifest_sits_beside_its_feature_matrix() -> None:
    matrix = paths.features_path("v1", "full")
    manifest = paths.manifest_path("v1", "full")

    assert manifest.parent == matrix.parent
    assert manifest.name == "features_v1_full.manifest.json"


def test_sql_and_ddl_directories_resolve_inside_the_package() -> None:
    assert any(paths.sql_dir().glob("*.sql"))
    assert any(paths.ddl_dir().glob("*.sql"))


def test_ensure_parent_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.parquet"

    returned = paths.ensure_parent(target)

    assert returned == target
    assert target.parent.is_dir()
    assert not target.exists()
