"""Inspect installment payments before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "installments_payments.parquet"

df = pd.read_parquet(source)

logger.info("Total rows: %s", len(df))
logger.info("Missing values:\n%s", df.isna().sum().to_string())

# Check for missing values in the amount columns, as well as the number of negative and zero values.
amount_columns = ["AMT_INSTALMENT", "AMT_PAYMENT"]

for column in amount_columns:
    logger.info(
        "%s | Negative: %s | Zero: %s",
        column,
        (df[column] < 0).sum(),
        (df[column] == 0).sum(),
    )

missing_date = df["DAYS_ENTRY_PAYMENT"].isna()
missing_amount = df["AMT_PAYMENT"].isna()

logger.info(
    "Missing both payment date and amount: %s",
    (missing_date & missing_amount).sum(),
)

logger.info(
    "Missing only payment date: %s",
    (missing_date & ~missing_amount).sum(),
)

logger.info(
    "Missing only payment amount: %s",
    (~missing_date & missing_amount).sum(),
)

df["PAYMENT_INFO_MISSING"] = missing_date & missing_amount

date_columns = ["DAYS_INSTALMENT", "DAYS_ENTRY_PAYMENT"]

logger.info(
    "Payment date ranges:\n%s",
    df[date_columns].agg(["min", "max"]).to_string(),
)

previous = pd.read_parquet(
    project_folder / "data" / "silver" / "previous_application.parquet",
    columns=["SK_ID_PREV"],
)

# Check link between installments_payments and previous_application tables to see if any previous application records are missing from the payments table then count unique previous application IDs missing.
df["PREV_ID_UNMATCHED"] = ~df["SK_ID_PREV"].isin(previous["SK_ID_PREV"])

logger.info(
    "Rows without matching previous application: %s",
    df["PREV_ID_UNMATCHED"].sum(),
)

logger.info(
    "Distinct unmatched previous IDs: %s",
    df.loc[df["PREV_ID_UNMATCHED"], "SK_ID_PREV"].nunique(),
)

duplicate_rows = df.duplicated().sum()

logger.info("Fully duplicated rows: %s", duplicate_rows)

assert len(df) == 13605401, "Row count changed"

required_columns = [
    "SK_ID_PREV",
    "SK_ID_CURR",
    "NUM_INSTALMENT_VERSION",
    "NUM_INSTALMENT_NUMBER",
    "DAYS_INSTALMENT",
]

assert df[required_columns].notna().all().all(), "Missing required values"

logger.info("Installment checks passed.")

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "installments_payments.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved installment payments to %s", destination)