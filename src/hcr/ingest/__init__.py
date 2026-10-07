"""Step 1: read the eight raw CSV files and write compressed Parquet.

Content is never altered here. Type coercion, sentinel handling and sign
conventions belong to the silver layer so that bronze stays a faithful,
cheap-to-read copy of the source.
"""
