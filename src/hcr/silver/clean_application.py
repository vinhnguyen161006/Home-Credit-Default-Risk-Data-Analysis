"""Step 3 for the application table: repair the value traps, keep the absences.

Every function takes a frame and returns a new one, so a step never mutates its input and
the whole module runs on small fixtures as well as on the 307511 real rows. Polars owns
this transformation; pandas stays in exploratory profiling and is not repeated here.

Missing data is never filled with zero. A null stays null and, where absence carries
meaning, gets a flag. The only fills are the agreed Unknown labels for XNA gender and for a
missing occupation, and the occupation flag is computed before its fill so it still records
which rows were null.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

import polars as pl

from hcr.config import load_silver_rules
from hcr.paths import bronze_path, ensure_parent, silver_path

if TYPE_CHECKING:
    from pathlib import Path

    from hcr.config import SilverRules

logger = logging.getLogger(__name__)

APPLICATION_TABLE: Final = "application_train"
DAYS_PER_YEAR: Final = 365.25
XNA_CODE: Final = "XNA"
BUILDING_AVERAGE_SUFFIX: Final = "_AVG"
BUILDING_DROPPED_SUFFIXES: Final = ("_MODE", "_MEDI")
BUILDING_COMPLETE_FLAG: Final = "FLAG_BUILDING_INFO_COMPLETE"
FLAG_DTYPE: Final = pl.Int8


def null_employment_sentinel(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Replace the DAYS_EMPLOYED sentinel with null and flag the rows it marked.

    The flag comes from the sentinel match and not from the resulting null, because
    DAYS_EMPLOYED can be null for other reasons and the flag means "not employed".

    Args:
        frame: Application table in bronze form.
        rules: Parsed silver rules naming the column, sentinel value and flag.

    Returns:
        Frame with the sentinel nulled and the flag column added.
    """
    column = rules.employment_sentinel["column"]
    is_sentinel = (pl.col(column) == rules.employment_sentinel["value"]).fill_null(False)
    return frame.with_columns(
        is_sentinel.cast(FLAG_DTYPE).alias(rules.employment_sentinel["emit_flag"]),
        pl.when(is_sentinel).then(None).otherwise(pl.col(column)).alias(column),
    )


def derive_age_and_tenure(frame: pl.DataFrame) -> pl.DataFrame:
    """Add AGE_YEARS and EMPLOYMENT_YEARS from the negative day offsets.

    Must run after the employment sentinel is nulled. Computed first, the sentinel would
    become a thousand years of tenure that no later step notices.

    Args:
        frame: Application table with DAYS_BIRTH and DAYS_EMPLOYED.

    Returns:
        Frame with the two derived columns; the DAYS_* columns keep their sign.
    """
    return frame.with_columns(
        (-pl.col("DAYS_BIRTH") / DAYS_PER_YEAR).alias("AGE_YEARS"),
        (-pl.col("DAYS_EMPLOYED") / DAYS_PER_YEAR).alias("EMPLOYMENT_YEARS"),
    )


