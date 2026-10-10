# Typed MICE file boundary

Engineering adapter only, not an official statistical method. Verifies the
upstream values payload against its successful frozen audit and writes an
explicit seven-field Parquet schema: lexical strings and nullable Float64.

Numeric-looking `row_id` cannot be left to the native TSV reader's inference:
that reader's current finite identifier whitelist does not contain `row_id`.
Casting inferred integers back to strings cannot restore leading zeros.
This bridge does not alter that reader or certify all TSV schemas. It preserves
the analysis TSV/RDS and original upstream hashes alongside typed materialized
outputs. No scientific eligibility, production install or G0 is granted.
