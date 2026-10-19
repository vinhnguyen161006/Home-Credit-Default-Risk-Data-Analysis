"""Contract schemas, and the consistency of the real data contract they are built from.

The real-contract tests run against configs/data_contract.yml itself. A typo there would
otherwise surface only as a failed gate on the full dataset, far from the line that caused it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

import polars as pl
import pytest
from pandera.errors import SchemaErrors

from hcr.config import ConfigError, TableContract, load_data_contract
from hcr.contracts.schemas import (
    DTYPE_ALIASES,
    build_table_schema,
    declared_columns,
    forbidden_column_check,
)

SMALL_CONTRACT: Final = TableContract(
    file="unused.csv",
    rows=2,
    columns=2,
    primary_key=("ID",),
    required_columns=("ID", "NAME"),
    forbidden_columns=("TARGET",),
    dtypes={"ID": "int", "AMOUNT": "float"},
)


def test_declared_columns_unites_required_and_typed_columns_in_order() -> None:
    assert declared_columns(SMALL_CONTRACT) == ("ID", "NAME", "AMOUNT")


def test_schema_accepts_declared_dtypes_and_undeclared_extra_columns() -> None:
    frame = pl.LazyFrame({"ID": [1, 2], "NAME": ["a", "b"], "AMOUNT": [1.0, 2.0], "EXTRA": [0, 0]})

    build_table_schema(SMALL_CONTRACT).validate(frame, lazy=True)


def test_schema_rejects_a_mistyped_column() -> None:
    frame = pl.LazyFrame({"ID": ["1", "2"], "NAME": ["a", "b"], "AMOUNT": [1.0, 2.0]})

    with pytest.raises(SchemaErrors) as raised:
        build_table_schema(SMALL_CONTRACT).validate(frame, lazy=True)

    assert raised.value.failure_cases["column"].to_list() == ["ID"]


def test_schema_leaves_absent_columns_to_the_presence_check() -> None:
    """validate_raw names absent columns; the schema reporting them too would double count."""
    build_table_schema(SMALL_CONTRACT).validate(pl.LazyFrame({"ID": [1]}), lazy=True)


def test_schema_with_unknown_dtype_alias_raises() -> None:
    contract = replace(SMALL_CONTRACT, dtypes={"ID": "integer"})

    with pytest.raises(ConfigError, match="ID"):
        build_table_schema(contract)


def test_forbidden_column_check_returns_the_declared_columns() -> None:
    assert forbidden_column_check(SMALL_CONTRACT) == ("TARGET",)


def test_real_contract_types_every_column_it_counts() -> None:
    """The full dtypes mapping makes a renamed column visible despite an unchanged count."""
    for table, entry in load_data_contract().tables.items():
        assert len(entry.dtypes) == entry.columns, table
        assert len(declared_columns(entry)) == entry.columns, table


def test_real_contract_uses_only_known_dtype_aliases() -> None:
    for entry in load_data_contract().tables.values():
        assert set(entry.dtypes.values()) <= set(DTYPE_ALIASES)


def test_real_contract_keys_and_forbidden_columns_are_consistent() -> None:
    for table, entry in load_data_contract().tables.items():
        declared = set(declared_columns(entry))
        assert set(entry.primary_key or ()) <= declared, table
        assert not set(entry.forbidden_columns) & declared, table


def test_real_contract_keeps_emergency_state_as_text() -> None:
    """The raw Yes and No text must survive ingest instead of becoming a boolean."""
    tables = load_data_contract().tables

    assert tables["application_train"].dtypes["EMERGENCYSTATE_MODE"] == "str"
    assert tables["application_test"].dtypes["EMERGENCYSTATE_MODE"] == "str"


def test_real_contract_builds_a_schema_for_every_table() -> None:
    for table, entry in load_data_contract().tables.items():
        assert len(build_table_schema(entry).columns) == entry.columns, table
