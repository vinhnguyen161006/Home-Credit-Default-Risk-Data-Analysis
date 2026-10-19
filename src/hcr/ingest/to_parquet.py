"""Convert raw CSV files to compressed Parquet without cleaning values."""

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def sql_path(path: Path) -> str:
    """Return a safely quoted SQL string for a filesystem path.

    Args:
        path: File path to quote.

    Returns:
        Quoted SQL string with embedded apostrophes escaped.
    """
    return "'" + path.as_posix().replace("'", "''") + "'"


def convert_table(source: Path, destination: Path) -> None:
    """Convert one CSV, validate row counts, and publish after closing DuckDB.

    Args:
        source: Original CSV file.
        destination: Output Parquet file.
    """
    temporary = destination.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)

    logger.info("Converting %s...", source.name)

    try:
        with duckdb.connect() as connection:
            connection.execute("SET memory_limit = '2GB'")

            connection.execute(f"""
                CREATE TEMP VIEW current_csv AS
                SELECT *
                FROM read_csv_auto(
                    {sql_path(source)},
                    header = true,
                    sample_size = -1
                )
            """)

            connection.execute(f"""
                COPY current_csv TO {sql_path(temporary)}
                (FORMAT PARQUET, COMPRESSION ZSTD)
            """)

            csv_result = connection.execute("SELECT COUNT(*) FROM current_csv").fetchone()

            parquet_result = connection.execute(f"""
                SELECT COUNT(*)
                FROM read_parquet({sql_path(temporary)})
            """).fetchone()

            if csv_result is None or parquet_result is None:
                raise RuntimeError(f"Could not read row counts for {source.name}")

            csv_rows = csv_result[0]
            parquet_rows = parquet_result[0]

            if csv_rows != parquet_rows:
                raise ValueError(f"Row counts do not match for {source.name}")

        temporary.replace(destination)

        logger.info(
            "OK: %s rows saved to %s",
            f"{csv_rows:,}",
            destination.name,
        )
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Convert all CSV files into validated Parquet files."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    project_folder = Path(__file__).resolve().parents[3]
    raw_folder = project_folder / "data" / "raw"
    output_folder = project_folder / "data" / "bronze"

    files = (
        "application_train.csv",
        "application_test.csv",
        "bureau.csv",
        "bureau_balance.csv",
        "previous_application.csv",
        "POS_CASH_balance.csv",
        "installments_payments.csv",
        "credit_card_balance.csv",
    )

    for filename in files:
        source = raw_folder / filename
        if not source.is_file():
            raise FileNotFoundError(f"Cannot find: {source}")

    output_folder.mkdir(parents=True, exist_ok=True)

    for filename in files:
        source = raw_folder / filename
        destination = output_folder / f"{source.stem}.parquet"
        convert_table(source, destination)

    logger.info("All CSV files converted to Parquet.")


if __name__ == "__main__":
    main()
