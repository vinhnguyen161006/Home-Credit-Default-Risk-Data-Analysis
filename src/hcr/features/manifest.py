"""The manifest written beside every feature matrix.

A column name alone does not say which table, which column or which window produced it,
and six months later neither does memory. The manifest records that for every column,
plus a content hash of every silver input, so a changed input is detectable.

The output is deterministic: sorted keys, a fixed field order and no timestamp. Two runs
on identical inputs must produce the same bytes, which the reproducibility acceptance
criterion checks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hcr.features.columns import ColumnProvenance

HASH_CHUNK_BYTES: Final = 1 << 20
JSON_INDENT: Final = 2


def hash_file_content(path: Path) -> str:
    """Return the SHA-256 of a file's bytes, read in chunks.

    Content rather than modification time: the point is to detect that the inputs
    changed, and a touch changes the time without changing the data.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    destination: Path,
    provenance: tuple[ColumnProvenance, ...],
    source_hashes: Mapping[str, str],
    feature_version: str,
    config_hash: str,
) -> Path:
    """Write the manifest recording how every column was produced.

    Args:
        destination: Manifest path, the .manifest.json sibling of the matrix.
        provenance: One entry per output column, in matrix order.
        source_hashes: Silver table name to a content hash.
        feature_version: The generating code version.
        config_hash: SHA-256 of configs/features.yml.

    Returns:
        The destination path.
    """
    document = {
        "feature_version": feature_version,
        "feature_config_sha256": config_hash,
        "source_sha256": dict(source_hashes),
        "column_count": len(provenance),
        "columns": [asdict(entry) for entry in provenance],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=JSON_INDENT, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination
