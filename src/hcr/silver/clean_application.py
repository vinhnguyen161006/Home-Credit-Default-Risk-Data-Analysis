"""Step 3 for the application tables: repair the seven known value traps.

Each repair here exists because the raw value cannot enter a calculation as it
stands. The governing rule: missing data is not zero. A null aggregate means the
customer never borrowed; a zero aggregate means they borrowed nothing. Filling
zero erases the distinction between a thin file and a clean history, which is
the distinction this problem most needs to make.

Grain is preserved. One silver row per application, same as bronze.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import polars as pl

    from hcr.config import SilverRules

logger = logging.getLogger(__name__)

EMPLOYMENT_SENTINEL: Final = 365243
DAYS_PER_YEAR: Final = 365.25
GENDER_UNKNOWN_CODE: Final = "XNA"
INCOME_WINSOR_QUANTILE: Final = 0.999


def null_employment_sentinel(frame: pl.DataFrame) -> pl.DataFrame:
    """Replace the 365243 employment code with null and flag the row.

    The highest-risk trap in this table. The value is a convention code for
    applicants who are not employed, about 18 percent of rows. Left in place it
    injects a figure equivalent to 1000 years into every mean and corrupts all
    employment tenure statistics.

    Args:
        frame: Application table at bronze grain.

    Returns:
        The frame with DAYS_EMPLOYED nulled where it held the sentinel and a new
        FLAG_NO_EMPLOYMENT column.

    TODO:
        - Null DAYS_EMPLOYED where it equals EMPLOYMENT_SENTINEL and set
          FLAG_NO_EMPLOYMENT to 1 on exactly those rows, 0 elsewhere.
        - Set the flag from the sentinel match, not from the resulting null.
          DAYS_EMPLOYED may be null in the source for other reasons, and the flag
          must mean "not employed", not "value absent".
        - Log the affected row count at INFO and warn if it falls outside 15 to
          21 percent, since a large shift means the source convention changed.
    """
    raise NotImplementedError


def derive_age_and_tenure(frame: pl.DataFrame) -> pl.DataFrame:
    """Add AGE_YEARS and EMPLOYMENT_YEARS as positive year counts.

    DAYS_BIRTH and DAYS_EMPLOYED stay negative, because the step 3 gate asserts
    every DAYS_* column is at most zero. Sign flipping is confined to these
    derived columns so that gate has one unambiguous rule to check.

    TODO:
        - Compute AGE_YEARS as -DAYS_BIRTH / DAYS_PER_YEAR.
        - Compute EMPLOYMENT_YEARS the same way, leaving it null wherever
          null_employment_sentinel nulled the source. Run this after that
          function, never before, or the sentinel becomes 1000 years of tenure.
    """
    raise NotImplementedError


def null_unknown_gender(frame: pl.DataFrame) -> pl.DataFrame:
    """Replace the four XNA gender rows with null.

    No replacement value is assigned. Imputing a gender on four rows would
    fabricate a protected attribute that the fairness measurement then reports
    on, which is worse than a null the model handles natively.

    TODO:
        - Null CODE_GENDER where it equals GENDER_UNKNOWN_CODE.
        - Emit no flag. Four rows carry no signal worth a column.
        - Assert the affected count is small, single digits, and warn otherwise.
    """
    raise NotImplementedError


def keep_organization_unknown_as_level(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep ORGANIZATION_TYPE XNA as a category of its own.

    About 18 percent of rows, overlapping almost entirely with the retired
    population. Not missing at random, so treating it as absent would discard a
    real group distinction.

    TODO:
        - Leave the value in place and return the frame unchanged, or normalise
          it to an explicit label such as "NOT_EMPLOYED_OR_UNKNOWN" if a
          readable category name is wanted for the BI layer.
        - Do not null it. This function exists to document that the omission is
          deliberate, so a later reader does not "fix" it.
    """
    raise NotImplementedError


def winsorize_income(frame: pl.DataFrame, upper_quantile: float) -> pl.DataFrame:
    """Cap AMT_INCOME_TOTAL at its upper quantile without dropping rows.

    One applicant reports 117000000, far outside the rest of the distribution.
    The row is a real application and dropping it would bias the sample; only the
    value needs containing.

    Args:
        frame: Application table.
        upper_quantile: Quantile to cap at, 0.999 per the silver rules.

    TODO:
        - Compute the quantile over non-null values and clip above it.
        - Never drop a row, and log how many values were capped.
        - Consider emitting log income as a separate column rather than
          replacing the raw value, so the BI layer can still report the real
          figure while the model sees the tamed one.
    """
    raise NotImplementedError


def add_missingness_flags(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Add an explicit presence flag for each column whose absence has meaning.

    EXT_SOURCE_1 is absent for about 56 percent of applicants and OWN_CAR_AGE for
    about 66 percent, the latter because the applicant owns no car. The null
    stays; the flag lets a linear baseline use the absence that LightGBM would
    learn from the missing branch anyway.

    TODO:
        - For each column in rules.missingness_flags, add the named flag as 1
          where the column is null and 0 elsewhere.
        - Never fill the source column. The flag is additive; filling would
          destroy the very signal the flag records.
    """
    raise NotImplementedError


def reduce_building_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Collapse the 47 apartment description columns to one variant plus a flag.

    Three variants, _AVG, _MODE and _MEDI, describe the same attribute and
    correlate tightly. The group is nearly two thirds of the table's columns and
    contributes the least predictive power of any group, with very high
    missingness throughout.

    Reduction happens here, before aggregation, so the variants never multiply
    through the four feature families.

    TODO:
        - Keep the _AVG variant and drop _MODE and _MEDI.
        - Add FLAG_BUILDING_INFO_COMPLETE recording whether the group was
          populated at all, which is the part of this group that does carry
          signal.
        - Consider replacing the kept columns with a single completeness score if
          the step 6 correlation filter removes most of them anyway; decide from
          the filter's output, not in advance.
    """
    raise NotImplementedError


def run() -> tuple[int, int]:
    """Normalize application_train and application_test into silver.

    Returns:
        Row counts written for train and test, in that order.

    TODO:
        - Apply the repairs in order: sentinel nulling, then derived years, then
          gender, then organisation, then winsorize, then flags, then building
          reduction. Order matters between the first two.
        - Apply identical logic to train and test. A repair applied to only one
          of them makes the two tables structurally different, which would break
          any later scoring of the test set.
        - Never write into the bronze directory.
        - Assert the output row count equals the input row count. This step
          repairs values and adds columns; it removes no row.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.silver.clean_application`.

    TODO:
        - Configure logging, call run, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
