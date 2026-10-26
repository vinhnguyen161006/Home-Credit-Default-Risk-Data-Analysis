"""Inspect credit card balances before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "credit_card_balance.parquet"

df = pd.read_parquet(source)

logger.info("Total rows: %s", len(df))
logger.info("Missing values:\n%s", df.isna().sum().to_string())

duplicate_months = df.duplicated(
    subset=["SK_ID_PREV", "MONTHS_BALANCE"]
).sum()

logger.info("Duplicate credit-month pairs: %s", duplicate_months)

logger.info(
    "Contract statuses:\n%s",
    df["NAME_CONTRACT_STATUS"].value_counts(dropna=False).to_string(),
)

drawing_columns = [
    "AMT_DRAWINGS_ATM_CURRENT",
    "AMT_DRAWINGS_OTHER_CURRENT",
    "AMT_DRAWINGS_POS_CURRENT",
]

# Mark missing values in the drawing channels to preserve the information that the value was missing.
missing_channels = df[drawing_columns].isna().all(axis=1)

logger.info(
    "Rows missing all three drawing channels: %s",
    missing_channels.sum(),
)

logger.info(
    "Of these, total drawings equal zero: %s",
    (missing_channels & df["AMT_DRAWINGS_CURRENT"].eq(0)).sum(),
)

logger.info(
    "Of these, total drawings differ from zero: %s",
    (missing_channels & df["AMT_DRAWINGS_CURRENT"].ne(0)).sum(),
)

df["DRAWING_CHANNELS_MISSING"] = missing_channels

numeric_columns = [
    column
    for column in df.columns
    if column.startswith(("AMT_", "CNT_"))
]

for column in numeric_columns:
    logger.info(
        "%s | Missing: %s | Negative: %s | Min: %s | Max: %s",
        column,
        df[column].isna().sum(),
        (df[column] < 0).sum(),
        df[column].min(),
        df[column].max(),
    )

# Check for negative values in the drawing channels, which is an anomaly.
negative_drawings = (
    (df["AMT_DRAWINGS_ATM_CURRENT"] < 0)
    | (df["AMT_DRAWINGS_CURRENT"] < 0)
)

review_columns = [
    "SK_ID_PREV",
    "MONTHS_BALANCE",
    "NAME_CONTRACT_STATUS",
    "AMT_DRAWINGS_ATM_CURRENT",
    "AMT_DRAWINGS_POS_CURRENT",
    "AMT_DRAWINGS_OTHER_CURRENT",
    "AMT_DRAWINGS_CURRENT",
]

logger.info(
    "Negative drawing records:\n%s",
    df.loc[negative_drawings, review_columns].to_string(index=False),
)

df["NEGATIVE_DRAWINGS"] = negative_drawings

check_columns = ["MONTHS_BALANCE", "SK_DPD", "SK_DPD_DEF"]

logger.info(
    "Month and overdue ranges:\n%s",
    df[check_columns].agg(["min", "max"]).to_string(),
)

# Check the link between credit_card_balance and previous_application tables to see if any previous application records are missing from the balance table then count unique previous application IDs missing.
previous = pd.read_parquet(
    project_folder / "data" / "silver" / "previous_application.parquet",
    columns=["SK_ID_PREV"],
)

df["PREV_ID_UNMATCHED"] = ~df["SK_ID_PREV"].isin(previous["SK_ID_PREV"])

logger.info(
    "Rows without matching previous application: %s",
    df["PREV_ID_UNMATCHED"].sum(),
)

logger.info(
    "Distinct unmatched previous IDs: %s",
    df.loc[df["PREV_ID_UNMATCHED"], "SK_ID_PREV"].nunique(),
)

assert len(df) == 3840312, "Row count changed"

key_columns = ["SK_ID_PREV", "SK_ID_CURR", "MONTHS_BALANCE"]
assert df[key_columns].notna().all().all(), "Missing identifiers or months"

assert not df.duplicated(
    subset=["SK_ID_PREV", "MONTHS_BALANCE"]
).any(), "Duplicate credit-month pairs"

assert df[["SK_DPD", "SK_DPD_DEF"]].ge(0).all().all(), "Invalid overdue days"

logger.info("Credit card checks passed.")

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "credit_card_balance.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved credit card data to %s", destination)