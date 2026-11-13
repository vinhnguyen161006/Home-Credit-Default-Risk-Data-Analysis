"""Bulk-load compact serving Parquet tables into SQL Server."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import duckdb
import polars as pl
import pyodbc

from hcr.config import mssql_connection_string, mssql_database_name
from hcr.paths import mart_dir
from hcr.serving.build_star import (
    DIMENSION_TABLES,
    EXPECTED_APPLICATION_ROWS,
    FACT_TABLES,
    MART_TABLES,
)

logger = logging.getLogger(__name__)

STAGING_PREFIX: Final = "stg_"
BATCH_SIZE: Final = 10000
NVARCHAR_SAFETY_MARGIN: Final = 1.2
MAX_INDEXED_STRING_LENGTH: Final = 850
PRIMARY_KEYS: Final = {
    "Dim_Customer": "CustomerKey",
    "Dim_Occupation": "OccupationKey",
    "Dim_Organization": "OrgKey",
    "Dim_Education": "EducationKey",
    "Dim_ContractType": "ContractKey",
    "Dim_HousingType": "HousingKey",
    "Dim_FamilyStatus": "FamilyKey",
    "Dim_AgeBand": "AgeBandKey",
    "Dim_IncomeBand": "IncomeBandKey",
    "Dim_RiskBand": "RiskBandKey",
    "Fact_Application": "SK_ID_CURR",
    "Fact_BureauLoan": "SK_ID_BUREAU",
    "Fact_PreviousApplication": "SK_ID_PREV",
}
FOREIGN_KEYS: Final = (
    ("Fact_Application", "CustomerKey", "Dim_Customer", "CustomerKey"),
    ("Fact_Application", "OccupationKey", "Dim_Occupation", "OccupationKey"),
    ("Fact_Application", "OrgKey", "Dim_Organization", "OrgKey"),
    ("Fact_Application", "EducationKey", "Dim_Education", "EducationKey"),
    ("Fact_Application", "ContractKey", "Dim_ContractType", "ContractKey"),
    ("Fact_Application", "HousingKey", "Dim_HousingType", "HousingKey"),
    ("Fact_Application", "FamilyKey", "Dim_FamilyStatus", "FamilyKey"),
    ("Fact_Application", "AgeBandKey", "Dim_AgeBand", "AgeBandKey"),
    ("Fact_Application", "IncomeBandKey", "Dim_IncomeBand", "IncomeBandKey"),
    ("Fact_Application", "RiskBandKey", "Dim_RiskBand", "RiskBandKey"),
    ("Fact_BureauLoan", "CustomerKey", "Dim_Customer", "CustomerKey"),
    ("Fact_PreviousApplication", "CustomerKey", "Dim_Customer", "CustomerKey"),
)
NON_NULL_COLUMNS: Final = frozenset(PRIMARY_KEYS.items()) | frozenset(
    (table, column) for table, column, _, _ in FOREIGN_KEYS
)


class LoadError(Exception):
    """Raised when a table load or a serving integrity gate fails."""


@dataclass(frozen=True)
class LoadReport:
    """Outcome of one complete serving load."""

    tables_loaded: dict[str, int]
    constraints_created: int
    orphan_keys: int
    duration_seconds: float


def infer_string_column_length(values: pl.Series) -> int:
    """Return a practical NVARCHAR length based on observed string values."""
    if values.dtype != pl.String:
        raise TypeError(f"Expected a string series, received {values.dtype}")
    maximum = 0
    for value in values.to_list():
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError(f"Expected a string value, received {type(value).__name__}")
        maximum = max(maximum, len(value))
    return max(1, math.ceil(maximum * NVARCHAR_SAFETY_MARGIN))


def _quote_identifier(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def _quote_duckdb_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parquet_schema(path: Path) -> list[tuple[str, str]]:
    connection = duckdb.connect()
    try:
        escaped_path = _sql_literal(str(path))
        rows = connection.execute(f"DESCRIBE SELECT * FROM read_parquet({escaped_path})").fetchall()
    finally:
        connection.close()
    return [(str(row[0]), str(row[1])) for row in rows]


def _observed_string_length(path: Path, column: str) -> int:
    connection = duckdb.connect()
    try:
        escaped_path = _sql_literal(str(path))
        escaped_column = _quote_duckdb_identifier(column)
        row = connection.execute(
            f"SELECT MAX(LENGTH({escaped_column})) FROM read_parquet({escaped_path})"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"Could not inspect string length for {column} in {path}")
    maximum = int(row[0] or 0)
    if maximum > MAX_INDEXED_STRING_LENGTH:
        raise ValueError(
            f"{column} is {maximum} characters; the serving string limit is "
            f"{MAX_INDEXED_STRING_LENGTH}"
        )
    return max(1, math.ceil(maximum * NVARCHAR_SAFETY_MARGIN))


def _sql_server_type(path: Path, column: str, duckdb_type: str) -> str:
    normalized_type = duckdb_type.upper()
    if normalized_type.startswith(("VARCHAR", "STRING", "TEXT")):
        length = _observed_string_length(path, column)
        return f"NVARCHAR({length})"
    if normalized_type == "BOOLEAN":
        return "BIT"
    if normalized_type in {"TINYINT", "UTINYINT"}:
        return "TINYINT"
    if normalized_type in {"SMALLINT", "USMALLINT"}:
        return "SMALLINT"
    if normalized_type in {"INTEGER", "UINTEGER"}:
        return "INT"
    if normalized_type in {"BIGINT", "UBIGINT", "HUGEINT"}:
        return "BIGINT"
    if normalized_type == "FLOAT":
        return "REAL"
    if normalized_type in {"DOUBLE", "DECIMAL"} or normalized_type.startswith("DECIMAL("):
        return "FLOAT(53)" if normalized_type == "DOUBLE" else duckdb_type
    if normalized_type == "DATE":
        return "DATE"
    if normalized_type.startswith("TIMESTAMP"):
        return "DATETIME2"
    raise TypeError(f"Unsupported Parquet type for SQL Server: {column} {duckdb_type}")


def create_staging_tables(connection: pyodbc.Connection, schemas: dict[str, Path]) -> None:
    """Drop and recreate staging tables from the generated Parquet schemas."""
    missing = set(MART_TABLES).difference(schemas)
    extra = set(schemas).difference(MART_TABLES)
    if missing or extra:
        raise ValueError(f"Mart table mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

    cursor = connection.cursor()
    for table in MART_TABLES:
        path = schemas[table]
        if not path.is_file():
            raise FileNotFoundError(f"Mart Parquet for {table} does not exist: {path}")
        definitions = [
            f"{_quote_identifier(name)} {_sql_server_type(path, name, dtype)} "
            f"{'NOT NULL' if (table, name) in NON_NULL_COLUMNS else 'NULL'}"
            for name, dtype in _parquet_schema(path)
        ]
        staging_table = STAGING_PREFIX + table
        cursor.execute(f"DROP TABLE IF EXISTS dbo.{_quote_identifier(staging_table)}")
        cursor.execute(
            f"CREATE TABLE dbo.{_quote_identifier(staging_table)} " f"({', '.join(definitions)})"
        )
    connection.commit()


def _insert_statement(table: str, columns: list[str]) -> str:
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    return (
        f"INSERT INTO dbo.{_quote_identifier(STAGING_PREFIX + table)} "
        f"({quoted_columns}) VALUES ({placeholders})"
    )


def bulk_insert(connection: pyodbc.Connection, table: str, path: Path) -> int:
    """Stream one Parquet mart table into its SQL Server staging table."""
    columns = [name for name, _ in _parquet_schema(path)]
    statement = _insert_statement(table, columns)
    read_connection = duckdb.connect()
    cursor = connection.cursor()
    cursor.fast_executemany = True
    inserted_rows = 0
    try:
        result = read_connection.execute(f"SELECT * FROM read_parquet({_sql_literal(str(path))})")
        while rows := result.fetchmany(BATCH_SIZE):
            cursor.executemany(statement, rows)
            connection.commit()
            inserted_rows += len(rows)
    finally:
        read_connection.close()
    if inserted_rows == 0:
        raise LoadError(f"{table} contains no rows")
    logger.info("Staged %s rows for %s", inserted_rows, table)
    return inserted_rows


def _drop_targets(cursor: pyodbc.Cursor) -> None:
    for table in (*FACT_TABLES, *reversed(DIMENSION_TABLES)):
        cursor.execute(f"DROP TABLE IF EXISTS dbo.{_quote_identifier(table)}")


def _rename_staging_tables(cursor: pyodbc.Cursor, tables: tuple[str, ...]) -> None:
    for table in tables:
        cursor.execute(
            "EXEC sys.sp_rename ?, ?",
            f"dbo.{STAGING_PREFIX}{table}",
            table,
        )


def create_constraints(connection: pyodbc.Connection) -> int:
    """Add primary and foreign keys to the newly published mart tables."""
    cursor = connection.cursor()
    created = 0
    for table, column in PRIMARY_KEYS.items():
        constraint = _quote_identifier(f"PK_{table}")
        cursor.execute(
            f"ALTER TABLE dbo.{_quote_identifier(table)} "
            f"ADD CONSTRAINT {constraint} PRIMARY KEY ({_quote_identifier(column)})"
        )
        created += 1
    for table, column, dimension, dimension_key in FOREIGN_KEYS:
        constraint = _quote_identifier(f"FK_{table}_{dimension}_{column}")
        cursor.execute(
            f"ALTER TABLE dbo.{_quote_identifier(table)} "
            f"ADD CONSTRAINT {constraint} FOREIGN KEY ({_quote_identifier(column)}) "
            f"REFERENCES dbo.{_quote_identifier(dimension)} "
            f"({_quote_identifier(dimension_key)})"
        )
        created += 1
    cursor.execute(
        "CREATE UNIQUE INDEX UX_Dim_Customer_SK_ID_CURR "
        "ON dbo.Dim_Customer(SK_ID_CURR) WHERE SK_ID_CURR IS NOT NULL"
    )
    return created


def gate_referential_integrity(connection: pyodbc.Connection) -> int:
    """Count and reject foreign keys without a matching dimension row."""
    cursor = connection.cursor()
    total_orphans = 0
    for table, column, dimension, dimension_key in FOREIGN_KEYS:
        cursor.execute(
            f"SELECT COUNT(*) FROM dbo.{_quote_identifier(table)} AS fact "
            f"LEFT JOIN dbo.{_quote_identifier(dimension)} AS dimension "
            f"ON fact.{_quote_identifier(column)} = "
            f"dimension.{_quote_identifier(dimension_key)} "
            f"WHERE dimension.{_quote_identifier(dimension_key)} IS NULL"
        )
        count = cursor.fetchone()[0]
        if count:
            raise LoadError(
                f"{table}.{column} has {count} orphan values in {dimension}.{dimension_key}"
            )
        total_orphans += int(count)
    return total_orphans


def gate_fact_row_count(connection: pyodbc.Connection) -> int:
    """Assert that the application fact retains every labeled application."""
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM dbo.Fact_Application")
    result = cursor.fetchone()
    if result is None:
        raise LoadError("Could not read Fact_Application row count")
    actual_rows = int(result[0])
    if actual_rows != EXPECTED_APPLICATION_ROWS:
        difference = actual_rows - EXPECTED_APPLICATION_ROWS
        raise LoadError(
            f"Fact_Application has {actual_rows} rows; expected "
            f"{EXPECTED_APPLICATION_ROWS} (difference {difference})"
        )
    return actual_rows


def swap_staging_into_place(
    connection: pyodbc.Connection, tables: tuple[str, ...] = MART_TABLES
) -> tuple[int, int]:
    """Replace serving tables atomically, then run row-count and FK gates.

    The non-autocommit pyodbc connection owns the transaction; an explicit
    BEGIN TRANSACTION would nest it and leave the DDL uncommitted.
    """
    cursor = connection.cursor()
    try:
        cursor.execute("SET XACT_ABORT ON")
        _drop_targets(cursor)
        _rename_staging_tables(cursor, tables)
        constraints_created = create_constraints(connection)
        gate_fact_row_count(connection)
        orphan_keys = gate_referential_integrity(connection)
        connection.commit()
    except pyodbc.Error as error:
        connection.rollback()
        raise LoadError("SQL Server mart replacement failed and was rolled back") from error
    except LoadError:
        connection.rollback()
        raise
    return constraints_created, orphan_keys


def _ensure_database_exists() -> None:
    database_name = mssql_database_name()
    connection = pyodbc.connect(
        mssql_connection_string(database_override="master"),
        autocommit=True,
    )
    try:
        cursor = connection.cursor()
        cursor.execute(
            "DECLARE @database_name sysname = ?; "
            "IF DB_ID(@database_name) IS NULL "
            "BEGIN "
            "DECLARE @statement nvarchar(max) = "
            "N'CREATE DATABASE ' + QUOTENAME(@database_name); "
            "EXEC sys.sp_executesql @statement; "
            "END",
            database_name,
        )
    finally:
        connection.close()


def run() -> LoadReport:
    """Build the database if needed and load all mart Parquet tables."""
    started_at = time.perf_counter()
    paths = {table: mart_dir() / f"{table}.parquet" for table in MART_TABLES}
    for table, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"Mart table {table} is missing: {path}. Run `make serve` to build it."
            )

    _ensure_database_exists()
    connection = pyodbc.connect(mssql_connection_string(), autocommit=False)
    try:
        create_staging_tables(connection, paths)
        loaded_rows = {table: bulk_insert(connection, table, path) for table, path in paths.items()}
        constraints_created, orphan_keys = swap_staging_into_place(connection)
    finally:
        connection.close()

    duration = time.perf_counter() - started_at
    logger.info(
        "Loaded %s BI tables into SQL Server in %.1f seconds",
        len(loaded_rows),
        duration,
    )
    return LoadReport(loaded_rows, constraints_created, orphan_keys, duration)


def main() -> None:
    """Run the SQL Server serving load."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()


if __name__ == "__main__":
    main()
