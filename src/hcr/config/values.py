"""Reading YAML and asserting the type of each value it holds.

The single reader for every config file, so encoding and error handling are defined once.
Every check raises ConfigError naming the file and the key, so a typo surfaces before a
four-minute aggregation runs rather than inside it.

YAML files document themselves through data keys such as meta, rationale and note,
because comments are banned. Those keys carry no behaviour and strip_annotations removes
them before a section is handed to the pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import yaml

ANNOTATION_KEYS: Final = frozenset({"meta", "rationale", "note"})
ANNOTATION_KEY_SUFFIXES: Final = ("_rationale", "_note")


class ConfigError(Exception):
    """Raised when a configuration file is missing a key or holds a bad value.

    Carries the file and the key so the message is actionable without opening
    the YAML.
    """


def load_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file into a plain dictionary.

    Uses safe_load: a config file must not be able to construct arbitrary Python
    objects.

    Args:
        path: File to read.

    Raises:
        ConfigError: If the file is absent or does not parse to a mapping.
    """
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    if not isinstance(parsed, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return parsed


def require_keys(data: Mapping[str, Any], keys: tuple[str, ...], source: Path) -> None:
    """Assert every required key is present, naming the file when one is not.

    Collects every missing key and raises once, because raising on the first
    makes fixing a config an iterative guessing game.

    Args:
        data: Parsed config mapping.
        keys: Keys that must be present.
        source: File the mapping came from, used in the message.

    Raises:
        ConfigError: If any key is absent.
    """
    missing_keys = [key for key in keys if key not in data]
    if missing_keys:
        raise ConfigError(f"{source}: missing required keys: {', '.join(missing_keys)}")


def strip_annotations(section: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the documentation keys of a YAML section, keeping only behaviour."""
    return {key: value for key, value in section.items() if not _is_annotation_key(key)}


def require_mapping(value: Any, label: str, source: Path) -> dict[str, Any]:
    """Return the value when it is a mapping, else raise naming the key."""
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {label} must be a mapping")
    return value


def require_section(
    data: Mapping[str, Any], key: str, required: tuple[str, ...], source: Path
) -> dict[str, Any]:
    """Return a nested mapping after asserting the keys it must hold."""
    section = require_mapping(data[key], key, source)
    require_keys(section, required, source)
    return section


def require_list(value: Any, label: str, source: Path) -> list[Any]:
    """Return the value when it is a list, else raise naming the key."""
    if not isinstance(value, list):
        raise ConfigError(f"{source}: {label} must be a list")
    return value


def require_string(value: Any, label: str, source: Path) -> str:
    """Return the value when it is a non-empty string, else raise naming the key."""
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{source}: {label} must be a non-empty string")
    return value


def require_string_tuple(value: Any, label: str, source: Path) -> tuple[str, ...]:
    """Return a list of non-empty strings as a tuple, else raise naming the key."""
    return tuple(require_string(item, label, source) for item in require_list(value, label, source))


def require_int(value: Any, label: str, source: Path) -> int:
    """Return the value when it is an integer, rejecting booleans, else raise."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{source}: {label} must be an integer, got {value!r}")
    return int(value)


def require_number(value: Any, label: str, source: Path) -> float:
    """Return the value as a float when it is numeric, rejecting booleans, else raise."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{source}: {label} must be a number, got {value!r}")
    return float(value)


def parse_string_mapping(value: Any, label: str, source: Path) -> dict[str, str]:
    """Return a mapping of string to non-empty string, annotations removed."""
    section = strip_annotations(require_mapping(value, label, source))
    return {key: require_string(item, f"{label}.{key}", source) for key, item in section.items()}


def parse_nested_field(value: Any, label: str, field: str, source: Path) -> dict[str, Any]:
    """Collapse a mapping of mappings to one required field per entry."""
    section = strip_annotations(require_mapping(value, label, source))
    parsed: dict[str, Any] = {}
    for key, entry in section.items():
        entry_mapping = require_mapping(entry, f"{label}.{key}", source)
        require_keys(entry_mapping, (field,), source)
        parsed[key] = entry_mapping[field]
    return parsed


def _is_annotation_key(key: str) -> bool:
    return key in ANNOTATION_KEYS or key.endswith(ANNOTATION_KEY_SUFFIXES)
