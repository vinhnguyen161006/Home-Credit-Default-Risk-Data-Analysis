"""Home Credit default risk scoring pipeline.

Eight one-way steps turn eight raw CSV files into a calibrated default
probability, a cost-based decision threshold and a star schema for reporting.
No step overwrites its own input, so two runs produce identical output.

Step order is fixed. The one ordering constraint that must never be inverted:
the holdout split (step 4) completes before any aggregation (step 5) runs.
Aggregating before splitting is the primary leakage source in this project and
shows up as cross-validated AUC exceeding holdout AUC by 0.02 to 0.05.
"""

__version__ = "0.1.0"
