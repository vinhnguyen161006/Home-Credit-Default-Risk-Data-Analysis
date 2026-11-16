"""Step 5: fold 58 million history rows down to 307511 customer rows.

All aggregation is SQL on DuckDB. The 27.3 million row bureau_balance exceeds
available memory as a DataFrame, and a chain of nested groupby().agg() calls is
harder to review than a named CTE. DuckDB reads Parquet column-wise and spills to
disk when needed, so this step does not depend on available RAM.

Four of the six history tables sit at the third relational level and must be
folded twice: first to the second-level grain, then to customer grain. Every join
is a LEFT JOIN from the parent table, because only about 48 percent of bureau
loans have monthly rows and some customers have no bureau record at all. An INNER
JOIN would discard more than half the available history.

The column list times aggregation list comes from configs/features.yml. The
columns module turns that declaration into one SQL expression per column; this
module drops the expressions into the skeletons under features/sql and runs them.
The matrix carries no TARGET: labels reach the trainer through the loader, and the
holdout labels only through the one-time reader of step 4.

Reproducibility: the manifest is byte-identical across runs. The matrix is identical in
every integer and flag column, but DuckDB sums floats across threads in a varying order,
so aggregate columns can differ in the last bit (relative error near 3e-16). Single
threaded execution would remove that at a large cost in run time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import duckdb

from hcr.config import FeatureSpec, load_feature_spec
from hcr.features.columns import (
    ColumnProvenance,
    FeatureColumn,
    stage_one_columns,
    stage_two_columns,
)
from hcr.features.manifest import hash_file_content, write_manifest
from hcr.paths import (
    configs_dir,
    duckdb_temp_dir,
    features_path,
    holdout_ids_path,
    manifest_path,
    silver_path,
    sql_dir,
)
from hcr.split.make_holdout import load_holdout_ids

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import polars as pl


logger = logging.getLogger(__name__)

EXPECTED_CUSTOMER_ROWS: Final = 307511
FEATURE_VERSION: Final = "v1"
FEATURE_CONFIG_FILENAME: Final = "features.yml"
CONFIGURATIONS: Final = ("full", "no_ext_source")
DUCKDB_MEMORY_LIMIT: Final = "10GB"

APPLICATION_TABLE: Final = "application_train"
FLAGS_TABLE: Final = "history_presence_flags"
RATIOS_RELATION: Final = "application_ratios"
CUSTOMER_KEY: Final = "SK_ID_CURR"
LABEL_COLUMN: Final = "TARGET"
SILVER_TABLES: Final = (
    APPLICATION_TABLE,
    "bureau",
    "bureau_balance",
    "previous_application",
    "pos_cash_balance",
    "installments_payments",
    "credit_card_balance",
    FLAGS_TABLE,
)
APPLICATION_RATIOS_FILENAME: Final = "application_ratios.sql"
SELECT_LIST_PLACEHOLDER: Final = "{select_list}"
SQL_FILENAMES: Final = {
    "bureau_balance": "bureau_balance_agg.sql",
    "pos_cash_balance": "pos_cash_agg.sql",
    "installments_payments": "installments_agg.sql",
    "credit_card_balance": "credit_card_agg.sql",
    "bureau": "bureau_agg.sql",
    "previous_application": "previous_agg.sql",
}
FIRST_STAGE: Final = 1
SECOND_STAGE: Final = 2
PASSTHROUGH: Final = "passthrough"
RATIO: Final = "ratio"
FLAG: Final = "flag"
RATIO_PREFIX: Final = "APP_"
PASSTHROUGH_STAGE: Final = 0
TEMP_SUFFIX: Final = ".tmp"


class AggregationError(Exception):
    """Raised when a generated query produces the wrong shape.

    Most often a row count other than the application count, which means a join
    fanned out and some customer now has more than one row.
    """


@dataclass(frozen=True)
class BuildLayout:
    """Where one build reads and writes.

    Attributes:
        silver: Silver table name to its Parquet file.
        matrices: Configuration to the matrix file written for it.
        manifests: Configuration to the manifest written beside it.
        temp_dir: Directory DuckDB spills to.
        config_path: The feature declaration, hashed into the manifest.
    """

    silver: Mapping[str, Path]
    matrices: Mapping[str, Path]
    manifests: Mapping[str, Path]
    temp_dir: Path
    config_path: Path


@dataclass(frozen=True)
class StageOne:
    """A folded third-level table: its name and the columns it carries."""

    relation: str
    columns: tuple[FeatureColumn, ...]


@dataclass(frozen=True)
class StageTwo:
    """A customer-grain table: its name and the columns it carries."""

    relation: str
    columns: tuple[FeatureColumn, ...]


def default_layout(configurations: tuple[str, ...]) -> BuildLayout:
    """Return the real locations for the requested configurations."""
    return BuildLayout(
        silver={table: silver_path(table) for table in SILVER_TABLES},
        matrices={name: features_path(FEATURE_VERSION, name) for name in configurations},
        manifests={name: manifest_path(FEATURE_VERSION, name) for name in configurations},
        temp_dir=duckdb_temp_dir(),
        config_path=configs_dir() / FEATURE_CONFIG_FILENAME,
    )


def register_silver_tables(
    connection: duckdb.DuckDBPyConnection, silver: Mapping[str, Path]
) -> None:
    """Expose each silver Parquet file to SQL under its table name.

    The path goes to DuckDB as an argument and never into a SQL string, so no path can
    change the meaning of a statement.
    """
    for name, path in silver.items():
        connection.read_parquet(str(path)).create_view(name)


def compute_application_ratios(
    connection: duckdb.DuckDBPyConnection,
    silver_application: Path,
) -> pl.DataFrame:
    """Compute the six mandatory application ratios, one row per SK_ID_CURR.

    Takes the Parquet path rather than a frame, so DuckDB reads the file where it sits,
    as the other aggregation steps do. Denominators go through NULLIF, so a zero yields
    null and never infinity, which the step 6 gate would reject.

    Args:
        connection: DuckDB connection; the caller owns its lifetime.
        silver_application: Silver application Parquet, with DAYS_EMPLOYED already null
            where the sentinel applied.

    Returns:
        The SK_ID_CURR column and the six APP_ ratio columns.
    """
    query = (sql_dir() / APPLICATION_RATIOS_FILENAME).read_text(encoding="utf-8")
    return connection.execute(query, [str(silver_application)]).pl()


def render_aggregation_sql(source: str, columns: tuple[FeatureColumn, ...]) -> str:
    """Render the SQL for one source by filling its skeleton with the generated columns.

    The join structure stays in the .sql file where it is reviewable; only the repetitive
    select list is generated. Every expression came from configs/features.yml, which is
    trusted input. No runtime value is interpolated.

    Args:
        source: Logical source table name.
        columns: The columns to aggregate, from the columns module.

    Returns:
        A complete SQL statement.
    """
    template = (sql_dir() / SQL_FILENAMES[source]).read_text(encoding="utf-8")
    select_list = ",\n    ".join(f"{column.expression} AS {column.name}" for column in columns)
    return template.replace(SELECT_LIST_PLACEHOLDER, select_list)


def fold_stage_one(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    feature_spec: FeatureSpec,
) -> StageOne:
    """Fold a third-level table to its second-level grain.

    bureau_balance folds to SK_ID_BUREAU; pos_cash_balance, installments_payments and
    credit_card_balance fold to SK_ID_PREV. The result is materialised, one source at a
    time. As a view, stage two would run all three monthly aggregations inside one join and
    hold their hash tables together, which ran out of memory on the real tables.

    Args:
        connection: Open DuckDB connection with the silver tables registered.
        source: Source table name.
        feature_spec: The parsed feature declaration.

    Returns:
        The table name and its columns.
    """
    columns = stage_one_columns(source, feature_spec)
    relation = f"{source}_stage_one"
    connection.execute(
        f"CREATE OR REPLACE TEMP TABLE {relation} AS {render_aggregation_sql(source, columns)}"
    )
    input_rows = _scalar(connection, f"SELECT COUNT(*) FROM {source}")
    logger.info("Folded %s input rows into %s", input_rows, relation)
    return StageOne(relation, columns)


def fold_stage_two(
    connection: duckdb.DuckDBPyConnection,
    parent: str,
    feature_spec: FeatureSpec,
    stage_ones: Mapping[str, StageOne],
) -> StageTwo:
    """Fold a second-level table to customer grain, joining its stage one views first.

    The skeleton LEFT JOINs from the parent onto each stage one view, never the other
    way round. The result is materialised: it is small, and both configurations reuse it
    without folding 58 million rows again.

    Args:
        connection: Open DuckDB connection.
        parent: bureau or previous_application.
        feature_spec: The parsed feature declaration.
        stage_ones: The folded third-level tables, by source name.

    Returns:
        The table name and its columns.

    Raises:
        AggregationError: If the result has more than one row for any customer.
    """
    columns = stage_two_columns(
        parent, feature_spec, {name: stage.columns for name, stage in stage_ones.items()}
    )
    relation = f"{parent}_customer"
    connection.execute(
        f"CREATE OR REPLACE TEMP TABLE {relation} AS {render_aggregation_sql(parent, columns)}"
    )
    rows = _scalar(connection, f"SELECT COUNT(*) FROM {relation}")
    customers = _scalar(connection, f"SELECT COUNT(DISTINCT {CUSTOMER_KEY}) FROM {relation}")
    if rows != customers:
        raise AggregationError(
            f"The {parent} fold produced {rows} rows for {customers} customers; a join fanned out"
        )
    logger.info("Folded %s to %s customers with %s columns", parent, rows, len(columns))
    return StageTwo(relation, columns)


def assemble_matrix(
    connection: duckdb.DuckDBPyConnection,
    configuration: str,
    feature_spec: FeatureSpec,
    stage_twos: tuple[StageTwo, ...],
    destination: Path,
    expected_rows: int,
) -> tuple[ColumnProvenance, ...]:
    """LEFT JOIN every folded source onto the application table and write the matrix.

    Starts from the silver application table so every application survives whatever its
    history. Nulls stay nulls: nothing here is coalesced to zero, because a null means
    the customer has no such history and LightGBM learns the missing branch, while a zero
    would claim they borrowed nothing. TARGET is left out. The no_ext_source
    configuration drops the EXT_SOURCE columns and their missingness flags.

    Args:
        connection: Open DuckDB connection with the silver tables, the ratios relation
            and the stage two tables in place.
        configuration: Either "full" or "no_ext_source".
        feature_spec: The parsed feature declaration.
        stage_twos: The customer-grain tables to join.
        destination: The Parquet file to write.
        expected_rows: The row count the matrix must have.

    Returns:
        The provenance of every column, in matrix order.

    Raises:
        AggregationError: If the matrix does not have exactly one row per application, or
            if a relation's columns disagree with the generated column list.
    """
    excluded = {
        LABEL_COLUMN,
        *feature_spec.configurations[configuration].get("excluded_columns", ()),
    }
    selections = _passthrough_selections(connection, feature_spec, excluded)
    joins = [
        f"LEFT JOIN {RATIOS_RELATION} AS r ON a.{CUSTOMER_KEY} = r.{CUSTOMER_KEY}",
        f"LEFT JOIN {FLAGS_TABLE} AS f ON a.{CUSTOMER_KEY} = f.{CUSTOMER_KEY}",
    ]
    for index, stage in enumerate(stage_twos):
        alias = f"s{index}"
        joins.append(
            f"LEFT JOIN {stage.relation} AS {alias} ON a.{CUSTOMER_KEY} = {alias}.{CUSTOMER_KEY}"
        )
        selections.extend(_stage_selections(connection, stage, alias))

    names = [provenance.name for _, _, provenance in selections]
    if len(set(names)) != len(names):
        duplicated = sorted({name for name in names if names.count(name) > 1})
        raise AggregationError(f"The matrix would repeat columns: {', '.join(duplicated)}")

    select_list = ",\n    ".join(f"{alias}.{_quote(column)}" for alias, column, _ in selections)
    query = (
        f"SELECT\n    {select_list}\nFROM {APPLICATION_TABLE} AS a\n"
        + "\n".join(joins)
        + f"\nORDER BY a.{CUSTOMER_KEY}"
    )
    _write_checked(connection, query, destination, expected_rows)
    return tuple(provenance for _, _, provenance in selections)


def build_features(
    layout: BuildLayout,
    feature_spec: FeatureSpec,
    configurations: tuple[str, ...],
    expected_rows: int,
) -> tuple[Path, ...]:
    """Fold the history once and write one matrix and manifest per configuration.

    Args:
        layout: Where to read and write.
        feature_spec: The parsed feature declaration.
        configurations: Which matrices to assemble.
        expected_rows: The application count every matrix must match.

    Returns:
        The matrix paths, in the order of the configurations.
    """
    layout.temp_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = {name: hash_file_content(path) for name, path in layout.silver.items()}
    config_hash = hash_file_content(layout.config_path)
    settings = {"memory_limit": DUCKDB_MEMORY_LIMIT, "temp_directory": str(layout.temp_dir)}

    with duckdb.connect(":memory:", config=settings) as connection:
        register_silver_tables(connection, layout.silver)
        ratios = compute_application_ratios(connection, layout.silver[APPLICATION_TABLE])
        connection.register(RATIOS_RELATION, ratios)

        stage_ones = {
            source: fold_stage_one(connection, source, feature_spec)
            for source, entry in feature_spec.sources.items()
            if entry["stage"] == FIRST_STAGE
        }
        stage_twos = tuple(
            fold_stage_two(connection, parent, feature_spec, stage_ones)
            for parent, entry in feature_spec.sources.items()
            if entry["stage"] == SECOND_STAGE
        )

        written: list[Path] = []
        for configuration in configurations:
            destination = layout.matrices[configuration]
            provenance = assemble_matrix(
                connection, configuration, feature_spec, stage_twos, destination, expected_rows
            )
            write_manifest(
                layout.manifests[configuration],
                provenance,
                source_hashes,
                FEATURE_VERSION,
                config_hash,
            )
            logger.info("Wrote %s with %s columns", destination, len(provenance))
            written.append(destination)
    return tuple(written)


def run(configurations: tuple[str, ...] = CONFIGURATIONS) -> tuple[Path, ...]:
    """Build the feature matrices and their manifests.

    Checks that the holdout split exists before any work. Aggregating before the split
    is the primary leakage source in this project, and the check is one line.

    Args:
        configurations: Any of "full" and "no_ext_source".

    Returns:
        The matrix paths.

    Raises:
        FileNotFoundError: If the holdout identifier list does not exist.
        AggregationError: If any join changed the row count.
    """
    load_holdout_ids(holdout_ids_path())
    return build_features(
        default_layout(configurations), load_feature_spec(), configurations, EXPECTED_CUSTOMER_ROWS
    )


def main() -> None:
    """Entry point for `python -m hcr.features.build`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run()
    except (AggregationError, FileNotFoundError) as error:
        logger.exception("Feature build failed")
        raise SystemExit(1) from error


