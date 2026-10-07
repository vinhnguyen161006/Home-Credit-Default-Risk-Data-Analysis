"""Pandera schemas describing every raw table.

Schemas are built from configs/data_contract.yml rather than written by hand, so
the declared shape has exactly one definition. A schema here checks structure
only: column presence, dtype and key uniqueness. Value-level repair belongs to
the silver layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import pandera.polars as pa

    from hcr.config import DataContract, TableContract

DTYPE_ALIASES: Final = {
    "int": "int64",
    "float": "float64",
    "str": "str",
}


def build_table_schema(contract: TableContract) -> pa.DataFrameSchema:
    """Build the Pandera schema for one raw table.

    Args:
        contract: Declared shape of the table.

    Returns:
        A schema asserting required columns, declared dtypes and key uniqueness.

    TODO:
        - Add a Column for each required column, with the dtype from
          contract.dtypes where declared and no dtype constraint otherwise.
        - Set unique on the primary key columns when contract.primary_key is not
          None. When it is None, add no uniqueness check: installments_payments
          is an event table with no natural key and asserting one would fail on
          valid data.
        - Set strict=False. The contract names the columns that must exist, not
          every column that may; a strict schema would reject the 122-column
          application table for the columns the contract does not list.
        - Do not encode row counts here. Pandera validates rows, and the count
          check belongs in validate_raw where it can report the delta.
    """
    raise NotImplementedError


def build_all_schemas(contract: DataContract) -> dict[str, pa.DataFrameSchema]:
    """Build one schema per table in the data contract.

    TODO:
        - Map each table name to build_table_schema of its contract.
    """
    raise NotImplementedError


def forbidden_column_check(contract: TableContract) -> tuple[str, ...]:
    """Return the columns whose presence must fail validation.

    Used to assert application_test carries no TARGET column: a labelled test
    set would mean the file is not what the contract describes.

    TODO:
        - Return contract.forbidden_columns. Pandera has no native absence
          check, so validate_raw asserts this separately against the frame's
          column list.
    """
    raise NotImplementedError
