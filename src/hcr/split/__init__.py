"""Step 4: reserve a holdout set before any feature is computed.

Runs before step 5. The identifier list is written to disk so the split is
fixed across runs, and the holdout stays independent only while it informs no
decision at all.
"""
