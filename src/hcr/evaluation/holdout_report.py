"""Open the holdout once, produce the final numbers, and record that it was used.

The holdout keeps its independence only while it informs no decision. After many
experiments a cross-validated score drifts optimistic, because the choices were
themselves selected against it; the holdout is the one estimate not subject to that,
and it stops being so the moment a result from it changes anything.

So this module is deliberately awkward to run twice. It writes a usage record on
first read, and refuses to run again without an explicit override that is logged as
such. The mechanism is not security, it is a speed bump against the thing people
actually do: look at the holdout, dislike the number, adjust something, look again.

Everything this module reports must already be decided elsewhere: the model, the
calibrator and the threshold all come in fixed. Nothing here is tuned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

PLAUSIBLE_AUC_MIN: Final = 0.74
PLAUSIBLE_AUC_MAX: Final = 0.80
LEAKAGE_ALARM_AUC: Final = 0.85
CV_HOLDOUT_GAP_WARNING: Final = 0.02
USAGE_RECORD_FILENAME: Final = "holdout_usage.json"


class HoldoutAlreadyUsedError(Exception):
    """Raised when the holdout has been read before and no override was given.

    The message names the earlier run, its AUC and its timestamp, so the person
    rerunning can see what they are about to compare against.
    """


@dataclass(frozen=True)
class HoldoutUsageRecord:
    """Record of one holdout read.

    Attributes:
        timestamp: When it was read.
        mlflow_run_id: Run that produced the model being evaluated.
        model_hash: Hash of the evaluated artifact.
        configuration: Which feature configuration.
        auc: The resulting AUC.
        forced: Whether the read bypassed the single-use guard.
    """

    timestamp: str
    mlflow_run_id: str
    model_hash: str
    configuration: str
    auc: float
    forced: bool


@dataclass(frozen=True)
class HoldoutReport:
    """The final acceptance numbers.

    Attributes:
        configuration: Feature configuration evaluated.
        rows: Holdout size, expected 61502.
        positives: Realised defaults, expected about 4964.
        auc: Holdout AUC.
        auc_ci_lower: Lower bound of the 95 percent interval.
        auc_ci_upper: Upper bound.
        pr_auc: Holdout PR-AUC.
        brier: Brier score after calibration.
        cv_auc: Cross-validated AUC for comparison.
        cv_holdout_gap: CV minus holdout, the leakage indicator.
        approval_rate: Approval rate at the chosen threshold.
        default_rate_approved: Default rate among the approved.
        within_plausible_range: Whether AUC fell in 0.74 to 0.80.
    """

    configuration: str
    rows: int
    positives: int
    auc: float
    auc_ci_lower: float
    auc_ci_upper: float
    pr_auc: float
    brier: float
    cv_auc: float
    cv_holdout_gap: float
    approval_rate: float
    default_rate_approved: float
    within_plausible_range: bool


def read_usage_record(path: Path) -> HoldoutUsageRecord | None:
    """Read the usage record, or None if the holdout has never been read.

    TODO:
        - Return None on a missing file; absence is the normal first-run state and not
          an error.
        - Treat a corrupt record as used, not unused. Failing closed is right here: a
          record that cannot be read may still be recording a real earlier read.
    """
    raise NotImplementedError


def write_usage_record(path: Path, record: HoldoutUsageRecord) -> None:
    """Append a usage record.

    TODO:
        - Append rather than overwrite, so the history of reads is visible. If the
          holdout was consulted four times, that is a fact about the project worth
          keeping, and overwriting would erase exactly the evidence that matters.
        - Write after a successful evaluation, so a crashed run does not consume the
          single use.
    """
    raise NotImplementedError


def evaluate_holdout(configuration: str, force: bool = False) -> HoldoutReport:
    """Score the holdout and produce the final acceptance numbers.

    Args:
        configuration: Feature configuration to evaluate.
        force: Bypass the single-use guard. Logged at WARNING when set.

    Returns:
        The report.

    Raises:
        HoldoutAlreadyUsedError: If a usage record exists and force is False.

    TODO:
        - Check the usage record first, before loading any data. Raise naming the
          earlier run.
        - Load the holdout rows by the identifier file written at step 4. Never by
          index, fraction or complement: those all break silently if the matrix row
          order changed, and the failure looks like a normal result.
        - Assert the holdout row count matches the expected 61502 and that its ids are
          disjoint from the training ids. The split gate already checked this, but
          checking again here costs nothing and this is the one number nobody gets to
          recompute.
        - Load the calibrated model and the chosen threshold as fixed inputs. Tune
          nothing. If the threshold looks wrong against holdout data, that is a finding
          to report, not a value to adjust.
        - Compute AUC with its confidence interval, PR-AUC and the Brier score.
        - Compute the CV minus holdout gap. A gap above CV_HOLDOUT_GAP_WARNING is the
          classic signature of aggregation before splitting, so report it even though
          step 4 should have prevented it. The gap is the measurement that confirms the
          prevention worked.
        - Flag an AUC outside 0.74 to 0.80 and treat anything above 0.85 as a leakage
          finding requiring investigation and written justification, not as a result.
        - Write the usage record last, after everything succeeded.
    """
    raise NotImplementedError


def write_result_document(reports: tuple[HoldoutReport, ...], destination: Path) -> Path:
    """Write the final numbers between the generated-content markers.

    The numbers in the result document are generated from pipeline output, never typed
    by hand. A document edited manually drifts from the code on the next run, and the
    drift is invisible because both look equally plausible.

    TODO:
        - Write between two marker lines so a regeneration replaces only the generated
          block and leaves the prose intact.
        - Format every AUC through confidence.format_auc_with_interval, so no bare
          figure can reach the document.
        - Include the three stated limitations verbatim: no absolute dates so no
          time-based validation, the label thresholds X and Y unpublished so the
          probability is not a Basel PD, and application_test unlabelled so every
          measurement rests on a self-made holdout.
        - Include the cost assumptions next to the threshold they produced, labelled as
          assumptions.
        - Read the figures from MLflow rather than from function arguments where
          possible, so the document and the tracked run cannot disagree.
    """
    raise NotImplementedError


def run(force: bool = False) -> tuple[HoldoutReport, ...]:
    """Evaluate both configurations on the holdout and write the document.

    TODO:
        - Evaluate full and no_ext_source in one read, so a single holdout use covers
          both. Two separate runs would consume two uses for one decision.
        - Coordinate with fairness, which also needs holdout predictions: compute them
          once here and pass them, rather than letting that module open the holdout
          independently.
        - Report the gap between the two configurations. The difference between the
          full model and the one without third-party scores is the project's actual
          finding about internal data.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.evaluation.holdout_report`.

    TODO:
        - Accept a --force flag, and log at WARNING when it is used, naming the earlier
          read. The flag exists because a legitimate rerun happens, for instance after
          a bug in the metric code; the log exists so the rerun is never silent.
        - Configure logging, call run, exit 1 on HoldoutAlreadyUsedError.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
