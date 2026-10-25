# Survey method-only technical data contract V2

V2 removes a wrapper-only requirement to call every input synthetic. It does
not authorize a study, choose a sampling design, supply population totals, or
certify the full survey package API. The official survey 4.5 / R 4.6.1 image,
statistical functions and explicitly frozen numerical arguments remain unchanged.

## Explicit route selection

The original eleven kinds and their manifest declarations remain unchanged.
Eleven additional kinds append `_v2` to the original names:

| Operation | Additional kind |
| --- | --- |
| Bind upstream state hash | `cachexia_survey_bind_contract_v2` |
| Construct complete design | `cachexia_survey_design_v2` |
| Mean | `cachexia_svymean_v2` |
| Variance/covariance | `cachexia_svyvar_v2` |
| Quantile | `cachexia_svyquantile_v2` |
| GLM | `cachexia_svyglm_v2` |
| Design-based t-test | `cachexia_svyttest_v2` |
| Post-stratify | `cachexia_post_stratify_v2` |
| Rake | `cachexia_rake_v2` |
| Calibrate | `cachexia_calibrate_v2` |
| Trim weights | `cachexia_trim_weights_v2` |

Each new manifest kind explicitly sets
`AUTONOMICS_TECHNICAL_CONTRACT_VERSION="2"`. An absent selector means V1;
unknown selectors fail. Merely writing `schema_version=2` cannot open the V1
route. No existing frozen DAG address is automatically rebound.

V2 uses the same exact request keys and parameter objects, with:

- integer `schema_version=2`;
- `input_role` explicitly `SYNTHETIC_TECHNICAL_INPUT` or
  `EMPIRICAL_TECHNICAL_INPUT`;
- unchanged `scope=TECHNICAL_ONLY_NOT_G0`,
  `scientific_qualification=NOT_GRANTED`, and
  `analysis_role=SURVEY_TECHNICAL_BACKGROUND_ASSOCIATION_NOT_CANCER_MECHANISM`.

V2 preserves the original ordered row IDs, hashes, input budgets, safe formula
terms, data types, factor levels, design stages, weights/probabilities, FPC,
domain rules, variance and lonely-PSU choices. Design state remains a complete
official `survey.design2` object; updated weights alone are not a replacement.

## Complete-state and downstream provenance

The five R outputs and their logical contents remain summary TSV, complete
state RDS, audit, log and original row ledger. V2 state adds `input_role` and
`scientific_qualification`; its `schema_version` is 2. Constructor and every
downstream lineage entry retain their original versioned request. Analysis and
binder reject a different parent version, changed role, missing lineage, mixed
V1/V2 lineage or asserted scientific qualification. No authoritative clinical
claim is inferred from an operator's declaration of empirical provenance.

R audit V2 records request and complete-state version, role and qualification
independently, in addition to the unchanged raw request bytes and complete RDS
hash. The binder still changes only the root unresolved `input0_sha256` token;
all other JSON bytes, including numeric tokens, remain unchanged.

Post-stratification, raking and calibration V2 require
`population_role=EXPLICIT_POPULATION_TOTALS_NOT_STUDY_QUALIFIED`. Their explicit
external population records/margins/totals must still be supplied and pass the
existing level, duplicate, total, matrix-rank, bounds, convergence and
`force=FALSE` checks. The adapter never estimates or manufactures these totals.
V1 continues to require its original synthetic-population role.

## Typed companion

`cachexia-survey-typed-values/cachexia_survey_values_to_parquet_v2` consumes the
same two summary/audit inputs and produces the same four Parquet/audit/log/schema
outputs. The logical table columns and `source_position` are unchanged. V2
checks raw-request SHA, request/audit/state version and input-role agreement,
authority-false flags and complete-state hash. Provenance is retained in the
typed audit and schema JSON, not new table columns.

The companion does not receive the RDS itself and cannot independently reopen
or certify its contents. It binds the successful upstream audit and RDS hash;
this is not a claim of safety against an arbitrarily forged audit or RDS.

## Verification scope

`tests.test_survey_v2_technical_contract` evaluates actual R guard, provenance
and binder AST/functions against self-cleaning toy fixtures. It does not invoke
survey fitting or design estimators. It compares official statistical call ASTs
with the pinned pre-V2 source and verifies all V1 manifest node declarations
are unchanged. Fake `survey.design2` classes in metadata tests exercise only
scope checks, not validity of a statistical design.

`tests.test_survey_v2_typed_values` tests pure Python parsing, null/numeric/source
order, provenance and role-relabel rejection without running PyArrow. Existing
V1 typed parser tests are retained. These are incremental interface proofs, not
new full-scale model, Parquet-runtime, scientific or G0 certification. Existing
official numerical proofs remain scoped to their original cases.
