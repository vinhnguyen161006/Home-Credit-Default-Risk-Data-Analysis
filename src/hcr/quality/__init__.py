"""Step 6: catch broken columns and leakage before training starts.

The univariate AUC gate is the most important defence in the system. A single
column scoring above 0.95 on a credit risk problem is almost certainly leakage
or a label copy, not a discovery. For reference, all three EXT_SOURCE columns
together reach only about 0.70.
"""
