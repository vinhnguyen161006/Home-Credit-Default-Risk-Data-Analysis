"""Inspect previous applications before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "previous_application.parquet"

df = pd.read_parquet(source)

logger.info("Total rows: %s", len(df))
logger.info("Missing previous IDs: %s", df["SK_ID_PREV"].isna().sum())
logger.info("Duplicate previous IDs: %s", df["SK_ID_PREV"].duplicated().sum())
logger.info("Missing applicant IDs: %s", df["SK_ID_CURR"].isna().sum())

logger.info(
    "Application statuses:\n%s",
    df["NAME_CONTRACT_STATUS"].value_counts(dropna=False).to_string(),
)

date_columns = [
    "DAYS_FIRST_DRAWING",
    "DAYS_FIRST_DUE",
    "DAYS_LAST_DUE_1ST_VERSION",
    "DAYS_LAST_DUE",
    "DAYS_TERMINATION",
]

for column in date_columns:
    logger.info(
        "%s | Missing: %s | Min: %s | Max: %s | 365243: %s",
        column,
        df[column].isna().sum(),
        df[column].min(),
        df[column].max(),
        df[column].eq(365243).sum(),
    )

# Remove the anomalous value 365243 in the date columns to preserve the information that the value was missing.
for column in date_columns:
    flag_column = f"{column}_SENTINEL"

    df[flag_column] = df[column].eq(365243)
    df.loc[df[flag_column], column] = float("nan")

    logger.info(
        "%s | Replaced: %s | Missing after: %s",
        column,
        df[flag_column].sum(),
        df[column].isna().sum(),
    )

assert not df[date_columns].eq(365243).any().any(), "365243 remains"

amount_columns = [
    "AMT_APPLICATION",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "AMT_DOWN_PAYMENT",
    "AMT_GOODS_PRICE",
]

for column in amount_columns:
    logger.info(
        "%s | Missing: %s | Negative: %s | Zero: %s",
        column,
        df[column].isna().sum(),
        (df[column] < 0).sum(),
        (df[column] == 0).sum(),
    )

# Identify records with negative down payment values, which are anomalies.
negative_down_payment = df[df["AMT_DOWN_PAYMENT"] < 0]

review_columns = [
    "SK_ID_PREV",
    "NAME_CONTRACT_STATUS",
    "NAME_CONTRACT_TYPE",
    "AMT_APPLICATION",
    "AMT_CREDIT",
    "AMT_DOWN_PAYMENT",
    "AMT_GOODS_PRICE",
]

logger.info(
    "Negative down payment records:\n%s",
    negative_down_payment[review_columns].to_string(index=False),
)

df["DOWN_PAYMENT_NEGATIVE"] = df["AMT_DOWN_PAYMENT"] < 0

logger.info(
    "Negative down payments marked: %s",
    df["DOWN_PAYMENT_NEGATIVE"].sum(),
)

# Fill missing columns with "Unknown" to preserve the information that the value was missing.
category_columns = ["NAME_TYPE_SUITE", "PRODUCT_COMBINATION"]

for column in category_columns:
    logger.info(
        "\n%s:\n%s",
        column,
        df[column].value_counts(dropna=False).to_string(),
    )

for column in category_columns:
    missing_before = df[column].isna().sum()

    df[column] = df[column].fillna("Unknown")

    logger.info(
        "%s | Filled: %s | Missing after: %s",
        column,
        missing_before,
        df[column].isna().sum(),
    )

assert len(df) == 1670214, "Row count changed"
assert df["SK_ID_PREV"].notna().all(), "Missing previous IDs"
assert df["SK_ID_PREV"].is_unique, "Duplicate previous IDs"
assert df["SK_ID_CURR"].notna().all(), "Missing applicant IDs"

assert not df[date_columns].eq(365243).any().any(), "365243 remains"
assert df[category_columns].notna().all().all(), "Missing categories remain"

logger.info("Previous application checks passed.")

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "previous_application.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved previous application data to %s", destination)