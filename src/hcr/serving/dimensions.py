"""Build deterministic serving dimensions from the application source."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import duckdb
import polars as pl

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

UNKNOWN_LABEL: Final = "Unknown"
UNKNOWN_KEY: Final = -1

AGE_BANDS: Final = ("<25", "25-34", "35-44", "45-54", "55-64", "65+")
INCOME_BANDS: Final = ("<50K", "50K-<100K", "100K-<150K", "150K-<250K", "250K+")
EDUCATION_ORDER: Final = (
    "Lower secondary",
    "Secondary / secondary special",
    "Incomplete higher",
    "Higher education",
    "Academic degree",
)


@dataclass(frozen=True)
class DimensionSpec:
    """Source and ordering rules for one application dimension."""

    table: str
    key: str
    value: str
    expected_rows: int
    ordered_values: tuple[str, ...] | None = None


DIMENSION_SPECS: Final = (
    DimensionSpec("Dim_Occupation", "OccupationKey", "OCCUPATION_TYPE", 19),
    DimensionSpec("Dim_Organization", "OrgKey", "ORGANIZATION_TYPE", 59),
    DimensionSpec("Dim_Education", "EducationKey", "NAME_EDUCATION_TYPE", 6, EDUCATION_ORDER),
    DimensionSpec("Dim_ContractType", "ContractKey", "NAME_CONTRACT_TYPE", 3),
    DimensionSpec("Dim_HousingType", "HousingKey", "NAME_HOUSING_TYPE", 7),
    DimensionSpec("Dim_FamilyStatus", "FamilyKey", "NAME_FAMILY_STATUS", 7),
    DimensionSpec("Dim_AgeBand", "AgeBandKey", "AGE_BAND", 7, AGE_BANDS),
    DimensionSpec("Dim_IncomeBand", "IncomeBandKey", "INCOME_BAND", 6, INCOME_BANDS),
    DimensionSpec("Dim_RiskBand", "RiskBandKey", "RISK_BAND", 1, ()),
)


def build_dimension_frame(
    values: Sequence[str],
    key_column: str,
    value_column: str,
    ordered_values: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Assign stable integer keys and include one unknown member."""
    observed_values = {value for value in values if value and value != UNKNOWN_LABEL}
    if ordered_values is None:
        sorted_values = sorted(observed_values)
    else:
        unexpected = observed_values.difference(ordered_values)
        if unexpected:
            raise ValueError(f"Unexpected values in {value_column}: {sorted(unexpected)}")
        sorted_values = [value for value in ordered_values if value in observed_values]

    rows = [(UNKNOWN_KEY, UNKNOWN_LABEL, 0)]
    for index, value in enumerate(sorted_values, start=1):
        order = ordered_values.index(value) + 1 if ordered_values is not None else index
        rows.append((index, value, order))
    return pl.DataFrame(
        rows,
        schema={key_column: pl.Int32, value_column: pl.String, "SortOrder": pl.Int16},
        orient="row",
    )


def _source_values(connection: duckdb.DuckDBPyConnection, source_column: str) -> list[str]:
    result = connection.execute(
        f'SELECT DISTINCT "{source_column}" FROM source_application '
        f'WHERE "{source_column}" IS NOT NULL AND "{source_column}" <> ?',
        [UNKNOWN_LABEL],
    )
    return sorted(row[0] for row in result.fetchall())


def _write_dimension(
    connection: duckdb.DuckDBPyConnection,
    output_dir: Path,
    spec: DimensionSpec,
    values: Sequence[str],
) -> int:
    dimension = build_dimension_frame(
        values,
        spec.key,
        spec.value,
        spec.ordered_values,
    )
    if spec.ordered_values is None:
        dimension = dimension.drop("SortOrder")
    if len(dimension) != spec.expected_rows:
        logger.warning(
            "%s has %s rows; the specification expects %s",
            spec.table,
            len(dimension),
            spec.expected_rows,
        )

    table_view = spec.table.casefold()
    connection.register(table_view, dimension)
    destination = output_dir / f"{spec.table}.parquet"
    dimension.write_parquet(destination, compression="zstd")
    return len(dimension)


def build_application_dimensions(
    connection: duckdb.DuckDBPyConnection, output_dir: Path
) -> dict[str, int]:
    """Build and register all application category dimensions."""
    row_counts: dict[str, int] = {}
    for spec in DIMENSION_SPECS:
        if spec.table in {"Dim_AgeBand", "Dim_IncomeBand"}:
            values = list(spec.ordered_values or ())
        elif spec.table == "Dim_RiskBand":
            values = []
        else:
            values = _source_values(connection, spec.value)
        row_counts[spec.table] = _write_dimension(
            connection,
            output_dir,
            spec,
            values,
        )
    return row_counts