def _passthrough_selections(
    connection: duckdb.DuckDBPyConnection, feature_spec: FeatureSpec, excluded: set[str]
) -> list[tuple[str, str, ColumnProvenance]]:
    selections: list[tuple[str, str, ColumnProvenance]] = []
    for column in _columns_of(connection, APPLICATION_TABLE):
        if column not in excluded:
            provenance = ColumnProvenance(
                column, APPLICATION_TABLE, column, PASSTHROUGH, None, PASSTHROUGH_STAGE
            )
            selections.append(("a", column, provenance))

    ratio_expressions = {
        f"{RATIO_PREFIX}{name}": expression
        for name, expression in feature_spec.application_ratios.items()
    }
    ratio_columns = [c for c in _columns_of(connection, RATIOS_RELATION) if c != CUSTOMER_KEY]
    if set(ratio_columns) != set(ratio_expressions):
        raise AggregationError(
            f"The ratios query returned {sorted(ratio_columns)}, "
            f"features.yml declares {sorted(ratio_expressions)}"
        )
    for column in ratio_columns:
        provenance = ColumnProvenance(
            column, APPLICATION_TABLE, ratio_expressions[column], RATIO, None, PASSTHROUGH_STAGE
        )
        selections.append(("r", column, provenance))

    for column in _columns_of(connection, FLAGS_TABLE):
        if column != CUSTOMER_KEY and column not in excluded:
            provenance = ColumnProvenance(
                column, FLAGS_TABLE, column, FLAG, None, PASSTHROUGH_STAGE
            )
            selections.append(("f", column, provenance))
    return selections