def add_missingness_flags(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Add one 0/1 flag per column whose absence carries meaning.

    Run before any fill so the flag still records which rows were originally null.

    Args:
        frame: Application table.
        rules: Parsed silver rules mapping each column to its flag name.

    Returns:
        Frame with the flags added and every original column unchanged.
    """
    return frame.with_columns(
        pl.col(column).is_null().cast(FLAG_DTYPE).alias(flag)
        for column, flag in rules.missingness_flags.items()
    )


def replace_unknown_categories(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Give XNA gender and missing occupation the agreed Unknown label.

    ORGANIZATION_TYPE is deliberately absent from both lists: its XNA covers about 18 percent
    of rows, overlaps the retired population, and stays a category of its own.

    Args:
        frame: Application table with missingness flags already added.
        rules: Parsed silver rules naming the columns and the label.

    Returns:
        Frame with the labels applied.
    """
    label = rules.unknown_label
    return frame.with_columns(
        *(
            pl.when(pl.col(column) == XNA_CODE)
            .then(pl.lit(label))
            .otherwise(pl.col(column))
            .alias(column)
            for column in rules.xna_to_unknown_columns
        ),
        *(pl.col(column).fill_null(label) for column in rules.null_to_unknown_columns),
    )


def flag_income_outliers(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Flag values above the configured quantile and leave every value untouched.

    Capping the income would hide the extreme applicant from the audit that most needs to
    see them, and dropping the row would bias the sample.

    Args:
        frame: Application table.
        rules: Parsed silver rules mapping each column to its quantile and flag.

    Returns:
        Frame with the outlier flags added.
    """
    return frame.with_columns(
        (pl.col(column) > pl.col(column).quantile(declaration.upper_quantile, "nearest"))
        .fill_null(False)
        .cast(FLAG_DTYPE)
        .alias(declaration.flag)
        for column, declaration in rules.outlier_flags.items()
    )


def reduce_building_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep the _AVG building variant and replace the others with one completeness flag.

    The _MODE and _MEDI variants are dropped only where an _AVG sibling exists, so the
    standalone categorical building columns survive.

    Args:
        frame: Application table.

    Returns:
        Frame without the redundant variants, plus FLAG_BUILDING_INFO_COMPLETE set to 1
        where every _AVG column is present. Unchanged if the frame has no _AVG column.
    """
    average_columns = [c for c in frame.columns if c.endswith(BUILDING_AVERAGE_SUFFIX)]
    if not average_columns:
        return frame

    bases = [column.removesuffix(BUILDING_AVERAGE_SUFFIX) for column in average_columns]
    redundant = [
        base + suffix
        for base in bases
        for suffix in BUILDING_DROPPED_SUFFIXES
        if base + suffix in frame.columns
    ]
    is_complete = pl.all_horizontal(pl.col(column).is_not_null() for column in average_columns)
    return frame.with_columns(is_complete.cast(FLAG_DTYPE).alias(BUILDING_COMPLETE_FLAG)).drop(
        redundant
    )


def normalize_application(frame: pl.DataFrame, rules: SilverRules) -> pl.DataFrame:
    """Apply every application repair in the one order that keeps them correct.

    The order is fixed: sentinel before tenure, flags before fills, outlier flag before
    anything could touch income.

    Args:
        frame: Application table in bronze form.
        rules: Parsed silver rules.

    Returns:
        Silver application table with the same rows and extra columns.
    """
    frame = null_employment_sentinel(frame, rules)
    frame = derive_age_and_tenure(frame)
    frame = add_missingness_flags(frame, rules)
    frame = replace_unknown_categories(frame, rules)
    frame = flag_income_outliers(frame, rules)
    return reduce_building_columns(frame)


def assert_application_clean(frame: pl.DataFrame, rules: SilverRules, expected_rows: int) -> None:
    """Assert the silver application table honours the step 3 gate.

    Raises:
        ValueError: If a row was lost, the key is not unique, a sentinel or XNA gender
            survived, or a DAYS_* value is positive.
    """
    if len(frame) != expected_rows:
        raise ValueError(f"Application row count {len(frame)} differs from {expected_rows}")
    if frame["SK_ID_CURR"].n_unique() != len(frame):
        raise ValueError("SK_ID_CURR is not unique in the silver application table")

    sentinel_column = rules.employment_sentinel["column"]
    if (frame[sentinel_column] == rules.employment_sentinel["value"]).any():
        raise ValueError(f"{sentinel_column} still holds the sentinel")
    for column in rules.xna_to_unknown_columns:
        if (frame[column] == XNA_CODE).any():
            raise ValueError(f"{column} still holds {XNA_CODE}")

    for column in rules.days_columns:
        if column in frame.columns and (frame[column] > 0).any():
            raise ValueError(f"{column} holds positive offsets after normalization")


def clean_application(source: Path, destination: Path, rules: SilverRules) -> int:
    """Read a bronze application file, normalize it and write a new silver file.

    Args:
        source: Bronze Parquet path, read and never modified.
        destination: Silver Parquet path, written once and distinct from source.
        rules: Parsed silver rules.

    Returns:
        Number of rows written.

    Raises:
        ValueError: If destination equals source or the cleaned table fails its gate.
    """
    if destination == source:
        raise ValueError("A step must not overwrite its own input")

    raw = pl.read_parquet(source)
    silver = normalize_application(raw, rules)
    assert_application_clean(silver, rules, expected_rows=len(raw))
    silver.write_parquet(ensure_parent(destination))
    logger.info("Wrote %s rows to %s", len(silver), destination)
    return len(silver)


def main() -> None:
    """Normalize application_train from bronze into silver."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    clean_application(
        bronze_path(APPLICATION_TABLE), silver_path(APPLICATION_TABLE), load_silver_rules()
    )


if __name__ == "__main__":
    main()
