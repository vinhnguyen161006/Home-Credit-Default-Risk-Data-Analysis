"""Step 3: normalize the known value traps and emit missingness flags.

One silver table per source table, original grain preserved. The governing
rule: missing data is not zero. A customer with no bureau history keeps nulls
plus a presence flag, because absence distinguishes a thin file from a clean
history, which is exactly the distinction this problem needs.
"""
