"""Step 4: reserve a holdout set before any feature is computed.

This step runs before step 5, and that ordering is the one constraint in the
pipeline that must never be inverted. Aggregating history before splitting is the
primary leakage source in this project: statistics computed over all customers
carry information from the holdout into training, and the symptom is
cross-validated AUC exceeding holdout AUC by 0.02 to 0.05.

The identifier list is written to disk so the split is identical across runs.
Twenty percent gives 61502 applications and about 4964 positives, which by
Hanley-McNeil puts the standard error near 0.0040 at AUC 0.78, a 95 percent
interval roughly 0.016 wide. That is narrow enough to separate two models 0.01
AUC apart on evidence rather than noise.

The holdout keeps its independence only while it informs no decision. It is read
once, by evaluation.holdout_report, after every modelling choice is settled.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

from hcr.config import load_model_config
from hcr.paths import ensure_parent, holdout_ids_path, silver_path

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

APPLICATION_TABLE: Final = "application_train"
IDENTIFIER_COLUMN: Final = "SK_ID_CURR"
LABEL_COLUMN: Final = "TARGET"
VALID_LABELS: Final = (0, 1)
EXPECTED_TOTAL_APPLICATIONS: Final = 307511
EXPECTED_HOLDOUT_ROWS: Final = 61502
PERCENT: Final = 100
PREVIEW_COUNT: Final = 5


class SplitViolationError(Exception):
    """Raised when the split fails one of its gates.

    Either the two sets intersect, the union misses an application, or their
    positive rates differ by more than the tolerance. Each makes every later
    comparison meaningless.
    """


@dataclass(frozen=True)
class SplitReport:
    """Outcome of the holdout split.

    Attributes:
        train_rows: Applications reserved for cross-validation.
        holdout_rows: Applications reserved for final acceptance.
        train_positive_rate: Positive rate in the training set.
        holdout_positive_rate: Positive rate in the holdout.
        rate_difference_pp: Absolute difference in percentage points.
        seed: Seed that produced this split.
    """

    train_rows: int
    holdout_rows: int
    train_positive_rate: float
    holdout_positive_rate: float
    rate_difference_pp: float
    seed: int


def positive_rate(labels: pl.Series) -> float:
    """Return the share of positive labels as a fraction."""
    return float(labels.sum()) / len(labels)


def stratified_split(
    identifiers: pl.Series,
    labels: pl.Series,
    holdout_fraction: float,
    seed: int,
) -> tuple[pl.Series, pl.Series]:
    """Split identifiers into training and holdout, stratified on the label.

    Stratifying keeps the 8.07 percent positive rate in both sets. An unstratified
    split at this imbalance can drift the rate far enough to shift every reported
    metric. The holdout size is rounded to an exact row count so the figure the
    confidence interval was computed from is reproduced.

    Args:
        identifiers: All SK_ID_CURR values in application_train.
        labels: TARGET aligned positionally with identifiers.
        holdout_fraction: Share reserved for holdout, 0.20.
        seed: Seed fixing the split across runs.

    Returns:
        Training identifiers and holdout identifiers, each sorted, in that order.

    Raises:
        ValueError: If identifiers and labels differ in length, or if labels hold
            a value outside {0, 1}. A third value would create a third stratum and
            quietly shrink both sets.
    """
    if len(identifiers) != len(labels):
        raise ValueError(f"{len(identifiers)} identifiers but {len(labels)} labels")
    unexpected = set(labels.unique().to_list()) - set(VALID_LABELS)
    if unexpected:
        raise ValueError(f"{LABEL_COLUMN} holds values outside {{0, 1}}: {unexpected}")

    holdout_size = round(holdout_fraction * len(identifiers))
    positions = np.arange(len(identifiers))
    train_positions, holdout_positions = train_test_split(
        positions,
        test_size=holdout_size,
        stratify=labels.to_numpy(),
        random_state=seed,
    )
    return (
        identifiers.gather(np.sort(train_positions)).sort(),
        identifiers.gather(np.sort(holdout_positions)).sort(),
    )


def assert_disjoint(train_ids: pl.Series, holdout_ids: pl.Series) -> None:
    """Assert the two identifier sets share no member.

    An overlap means the holdout was partly trained on, which invalidates the final
    number entirely rather than slightly.

    Raises:
        SplitViolationError: If the intersection is non-empty, naming its size and
            a few offending identifiers.
    """
    shared = train_ids.filter(train_ids.is_in(holdout_ids))
    if len(shared) > 0:
        raise SplitViolationError(
            f"{len(shared)} identifiers appear in both sets, e.g. "
            f"{shared.head(PREVIEW_COUNT).to_list()}"
        )


def assert_covers_all(train_ids: pl.Series, holdout_ids: pl.Series, identifiers: pl.Series) -> None:
    """Assert the two sets together hold every application exactly once.

    Raises:
        SplitViolationError: If any application is missing or appears twice.
    """
    combined = pl.concat([train_ids, holdout_ids]).sort()
    if not combined.equals(identifiers.sort()):
        raise SplitViolationError(
            f"Split holds {len(combined)} identifiers for {len(identifiers)} applications"
        )


def assert_rate_parity(
    train_labels: pl.Series,
    holdout_labels: pl.Series,
    tolerance_pp: float,
) -> float:
    """Assert both sets carry the same positive rate within tolerance.

    The comparison is in percentage points, matching how the gate is specified, so a
    ratio-based check cannot pass by using different units.

    Args:
        train_labels: TARGET for the training identifiers.
        holdout_labels: TARGET for the holdout identifiers.
        tolerance_pp: Allowed difference in percentage points, 0.1.

    Returns:
        The observed absolute difference in percentage points.

    Raises:
        SplitViolationError: If the difference reaches the tolerance. The message
            gives both rates so the direction of the drift is visible.
    """
    train_rate = positive_rate(train_labels) * PERCENT
    holdout_rate = positive_rate(holdout_labels) * PERCENT
    difference = abs(train_rate - holdout_rate)
    if difference >= tolerance_pp:
        raise SplitViolationError(
            f"Positive rate drift: train {train_rate:.3f}% vs holdout {holdout_rate:.3f}%, "
            f"difference {difference:.3f} pp reaches tolerance {tolerance_pp} pp"
        )
    return difference


def write_holdout_ids(holdout_ids: pl.Series, destination: Path, force: bool = False) -> Path:
    """Write the holdout identifier list to Parquet, refusing to replace a different split.

    Rewriting identical content is a no-op, so rerunning the step is safe. Replacing a
    file with a different split would move customers between the sets and compromise a
    holdout that earlier runs already trained around, so that needs an explicit force.

    Args:
        holdout_ids: Identifiers to reserve.
        destination: File to write.
        force: Replace an existing, different split. Logged at WARNING when used.

    Returns:
        The destination path.

    Raises:
        FileExistsError: If a different split already exists and force is False.
    """
    frame = pl.DataFrame({IDENTIFIER_COLUMN: holdout_ids})
    if destination.exists():
        if pl.read_parquet(destination).equals(frame):
            return destination
        if not force:
            raise FileExistsError(
                f"{destination} holds a different split; pass force=True to replace it"
            )
        logger.warning("Replacing existing holdout split at %s", destination)
    frame.write_parquet(ensure_parent(destination))
    return destination


class HoldoutReadError(Exception):
    """Raised when the holdout labels are read again without an explicit, reasoned force."""


def read_usage_log(usage_path: Path) -> list[dict[str, Any]]:
    """Return every recorded holdout read, or an empty list before the first read.

    Raises:
        json.JSONDecodeError: If the log exists but cannot be parsed. Treated as already
            read: a corrupt log may still record an earlier read, so the guard fails closed.
    """
    if not usage_path.is_file():
        return []
    records: list[dict[str, Any]] = json.loads(usage_path.read_text(encoding="utf-8"))
    return records


def append_usage_record(usage_path: Path, record: dict[str, Any]) -> None:
    """Append one read to the log, keeping every earlier entry."""
    records = [*read_usage_log(usage_path), record]
    ensure_parent(usage_path).write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_holdout_labels(
    applications: pl.DataFrame,
    holdout_ids: pl.Series,
    usage_path: Path,
    force: bool = False,
    reason: str | None = None,
) -> pl.DataFrame:
    """Return TARGET for the holdout applications, logging every read.

    The first read needs no justification. Any later read raises unless force is set
    together with a reason, and that reason is written into the log so the exception
    stays on record. The read is appended only after its labels are returned.

    Args:
        applications: Silver application table with SK_ID_CURR and TARGET.
        holdout_ids: Holdout identifiers from load_holdout_ids.
        usage_path: Usage log, normally holdout_usage_path().
        force: Allow a read after the holdout was already read.
        reason: Required with force; why the holdout is being read again.

    Returns:
        SK_ID_CURR and TARGET for the holdout applications.

    Raises:
        HoldoutReadError: If the holdout was read before and force is not set, or force
            is set without a reason.
    """
    previous_reads = read_usage_log(usage_path)
    if previous_reads and not force:
        raise HoldoutReadError(
            f"Holdout labels were read {len(previous_reads)} time(s); pass force=True "
            "with a reason to read them again"
        )
    if force and not reason:
        raise HoldoutReadError("force=True requires a reason")

    labels = applications.filter(pl.col(IDENTIFIER_COLUMN).is_in(holdout_ids)).select(
        IDENTIFIER_COLUMN, LABEL_COLUMN
    )
    append_usage_record(
        usage_path,
        {
            "read_at": datetime.now(UTC).isoformat(),
            "rows": len(labels),
            "forced": force,
            "reason": reason,
        },
    )
    if force:
        logger.warning("Holdout labels read again, forced: %s", reason)
    return labels


def load_holdout_ids(source: Path) -> pl.Series:
    """Read the holdout identifier list.

    Raises:
        FileNotFoundError: If the split has not been made yet. Creating it here would
            let two runs each produce a different, "authoritative" split.
    """
    if not source.is_file():
        raise FileNotFoundError(f"{source} is missing; run `make split` (step 4) first")
    return pl.read_parquet(source).get_column(IDENTIFIER_COLUMN)


def run() -> SplitReport:
    """Split application_train and write the holdout identifier list.

    Gates run before anything is written, so an invalid split never reaches disk for
    the next step to consume.

    Returns:
        The split report.

    Raises:
        SplitViolationError: If the table size is wrong or any gate fails.
    """
    config = load_model_config()
    applications = pl.read_parquet(
        silver_path(APPLICATION_TABLE), columns=[IDENTIFIER_COLUMN, LABEL_COLUMN]
    )
    if len(applications) != EXPECTED_TOTAL_APPLICATIONS:
        raise SplitViolationError(
            f"{len(applications)} applications, expected {EXPECTED_TOTAL_APPLICATIONS}"
        )

    identifiers = applications.get_column(IDENTIFIER_COLUMN)
    labels = applications.get_column(LABEL_COLUMN)
    train_ids, holdout_ids = stratified_split(
        identifiers, labels, config.holdout_fraction, config.random_seed
    )
    assert_disjoint(train_ids, holdout_ids)
    assert_covers_all(train_ids, holdout_ids, identifiers)

    train_labels = applications.filter(pl.col(IDENTIFIER_COLUMN).is_in(train_ids))[LABEL_COLUMN]
    holdout_labels = applications.filter(pl.col(IDENTIFIER_COLUMN).is_in(holdout_ids))[LABEL_COLUMN]
    difference = assert_rate_parity(train_labels, holdout_labels, config.target_rate_tolerance_pp)

    write_holdout_ids(holdout_ids, holdout_ids_path())
    if len(holdout_ids) != EXPECTED_HOLDOUT_ROWS:
        logger.warning("Holdout has %s rows, expected %s", len(holdout_ids), EXPECTED_HOLDOUT_ROWS)

    report = SplitReport(
        train_rows=len(train_ids),
        holdout_rows=len(holdout_ids),
        train_positive_rate=positive_rate(train_labels),
        holdout_positive_rate=positive_rate(holdout_labels),
        rate_difference_pp=difference,
        seed=config.random_seed,
    )
    logger.info(
        "Split %s train rows and %s holdout rows with seed %s, rate difference %.4f pp",
        report.train_rows,
        report.holdout_rows,
        report.seed,
        report.rate_difference_pp,
    )
    return report


def main() -> None:
    """Entry point for `python -m hcr.split.make_holdout`."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run()
    except SplitViolationError:
        logger.exception("Holdout split rejected")
        sys.exit(1)


if __name__ == "__main__":
    main()
