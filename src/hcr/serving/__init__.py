"""Step 8: build the star schema and load SQL Server for Power BI.

The serving store holds roughly 307 thousand fact rows and a few hundred
dimension rows, about 190 times smaller than the raw data. Compute stays in
DuckDB; raw data never enters SQL Server.
"""
