"""Configuration loading. Every YAML file loads, and a missing key fails loudly.

Each negative test loads a copy of the real config with one change applied, so the test
exercises the exact file the pipeline reads rather than a hand-written imitation of it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from hcr import config
from hcr.paths import configs_dir

Loader = Callable[[Path], object]

LOADERS_BY_FILE: list[tuple[str, Loader, str]] = [
    ("data_contract.yml", config.load_data_contract, "tables"),
    ("silver_rules.yml", config.load_silver_rules, "employment_sentinel"),
    ("features.yml", config.load_feature_spec, "application_ratios"),
    ("model.yml", config.load_model_config, "random_seed"),
    ("cost.yml", config.load_cost_config, "profit_margin"),
]

MSSQL_ENVIRONMENT = {
    config.ENV_MSSQL_HOST: "localhost",
    config.ENV_MSSQL_PORT: "14330",
    config.ENV_MSSQL_DATABASE: "HomeCredit",
    config.ENV_MSSQL_PASSWORD: "Secret_Passw0rd",
}


def _write_modified_config(
    tmp_path: Path, filename: str, modify: Callable[[dict[str, Any]], None]
) -> Path:
    data = yaml.safe_load((configs_dir() / filename).read_text(encoding="utf-8"))
    modify(data)
    target = tmp_path / filename
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    return target


@pytest.fixture
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in (*MSSQL_ENVIRONMENT, config.ENV_MLFLOW_URI, config.ENV_MLFLOW_EXPERIMENT):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / ".env"


@pytest.mark.parametrize(("filename", "loader", "_key"), LOADERS_BY_FILE)
def test_config_loader_reads_the_repository_file(filename: str, loader: Loader, _key: str) -> None:
    assert loader(configs_dir() / filename) is not None


@pytest.mark.parametrize(("filename", "loader", "key"), LOADERS_BY_FILE)
def test_config_loader_missing_key_names_file_and_key(
    tmp_path: Path, filename: str, loader: Loader, key: str
) -> None:
    modified = _write_modified_config(tmp_path, filename, lambda data: data.pop(key))

    with pytest.raises(config.ConfigError, match=key) as raised:
        loader(modified)

    assert filename in str(raised.value)


def test_require_keys_lists_every_missing_key() -> None:
    with pytest.raises(config.ConfigError, match="alpha, gamma"):
        config.require_keys({"beta": 1}, ("alpha", "beta", "gamma"), Path("example.yml"))


def test_load_yaml_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="not found"):
        config.load_yaml(tmp_path / "absent.yml")


def test_load_yaml_non_mapping_raises(tmp_path: Path) -> None:
    target = tmp_path / "list.yml"
    target.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(config.ConfigError, match="mapping"):
        config.load_yaml(target)


def test_data_contract_missing_table_raises(tmp_path: Path) -> None:
    modified = _write_modified_config(
        tmp_path, "data_contract.yml", lambda data: data["tables"].pop("bureau_balance")
    )

    with pytest.raises(config.ConfigError, match="bureau_balance"):
        config.load_data_contract(modified)


def test_data_contract_event_table_has_no_primary_key() -> None:
    contract = config.load_data_contract()

    assert contract.tables["installments_payments"].primary_key is None
    assert contract.tables["bureau"].primary_key == ("SK_ID_BUREAU",)


def test_data_contract_application_test_forbids_target() -> None:
    contract = config.load_data_contract()

    assert contract.tables["application_test"].forbidden_columns == ("TARGET",)


def test_silver_rules_wrong_sentinel_value_raises(tmp_path: Path) -> None:
    def change_sentinel(data: dict[str, Any]) -> None:
        data["employment_sentinel"]["value"] = 365244

    modified = _write_modified_config(tmp_path, "silver_rules.yml", change_sentinel)

    with pytest.raises(config.ConfigError, match="365243"):
        config.load_silver_rules(modified)


def test_silver_rules_strip_annotation_keys() -> None:
    rules = config.load_silver_rules()

    assert "rationale" not in rules.missingness_flags
    assert "rationale" not in rules.history_presence_flags
    assert rules.employment_sentinel["emit_flag"] == "FLAG_NO_EMPLOYMENT"


def test_feature_spec_missing_mandatory_ratio_raises(tmp_path: Path) -> None:
    def drop_ratio(data: dict[str, Any]) -> None:
        data["application_ratios"]["ratios"].pop("EMPLOYED_BIRTH_RATIO")

    modified = _write_modified_config(tmp_path, "features.yml", drop_ratio)

    with pytest.raises(config.ConfigError, match="EMPLOYED_BIRTH_RATIO"):
        config.load_feature_spec(modified)


def test_feature_spec_unknown_prefix_raises(tmp_path: Path) -> None:
    def rename_prefix(data: dict[str, Any]) -> None:
        data["sources"]["bureau"]["prefix"] = "BUREAU"

    modified = _write_modified_config(tmp_path, "features.yml", rename_prefix)

    with pytest.raises(config.ConfigError, match="BUREAU"):
        config.load_feature_spec(modified)


def test_feature_spec_duplicate_prefix_raises(tmp_path: Path) -> None:
    def duplicate_prefix(data: dict[str, Any]) -> None:
        data["sources"]["credit_card_balance"]["prefix"] = "POS"

    modified = _write_modified_config(tmp_path, "features.yml", duplicate_prefix)

    with pytest.raises(config.ConfigError, match="more than once"):
        config.load_feature_spec(modified)


def test_feature_spec_roll_up_without_parent_raises(tmp_path: Path) -> None:
    def drop_parent(data: dict[str, Any]) -> None:
        data["sources"]["pos_cash_balance"].pop("join_from")

    modified = _write_modified_config(tmp_path, "features.yml", drop_parent)

    with pytest.raises(config.ConfigError, match="join_from"):
        config.load_feature_spec(modified)


def test_feature_spec_repeated_aggregation_raises(tmp_path: Path) -> None:
    def repeat_function(data: dict[str, Any]) -> None:
        data["sources"]["bureau"]["aggregations"]["AMT_CREDIT_SUM"].append("mean")

    modified = _write_modified_config(tmp_path, "features.yml", repeat_function)

    with pytest.raises(config.ConfigError, match="AMT_CREDIT_SUM"):
        config.load_feature_spec(modified)


def test_model_config_synthetic_oversampling_cannot_be_relaxed(tmp_path: Path) -> None:
    def allow_smote(data: dict[str, Any]) -> None:
        data["class_imbalance"]["synthetic_oversampling"] = "allowed"

    modified = _write_modified_config(tmp_path, "model.yml", allow_smote)

    with pytest.raises(config.ConfigError, match="synthetic_oversampling"):
        config.load_model_config(modified)


def test_model_config_time_based_validation_cannot_be_enabled(tmp_path: Path) -> None:
    def enable_time_split(data: dict[str, Any]) -> None:
        data["cross_validation"]["time_based"] = True

    modified = _write_modified_config(tmp_path, "model.yml", enable_time_split)

    with pytest.raises(config.ConfigError, match="time_based"):
        config.load_model_config(modified)


def test_model_config_holdout_fraction_outside_unit_interval_raises(tmp_path: Path) -> None:
    def widen_holdout(data: dict[str, Any]) -> None:
        data["split"]["holdout_fraction"] = 1.2

    modified = _write_modified_config(tmp_path, "model.yml", widen_holdout)

    with pytest.raises(config.ConfigError, match="holdout_fraction"):
        config.load_model_config(modified)


def test_model_config_leakage_alarm_must_exceed_acceptance_ceiling(tmp_path: Path) -> None:
    def lower_alarm(data: dict[str, Any]) -> None:
        data["acceptance"]["leakage_alarm_auc"] = 0.79

    modified = _write_modified_config(tmp_path, "model.yml", lower_alarm)

    with pytest.raises(config.ConfigError, match="leakage_alarm_auc"):
        config.load_model_config(modified)


def test_model_config_strips_notes_from_numeric_sections() -> None:
    model = config.load_model_config()

    assert "rationale" not in model.lightgbm_params
    assert "leakage_alarm_note" not in model.acceptance
    assert model.acceptance["univariate_auc_max"] == pytest.approx(0.95)


def test_cost_config_fraction_outside_unit_interval_raises(tmp_path: Path) -> None:
    def inflate_margin(data: dict[str, Any]) -> None:
        data["profit_margin"] = 1.5

    modified = _write_modified_config(tmp_path, "cost.yml", inflate_margin)

    with pytest.raises(config.ConfigError, match="profit_margin"):
        config.load_cost_config(modified)


def test_cost_config_non_positive_threshold_step_raises(tmp_path: Path) -> None:
    def zero_step(data: dict[str, Any]) -> None:
        data["threshold_search"]["step"] = 0

    modified = _write_modified_config(tmp_path, "cost.yml", zero_step)

    with pytest.raises(config.ConfigError, match="step"):
        config.load_cost_config(modified)


def test_random_seed_comes_from_model_config() -> None:
    assert config.random_seed() == config.load_model_config().random_seed


def test_mssql_connection_string_missing_variable_raises(
    monkeypatch: pytest.MonkeyPatch, clean_environment: Path
) -> None:
    for name, value in MSSQL_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(config.ENV_MSSQL_PORT)

    with pytest.raises(config.ConfigError, match=config.ENV_MSSQL_PORT):
        config.mssql_connection_string(clean_environment)


def test_mssql_connection_string_rejects_non_integer_port(
    monkeypatch: pytest.MonkeyPatch, clean_environment: Path
) -> None:
    for name, value in MSSQL_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(config.ENV_MSSQL_PORT, "port")

    with pytest.raises(config.ConfigError, match=config.ENV_MSSQL_PORT):
        config.mssql_connection_string(clean_environment)


def test_mssql_connection_string_never_logs_the_password(
    monkeypatch: pytest.MonkeyPatch, clean_environment: Path, caplog: pytest.LogCaptureFixture
) -> None:
    for name, value in MSSQL_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    with caplog.at_level(logging.DEBUG):
        connection_string = config.mssql_connection_string(clean_environment)

    assert "SERVER=localhost,14330" in connection_string
    assert MSSQL_ENVIRONMENT[config.ENV_MSSQL_PASSWORD] not in caplog.text


def test_process_environment_overrides_env_file(
    monkeypatch: pytest.MonkeyPatch, clean_environment: Path
) -> None:
    clean_environment.write_text(f"{config.ENV_MLFLOW_URI}=file:./from-dotenv\n", encoding="utf-8")
    assert config.mlflow_tracking_uri(clean_environment) == "file:./from-dotenv"

    monkeypatch.setenv(config.ENV_MLFLOW_URI, "file:./from-process")

    assert config.mlflow_tracking_uri(clean_environment) == "file:./from-process"


def test_mlflow_defaults_apply_when_environment_is_empty(clean_environment: Path) -> None:
    assert config.mlflow_tracking_uri(clean_environment) == config.DEFAULT_MLFLOW_URI
    assert (
        config.mlflow_experiment_name(clean_environment)
        == config.load_model_config().mlflow_experiment_name
    )
