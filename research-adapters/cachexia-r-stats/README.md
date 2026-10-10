# Official R statistics, isolated study staging

Six declared factories call the unmodified `stats` package in the frozen R 4.5.1
image digest. No default method choices are supplied by the wrapper: a second
input file supplies all method parameters, a test identity, missing-value policy
and the content hash of the first input. This is not a production installation.

Inputs are lexical TSVs with unique `row_id`, and a `key/value` TSV. Numeric
missing values are empty or `NA`; nonfinite supplied values are rejected. Modes
are `one` (`row_id,x`), `wide/paired` (`row_id,x,y`), or `groups`
(`row_id,x,group` with frozen `group1/group2`). Correlation always uses paired
rows. Proportions use `row_id,count,total`; adjustment uses `row_id,p_value`.
Group membership, donor eligibility and family assembly remain upstream duties.
There is a declared 1..10000 input-row bound, not a whole-R-API certification.

Common mandatory contract keys: `operation,scope,test_id,input_sha256,missing_policy`.
Scope is `TECHNICAL_ONLY_NOT_G0`; missing policy is `official`.
Per-method keys are enforced by the script; unknown/irrelevant keys are rejected.
`exact` is `auto/true/false`. Auto delegates to R's documented version-specific
defaults and preserves warnings. An explicit true request which cannot be exact
because of ties/zeros is blocked, not silently approximated.

Declared ports: 0 summary TSV, 1 all official numeric parameters with indices,
labels and typed nonfinite values, 2 full RDS with arguments/identities/warnings,
3 nonempty log, 4 hash/status audit. Summary includes both F degrees of freedom,
both group estimates, actual confidence level and typed infinite CI bounds.
All original official objects are retained in RDS. Official unestimable NA is a
`NOT_ESTIMABLE` row, not zero P, a discarded family member or a G0 decision.
Adjustments retain all ordered rows and enforce `n_total >= raw row count`.
Their output `test_id` is the unchanged input `row_id`, using the engine's
lexical test-identifier column contract rather than inferred numeric row IDs.

Wrappers do not implement R formulas, arbitrary matrix/table overloads, data
qualification, causal claims, a study-wide release gate or resident deployment.
Pratt/zsplit is not the definition of official `stats::wilcox.test` and is not
invented here. Version-specific exact tests, confidence intervals, and all
actually used vector arguments require independent reference proof.

Reference source: R Core `stats` at fixed R 4.5.1, with selected installed
function bodies and formals checked against its release-tag source before
numerical/DAG acceptance. The existing image's unrelated coloc/susieR libraries
are not used or certified by these nodes.
