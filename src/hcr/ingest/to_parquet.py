"""Convert raw CSV files to compressed Parquet without cleaning values.

Type inference is limited to integers, doubles and text. Left to its defaults, DuckDB
reads the Yes and No text of EMERGENCYSTATE_MODE as a boolean, which changes the content
bronze must preserve and fails the step 2 contract.
"""

import logging
from pathlib import Path
from typing import Final

import duckdb

from hcr.config import load_data_contract
from hcr.paths import bronze_path, ensure_parent, raw_path

logger = logging.getLogger(__name__)

TYPE_CANDIDATES: Final = "['BIGINT', 'DOUBLE', 'VARCHAR']"


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
                    sample_size = -1,
                    auto_type_candidates = {TYPE_CANDIDATES}
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

    contract = load_data_contract()
    sources = {table: raw_path(table, contract) for table in contract.tables}

    for source in sources.values():
        if not source.is_file():
            raise FileNotFoundError(f"Cannot find: {source}")

    for table, source in sources.items():
        convert_table(source, ensure_parent(bronze_path(table)))

    logger.info("All CSV files converted to Parquet.")


if __name__ == "__main__":
    main()
