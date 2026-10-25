# Versioned empirical-capable technical MICE interface

The five existing v1 kinds, their manifest environment and ports are retained.
They default to technical contract version 1 and reject schema2. Five distinct
new kinds append `_v2` to each existing kind:

- `cachexia_mice_bind_contract_v2`
- `cachexia_mice_v2`
- `cachexia_mice_complete_v2`
- `cachexia_mice_impute_pmm_v2`
- `cachexia_mice_impute_logreg_v2`

Each v2 manifest explicitly sets
`AUTONOMICS_TECHNICAL_CONTRACT_VERSION="2"`. It requires integer
`schema_version=2`, `scope="TECHNICAL_ONLY_NOT_G0"`,
`scientific_qualification="NOT_GRANTED"`, and the neutral
`analysis_role="MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION"`.
The caller must explicitly declare either `SYNTHETIC_TECHNICAL_INPUT` or
`EMPIRICAL_TECHNICAL_INPUT`. The wrapper does not infer or relabel source role.
Technical version 2 is not a scientific authorization or an assertion that an
empirical source satisfies a study design.

The official MICE methods, complete.mids extraction, RNG, method parameters,
warning refusal, observation axes and all byte/row budgets remain unchanged.
The original ordered missingness receipt is still mandatory. Death,
structural missingness, medical contraindication and not-applicable cells
remain protected. No MCAR, MAR, MNAR, stationarity or longitudinal assumption is
inferred from acceptance of empirical input; all scientific/G0 grants remain
false. No scientific signature or eligibility receipt is fabricated.

V2 stores the original request and full result in the complete RDS as before,
and adds the explicit source role and technical lineage. Audit retains the raw
request JSON and matching role/schema/lineage. Completion and binding reject
schema1 parent state, mismatched original/nested request roles, contradictory
lineage and changes of source role through nested parent state. V1 state is not
silently promoted to v2; it requires a separately reviewed v2 execution.
These consistency checks do not cryptographically certify that an arbitrary
caller honestly classified its input; source content hashes and external study
qualification remain necessary.

The binder still modifies only the single root upstream SHA placeholder in
the original JSON bytes. It does not reserialize or alter numeric parameters,
missingness classification, role or eligibility.

## Typed companion

`cachexia-mice-typed-values/cachexia_mice_values_to_parquet_v2` is the matching
versioned boundary. Its two inputs, four outputs, seven logical value columns,
nullable numeric conversion and lexical IDs are unchanged. Request, upstream
audit and lineage must agree on version, role and non-scientific scope.
Role/schema/NOT_GRANTED provenance is retained in `typed_audit.json` and
`schema.json`. The original typed v1 kind remains separate.

## Incremental verification boundary

`tests/test_mice_v2_technical_contract.py` covers ten self-cleaning toy cases:
unchanged v1 manifests, explicit v2 ports/environment, version and source-role
guards, nested lineage laundering rejection, byte-preserving binding, actual
R AST RDS/audit provenance and typed Python guard/output-provenance AST.
It also checks that official method and missingness-receipt function bodies are
byte-identical to the retained source. All ten cases passed locally.

No new MICE model is fitted, no empirical data is analyzed, and no fake author
fit is presented as an official result. The RDS provenance case uses an
explicit guard-only placeholder object and does not claim full MICE entrypoint
or container execution. Source publication, frozen use selection, isolated
full-method/DAG validation and production installation remain separate steps.
