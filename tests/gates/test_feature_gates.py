"""Step 6 gates, including the univariate AUC check.

The univariate gate is the most important defence in the system, so it gets the most tests. A
single column scoring above 0.95 on a credit risk problem is almost certainly leakage or a label
copy; for scale, all three EXT_SOURCE columns together reach about 0.70.

Note which gates stop and which drop a column. An all-null column is a configuration mistake the
run can absorb; an infinity or a suspicious correlation means a downstream number would be wrong
rather than merely absent.
"""

from __future__ import annotations


def test_all_null_column_is_dropped_not_fatal() -> None:
    """TODO An entirely null column is removed and the run continues.

    Assert the column is gone and no exception was raised. It signals a features.yml defect worth
    logging, not a reason to discard a completed aggregation.
    """
    raise NotImplementedError


def test_dropped_column_is_logged_and_recorded_in_manifest() -> None:
    """TODO A dropped column appears in the log and in the manifest record.

    A column that disappears without a record makes the matrix unauditable, and the column count
    difference between generation and training becomes unexplainable.
    """
    raise NotImplementedError


def test_constant_column_is_dropped() -> None:
    """TODO A single-valued column is removed."""
    raise NotImplementedError


def test_constant_column_with_informative_nulls_is_kept() -> None:
    """TODO A column of one value plus varying nulls is kept when no flag covers it.

    The absence is the signal. Dropping it would discard the information the missingness flag
    convention exists to preserve.
    """
    raise NotImplementedError


def test_infinite_value_stops_the_pipeline() -> None:
    """TODO A column containing infinity raises.

    Stop, not drop. An infinity reaching LightGBM produces an uninterpretable split, and reaching
    Power BI produces a blank measure with no indication why.
    """
    raise NotImplementedError


def test_infinite_value_is_not_silently_replaced() -> None:
    """TODO The gate does not convert infinity to null and continue.

    The unguarded division that produced it is the defect. Repairing it here would leave the
    feature SQL wrong and the next run would reproduce it.
    """
    raise NotImplementedError


def test_perfectly_correlated_pair_is_detected() -> None:
    """TODO Two identical columns are reported at correlation 1.0.

    A copied column is one of the five named leakage sources.
    """
    raise NotImplementedError


def test_correlation_check_excludes_the_label() -> None:
    """TODO A feature correlating with TARGET is not reported by the correlation gate.

    That case belongs to the univariate AUC gate, which stops and asks for an investigation. The
    correlation gate silently removing it would lose the finding.
    """
    raise NotImplementedError


def test_correlation_survivor_choice_is_deterministic() -> None:
    """TODO The same pair yields the same survivor across two runs.

    An arbitrary choice makes two runs produce different matrices, which breaks the
    reproducibility criterion in a way that is tedious to diagnose.
    """
    raise NotImplementedError


def test_univariate_auc_above_ceiling_stops_the_pipeline() -> None:
    """TODO A column with AUC above 0.95 raises.

    The system's most important gate. Assert the message names the column and its score.
    """
    raise NotImplementedError


def test_univariate_auc_detects_inverted_leakage() -> None:
    """TODO A column with AUC 0.02 is also caught.

    Direction does not matter for leakage. A one-sided check would pass a perfectly inverted label
    copy, which is the same defect wearing a minus sign.
    """
    raise NotImplementedError


def test_univariate_auc_ignores_nulls_rather_than_imputing() -> None:
    """TODO A mostly-null leaking column is still caught.

    Mean imputation pulls the score toward 0.5 and would mask a column that leaks on the few rows
    where it is present.
    """
    raise NotImplementedError


def test_univariate_auc_returns_neutral_for_tiny_samples() -> None:
    """TODO A column with 30 non-null rows scores 0.5 rather than a real value.

    A score from 30 rows is noise and would trigger the gate at random, which is how a gate gets
    disabled.
    """
    raise NotImplementedError


def test_univariate_gate_reads_training_rows_only() -> None:
    """TODO The gate does not touch holdout rows.

    Scoring the holdout here would read it before its single permitted use, which is exactly the
    independence the split exists to protect.
    """
    raise NotImplementedError


def test_ext_source_columns_pass_the_univariate_gate() -> None:
    """TODO The real EXT_SOURCE columns do not trigger the gate.

    They score around 0.60 each. A gate that flags them is miscalibrated and would stop every
    legitimate run.
    """
    raise NotImplementedError


def test_all_gates_report_before_raising() -> None:
    """TODO A matrix failing several gates reports every failure.

    One run should surface every problem rather than one per run.
    """
    raise NotImplementedError
