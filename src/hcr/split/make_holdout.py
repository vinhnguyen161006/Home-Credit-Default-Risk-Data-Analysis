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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    import polars as pl

logger = logging.getLogger(__name__)

EXPECTED_TOTAL_APPLICATIONS: Final = 307511
EXPECTED_HOLDOUT_ROWS: Final = 61502
EXPECTED_HOLDOUT_POSITIVES: Final = 4964
TARGET_RATE_TOLERANCE_PP: Final = 0.1


class SplitViolationError(Exception):
    """Raised when the split fails one of its two gates.

    Either the two sets intersect, or their positive rates differ by more than
    the tolerance. Both make every later comparison meaningless.
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


def stratified_split(
    identifiers: pl.Series,
    labels: pl.Series,
    holdout_fraction: float,
    seed: int,
) -> tuple[pl.Series, pl.Series]:
    """Split identifiers into training and holdout, stratified on the label.

    Args:
        identifiers: All SK_ID_CURR values in application_train.
        labels: TARGET aligned positionally with identifiers.
        holdout_fraction: Share reserved for holdout, 0.20.
        seed: Seed fixing the split across runs.

    Returns:
        Training identifiers and holdout identifiers, in that order.

    Raises:
        ValueError: If identifiers and labels differ in length, or if labels hold
            a value outside {0, 1}.

    TODO:
        - Stratify on the label so the 8.07 percent positive rate is preserved in
          both sets. An unstratified split at this imbalance can drift the rate
          far enough to shift every reported metric.
        - Use sklearn's train_test_split with stratify and the explicit seed, or
          an equivalent deterministic method. Do not use a hash of the id: the
          partition would be stable but the strata would not be balanced.
        - Sort both outputs before returning. A deterministic order makes the
          written file byte-identical across runs, which is what lets the
          reproducibility check compare two runs directly.
        - Validate the label domain before splitting. A third label value would
          produce a third stratum and silently shrink both sets.
    """
    raise NotImplementedError


def assert_disjoint(train_ids: pl.Series, holdout_ids: pl.Series) -> None:
    """Assert the two identifier sets share no member.

    Raises:
        SplitViolationError: If the intersection is non-empty.

    TODO:
        - Compute the intersection and raise naming its size and a few offending
          ids. An overlap means the holdout was partly trained on, which
          invalidates the final number entirely rather than slightly.
        - Also assert the union covers every application exactly once, so no
          customer is silently dropped from both sets.
    """
    raise NotImplementedError


def assert_rate_parity(
    train_labels: pl.Series,
    holdout_labels: pl.Series,
    tolerance_pp: float,
) -> float:
    """Assert both sets carry the same positive rate within tolerance.

    Args:
        train_labels: TARGET for the training identifiers.
        holdout_labels: TARGET for the holdout identifiers.
        tolerance_pp: Allowed difference in percentage points, 0.1.

    Returns:
        The observed absolute difference in percentage points.

    Raises:
        SplitViolationError: If the difference exceeds the tolerance.

    TODO:
        - Compare in percentage points, not as a ratio, matching how the gate is
          specified.
        - Report both rates and the difference in the message, so a failure says
          which direction drifted.
    """
    raise NotImplementedError


def write_holdout_ids(holdout_ids: pl.Series, destination: Path) -> Path:
    """Write the holdout identifier list to Parquet.

    This file is the contract between step 4 and everything after it. It is
    written once and read, never rewritten: regenerating it with a different seed
    would silently move customers between the two sets and compromise a holdout
    that earlier runs had already trained around.

    Args:
        holdout_ids: Identifiers to reserve.
        destination: File to write.

    Returns:
        The destination path.

    TODO:
        - Refuse to overwrite an existing file unless an explicit force argument
          is passed, and log loudly when forced. The accidental rerun is the
          realistic failure mode here, not a malicious one.
        - Write the seed and the row count alongside the ids, so a later reader
          can tell which run produced the split without consulting a log.
    """
    raise NotImplementedError


def load_holdout_ids(source: Path) -> pl.Series:
    """Read the holdout identifier list.

    Raises:
        FileNotFoundError: If the split has not been made yet.

    TODO:
        - Raise with a message naming the Makefile target that creates the file,
          since the realistic cause is running step 5 before step 4.
        - Do not create the split on the fly when the file is absent. An
          implicitly created split would differ between two runs that each
          thought they were authoritative.
    """
    raise NotImplementedError


def run() -> SplitReport:
    """Split application_train and write the holdout identifier list.

    Returns:
        The split report.

    Raises:
        SplitViolationError: If either gate fails.

    TODO:
        - Read SK_ID_CURR and TARGET from the silver application table only.
          Never read a feature file: if one exists, this step ran too late.
        - Assert the input row count equals EXPECTED_TOTAL_APPLICATIONS before
          splitting, so a truncated silver table cannot produce a plausible
          looking but wrong split.
        - Run both gates, then write the file. Writing before the gates pass
          would leave an invalid split on disk for the next step to consume.
        - Log the report at INFO, including the seed, and warn if the holdout row
          count differs from EXPECTED_HOLDOUT_ROWS.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.split.make_holdout`.

    TODO:
        - Configure logging, call run, exit 1 on SplitViolationError.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
