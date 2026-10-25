# Explicit LCMM technical contract V2

This version removes a synthetic-only engineering restriction. It does not
approve any dataset, trajectory estimand, landmark analysis, biological subtype,
class-selection rule, missingness model or scientific G0.

The four original kinds, ports, resources and environment declarations remain.
They default to contract version 1 and reject version 2. Four additional kinds
append `_v2` and explicitly set `AUTONOMICS_TECHNICAL_CONTRACT_VERSION=2`.
The official lcmm 2.2.2 calls, parameters, complete-observation requirement,
convergence checks, source hashes, original row axis and complete RDS remain.

V2 requests retain the existing field names, set `schema_version=2`, retain
`scope=TECHNICAL_ONLY_NOT_G0` and `scientific_qualification=NOT_GRANTED`, and use
`analysis_role=TRAJECTORY_TECHNICAL_NOT_LANDMARK_OR_BIOLOGICAL_SUBTYPE`.
`input_role` is explicitly `SYNTHETIC_TECHNICAL_INPUT` or
`EMPIRICAL_TECHNICAL_INPUT`; it is not inferred from values or file names.

For a single-class fit, the complete-observation receipt retains the original
five fields and adds `input_role`, `scope`, `scientific_qualification` matching
the request. Its eligibility token is
`COMPLETE_OBSERVATIONS_NOT_RESEARCH_PERMISSION`. It is an input consistency
receipt, not a reviewer signature or research authorization. The numeric TSV is
still independently checked for complete finite observations and exact rows.

V2 RDS state, accepted-request diagnostics, audit and each lineage entry retain
version, input role, neutral analysis role and non-scientific scope. Prediction,
comparison and multi-class initialization reject mismatching parent versions,
roles or lineage; empirical state cannot silently become synthetic state.
V1 state is not a V2 parent. Existing V1 output structures are unchanged.

The companion `cachexia_lcmm_values_to_parquet_v2` consumes the same two Files
and emits the same four Files as V1. It requires matching request/audit V2
provenance, preserves the original fields and `source_position`, and carries
provenance in typed audit, schema receipt and Parquet schema metadata. It does
not add logical result columns or grant scientific permission.

## Incremental tests

`tests/technical_v2_guards.R` extracts the actual guard/provenance functions from
the adapter. Its ten self-cleaning toy groups cover both roles, version/permission
rejection, V1 metadata identity, receipt/row/hash checks, lineage consistency and
complete RDS roundtrip. Its fabricated `hlme`-class object is a provenance
fixture, not a fitted model or an official-method numerical oracle.

`tests/test_technical_v2.py` adds seven pure Python tests for original/new
manifest contracts and the actual typed provenance guard. No LCMM model is
fitted, no empirical data is used, and existing author-method numerical proofs
must be reused rather than relabeled as newly executed. Production deployment
and current-SDK integration are separate pending steps.
