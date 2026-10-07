"""The eight steps in order, with their gates and their one hard ordering rule.

Data flows one way. Each step takes an input path and writes a new output path, so no
step can overwrite its own input and two runs produce identical results.

The ordering constraint that must never be inverted: step 4 completes before step 5
starts. Aggregating history before splitting the data is the primary leakage source in
this project, and its symptom is a cross-validated AUC exceeding holdout AUC by 0.02 to
0.05 - a gap small enough to be mistaken for ordinary variance.

Makefile first, Prefect later. The requirement is a single command that reruns
everything; a scheduler is only worth adding once the pipeline runs unattended.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineStep:
    """One step and the gate guarding it.

    Attributes:
        number: Step number, 1 through 8.
        name: Short identifier.
        description: What the step does.
        runner: Callable executing it.
        gate: Callable asserting its postcondition, or None where the step has none.
        must_follow: Step numbers that must complete first.
        on_gate_failure: Either "stop" or "warn".
    """

    number: int
    name: str
    description: str
    runner: Callable[[], object]
    gate: Callable[[], object] | None
    must_follow: tuple[int, ...]
    on_gate_failure: str


STEP_ORDER: Final = (
    (1, "ingest", "Raw CSV to compressed Parquet, content unchanged"),
    (2, "contracts", "Assert row counts, column counts, dtypes, primary keys"),
    (3, "silver", "Normalize the seven value traps, emit missingness flags"),
    (4, "split", "Stratified holdout split, write the identifier list"),
    (5, "features", "Two-stage DuckDB aggregation to customer grain"),
    (6, "gates", "Feature quality gates and the univariate AUC leakage gate"),
    (7, "train", "Baselines, cross-validated LightGBM, calibration, threshold"),
    (8, "serve", "Build the star schema and load SQL Server"),
)

CRITICAL_ORDERING: Final = (4, 5)


class PipelineHaltedError(Exception):
    """Raised when a stop-level gate fails.

    Names the step, the gate and the observed value. Later steps do not run, because
    each one builds on the output of the last and a failed gate means that output is
    not trustworthy.
    """


def build_steps() -> tuple[PipelineStep, ...]:
    """Assemble the eight steps with their gates and dependencies.

    TODO:
        - Declare must_follow for every step, and assert step 5 lists step 4. That
          assertion is cheap and it encodes the one constraint whose violation is
          hardest to notice after the fact.
        - Attach the gate functions from the quality and contracts modules rather than
          reimplementing the checks here. A gate defined twice is a gate that will
          disagree with itself.
        - Mark the step 6 column gates as warn, since they drop a column and continue,
          and everything else as stop.
    """
    raise NotImplementedError


def assert_ordering(steps: tuple[PipelineStep, ...]) -> None:
    """Assert the declared dependencies form a valid order.

    Raises:
        ValueError: If a step precedes one of its dependencies, or if step 5 does not
            depend on step 4.

    TODO:
        - Check that each step number exceeds every number in its must_follow.
        - Check CRITICAL_ORDERING explicitly and by name in the error message, so a
          future reordering fails with an explanation rather than a generic cycle
          error.
    """
    raise NotImplementedError


def run_step(step: PipelineStep) -> object:
    """Run one step and its gate.

    Raises:
        PipelineHaltedError: If the gate fails and on_gate_failure is "stop".

    TODO:
        - Log the step number, name and elapsed time at INFO. Step 5 takes minutes, and
          a log that shows which step is running is the difference between waiting and
          wondering.
        - Run the gate after the step, never inside it. A gate embedded in the step
          cannot be run on its own in CI, which is the reason it is separate.
        - On a warn-level failure, log at WARNING and continue; on stop, raise.
    """
    raise NotImplementedError


def run_from(start_step: int = 1, stop_step: int = 8) -> dict[int, object]:
    """Run a contiguous range of steps.

    Args:
        start_step: First step to run.
        stop_step: Last step to run.

    Returns:
        Step number to its return value.

    TODO:
        - Refuse to start at step 5 or later when the holdout identifier file does not
          exist. Resuming mid-pipeline is legitimate; resuming past the split without a
          split is the leakage path and it should fail immediately.
        - Validate the range before running anything.
        - Make each step skippable when its output is newer than its input, so a resumed
          run does not redo finished work. Log every skip: a silent skip after an edit
          to a config file produces a result from stale inputs.
    """
    raise NotImplementedError
