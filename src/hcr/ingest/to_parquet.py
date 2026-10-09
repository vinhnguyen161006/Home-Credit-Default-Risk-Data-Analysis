"""Step 1: convert the eight raw CSV files to compressed Parquet.

Content is never altered here. Sentinel handling, sign conventions and type
repair belong to the silver layer, so bronze stays a faithful and cheap-to-read
copy of the source. That separation is what lets step 2 assert the contract
against something equivalent to the original file.

Conversion is the reason the rest of the pipeline is affordable: 2.5 GB of CSV
across 58.4 million rows is slow to parse repeatedly and columnar reads let
DuckDB touch only the columns an aggregation names.
"""

from pathlib import Path
import duckdb

project_folder = Path(__file__).resolve().parents[3]
raw_folder = project_folder / "data" / "raw"
output_folder = project_folder / "data" / "bronze"
output_folder.mkdir(parents=True, exist_ok=True)

files = [
    "application_train.csv",
    "application_test.csv",
    "bureau.csv",
    "bureau_balance.csv",
    "previous_application.csv",
    "POS_CASH_balance.csv",
    "installments_payments.csv",
    "credit_card_balance.csv",
]

def sql_path(path):
    return "'" + path.as_posix().replace("'", "''") + "'"

connection = duckdb.connect()
connection.execute("SET memory_limit = '2GB'")

try:
    for filename in files:
        source = raw_folder / filename
        destination = output_folder / f"{source.stem}.parquet"

        if not source.is_file():
            raise FileNotFoundError(f"Cannot find: {source}")

        print(f"Converting {filename}...")

        connection.execute(f"""
            CREATE OR REPLACE TEMP VIEW current_csv AS
            SELECT *
            FROM read_csv_auto(
                {sql_path(source)},
                header = true,
                sample_size = -1
            )
        """)

        connection.execute(f"""
            COPY current_csv TO {sql_path(destination)}
            (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        csv_rows = connection.execute(
            "SELECT COUNT(*) FROM current_csv"
        ).fetchone()[0]

        parquet_rows = connection.execute(f"""
            SELECT COUNT(*)
            FROM read_parquet({sql_path(destination)})
        """).fetchone()[0]

        if csv_rows != parquet_rows:
            raise ValueError(f"Row counts do not match for {filename}")

        print(f"OK: {csv_rows:,} rows saved to {destination.name}")

finally:
    connection.close()

print("All CSV files converted to parquet.")
                         