"""Step 5: fold 58 million history rows down to 307511 customer rows.

All aggregation is SQL on DuckDB. The 27.3 million row bureau_balance exceeds
available memory as a DataFrame, and a chain of nested groupby().agg() calls is
harder to review than a named CTE. DuckDB reads Parquet column-wise and spills to
disk when needed, so this step does not depend on available RAM.

Four of the six history tables sit at the third relational level and must be
folded twice: first to the second-level grain, then to customer grain. Every join
is a LEFT JOIN from the parent table, because only about 48 percent of bureau
loans have monthly rows and about 1700 customers have no bureau record at all.
An INNER JOIN would discard more than half the available history.

The column list times aggregation list comes from configs/features.yml. This
module generates SQL from that declaration and never loops over every column: std
over a binary flag produces a column that carries nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb


logger = logging.getLogger(__name__)

EXPECTED_CUSTOMER_ROWS: Final = 307511
FEATURE_VERSION: Final = "v1"

AGGREGATION_FUNCTIONS: Final = ("count", "sum", "mean", "max", "min", "std")
TREND_FUNCTION: Final = "regr_slope"


class AggregationError(Exception):
    """Raised when a generated query produces the wrong shape.

    Most often a row count other than the application count, which means a join
    fanned out and some customer now has more than one row.
    """


@dataclass(frozen=True)
class ColumnProvenance:
    """How one feature column was produced.

    Recorded in the manifest so a column such as BURO_AMT_CREDIT_SUM_MEAN can be
    traced back to its source table, source column and aggregation. Without this,
    a reviewer reading a SHAP plot cannot tell what a column means.

    Attributes:
        name: Output column name.
        source_table: History table it came from.
        source_column: Column aggregated, or the derived expression.
        aggregation: Function applied, or "ratio" or "regr_slope".
        window_months: Window in months, or None for whole history.
        stage: 1 for the intermediate fold, 2 for the fold to customer grain.
    """

    name: str
    source_table: str
    source_column: str
    aggregation: str
    window_months: int | None
    stage: int


def feature_column_name(
    prefix: str,
    source_column: str,
    aggregation: str,
    window_months: int | None,
) -> str:
    """Build a feature column name from its parts.

    The naming contract is PREFIX_COLUMN_AGG for whole-history features and
    PREFIX_COLUMN_AGG_NM for windowed ones. Generating every name through this one
    function is what keeps 500 to 800 columns consistent.

    Args:
        prefix: Source prefix, one of APP, BURO, BB, PREV, POS, INST, CC.
        source_column: Column or derived expression name.
        aggregation: Aggregation function applied.
        window_months: Window in months, or None.

    Returns:
        The upper-case column name.

    TODO:
        - Join the parts with underscores and upper-case the result.
        - Append the window as f"_{window_months}M" when a window is given.
        - Raise on a prefix outside the fixed set. A new prefix invented at a call
          site would break every convention the manifest relies on.
    """
    raise NotImplementedError


def render_aggregation_sql(
    source: str,
    spec: dict[str, object],
    windows: tuple[int, ...],
) -> str:
    """Render the SQL for one source from its declaration.

    Args:
        source: Logical source table name.
        spec: That source's entry in configs/features.yml.
        windows: Window lengths in months.

    Returns:
        A complete SQL statement.

    TODO:
        - Read the statement skeleton from the matching file in features/sql and
          substitute the generated aggregation expressions into it. Keep the join
          structure in the .sql file where it is reviewable, and generate only the
          repetitive select list here.
        - Generate one expression per declared column and function pair, plus one
          per window where the source declares windowed true.
        - Express a window as a filter on the source's declared time column, since
          the offsets are negative: the last three months is time_column greater
          than or equal to -3 for MONTHS_BALANCE, or -90 for a DAYS_ column.
          Convert correctly per column; mixing the two units silently produces a
          window 30 times too wide.
        - Emit count over the key, not count(*), so a LEFT JOIN with no match
          yields zero rather than one.
        - Guard every division against a zero denominator with a conditional that
          yields null, never infinity. The step 6 gate stops on infinite values.
        - Quote identifiers exactly as the source spells them. The Kaggle casing
          is the contract.
        - Never interpolate a value that came from outside configs/features.yml
          into the statement. The config is trusted input; a runtime string is
          not.
    """
    raise NotImplementedError


def fold_stage_one(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    spec: dict[str, object],
) -> str:
    """Fold a third-level table to its second-level grain.

    bureau_balance folds to SK_ID_BUREAU; pos_cash_balance, installments_payments
    and credit_card_balance fold to SK_ID_PREV.

    Args:
        connection: Open DuckDB connection.
        source: Source table name.
        spec: Its feature declaration.

    Returns:
        Name of the temporary relation holding the folded result.

    TODO:
        - Register the result as a temporary view rather than materialising it to
          disk, so stage two reads it without a round trip.
        - Keep the grouping key in the output. Stage two joins on it.
        - Log the input and output row counts, so the fold ratio is visible: 27.3
          million bureau_balance rows should collapse to roughly 1.7 million.
    """
    raise NotImplementedError


def fold_stage_two(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    spec: dict[str, object],
    stage_one_relation: str | None,
) -> str:
    """Fold a second-level table to customer grain, joining stage one first.

    Args:
        connection: Open DuckDB connection.
        source: Parent table name, bureau or previous_application.
        spec: Its feature declaration.
        stage_one_relation: Relation from fold_stage_one, or None when the parent
            has no third-level child to attach.

    Returns:
        Name of the relation at customer grain.

    TODO:
        - LEFT JOIN from the parent table onto the stage one relation, never the
          other way round. Joining from the child discards parents with no child
          rows, which is more than half of bureau.
        - Aggregate the already-aggregated stage one columns again, taking mean
          and max of a per-loan mean. Name them so the double fold is visible in
          the column name, as in BURO_BB_STATUS_IS_DPD_MEAN_MEAN, rather than
          collapsing to one MEAN that hides a step.
        - Assert the output has at most one row per SK_ID_CURR before returning.
          A fan-out here is the defect the step 5 gate exists to catch, and
          catching it at the source names the responsible join.
    """
    raise NotImplementedError


def assemble_matrix(
    connection: duckdb.DuckDBPyConnection,
    relations: dict[str, str],
    configuration: str,
) -> Path:
    """LEFT JOIN every folded source onto the application table.

    Args:
        connection: Open DuckDB connection.
        relations: Source name to its customer-grain relation.
        configuration: Either "full" or "no_ext_source".

    Returns:
        The Parquet file written.

    TODO:
        - Start from the silver application table and LEFT JOIN each relation on
          SK_ID_CURR, so every application survives regardless of history.
        - Keep nulls. Do not coalesce to zero anywhere in this statement. A null
          means the customer has no such history and LightGBM learns the missing
          branch; a zero would claim they borrowed nothing, erasing the
          distinction between a thin file and a clean one.
        - Drop the EXT_SOURCE columns and their missingness flags for the
          no_ext_source configuration, per the exclusion list in the config.
        - Assert the result has exactly EXPECTED_CUSTOMER_ROWS rows and raise
          AggregationError naming the join that fanned out otherwise. This is the
          step 5 gate.
        - Write to a new Parquet file; never overwrite an input.
    """
    raise NotImplementedError


def write_manifest(
    destination: Path,
    provenance: tuple[ColumnProvenance, ...],
    source_hashes: dict[str, str],
) -> Path:
    """Write the manifest recording how every column was produced.

    A matrix without a manifest is unauditable: a column name alone does not say
    which table, which column or which window produced it, and six months later
    neither does memory.

    Args:
        destination: Manifest path, the .manifest.json sibling of the matrix.
        provenance: One entry per output column.
        source_hashes: Silver table name to a content hash.

    Returns:
        The destination path.

    TODO:
        - Record the column list, the provenance of each column, the source
          hashes, the feature config version and the generating code version.
        - Hash the silver Parquet files by content, not by modification time. The
          point is to detect that the inputs changed, and a touch changes the
          time without changing the data.
        - Write deterministically: sorted keys, stable field order. Two runs on
          identical inputs must produce an identical manifest, which is what the
          reproducibility acceptance criterion checks.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> Path:
    """Build one feature matrix and its manifest.

    Args:
        configuration: Either "full" or "no_ext_source".

    Returns:
        The matrix path.

    Raises:
        FileNotFoundError: If the holdout identifier list does not exist.
        AggregationError: If any join changed the row count.

    TODO:
        - Assert the holdout file exists before doing any work, and raise naming
          step 4 if it does not. This is the ordering guard: aggregating before
          the split is the primary leakage source in this project, and the check
          is one line.
        - Do not filter the matrix to the training identifiers. Both sets are
          built here so the holdout can be scored later; the separation is
          enforced by which rows the trainer reads, and the aggregation itself is
          per customer so it carries no cross-customer information.
        - Fold stage one for the four third-level tables, then stage two for
          bureau and previous_application, then assemble.
        - Use one DuckDB connection in a context manager for the whole run. Do not
          hold it in a module global.
        - Set a memory limit and a temp directory on the connection, so a spill
          lands somewhere known rather than filling the system temp volume.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.features.build`.

    TODO:
        - Build both configurations, full and no_ext_source, since the second is
          what the business analysis reads.
        - Configure logging, exit non-zero on failure.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
