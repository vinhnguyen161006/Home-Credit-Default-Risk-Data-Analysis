"""Feature column naming and the SQL aggregate expression behind every column.

configs/features.yml declares which columns are aggregated by which functions. This module
turns that declaration into one named SQL expression per output column, together with the
provenance the manifest records. Nothing here touches a database, so the whole column
inventory is testable and countable without reading a table.

Window arithmetic lives here too, because mixing the two time units is the defect that
looks most plausible. MONTHS_BALANCE counts months, every DAYS_ column counts days, and a
three month window on the second is 90 units wide, not 3.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Final

from hcr.config import FeatureSpec
from hcr.config.rules import FEATURE_PREFIXES, FIRST_STAGE

IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DAYS_PER_MONTH: Final = 30
MONTHS_COLUMN_PREFIX: Final = "MONTHS_"
DAYS_COLUMN_PREFIX: Final = "DAYS_"
NUMERIC_TYPE: Final = "DOUBLE"
TREND_FUNCTION: Final = "regr_slope"
TREND_SUFFIX: Final = "slope"
COUNT_FUNCTION: Final = "count"
GUARDED_DIVISION: Final = "NULLIF("
STAGE_ONE: Final = 1
STAGE_TWO: Final = 2
SQL_FUNCTIONS: Final = {
    "count": "COUNT",
    "sum": "SUM",
    "mean": "AVG",
    "max": "MAX",
    "min": "MIN",
    "std": "STDDEV_SAMP",
}


@dataclass(frozen=True)
class ColumnProvenance:
    """How one feature column was produced.

    Recorded in the manifest so a column such as BURO_AMT_CREDIT_SUM_MEAN can be traced
    back to its source table, source column and aggregation. Without this, a reviewer
    reading a SHAP plot cannot tell what a column means.

    Attributes:
        name: Output column name.
        source_table: History table it came from.
        source_column: Column aggregated, the derived expression, or the stage one column
            that a second fold aggregated again.
        aggregation: Function applied, or "ratio", "passthrough" or "flag".
        window_months: Window in months, or None for whole history.
        stage: 0 for a passthrough, 1 for the intermediate fold, 2 for the fold to
            customer grain.
    """

    name: str
    source_table: str
    source_column: str
    aggregation: str
    window_months: int | None
    stage: int


@dataclass(frozen=True)
class FeatureColumn:
    """One output column: its SQL aggregate, its unwindowed name and its provenance.

    Attributes:
        base_name: The name without any window suffix. A second fold appends its own
            function to this and then re-applies the window, so the window stays last.
        expression: The SQL aggregate, without an alias.
        provenance: What the manifest records for the column.
    """

    base_name: str
    expression: str
    provenance: ColumnProvenance

    @property
    def name(self) -> str:
        """Return the output column name."""
        return self.provenance.name


def feature_column_name(
    prefix: str,
    source_column: str,
    aggregation: str,
    window_months: int | None,
) -> str:
    """Build a feature column name from its parts.

    The naming contract is PREFIX_COLUMN_AGG for whole-history features and
    PREFIX_COLUMN_AGG_NM for windowed ones. Generating every name through this one
    function is what keeps several hundred columns consistent.

    Args:
        prefix: Source prefix, one of APP, BURO, BB, PREV, POS, INST, CC.
        source_column: Column or derived expression name.
        aggregation: Aggregation function applied.
        window_months: Window in months, or None.

    Returns:
        The upper-case column name.

    Raises:
        ValueError: If the prefix is outside the fixed set. A prefix invented at a call
            site would break every convention the manifest relies on.
    """
    if prefix not in FEATURE_PREFIXES:
        raise ValueError(f"Prefix {prefix!r} is outside the fixed set {sorted(FEATURE_PREFIXES)}")
    name = "_".join((prefix, source_column, aggregation)).upper()
    return name if window_months is None else f"{name}_{window_months}M"


def validate_identifier(value: str) -> str:
    """Return the value if it is a plain SQL identifier, otherwise raise.

    Column names reach SQL text. They come from configs/features.yml, which is trusted,
    but a typo there should fail here with the offending name rather than as a parser
    error somewhere inside a large statement.

    Raises:
        ValueError: If the value is not letters, digits and underscores.
    """
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{value!r} is not a plain SQL identifier")
    return value


def window_threshold(time_column: str, window_months: int) -> int:
    """Return how many units of the time column a window of N months spans.

    Args:
        time_column: MONTHS_* counts months, DAYS_* counts days.
        window_months: Window length in months.

    Raises:
        ValueError: If the column is neither a months nor a days column. Guessing the
            unit would silently produce a window thirty times too wide or too narrow.
    """
    if time_column.startswith(MONTHS_COLUMN_PREFIX):
        return window_months
    if time_column.startswith(DAYS_COLUMN_PREFIX):
        return window_months * DAYS_PER_MONTH
    raise ValueError(f"Cannot tell the unit of {time_column!r}; expected MONTHS_ or DAYS_")


def window_filter(time_column: str, window_months: int) -> str:
    """Return the predicate keeping rows inside the last N months.

    Offsets are negative, so the last three months of a DAYS_ column is >= -90.
    """
    validate_identifier(time_column)
    return f"{time_column} >= {-window_threshold(time_column, window_months)}"


def aggregate_sql(function: str, expression: str, filter_predicate: str | None) -> str:
    """Return one SQL aggregate over an expression, optionally restricted to a window.

    COUNT runs over the raw expression so a LEFT JOIN with no match yields zero rather
    than one. Every other function casts to DOUBLE, which also turns boolean columns into
    0 and 1 so they can be summed and averaged.

    Raises:
        KeyError: If the function is not one of the declared aggregation functions.
    """
    sql_function = SQL_FUNCTIONS[function]
    body = (
        f"{sql_function}({expression})"
        if function == COUNT_FUNCTION
        else f"{sql_function}(CAST(({expression}) AS {NUMERIC_TYPE}))"
    )
    return body if filter_predicate is None else f"{body} FILTER (WHERE {filter_predicate})"


def validate_derived_expression(name: str, expression: str) -> None:
    """Assert a derived expression divides only through NULLIF.

    Division by zero yields infinity, and the step 6 gate stops the pipeline on any
    infinite value, so the guard has to be where the division is written.

    Raises:
        ValueError: If the expression divides without a NULLIF guard.
    """
    if "/" in expression and GUARDED_DIVISION not in expression:
        raise ValueError(f"Derived column {name} divides without a NULLIF guard: {expression}")


def own_columns(
    source: str,
    entry: Mapping[str, Any],
    feature_spec: FeatureSpec,
    stage: int,
) -> Iterator[FeatureColumn]:
    """Yield the columns aggregated directly from one source table.

    Whole-history aggregates come first for every declared column and function. Windowed
    aggregates follow for each window, restricted to the functions allowed inside a
    window and skipping the time column itself, whose extremes inside a window say
    nothing. Trends are whole-history only.

    Args:
        source: Logical table name.
        entry: That source's entry in configs/features.yml.
        feature_spec: The parsed feature declaration.
        stage: STAGE_ONE or STAGE_TWO, recorded in the provenance.
    """
    prefix = entry["prefix"]
    derived: Mapping[str, str] = entry.get("derived", {})
    time_column: str | None = entry.get("time_column")
    windows = feature_spec.windows_months if entry.get("windowed") else ()

    for name, expression in derived.items():
        validate_derived_expression(name, expression)

    for column, functions in entry["aggregations"].items():
        validate_identifier(column)
        value = derived.get(column, column)
        for function in functions:
            yield _column(source, prefix, column, value, function, None, None, stage)
        if time_column is None or column == time_column:
            continue
        for window in windows:
            predicate = window_filter(time_column, window)
            for function in functions:
                if function in feature_spec.windowed_aggregations:
                    yield _column(source, prefix, column, value, function, window, predicate, stage)

    for column, trend in entry.get("trends", {}).items():
        yield _trend_column(source, entry, column, trend, derived, stage)


def _column(
    source: str,
    prefix: str,
    column: str,
    value: str,
    function: str,
    window: int | None,
    predicate: str | None,
    stage: int,
) -> FeatureColumn:
    base_name = feature_column_name(prefix, column, function, None)
    provenance = ColumnProvenance(
        name=feature_column_name(prefix, column, function, window),
        source_table=source,
        source_column=value,
        aggregation=function,
        window_months=window,
        stage=stage,
    )
    return FeatureColumn(base_name, aggregate_sql(function, value, predicate), provenance)


def _trend_column(
    source: str,
    entry: Mapping[str, Any],
    column: str,
    trend: str,
    derived: Mapping[str, str],
    stage: int,
) -> FeatureColumn:
    if trend != TREND_FUNCTION:
        raise ValueError(f"{source}.trends.{column} must be {TREND_FUNCTION}, got {trend!r}")
    time_column = validate_identifier(entry["time_column"])
    value = derived.get(column, column)
    name = feature_column_name(entry["prefix"], column, TREND_SUFFIX, None)
    provenance = ColumnProvenance(name, source, value, TREND_FUNCTION, None, stage)
    dependent = f"CAST(({value}) AS {NUMERIC_TYPE})"
    independent = f"CAST({time_column} AS {NUMERIC_TYPE})"
    expression = f"{TREND_FUNCTION}({dependent}, {independent})"
    return FeatureColumn(name, expression, provenance)


def stage_one_columns(source: str, feature_spec: FeatureSpec) -> tuple[FeatureColumn, ...]:
    """Return the columns of a third-level table folded to its second-level grain."""
    return tuple(own_columns(source, feature_spec.sources[source], feature_spec, STAGE_ONE))


def stage_one_children(feature_spec: FeatureSpec, parent: str) -> tuple[str, ...]:
    """Return the stage one sources that fold into a second-level table.

    The declaration points the two ways. bureau names its child through join_from, while
    the three monthly and event tables name their parent through join_from. Both
    directions are resolved here so no caller has to know which table uses which.
    """
    sources = feature_spec.sources
    declared = sources[parent].get("join_from")
    named_child = (declared,) if declared and sources[declared]["stage"] == FIRST_STAGE else ()
    siblings = tuple(
        name
        for name, entry in sources.items()
        if entry.get("join_from") == parent and entry["stage"] == FIRST_STAGE
    )
    return (*named_child, *siblings)


def rolled_up_columns(
    child: str,
    parent_prefix: str,
    feature_spec: FeatureSpec,
    child_columns: tuple[FeatureColumn, ...],
) -> Iterator[FeatureColumn]:
    """Yield the columns that fold a stage one relation up to customer grain.

    Whole-history stage one columns take the rollup functions and windowed ones take the
    windowed rollup functions. The double fold stays visible in the name, as in
    BURO_BB_STATUS_IS_DPD_MEAN_MEAN, rather than collapsing to one MEAN that hides a
    step. A table that rolls straight to the customer keeps its own prefix; one that
    rolls through its parent, such as bureau_balance, takes the parent's prefix and keeps
    its own as part of the column.
    """
    entry = feature_spec.sources[child]
    own_prefix = entry["prefix"]
    rolls_to_customer = "roll_up_to" in entry
    final_prefix = own_prefix if rolls_to_customer else parent_prefix

    for column in child_columns:
        window = column.provenance.window_months
        functions = (
            feature_spec.windowed_rollup_aggregations
            if window
            else feature_spec.rollup_aggregations
        )
        source_column = (
            column.base_name.removeprefix(f"{own_prefix}_")
            if rolls_to_customer
            else column.base_name
        )
        for function in functions:
            name = feature_column_name(final_prefix, source_column, function, window)
            provenance = ColumnProvenance(name, child, column.name, function, window, STAGE_TWO)
            yield FeatureColumn(
                base_name=feature_column_name(final_prefix, source_column, function, None),
                expression=aggregate_sql(function, column.name, None),
                provenance=provenance,
            )


def stage_two_columns(
    parent: str,
    feature_spec: FeatureSpec,
    stage_one_by_child: Mapping[str, tuple[FeatureColumn, ...]],
) -> tuple[FeatureColumn, ...]:
    """Return every customer-grain column of bureau or previous_application.

    Args:
        parent: The second-level table.
        feature_spec: The parsed feature declaration.
        stage_one_by_child: Each child source's stage one columns.
    """
    entry = feature_spec.sources[parent]
    columns = list(own_columns(parent, entry, feature_spec, STAGE_TWO))
    for child in stage_one_children(feature_spec, parent):
        columns.extend(
            rolled_up_columns(child, entry["prefix"], feature_spec, stage_one_by_child[child])
        )
    names = [column.name for column in columns]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        raise ValueError(f"{parent} generates duplicate columns: {', '.join(duplicated)}")
    return tuple(columns)
