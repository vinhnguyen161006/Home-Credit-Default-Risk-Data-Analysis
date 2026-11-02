"""Clean application data while preserving missing-value information."""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

project_folder = Path(__file__).resolve().parents[3]
source = project_folder / "data" / "bronze" / "application_train.parquet"

df = pd.read_parquet(source)

# Calculate age in years from DAYS_BIRTH and add it as a new column
df["AGE_YEARS"] = -df["DAYS_BIRTH"] / 365.25

logger.info(
    "Age range: %.2f to %.2f years",
    df["AGE_YEARS"].min(),
    df["AGE_YEARS"].max(),
)

# Replace missing values in OCCUPATION_TYPE with "Unknown"
logger.info("Missing before: %s", df["OCCUPATION_TYPE"].isna().sum())

df["OCCUPATION_TYPE"] = df["OCCUPATION_TYPE"].fillna("Unknown")

logger.info("Missing after: %s", df["OCCUPATION_TYPE"].isna().sum())

# Add a new column to indicate whether car age is missing for car owners
missing_car_age = df[df["OWN_CAR_AGE"].isna()]

logger.info(
    "Car ownership among rows missing car age:\n%s",
    missing_car_age["FLAG_OWN_CAR"].value_counts(dropna=False).to_string(),
)
df["CAR_AGE_MISSING"] = (df["FLAG_OWN_CAR"] == "Y") & df["OWN_CAR_AGE"].isna()

logger.info(
    "Car owners with missing car age: %s",
    df["CAR_AGE_MISSING"].sum(),
)

# Replace missing values in NAME_TYPE_SUITE with "Unknown"
logger.info("Missing suite before: %s", df["NAME_TYPE_SUITE"].isna().sum())

df["NAME_TYPE_SUITE"] = df["NAME_TYPE_SUITE"].fillna("Unknown")

logger.info("Missing suite after: %s", df["NAME_TYPE_SUITE"].isna().sum())

# Flag customers with anomalous employment duration
df["FLAG_NO_EMPLOYMENT"] = df["DAYS_EMPLOYED"].eq(365243)

logger.info(
    "Customers with no employment information: %s",
    df["FLAG_NO_EMPLOYMENT"].sum(),
)

# Replace the anomalous sentinel with missing value
df.loc[df["FLAG_NO_EMPLOYMENT"], "DAYS_EMPLOYED"] = pd.NA

# Mark review for anomalous income records for the application with SK_ID_CURR 114967
df["INCOME_REVIEW_REQUIRED"] = df["SK_ID_CURR"].eq(114967)

logger.info(
    "Income records requiring review: %s",
    df["INCOME_REVIEW_REQUIRED"].sum(),
)

# Replace the anomalous value "XNA" in CODE_GENDER with "Unknown"
df["CODE_GENDER"] = df["CODE_GENDER"].replace("XNA", "Unknown")

logger.info(
    "Gender after cleaning:\n%s",
    df["CODE_GENDER"].value_counts(dropna=False).to_string(),
)

assert len(df) == 307511, "Row count changed"
assert df["SK_ID_CURR"].notna().all(), "Missing application IDs"
assert df["SK_ID_CURR"].is_unique, "Duplicate application IDs"
assert df["TARGET"].isin([0, 1]).all(), "Invalid TARGET"

assert df["OCCUPATION_TYPE"].notna().all(), "Missing occupation"
assert df["NAME_TYPE_SUITE"].notna().all(), "Missing suite"
assert not df["CODE_GENDER"].eq("XNA").any(), "XNA remains"
assert not df["DAYS_EMPLOYED"].eq(365243).any(), "365243 remains"

logger.info("Cleaning checks passed.")

# Add columns to indicate amount of missing values in amount columns
amount_columns = ["AMT_ANNUITY", "AMT_GOODS_PRICE"]

for column in amount_columns:
    df[f"{column}_MISSING"] = df[column].isna()

    logger.info(
        "%s: kept %s missing values",
        column,
        df[f"{column}_MISSING"].sum(),
    )

df["EXT_SOURCE_1_MISSING"] = df["EXT_SOURCE_1"].isna()

logger.info(
    "Missing EXT_SOURCE_1: %s",
    df["EXT_SOURCE_1_MISSING"].sum(),
)

# Save the cleaned data to the silver folder
silver_folder = project_folder / "data" / "silver"
silver_folder.mkdir(parents=True, exist_ok=True)

destination = silver_folder / "application_train.parquet"
df.to_parquet(destination, index=False)

logger.info("Saved cleaned data to %s", destination)
