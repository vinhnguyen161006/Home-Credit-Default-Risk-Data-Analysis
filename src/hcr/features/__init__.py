"""Step 5: fold 58 million history rows down to 307511 customer rows.

All aggregation is SQL on DuckDB. The four largest tables sit at the third
relational level and must be folded twice: first to the second-level grain,
then to customer grain. Every join is a LEFT JOIN from the parent table,
because coverage is incomplete by design.
"""
