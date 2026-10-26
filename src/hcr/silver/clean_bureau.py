"""Inspect bureau identifiers before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "bureau.parquet"

df = pd.read_parquet(source)

# Check for credit that is closed but has a missing end date, which is an anomaly.
enddate_summary = (
    df.groupby("CREDIT_ACTIVE")["DAYS_ENDDATE_FACT"]
    .agg(
        total_rows="size",
        known_enddate="count",
    )
)

enddate_summary["missing_enddate"] = (
    enddate_summary["total_rows"] - enddate_summary["known_enddate"]
)

logger.info(
    "End date availability by credit status:\n%s",
    enddate_summary.to_string(),
)

df["CLOSED_ENDDATE_MISSING"] = (
    (df["CREDIT_ACTIVE"] == "Closed")
    & df["DAYS_ENDDATE_FACT"].isna()
)

logger.info(
    "Closed credits missing actual end date: %s",
    df["CLOSED_ENDDATE_MISSING"].sum(),
)

# Count the number of records with missing values in the amount columns, as well as the number of negative and zero values. 
amount_columns = [
    "AMT_CREDIT_SUM",
    "AMT_CREDIT_SUM_DEBT",
    "AMT_CREDIT_SUM_LIMIT",
    "AMT_CREDIT_SUM_OVERDUE",
    "AMT_CREDIT_MAX_OVERDUE",
    "AMT_ANNUITY",
]

for column in amount_columns:
    logger.info(
        "%s | Missing: %s | Negative: %s | Zero: %s",
        column,
        df[column].isna().sum(),
        (df[column] < 0).sum(),
        (df[column] == 0).sum(),
    )

# Identify records with negative debt and limit values, which are anomalies.
negative_debt = df[df["AMT_CREDIT_SUM_DEBT"] < 0]

review_columns = [
    "SK_ID_BUREAU",
    "CREDIT_ACTIVE",
    "CREDIT_TYPE",
    "AMT_CREDIT_SUM",
    "AMT_CREDIT_SUM_DEBT",
    "AMT_CREDIT_SUM_LIMIT",
]

logger.info(
    "Negative debt examples:\n%s",
    negative_debt.nsmallest(10, "AMT_CREDIT_SUM_DEBT")[
        review_columns
    ].to_string(index=False),
)

df["DEBT_NEGATIVE"] = df["AMT_CREDIT_SUM_DEBT"] < 0
df["LIMIT_NEGATIVE"] = df["AMT_CREDIT_SUM_LIMIT"] < 0

logger.info("Negative debt: %s", df["DEBT_NEGATIVE"].sum())
logger.info("Negative limit: %s", df["LIMIT_NEGATIVE"].sum())

logger.info(
    "Negative debt by credit type:\n%s",
    df.loc[df["DEBT_NEGATIVE"], "CREDIT_TYPE"].value_counts().to_string(),
)

# Identify credit with anomalous end dates that occur before the credit start date, which is an anomaly.
date_columns = [
    "DAYS_CREDIT",
    "DAYS_CREDIT_ENDDATE",
    "DAYS_ENDDATE_FACT",
    "DAYS_CREDIT_UPDATE",
]

logger.info(
    "Date ranges:\n%s",
    df[date_columns].agg(["min", "max"]).to_string(),
)

df["ACTUAL_END_BEFORE_CREDIT"] = (
    df["DAYS_ENDDATE_FACT"].notna()
    & (df["DAYS_ENDDATE_FACT"] < df["DAYS_CREDIT"])
)

df["PLANNED_END_BEFORE_CREDIT"] = (
    df["DAYS_CREDIT_ENDDATE"].notna()
    & (df["DAYS_CREDIT_ENDDATE"] < df["DAYS_CREDIT"])
)

logger.info(
    "Actual end before credit: %s",
    df["ACTUAL_END_BEFORE_CREDIT"].sum(),
)
logger.info(
    "Planned end before credit: %s",
    df["PLANNED_END_BEFORE_CREDIT"].sum(),
)

assert len(df) == 1716428, "Row count changed"
assert df["SK_ID_BUREAU"].notna().all(), "Missing bureau IDs"
assert df["SK_ID_BUREAU"].is_unique, "Duplicate bureau IDs"
assert df["SK_ID_CURR"].notna().all(), "Missing applicant IDs"

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "bureau.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved bureau data to %s", destination)