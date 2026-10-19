"""Step 1 ingest. Bronze is the CSV in another format, with its content unchanged."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from hcr.ingest.to_parquet import convert_table

if TYPE_CHECKING:
    from pathlib import Path

CSV_TEXT = "SK_ID_CURR,AMT_CREDIT,EMERGENCYSTATE_MODE\n1,100.5,Yes\n2,200.0,No\n3,300.0,\n"


def test_yes_no_text_stays_text_instead_of_becoming_boolean(tmp_path: Path) -> None:
    source = tmp_path / "application.csv"
    source.write_text(CSV_TEXT, encoding="utf-8")
    destination = tmp_path / "application.parquet"

    convert_table(source, destination)

    frame = pl.read_parquet(destination)
    assert frame.schema["EMERGENCYSTATE_MODE"] == pl.String
    assert frame["EMERGENCYSTATE_MODE"].to_list() == ["Yes", "No", None]


def test_conversion_keeps_rows_column_names_and_numeric_types(tmp_path: Path) -> None:
    source = tmp_path / "application.csv"
    source.write_text(CSV_TEXT, encoding="utf-8")
    destination = tmp_path / "application.parquet"

    convert_table(source, destination)

    frame = pl.read_parquet(destination)
    assert frame.columns == ["SK_ID_CURR", "AMT_CREDIT", "EMERGENCYSTATE_MODE"]
    assert frame.height == CSV_TEXT.count("\n") - 1
    assert frame.schema["SK_ID_CURR"] == pl.Int64
    assert frame.schema["AMT_CREDIT"] == pl.Float64
