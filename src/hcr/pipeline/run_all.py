"""The single command that reruns everything from raw CSV.

An acceptance criterion: the whole pipeline runs from raw data on a clean machine via
one command, and running it twice produces the same result. Both halves matter. The
one command is reproducibility for someone else; the identical second run is
reproducibility for the author.

This entry point deliberately stops before the final holdout evaluation. The holdout is
read once, by its own command, after the model is settled. Folding it into "run
everything" would make the independence of the final number depend on nobody typing
make all a second time.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

LOG_FORMAT: Final = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
DEFAULT_START_STEP: Final = 1
DEFAULT_STOP_STEP: Final = 8


def configure_logging(verbose: bool = False) -> None:
    """Configure logging for a pipeline run.

    TODO:
        - Set INFO by default and DEBUG when verbose. Use LOG_FORMAT with timestamps:
          step 5 takes minutes and the timestamps are what identify the slow step on a
          later read.
        - Configure the root logger here only, never at import time in a library module,
          so importing hcr does not reconfigure a caller's logging.
        - Quiet the third-party loggers that are noisy at INFO, notably py4j and
          matplotlib font manager.
    """
    raise NotImplementedError


def main() -> int:
    """Run the pipeline end to end.

    Returns:
        Zero on success, non-zero on failure.

    TODO:
        - Accept --from and --to step numbers for resuming, --verbose, and --configuration
          to run one feature configuration only.
        - Do not accept a flag that skips a gate. A gate that can be skipped by a flag
          will be skipped under time pressure, which is when it matters most.
        - Exit non-zero on PipelineHaltedError after logging which gate stopped the
          run, so the Makefile and CI both fail correctly.
        - Log total elapsed time and a per-step breakdown at the end.
        - Do not run the holdout evaluation. Leave it to its own command, and say so in
          the closing log line, naming the target to run next.
    """
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
