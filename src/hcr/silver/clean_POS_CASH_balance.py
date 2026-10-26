"""Inspect POS cash balances before cleaning."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "POS_CASH_balance.parquet"

df = pd.read_parquet(source)

logger.info("Total rows: %s", len(df))
logger.info("Missing values:\n%s", df.isna().sum().to_string())

duplicate_months = df.duplicated(
    subset=["SK_ID_PREV", "MONTHS_BALANCE"]
).sum()

logger.info("Duplicate loan-month pairs: %s", duplicate_months)

# Mark missing values in CNT_INSTALMENT and CNT_INSTALMENT_FUTURE to preserve the information that the value was missing.
instalment_columns = ["CNT_INSTALMENT", "CNT_INSTALMENT_FUTURE"]

for column in instalment_columns:
    missing_rows = df[df[column].isna()]

    logger.info(
        "\nMissing %s by contract status:\n%s",
        column,
        missing_rows["NAME_CONTRACT_STATUS"]
        .value_counts(dropna=False)
        .to_string(),
    )

df["CNT_INSTALMENT_FUTURE_MISSING"] = df["CNT_INSTALMENT_FUTURE"].isna()


numeric_columns = [
    "MONTHS_BALANCE",
    "CNT_INSTALMENT",
    "CNT_INSTALMENT_FUTURE",
    "SK_DPD",
    "SK_DPD_DEF",
]

logger.info(
    "Numeric ranges:\n%s",
    df[numeric_columns].agg(["min", "max"]).to_string(),
)

df["FUTURE_INSTALMENTS_EXCEED_TOTAL"] = (
    df["CNT_INSTALMENT"].notna()
    & df["CNT_INSTALMENT_FUTURE"].notna()
    & (df["CNT_INSTALMENT_FUTURE"] > df["CNT_INSTALMENT"])
)

logger.info(
    "Future instalments exceed total: %s",
    df["FUTURE_INSTALMENTS_EXCEED_TOTAL"].sum(),
)

# Check the rows where future instalments exceed total instalments to see if there are any patterns or anomalies that need to be addressed.
review_rows = df[df["FUTURE_INSTALMENTS_EXCEED_TOTAL"]]

review_columns = [
    "SK_ID_PREV",
    "MONTHS_BALANCE",
    "NAME_CONTRACT_STATUS",
    "CNT_INSTALMENT",
    "CNT_INSTALMENT_FUTURE",
]

logger.info(
    "Instalment inconsistencies:\n%s",
    review_rows[review_columns].head(10).to_string(index=False),
)

logger.info(
    "Distinct loans affected: %s",
    review_rows["SK_ID_PREV"].nunique(),
)

difference = (
    review_rows["CNT_INSTALMENT_FUTURE"]
    - review_rows["CNT_INSTALMENT"]
)

logger.info(
    "Instalment difference counts:\n%s",
    difference.value_counts().sort_index().to_string(),
)

previous = pd.read_parquet(
    project_folder / "data" / "silver" / "previous_application.parquet",
    columns=["SK_ID_PREV"],
)

# Mark rows in the POS cash balance data that do not have a matching previous application record to preserve the information that the value was missing.
df["PREV_ID_UNMATCHED"] = ~df["SK_ID_PREV"].isin(previous["SK_ID_PREV"])

logger.info(
    "Rows without matching previous application: %s",
    df["PREV_ID_UNMATCHED"].sum(),
)

logger.info(
    "Distinct unmatched previous IDs: %s",
    df.loc[df["PREV_ID_UNMATCHED"], "SK_ID_PREV"].nunique(),
)

assert len(df) == 10001358, "Row count changed"

key_columns = ["SK_ID_PREV", "SK_ID_CURR", "MONTHS_BALANCE"]
assert df[key_columns].notna().all().all(), "Missing identifiers or months"

assert not df.duplicated(
    subset=["SK_ID_PREV", "MONTHS_BALANCE"]
).any(), "Duplicate loan-month pairs"

logger.info("POS cash checks passed.")

silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "POS_CASH_balance.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved POS cash data to %s", destination)