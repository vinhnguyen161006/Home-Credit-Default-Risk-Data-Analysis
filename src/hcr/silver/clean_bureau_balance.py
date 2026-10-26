"""Inspect monthly bureau balances before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "bureau_balance.parquet"

df = pd.read_parquet(source)

# Check for duplicate credit-month pairs, which is an anomaly.
logger.info("Total rows: %s", len(df))
logger.info("Missing values:\n%s", df.isna().sum().to_string())

duplicate_months = df.duplicated(
    subset=["SK_ID_BUREAU", "MONTHS_BALANCE"]
).sum()

logger.info("Duplicate credit-month pairs: %s", duplicate_months)

logger.info(
    "STATUS values:\n%s",
    df["STATUS"].value_counts(dropna=False).to_string(),
)

logger.info(
    "Month range: %s to %s",
    df["MONTHS_BALANCE"].min(),
    df["MONTHS_BALANCE"].max(),
)

# Check link between bureau_balance and bureau tables to see if any bureau records are missing from the balance table then count unique credit IDs missing.
bureau = pd.read_parquet(
    project_folder / "data" / "silver" / "bureau.parquet",
    columns=["SK_ID_BUREAU"],
)

unmatched = ~df["SK_ID_BUREAU"].isin(bureau["SK_ID_BUREAU"])
df["BUREAU_ID_UNMATCHED"] = unmatched

logger.info("Rows without matching bureau credit: %s", unmatched.sum())

logger.info(
    "Distinct unmatched credit IDs: %s",
    df.loc[unmatched, "SK_ID_BUREAU"].nunique(),
)

assert df["SK_ID_BUREAU"].notna().all(), "Missing bureau IDs"
assert df["MONTHS_BALANCE"].notna().all(), "Missing months"

assert not df.duplicated(
    subset=["SK_ID_BUREAU", "MONTHS_BALANCE"]
).any(), "Duplicate credit-month pairs"

logger.info("Bureau balance checks passed.")

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "bureau_balance.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved bureau balance data to %s", destination)