def _stage_selections(
    connection: duckdb.DuckDBPyConnection, stage: StageTwo, alias: str
) -> list[tuple[str, str, ColumnProvenance]]:
    generated = {column.name: column.provenance for column in stage.columns}
    actual = [c for c in _columns_of(connection, stage.relation) if c != CUSTOMER_KEY]
    if set(actual) != set(generated):
        raise AggregationError(
            f"{stage.relation} columns disagree with the generated list: "
            f"{sorted(set(actual) ^ set(generated))}"
        )
    return [(alias, column, generated[column]) for column in actual]


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise AggregationError(f"{query} returned no row")
    return int(row[0])


def _columns_of(connection: duckdb.DuckDBPyConnection, relation: str) -> list[str]:
    return [row[0] for row in connection.execute(f"DESCRIBE {relation}").fetchall()]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _write_checked(
    connection: duckdb.DuckDBPyConnection, query: str, destination: Path, expected_rows: int
) -> None:
    """Write a query to Parquet, check its shape, and only then move it into place.

    The path comes from hcr.paths, not from user input, and is quote-escaped because COPY
    does not accept it as a parameter. Writing to a sibling first means a failed check
    leaves no half-valid matrix where a later step would read it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(destination.name + TEMP_SUFFIX)
    literal = str(pending).replace("'", "''")
    connection.execute(f"COPY ({query}) TO '{literal}' (FORMAT PARQUET)")
    shape = (
        connection.read_parquet(str(pending))
        .aggregate(f"COUNT(*), COUNT(DISTINCT {CUSTOMER_KEY})")
        .fetchone()
    )
    if shape is None or shape[0] != expected_rows or shape[1] != expected_rows:
        pending.unlink()
        raise AggregationError(
            f"Matrix has {shape} (rows, distinct customers), expected {expected_rows} of each; "
            "a join fanned out or dropped customers"
        )
    pending.replace(destination)


if __name__ == "__main__":
    main()
