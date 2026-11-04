"""Step 4 gates. The two conditions that make every later number meaningful.

An overlap between training and holdout invalidates the final estimate entirely rather than
slightly: the model was partly trained on the rows used to accept it. A positive rate drift makes
the holdout a different population, so its AUC answers a different question than the
cross-validated figure it is compared against.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from hcr.config import load_model_config
from hcr.split.make_holdout import (
    EXPECTED_HOLDOUT_ROWS,
    EXPECTED_TOTAL_APPLICATIONS,
    HoldoutReadError,
    SplitViolationError,
    assert_covers_all,
    assert_disjoint,
    assert_rate_parity,
    read_holdout_labels,
    stratified_split,
    write_holdout_ids,
)

SYNTHETIC_POSITIVE_RATE: float = 0.0807
SYNTHETIC_SEED: int = 7
ALTERNATIVE_SEED: int = 8
HOLDOUT_FRACTION: float = load_model_config().holdout_fraction
TOLERANCE_PP: float = 0.1


def _synthetic_applications(
    count: int = EXPECTED_TOTAL_APPLICATIONS, seed: int = SYNTHETIC_SEED
) -> tuple[pl.Series, pl.Series]:
    rng = np.random.default_rng(seed)
    identifiers = pl.Series("SK_ID_CURR", np.arange(100_001, 100_001 + count))
    labels = pl.Series("TARGET", (rng.random(count) < SYNTHETIC_POSITIVE_RATE).astype(np.int64))
    return identifiers, labels


def _split(seed: int = SYNTHETIC_SEED) -> tuple[pl.Series, pl.Series]:
    identifiers, labels = _synthetic_applications()
    return stratified_split(identifiers, labels, HOLDOUT_FRACTION, seed)


def test_train_and_holdout_are_disjoint() -> None:
    train_ids, holdout_ids = _split()

    assert_disjoint(train_ids, holdout_ids)


def test_overlapping_sets_raise() -> None:
    train_ids = pl.Series([1, 2, 3])
    holdout_ids = pl.Series([3, 4])

    with pytest.raises(SplitViolationError, match="1 identifiers appear in both sets"):
        assert_disjoint(train_ids, holdout_ids)


def test_split_covers_every_application_exactly_once() -> None:
    identifiers, labels = _synthetic_applications()
    train_ids, holdout_ids = stratified_split(identifiers, labels, 0.2, SYNTHETIC_SEED)

    assert_covers_all(train_ids, holdout_ids, identifiers)


def test_dropped_application_is_detected() -> None:
    identifiers, labels = _synthetic_applications()
    train_ids, holdout_ids = stratified_split(identifiers, labels, 0.2, SYNTHETIC_SEED)

    with pytest.raises(SplitViolationError, match="for"):
        assert_covers_all(train_ids.head(-1), holdout_ids, identifiers)


def test_target_rate_difference_is_within_tolerance() -> None:
    identifiers, labels = _synthetic_applications()
    train_ids, holdout_ids = stratified_split(identifiers, labels, 0.2, SYNTHETIC_SEED)
    lookup = pl.DataFrame({"SK_ID_CURR": identifiers, "TARGET": labels})
    train_labels = lookup.filter(pl.col("SK_ID_CURR").is_in(train_ids))["TARGET"]
    holdout_labels = lookup.filter(pl.col("SK_ID_CURR").is_in(holdout_ids))["TARGET"]

    difference = assert_rate_parity(train_labels, holdout_labels, TOLERANCE_PP)

    assert difference < TOLERANCE_PP


def test_excessive_target_rate_drift_raises() -> None:
    train_labels = pl.Series([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    holdout_labels = pl.Series([1, 1, 0, 0, 0])

    with pytest.raises(SplitViolationError, match="drift"):
        assert_rate_parity(train_labels, holdout_labels, TOLERANCE_PP)


def test_holdout_fraction_produces_expected_row_count() -> None:
    _, holdout_ids = _split()

    assert len(holdout_ids) == EXPECTED_HOLDOUT_ROWS


def test_split_is_identical_across_two_runs_with_same_seed(tmp_path: Path) -> None:
    first = write_holdout_ids(_split()[1], tmp_path / "first.parquet")
    second = write_holdout_ids(_split()[1], tmp_path / "second.parquet")

    assert first.read_bytes() == second.read_bytes()


def test_split_differs_with_different_seed() -> None:
    _, holdout_default = _split()
    _, holdout_other = _split(seed=ALTERNATIVE_SEED)

    assert not holdout_default.equals(holdout_other)


def test_holdout_file_is_not_silently_overwritten(tmp_path: Path) -> None:
    destination = tmp_path / "holdout_ids.parquet"
    write_holdout_ids(_split(seed=SYNTHETIC_SEED)[1], destination)
    different = _split(seed=ALTERNATIVE_SEED)[1]

    with pytest.raises(FileExistsError, match="different split"):
        write_holdout_ids(different, destination)


def test_holdout_file_is_replaced_only_with_force(tmp_path: Path) -> None:
    destination = tmp_path / "holdout_ids.parquet"
    write_holdout_ids(_split(seed=SYNTHETIC_SEED)[1], destination)
    different = _split(seed=ALTERNATIVE_SEED)[1]

    write_holdout_ids(different, destination, force=True)

    assert pl.read_parquet(destination)["SK_ID_CURR"].equals(different)


def test_split_rejects_label_values_outside_zero_and_one() -> None:
    identifiers = pl.Series("SK_ID_CURR", range(20))
    labels = pl.Series("TARGET", [0] * 10 + [2] * 10)

    with pytest.raises(ValueError, match="outside"):
        stratified_split(identifiers, labels, 0.2, SYNTHETIC_SEED)


def test_feature_build_fails_without_holdout_file() -> None:
    """TODO Step 5 raises when the holdout file is absent.

    The ordering constraint, asserted from the other side. The message should name step 4, since
    the realistic cause is running the steps out of order.
    """
    raise NotImplementedError


def _labelled_applications() -> tuple[pl.DataFrame, pl.Series]:
    identifiers, labels = _synthetic_applications()
    return pl.DataFrame({"SK_ID_CURR": identifiers, "TARGET": labels}), _split()[1]


def test_first_holdout_read_is_allowed_and_logged(tmp_path: Path) -> None:
    applications, holdout_ids = _labelled_applications()
    usage = tmp_path / "holdout_usage.json"

    labels = read_holdout_labels(applications, holdout_ids, usage)

    assert len(labels) == EXPECTED_HOLDOUT_ROWS
    assert json.loads(usage.read_text(encoding="utf-8"))[0]["rows"] == EXPECTED_HOLDOUT_ROWS


def test_second_holdout_read_without_force_raises(tmp_path: Path) -> None:
    applications, holdout_ids = _labelled_applications()
    usage = tmp_path / "holdout_usage.json"
    read_holdout_labels(applications, holdout_ids, usage)

    with pytest.raises(HoldoutReadError, match="read 1 time"):
        read_holdout_labels(applications, holdout_ids, usage)


def test_forced_holdout_read_without_reason_raises(tmp_path: Path) -> None:
    applications, holdout_ids = _labelled_applications()
    usage = tmp_path / "holdout_usage.json"
    read_holdout_labels(applications, holdout_ids, usage)

    with pytest.raises(HoldoutReadError, match="requires a reason"):
        read_holdout_labels(applications, holdout_ids, usage, force=True)


def test_forced_holdout_read_is_logged_with_its_reason(tmp_path: Path) -> None:
    applications, holdout_ids = _labelled_applications()
    usage = tmp_path / "holdout_usage.json"
    read_holdout_labels(applications, holdout_ids, usage)

    read_holdout_labels(
        applications, holdout_ids, usage, force=True, reason="re-check after bug fix"
    )

    records = json.loads(usage.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[1]["forced"] is True
    assert records[1]["reason"] == "re-check after bug fix"


def test_corrupt_usage_log_fails_closed(tmp_path: Path) -> None:
    applications, holdout_ids = _labelled_applications()
    usage = tmp_path / "holdout_usage.json"
    usage.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        read_holdout_labels(applications, holdout_ids, usage)
