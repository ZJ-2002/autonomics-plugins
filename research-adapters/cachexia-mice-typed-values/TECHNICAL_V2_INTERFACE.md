# Typed MICE boundary v2

The existing `cachexia_mice_values_to_parquet` kind remains version 1.
`cachexia_mice_values_to_parquet_v2` explicitly sets technical contract version 2
and consumes only schema2 MICE request/audit pairs with a neutral technical role.
Both explicitly synthetic and explicitly empirical technical input are allowed;
the upstream request, audit and lineage must agree without relabeling.

The two input and four output ports, seven value columns, numerical parsing,
null handling and lexical identities are unchanged. `typed_audit.json` and
`schema.json` carry the exact source role, schema2, NOT_GRANTED qualification and
matching upstream technical lineage. A scientific qualification remains false.
Conversion does not establish MCAR/MAR/MNAR assumptions, study eligibility or G0.

See `research-adapters/cachexia-mice/TECHNICAL_V2_INTERFACE.md` and
`tests/test_mice_v2_technical_contract.py` for the paired R contract and the ten
guard/provenance-only toy cases. No new imputation or empirical-data execution
was performed; this does not claim a current-image or production DAG pass.
