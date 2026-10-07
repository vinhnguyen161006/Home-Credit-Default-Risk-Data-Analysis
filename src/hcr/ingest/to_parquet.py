"""Step 1: convert the eight raw CSV files to compressed Parquet.

Content is never altered here. Sentinel handling, sign conventions and type
repair belong to the silver layer, so bronze stays a faithful and cheap-to-read
copy of the source. That separation is what lets step 2 assert the contract
against something equivalent to the original file.

Conversion is the reason the rest of the pipeline is affordable: 2.5 GB of CSV
across 58.4 million rows is slow to parse repeatedly and columnar reads let
DuckDB touch only the columns an aggregation names.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

COMPRESSION: Final = "zstd"
COMPRESSION_LEVEL: Final = 3

TABLES: Final = (
    "application_train",
    "application_test",
    "bureau",
    "bureau_balance",
    "previous_application",
    "pos_cash_balance",
    "installments_payments",
    "credit_card_balance",
)


def convert_table(table: str, source: Path, destination: Path) -> Path:
    """Convert one raw CSV to Parquet without changing its content.

    Args:
        table: Logical table name, used for logging only.
        source: Raw CSV to read.
        destination: Parquet file to write.

    Returns:
        The destination path.

    Raises:
        FileNotFoundError: If the source CSV is absent.

    TODO:
        - Convert with DuckDB's read_csv_auto straight into COPY TO, so the file
          streams and the 27.3 million row bureau_balance never materialises in
          memory. This is the one place a function takes paths rather than
          frames, because DuckDB reads and writes disk directly.
        - Pass sample_size=-1 so DuckDB scans the whole file for type inference.
          A sampled inference reads a numeric column as text when the first rows
          happen to be empty, which would move a parsing decision into bronze.
        - Keep the raw column names and the raw casing exactly. Downstream SQL
          and the data contract both reference the Kaggle spelling.
        - Write through a temporary file in the destination directory and rename
          on success, so an interrupted run leaves no half-written Parquet that
          a later step would read as complete.
        - Log the row count written and the elapsed time at INFO, with lazy
          formatting: logger.info("Wrote %s rows to %s", rows, destination).
    """
    raise NotImplementedError


def flatten_raw_layout(table: str) -> Path:
    """Resolve a table name to its raw CSV despite the nested directory.

    The raw tree is not flat: application_train, application_test and
    sample_submission sit under home-credit-default-risk while the six history
    files sit directly in the raw directory.

    TODO:
        - Delegate to paths.raw_path, which reads the location from the data
          contract. Do not re-derive the filename here; one mapping only.
    """
    raise NotImplementedError


def run() -> dict[str, Path]:
    """Convert all eight tables and return the bronze path of each.

    Returns:
        Logical table name to the Parquet file written.

    TODO:
        - Convert the tables in TABLES order, which puts the small application
          tables first so a misconfigured raw directory fails in seconds rather
          than after the largest file.
        - Skip a table whose Parquet is newer than its CSV and log the skip, so
          a rerun after a failure does not redo finished work. Offer a force
          argument to override; a changed CSV with an unchanged timestamp is the
          one case the check misses.
        - Never write into the raw directory. Bronze is a separate layer so this
          step cannot overwrite its own input.
        - Return the mapping rather than printing it; the orchestrator logs.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.ingest.to_parquet`.

    TODO:
        - Configure logging, call run, and exit non-zero on failure so the
          Makefile target stops the chain.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
