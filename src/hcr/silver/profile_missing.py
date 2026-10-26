"""Show missing values in application data."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

bronze_folder = Path(__file__).resolve().parents[3] / "data" / "bronze"

for source in sorted(bronze_folder.glob("*.parquet")):
    df = pd.read_parquet(source)

    if df.empty:
        logger.info("%s: empty table", source.name)
        del df
        continue

    missing_count = df.isna().sum()
    missing_percent = missing_count / len(df) * 100

    summary = pd.DataFrame(
        {
            "missing_count": missing_count,
            "missing_percent": missing_percent,
        }
    )

    summary = summary[summary["missing_count"] > 0]
    summary = summary.sort_values("missing_count", ascending=False)

    logger.info("\nDataset: %s | Rows: %s", source.name, f"{len(df):,}")

    if summary.empty:
        logger.info("No missing values.")
    else:
        logger.info("\n%s", summary.round(2).to_string())

    del df
