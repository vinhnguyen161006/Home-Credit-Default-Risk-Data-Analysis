"""The two mandatory leakage checks: univariate AUC and feature ablation.

The source data is anchored at application time. Every DAYS_* and MONTHS_BALANCE
offset is negative, so the rows contain only past information. Leakage therefore
does not arrive through the data; it arrives through processing, and these two
checks are what catch it before a result gets believed.

The univariate AUC gate is the most important defence in the system. A single
column scoring above 0.95 on a credit risk problem is almost certainly leakage or
a label copy, not a discovery. For scale: all three EXT_SOURCE columns together
reach only about 0.70, and the final model is expected between 0.78 and 0.79.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)

UNIVARIATE_AUC_CEILING: Final = 0.95
EXT_SOURCE_COMBINED_REFERENCE: Final = 0.70
ABLATION_TOP_FEATURES: Final = 5


class LeakageSuspicionError(Exception):
    """Raised when a column scores above the univariate ceiling.

    The message names the column and its AUC. Treat it as a finding to
    investigate, not a bug to suppress: the resolution is to understand what the
    column is, and only then to decide whether it stays.
    """


@dataclass(frozen=True)
class UnivariateScore:
    """One column scored against the label on its own.

    Attributes:
        column: Column name.
        auc: Univariate ROC AUC, oriented so values above 0.5 are informative.
        null_fraction: Share of rows where the column is null.
        suspicious: Whether the AUC exceeds the ceiling.
    """

    column: str
    auc: float
    null_fraction: float
    suspicious: bool


@dataclass(frozen=True)
class AblationResult:
    """Model performance with one feature removed.

    Attributes:
        removed_feature: Feature dropped for this run.
        auc_without: Cross-validated AUC without it.
        auc_delta: Drop from the full-feature AUC, positive meaning it helped.
    """

    removed_feature: str
    auc_without: float
    auc_delta: float


def score_column_univariate(values: pl.Series, labels: pl.Series) -> float:
    """Score one column against the label with roc_auc_score.

    Args:
        values: Feature column, may contain nulls.
        labels: TARGET aligned positionally.

    Returns:
        ROC AUC, reflected above 0.5 so a perfectly inverted column scores the same
        as a perfectly aligned one.

    TODO:
        - Drop rows where the value is null rather than imputing. Imputing with the
          mean pulls the score toward 0.5 and would mask a leaking column that is
          mostly absent.
        - Return 0.5 when fewer than a few hundred non-null rows remain, or when
          one class vanishes after dropping nulls. A score from 30 rows is noise
          that would trigger the gate at random.
        - Reflect the score: return max(auc, 1 - auc). Direction does not matter for
          leakage detection, and an uncaught inverted column at 0.02 would pass a
          one-sided check.
        - Score categorical columns only after an ordered encoding, or skip them
          and say so in the report. Silently skipping is how a leaking category
          column goes unexamined.
    """
    raise NotImplementedError


def run_univariate_gate(
    frame: pl.DataFrame,
    labels: pl.Series,
) -> tuple[UnivariateScore, ...]:
    """Score every column and flag those above the ceiling.

    Returns:
        One score per column, sorted by AUC descending.

    Raises:
        LeakageSuspicionError: If any column exceeds UNIVARIATE_AUC_CEILING.

    TODO:
        - Score every feature column, excluding SK_ID_CURR and TARGET.
        - Score the training portion only. Scoring the holdout here would read it
          before the single permitted read, which is exactly the independence the
          split exists to protect.
        - Log the top twenty scores at INFO regardless of outcome. The distribution
          is the diagnostic: a healthy matrix has its best single column near 0.60,
          and seeing that is worth more than a bare pass.
        - Raise after scoring everything, listing every offender rather than the
          first.
        - Also warn on a column between 0.80 and the ceiling. Nothing in this
          dataset should score that high alone, so it is worth a look even though
          it does not stop the run.
    """
    raise NotImplementedError


def run_ablation(
    frame: pl.DataFrame,
    labels: pl.Series,
    top_n: int,
) -> tuple[AblationResult, ...]:
    """Retrain without each of the top features in turn and record the AUC.

    Catches the case where one feature carries most of the performance, which is
    usually a leak or a label proxy rather than a strong predictor. Results go into
    the result document as a table.

    Args:
        frame: Training feature matrix.
        labels: TARGET.
        top_n: How many top-importance features to ablate, 5.

    Returns:
        One result per ablated feature.

    TODO:
        - Rank features by the full model importance first, then ablate the top
          top_n one at a time. Use gain, not split count: split count favours
          high-cardinality columns regardless of contribution.
        - Retrain with the same folds and seed each time, so the AUC difference
          reflects the removed feature and not a different partition.
        - Flag any single feature whose removal costs more than about 0.02 AUC as
          worth investigating, and say so in the returned detail rather than only
          in a log line.
        - This is the expensive check, five extra fits. Run it once per accepted
          model, not on every experiment, and cache against the matrix hash.
    """
    raise NotImplementedError


def run(configuration: str = "full") -> tuple[UnivariateScore, ...]:
    """Run the univariate gate over one feature matrix.

    Raises:
        LeakageSuspicionError: If any column exceeds the ceiling.

    TODO:
        - Read the training rows only, excluding the holdout ids.
        - Write the full score table to the reports directory, so the result
          document can cite the distribution rather than only the verdict.
        - Run the ablation separately, from the modelling step where a trained
          model already exists; it needs one.
    """
    raise NotImplementedError


def main() -> None:
    """Entry point for `python -m hcr.quality.leakage_checks`.

    TODO:
        - Configure logging, call run, exit 1 on LeakageSuspicionError after logging
          every offending column with its AUC.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
