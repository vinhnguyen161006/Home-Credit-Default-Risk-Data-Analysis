"""Build the star schema: nine dimensions and one fact table.

This is a different shape from the training matrix, deliberately. The matrix is wide,
flat and unnormalised, read once in full into memory. The star schema is narrow, about
30 business fields with readable names, queried by aggregation from Power BI. The two
access patterns cannot be optimised at once, so they are separate structures and the
matrix never enters SQL Server.

TARGET and PD_Predicted sit side by side in the fact table on purpose. It lets the
dashboard measure the model itself rather than only describe the portfolio, and the
IsHoldout flag lets a reader isolate the part the model never trained on.

Each SK_ID_CURR appears exactly once in application_train, so there is no slowly
changing dimension problem. Every attribute is an attribute as at application time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)

EXPECTED_FACT_ROWS: Final = 307511
UNKNOWN_KEY: Final = -1

DIMENSION_SPECS: Final = {
    "Dim_Occupation": ("OccupationKey", "OCCUPATION_TYPE", 19, False),
    "Dim_Organization": ("OrgKey", "ORGANIZATION_TYPE", 59, False),
    "Dim_Education": ("EducationKey", "NAME_EDUCATION_TYPE", 6, True),
    "Dim_ContractType": ("ContractKey", "NAME_CONTRACT_TYPE", 3, False),
    "Dim_HousingType": ("HousingKey", "NAME_HOUSING_TYPE", 7, False),
    "Dim_FamilyStatus": ("FamilyKey", "NAME_FAMILY_STATUS", 7, False),
    "Dim_AgeBand": ("AgeBandKey", "AGE_BAND", 7, True),
    "Dim_IncomeBand": ("IncomeBandKey", "INCOME_BAND", 6, True),
    "Dim_RiskBand": ("RiskBandKey", "RISK_BAND", 6, True),
}

FACT_MEASURES: Final = (
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "AMT_INCOME_TOTAL",
    "AMT_GOODS_PRICE",
    "CREDIT_INCOME_RATIO",
    "ANNUITY_INCOME_RATIO",
)

FACT_MODEL_COLUMNS: Final = (
    "TARGET",
    "PD_Predicted",
    "CreditScore",
    "Model_Version",
    "IsHoldout",
)


@dataclass(frozen=True)
class DimensionTable:
    """One built dimension.

    Attributes:
        name: Table name.
        key_column: Surrogate key column name.
        source_column: Application column it was derived from.
        rows: Row count including the unknown member.
        has_sort_order: Whether it carries a SortOrder column.
    """

    name: str
    key_column: str
    source_column: str
    rows: int
    has_sort_order: bool


def build_dimension(
    values: pl.Series,
    name: str,
    key_column: str,
    has_sort_order: bool,
) -> pl.DataFrame:
    """Build one dimension table from the distinct values of a source column.

    Args:
        values: Distinct source values.
        name: Dimension table name.
        key_column: Surrogate key column to generate.
        has_sort_order: Whether to add SortOrder.

    Returns:
        The dimension, including the unknown member.

    TODO:
        - Generate integer surrogate keys. Never use the business string as the key: a
          long string indexes poorly and breaks on a whitespace or casing difference,
          and both occur in this data.
        - Add exactly one unknown member at key UNKNOWN_KEY. That member is what keeps
          the fact table free of null foreign keys, which is what keeps the report free
          of blank rows.
        - Add SortOrder where has_sort_order is set, which covers Dim_AgeBand,
          Dim_IncomeBand, Dim_RiskBand and Dim_Education. Without it a chart orders the
          bands alphabetically, so "Higher education" precedes "Secondary" and an income
          band chart reads as nonsense.
        - Assign the key deterministically, ordered by the natural sequence where one
          exists and alphabetically otherwise, so two runs produce the same keys and the
          Power BI file does not need rebinding.
        - Assert the row count matches the expected figure in DIMENSION_SPECS and warn on
          a mismatch, which usually means a new category appeared in the source.
    """
    raise NotImplementedError


def build_age_bands(ages: pl.Series) -> pl.Series:
    """Cut AGE_YEARS into the seven age bands.

    TODO:
        - Define the boundaries once, in this function, and have evaluation.fairness
          import them. Two definitions would let the dashboard and the fairness report
          publish different numbers for the same question.
        - Return the unknown band for null ages rather than dropping the row.
    """
    raise NotImplementedError


def build_income_bands(incomes: pl.Series) -> pl.Series:
    """Cut AMT_INCOME_TOTAL into the six income bands.

    TODO:
        - Use fixed currency boundaries, not quantiles. A quantile band shifts whenever
          the population shifts, which makes two reports incomparable over time.
        - Band the winsorized income, so the single 117000000 outlier does not define an
          otherwise empty top band.
    """
    raise NotImplementedError


def build_fact_application(
    applications: pl.DataFrame,
    predictions: pl.DataFrame,
    dimensions: dict[str, pl.DataFrame],
    holdout_ids: pl.Series,
    model_version: str,
) -> pl.DataFrame:
    """Build the fact table: nine keys, six measures, five model columns.

    Args:
        applications: Silver applications.
        predictions: Calibrated probability and score per SK_ID_CURR.
        dimensions: Built dimensions, for key lookup.
        holdout_ids: Identifiers to flag as holdout.
        model_version: Version string recorded on every row.

    Returns:
        The fact table, one row per application.

    Raises:
        ValueError: If the row count is not EXPECTED_FACT_ROWS or any key is null.

    TODO:
        - Look up each foreign key through its dimension, mapping an unmatched or null
          source value to UNKNOWN_KEY. Assert afterwards that no key column holds a
          null; that assertion is the step 8 gate.
        - Set IsHoldout from the identifier file, so the model quality page can filter
          to the rows the model never saw. The dashboard page depends on this flag being
          right, and nothing else would reveal it if it were wrong.
        - Carry TARGET and PD_Predicted both, and in the same table. Splitting them
          across tables would make the calibration gap measure require a relationship
          traversal and the DAX would be worse for no benefit.
        - Record Model_Version on every row, so a dashboard showing two refreshes can
          tell them apart.
        - Assert the row count equals EXPECTED_FACT_ROWS exactly.
        - Keep the column count near 30. Every extra column here is a column Power BI
          loads and a reader has to ignore.
    """
    raise NotImplementedError


def run() -> tuple[DimensionTable, ...]:
    """Build every dimension and the fact table, and write them for loading.

    TODO:
        - Build the dimensions first, then the fact, so key lookup has something to
          match against.
        - Write to Parquet as the handoff to the loader, rather than passing frames. It
          makes the load step rerunnable without rebuilding.
        - Do not write to SQL Server here. Building and loading are separate steps so a
          build can be inspected before it reaches the database.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.serving.build_star`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
