"""Exploratory profiling of missing values in the bronze tables.

Pandas serves exploration here and nothing else. The silver transformations live in
Polars, so no cleaning rule is stated twice. Run it to see where nulls concentrate before
deciding whether a column needs a flag.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from hcr.paths import data_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

BRONZE_GLOB = "*.parquet"
PERCENT = 100
DISPLAY_DECIMALS = 2


def summarize_missing_values(table: pd.DataFrame) -> pd.DataFrame:
    """Return the columns holding nulls with their count and percentage, worst first."""
    missing_count = table.isna().sum()
    summary = pd.DataFrame(
        {
            "missing_count": missing_count,
            "missing_percent": missing_count / len(table) * PERCENT,
        }
    )
    return summary[summary["missing_count"] > 0].sort_values("missing_count", ascending=False)


def profile_file(source: Path) -> None:
    """Log the missing-value summary of one Parquet file."""
    table = pd.read_parquet(source)
    if table.empty:
        logger.info("%s: empty table", source.name)
        return
    summary = summarize_missing_values(table)
    logger.info("Dataset: %s | Rows: %s", source.name, f"{len(table):,}")
    if summary.empty:
        logger.info("No missing values.")
        return
    logger.info("\n%s", summary.round(DISPLAY_DECIMALS).to_string())


def main() -> None:
    """Profile every bronze table, one at a time to bound memory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for source in sorted((data_dir() / "bronze").glob(BRONZE_GLOB)):
        profile_file(source)


if __name__ == "__main__":
    main()
