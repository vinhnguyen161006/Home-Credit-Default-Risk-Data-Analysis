"""Step 2: assert the raw data matches the declared contract.

Row counts, column counts, dtypes and primary key uniqueness are checked
against configs/data_contract.yml. Gates live here rather than inside the load
functions so they can run independently in CI.
"""
