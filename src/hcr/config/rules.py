"""Business rules a configuration must satisfy beyond holding the right keys.

Each rule here guards a decision the specification fixes. A config file states the rule;
these checks stop a silent edit from relaxing it, because every one of them, if broken,
produces a plausible-looking result rather than an error.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from hcr.config.models import TableContract
from hcr.config.values import (
    ConfigError,
    parse_string_mapping,
    require_int,
    require_keys,
    require_mapping,
    require_number,
    require_string,
    require_string_tuple,
    strip_annotations,
)

EMPLOYMENT_SENTINEL_VALUE: Final = 365243
FEATURE_PREFIXES: Final = frozenset({"APP", "BURO", "BB", "PREV", "POS", "INST", "CC"})
FIRST_STAGE: Final = 1
SYNTHETIC_OVERSAMPLING_FORBIDDEN: Final = "forbidden"
MIN_CV_SPLITS: Final = 2
ACCEPTANCE_KEYS: Final = (
    "holdout_auc_min",
    "holdout_auc_max",
    "leakage_alarm_auc",
    "univariate_auc_max",
)


def parse_table_contract(name: str, entry: Any, source: Path) -> TableContract:
    """Build one table contract, keeping a null primary key distinct from an empty one.

    A null primary key marks an event table such as installments_payments. Mapping it to
    an empty tuple would make that indistinguishable from a declaration mistake.
    """
    table = require_mapping(entry, f"tables.{name}", source)
    require_keys(table, ("file", "rows", "columns", "primary_key"), source)
    primary_key = table["primary_key"]
    return TableContract(
        file=require_string(table["file"], f"tables.{name}.file", source),
        rows=require_int(table["rows"], f"tables.{name}.rows", source),
        columns=require_int(table["columns"], f"tables.{name}.columns", source),
        primary_key=None
        if primary_key is None
        else require_string_tuple(primary_key, f"tables.{name}.primary_key", source),
        required_columns=require_string_tuple(
            table.get("required_columns", []), f"tables.{name}.required_columns", source
        ),
        forbidden_columns=require_string_tuple(
            table.get("forbidden_columns", []), f"tables.{name}.forbidden_columns", source
        ),
        dtypes=parse_string_mapping(table.get("dtypes", {}), f"tables.{name}.dtypes", source),
    )


def parse_employment_sentinel(value: Any, source: Path) -> dict[str, Any]:
    """Assert the sentinel is 365243 and declares the flag that preserves its signal."""
    sentinel = strip_annotations(require_mapping(value, "employment_sentinel", source))
    require_keys(sentinel, ("column", "value", "emit_flag"), source)
    if sentinel["value"] != EMPLOYMENT_SENTINEL_VALUE:
        raise ConfigError(
            f"{source}: employment_sentinel.value must be {EMPLOYMENT_SENTINEL_VALUE}, "
            f"got {sentinel['value']!r}"
        )
    require_string(sentinel["emit_flag"], "employment_sentinel.emit_flag", source)
    return sentinel


def validate_prefixes(
    ratio_prefix: Any, sources: Mapping[str, Mapping[str, Any]], source: Path
) -> None:
    """Assert every feature prefix comes from the fixed set and appears once."""
    declared = [require_string(ratio_prefix, "application_ratios.prefix", source)]
    for name, entry in sources.items():
        require_keys(entry, ("prefix",), source)
        declared.append(require_string(entry["prefix"], f"sources.{name}.prefix", source))

    unknown = sorted(set(declared) - FEATURE_PREFIXES)
    if unknown:
        raise ConfigError(f"{source}: prefixes outside the fixed set: {', '.join(unknown)}")
    duplicated = sorted({prefix for prefix in declared if declared.count(prefix) > 1})
    if duplicated:
        raise ConfigError(f"{source}: prefixes declared more than once: {', '.join(duplicated)}")


def validate_source_entry(name: str, entry: Mapping[str, Any], source: Path) -> None:
    """Assert a source can be folded and generates no duplicate output column.

    A stage-1 source that rolls up to customer grain needs a parent table to fold
    through. A function repeated for one column would emit the same column twice.
    """
    require_keys(entry, ("stage", "group_by", "aggregations"), source)
    rolls_up = entry["stage"] == FIRST_STAGE and "roll_up_to" in entry
    if rolls_up and "join_from" not in entry:
        raise ConfigError(f"{source}: sources.{name} declares roll_up_to without join_from")

    aggregations = require_mapping(entry["aggregations"], f"sources.{name}.aggregations", source)
    for column, functions in aggregations.items():
        names = require_string_tuple(functions, f"sources.{name}.aggregations.{column}", source)
        if len(set(names)) != len(names):
            raise ConfigError(
                f"{source}: sources.{name}.aggregations.{column} repeats a function, "
                "which would generate a duplicate output column"
            )


def parse_acceptance(value: Any, source: Path) -> dict[str, float]:
    """Return the AUC bounds after asserting they are ordered.

    The leakage alarm must sit above the acceptance ceiling, otherwise a legitimate
    result would trigger it or a leaking one would pass.
    """
    section = strip_annotations(require_mapping(value, "acceptance", source))
    require_keys(section, ACCEPTANCE_KEYS, source)
    acceptance = {
        key: require_number(item, f"acceptance.{key}", source) for key, item in section.items()
    }
    if not acceptance["holdout_auc_min"] < acceptance["holdout_auc_max"]:
        raise ConfigError(f"{source}: acceptance.holdout_auc_min must be below holdout_auc_max")
    if not acceptance["leakage_alarm_auc"] > acceptance["holdout_auc_max"]:
        raise ConfigError(f"{source}: acceptance.leakage_alarm_auc must exceed holdout_auc_max")
    return acceptance


def validate_split_policy(holdout_fraction: float, n_splits: int, source: Path) -> None:
    """Assert the holdout is a proper fraction and cross-validation has at least two folds."""
    if not 0 < holdout_fraction < 1:
        raise ConfigError(f"{source}: split.holdout_fraction must lie in (0, 1)")
    if n_splits < MIN_CV_SPLITS:
        raise ConfigError(f"{source}: cross_validation.n_splits must be at least {MIN_CV_SPLITS}")


def validate_model_rules(
    class_imbalance: Any, cross_validation: Mapping[str, Any], source: Path
) -> None:
    """Assert synthetic oversampling stays forbidden and validation stays non-temporal.

    Synthetic samples destroy probability calibration. The data carries no date column
    and SK_ID_CURR is not guaranteed to follow submission time, so a time-based split
    would rest on an unverifiable assumption.
    """
    imbalance = require_mapping(class_imbalance, "class_imbalance", source)
    require_keys(imbalance, ("synthetic_oversampling",), source)
    if imbalance["synthetic_oversampling"] != SYNTHETIC_OVERSAMPLING_FORBIDDEN:
        raise ConfigError(
            f"{source}: class_imbalance.synthetic_oversampling must stay "
            f"{SYNTHETIC_OVERSAMPLING_FORBIDDEN!r}"
        )
    if cross_validation["time_based"] is not False:
        raise ConfigError(f"{source}: cross_validation.time_based must be false")


def validate_cost_fractions(fractions: Mapping[str, float], source: Path) -> None:
    """Assert each cost fraction lies in (0, 1).

    A value outside that range silently produces a meaningless threshold rather than
    failing.
    """
    for key, value in fractions.items():
        if not 0 < value < 1:
            raise ConfigError(f"{source}: {key} must lie in (0, 1), got {value}")


def validate_threshold_grid(grid: Mapping[str, float], source: Path) -> None:
    """Assert the threshold search range is ordered and its step is positive."""
    if not grid["min"] < grid["max"]:
        raise ConfigError(f"{source}: threshold_search.min must be below threshold_search.max")
    if grid["step"] <= 0:
        raise ConfigError(f"{source}: threshold_search.step must be positive")
