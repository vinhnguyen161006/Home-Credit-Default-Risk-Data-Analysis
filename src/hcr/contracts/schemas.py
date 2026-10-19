"""Pandera schemas describing every raw table.

Schemas are built from configs/data_contract.yml rather than written by hand, so
the declared shape has exactly one definition. A schema here checks dtypes only.
Column presence is asserted by validate_raw, so a missing column is reported once
and by name; key uniqueness is counted by DuckDB in measure, because Pandera skips
uniqueness on a LazyFrame and fails on composite keys. Value-level repair belongs
to the silver layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pandera.polars as pa

from hcr.config import ConfigError

if TYPE_CHECKING:
    from hcr.config import TableContract

DTYPE_ALIASES: Final = {
    "int": "int64",
    "float": "float64",
    "str": "string",
}


def declared_columns(contract: TableContract) -> tuple[str, ...]:
    """Return every column the contract names, in declaration order.

    The union of required_columns and the dtypes keys. The full dtypes mapping
    lists every column of the table, so a renamed column cannot hide behind an
    unchanged column count.
    """
    return tuple(dict.fromkeys((*contract.required_columns, *contract.dtypes)))


def build_table_schema(contract: TableContract) -> pa.DataFrameSchema:
    """Build the Pandera schema for one raw table.

    Every declared column gets a dtype constraint where one is declared. Columns
    are not required here: validate_raw names absent columns itself, and doing it
    twice would report each absence twice. The schema is not strict, because
    presence and count are asserted separately against the contract. Row counts
    and key uniqueness are not encoded here either; validate_raw reports both with
    the delta and the offending keys.

    Args:
        contract: Declared shape of the table.

    Returns:
        A schema asserting the declared dtypes of the columns that are present.

    Raises:
        ConfigError: If a declared dtype is not one of DTYPE_ALIASES.
    """
    columns = {
        name: _build_column(name, contract.dtypes.get(name)) for name in declared_columns(contract)
    }
    return pa.DataFrameSchema(columns, strict=False)


def forbidden_column_check(contract: TableContract) -> tuple[str, ...]:
    """Return the columns whose presence must fail validation.

    Used to assert application_test carries no TARGET column: a labelled test
    set would mean the file is not what the contract describes. Pandera has no
    native absence check, so validate_raw asserts this against the column list.
    """
    return contract.forbidden_columns


def _build_column(name: str, alias: str | None) -> pa.Column:
    if alias is None:
        return pa.Column(required=False)
    if alias not in DTYPE_ALIASES:
        known = ", ".join(DTYPE_ALIASES)
        raise ConfigError(f"Column {name} declares dtype {alias!r}; expected one of: {known}")
    return pa.Column(DTYPE_ALIASES[alias], required=False)
