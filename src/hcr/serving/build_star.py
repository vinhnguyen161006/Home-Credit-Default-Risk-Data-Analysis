"""Build compact Power BI facts and dimensions from the Silver Parquet layer."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Final

import duckdb

from hcr.paths import mart_dir, serving_sql_dir, silver_path
from hcr.serving.dimensions import build_application_dimensions

logger = logging.getLogger(__name__)

APPLICATION_TABLE: Final = "application_train"
SOURCE_TABLES: Final = (
    APPLICATION_TABLE,
    "bureau",
    "bureau_balance",
    "previous_application",
    "pos_cash_balance",
    "installments_payments",
    "credit_card_balance",
)
SOURCE_VIEWS: Final = {
    "application_train": "source_application",
    "bureau": "source_bureau",
    "bureau_balance": "source_bureau_balance",
    "previous_application": "source_previous_application",
    "pos_cash_balance": "source_pos_cash",
    "installments_payments": "source_installments",
    "credit_card_balance": "source_credit_card",
}
DIMENSION_TABLES: Final = (
    "Dim_Customer",
    "Dim_Occupation",
    "Dim_Organization",
    "Dim_Education",
    "Dim_ContractType",
    "Dim_HousingType",
    "Dim_FamilyStatus",
    "Dim_AgeBand",
    "Dim_IncomeBand",
    "Dim_RiskBand",
)
FACT_TABLES: Final = (
    "Fact_Application",
    "Fact_BureauLoan",
    "Fact_PreviousApplication",
)
MART_TABLES: Final = (*DIMENSION_TABLES, *FACT_TABLES)
DIMENSION_SQL_VIEWS: Final = {
    "Dim_Customer": "dim_customer",
    "Dim_Occupation": "dim_occupation",
    "Dim_Organization": "dim_organization",
    "Dim_Education": "dim_education",
    "Dim_ContractType": "dim_contract_type",
    "Dim_HousingType": "dim_housing_type",
    "Dim_FamilyStatus": "dim_family_status",
    "Dim_AgeBand": "dim_age_band",
    "Dim_IncomeBand": "dim_income_band",
    "Dim_RiskBand": "dim_risk_band",
}
EXPECTED_APPLICATION_ROWS: Final = 307511
UNKNOWN_KEY: Final = -1


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _register_source_views(
    connection: duckdb.DuckDBPyConnection, source_paths: dict[str, Path]
) -> None:
    missing = set(SOURCE_TABLES).difference(source_paths)
    extra = set(source_paths).difference(SOURCE_TABLES)
    if missing or extra:
        raise ValueError(f"Source table mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

    for table in SOURCE_TABLES:
        path = source_paths[table]
        if not path.is_file():
            raise FileNotFoundError(f"Silver Parquet for {table} does not exist: {path}")
        source_view = SOURCE_VIEWS[table]
        connection.execute(
            f"CREATE VIEW {source_view} AS SELECT * FROM read_parquet({_sql_literal(str(path))})"
        )


def _validate_unique_source_keys(connection: duckdb.DuckDBPyConnection) -> None:
    key_columns = {
        "source_application": "SK_ID_CURR",
        "source_bureau": "SK_ID_BUREAU",
        "source_previous_application": "SK_ID_PREV",
    }
    for table, key in key_columns.items():
        duplicate = connection.execute(
            f'SELECT "{key}" FROM {table} GROUP BY "{key}" ' f"HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicate is not None:
            raise ValueError(f"{table} repeats {key} value {duplicate[0]}")


def _validate_previous_customer_keys(connection: duckdb.DuckDBPyConnection) -> None:
    mismatch = connection.execute(
        """
        WITH all_previous_rows AS (
            SELECT SK_ID_PREV, SK_ID_CURR FROM source_previous_application
            UNION ALL
            SELECT SK_ID_PREV, SK_ID_CURR FROM source_pos_cash
            UNION ALL
            SELECT SK_ID_PREV, SK_ID_CURR FROM source_installments
            UNION ALL
            SELECT SK_ID_PREV, SK_ID_CURR FROM source_credit_card
        )
        SELECT SK_ID_PREV
        FROM all_previous_rows
        GROUP BY SK_ID_PREV
        HAVING COUNT(DISTINCT SK_ID_CURR) > 1
        LIMIT 1
        """
    ).fetchone()
    if mismatch is not None:
        raise ValueError(f"SK_ID_PREV {mismatch[0]} maps to multiple SK_ID_CURR values")


def _copy_query(connection: duckdb.DuckDBPyConnection, query: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    sql = query.strip().removesuffix(";")
    connection.execute(
        f"COPY ({sql}) TO {_sql_literal(str(destination))} " "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _read_sql(filename: str) -> str:
    path = serving_sql_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(f"Serving query does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _register_customer_dimension(connection: duckdb.DuckDBPyConnection, path: Path) -> None:
    connection.execute(
        f"CREATE VIEW dim_customer AS SELECT * FROM read_parquet({_sql_literal(str(path))})"
    )


def _register_category_dimensions(connection: duckdb.DuckDBPyConnection) -> None:
    registered_views = {row[0].casefold() for row in connection.execute("SHOW TABLES").fetchall()}
    for table in DIMENSION_TABLES:
        if table == "Dim_Customer":
            continue
        source_view = table.casefold()
        sql_view = DIMENSION_SQL_VIEWS[table]
        if source_view not in registered_views:
            raise ValueError(f"Dimension view {source_view} was not registered")
        if sql_view != source_view:
            connection.execute(f"CREATE VIEW {sql_view} AS SELECT * FROM {source_view}")


def _write_customer_dimension(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    _copy_query(connection, _read_sql("customer_dimension.sql"), path)
    _register_customer_dimension(connection, path)
    return _count_rows(connection, path)


def _count_rows(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    count = connection.execute(
        f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(path))})"
    ).fetchone()
    if count is None:
        raise ValueError(f"Could not count rows in {path}")
    return int(count[0])


def _expected_union_count(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    count = connection.execute(query).fetchone()
    if count is None:
        raise ValueError("A source-key count query returned no result")
    return int(count[0])


def _validate_fact_file(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    path: Path,
    key_column: str,
    expected_rows: int,
) -> int:
    row_count = _count_rows(connection, path)
    if row_count != expected_rows:
        raise ValueError(f"{table} has {row_count} rows; expected {expected_rows}")
    duplicate = connection.execute(
        f'SELECT "{key_column}" FROM read_parquet({_sql_literal(str(path))}) '
        f'GROUP BY "{key_column}" HAVING COUNT(*) > 1 LIMIT 1'
    ).fetchone()
    if duplicate is not None:
        raise ValueError(f"{table} repeats {key_column} value {duplicate[0]}")
    null_key = connection.execute(
        f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(path))}) "
        f'WHERE "{key_column}" IS NULL'
    ).fetchone()
    if null_key is None or null_key[0]:
        raise ValueError(f"{table} contains null {key_column} values")
    return row_count


def _validate_customer_unknown_member(connection: duckdb.DuckDBPyConnection, path: Path) -> None:
    unknown_rows = connection.execute(
        f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(path))}) "
        f"WHERE CustomerKey = {UNKNOWN_KEY}"
    ).fetchone()
    if unknown_rows is None or unknown_rows[0] != 1:
        raise ValueError("Dim_Customer must contain exactly one unknown member at key -1")


def _publish_files(temporary_dir: Path, output_dir: Path) -> None:
    for table in MART_TABLES:
        (temporary_dir / f"{table}.parquet").replace(output_dir / f"{table}.parquet")


def build_mart(
    source_paths: dict[str, Path],
    output_dir: Path,
    expected_application_rows: int | None = EXPECTED_APPLICATION_ROWS,
) -> dict[str, int]:
    """Build the serving mart from the seven Silver Parquet sources.

    The historical facts retain their parent keys. Monthly and event data are
    aggregated in DuckDB before writing, so SQL Server receives only compact
    application-, bureau-loan-, and previous-application-grain tables.
    """
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    row_counts: dict[str, int] = {}

    with tempfile.TemporaryDirectory(prefix="hcr-mart-", dir=output_dir.parent) as temp_name:
        temporary_dir = Path(temp_name)
        connection = duckdb.connect()
        try:
            _register_source_views(connection, source_paths)
            _validate_unique_source_keys(connection)
            _validate_previous_customer_keys(connection)

            customer_path = temporary_dir / "Dim_Customer.parquet"
            row_counts["Dim_Customer"] = _write_customer_dimension(connection, customer_path)
            _validate_customer_unknown_member(connection, customer_path)
            row_counts.update(build_application_dimensions(connection, temporary_dir))
            _register_category_dimensions(connection)

            for table, filename in (
                ("Fact_Application", "application_fact.sql"),
                ("Fact_BureauLoan", "bureau_loan_fact.sql"),
                ("Fact_PreviousApplication", "previous_application_fact.sql"),
            ):
                _copy_query(connection, _read_sql(filename), temporary_dir / f"{table}.parquet")

            application_rows = _expected_union_count(
                connection, "SELECT COUNT(*) FROM source_application"
            )
            if (
                expected_application_rows is not None
                and application_rows != expected_application_rows
            ):
                raise ValueError(
                    f"Application source has {application_rows} rows; "
                    f"expected {expected_application_rows}"
                )
            row_counts["Fact_Application"] = _validate_fact_file(
                connection,
                "Fact_Application",
                temporary_dir / "Fact_Application.parquet",
                "SK_ID_CURR",
                application_rows,
            )

            bureau_rows = _expected_union_count(
                connection,
                """
                SELECT COUNT(*) FROM (
                    SELECT SK_ID_BUREAU FROM source_bureau
                    UNION
                    SELECT SK_ID_BUREAU FROM source_bureau_balance
                )
                """,
            )
            row_counts["Fact_BureauLoan"] = _validate_fact_file(
                connection,
                "Fact_BureauLoan",
                temporary_dir / "Fact_BureauLoan.parquet",
                "SK_ID_BUREAU",
                bureau_rows,
            )

            previous_rows = _expected_union_count(
                connection,
                """
                SELECT COUNT(*) FROM (
                    SELECT SK_ID_PREV FROM source_previous_application
                    UNION
                    SELECT SK_ID_PREV FROM source_pos_cash
                    UNION
                    SELECT SK_ID_PREV FROM source_installments
                    UNION
                    SELECT SK_ID_PREV FROM source_credit_card
                )
                """,
            )
            row_counts["Fact_PreviousApplication"] = _validate_fact_file(
                connection,
                "Fact_PreviousApplication",
                temporary_dir / "Fact_PreviousApplication.parquet",
                "SK_ID_PREV",
                previous_rows,
            )

            _publish_files(temporary_dir, output_dir)
        finally:
            connection.close()

    for table, rows in row_counts.items():
        logger.info("Built %s with %s rows", table, rows)
    return row_counts


def run() -> dict[str, int]:
    """Build the BI mart from the seven existing Silver Parquet files."""
    source_paths = {table: silver_path(table) for table in SOURCE_TABLES}
    return build_mart(source_paths, mart_dir())


def main() -> None:
    """Build serving Parquet files for the SQL Server loader."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()


if __name__ == "__main__":
    main()
