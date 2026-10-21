# Official R statistics

This candidate calls the installed official R/stats 4.6.1 package directly:
`t.test`, `cor.test`, `var.test`, `wilcox.test`, `prop.test`, and `p.adjust`.
There is no Rust numerical implementation or fallback estimator.

The measured, digest-pinned existing R image is shared with `r-stats-lm` and
`donor-composition-official`; other packages in that image are not used.
The older `research-adapters/cachexia-r-stats` R/stats 4.5.1 profile is retained
unchanged. Its numerical results are not treated as new 4.6.1 references.

Every node takes two Files: a lexical TSV with unique `row_id`, and an explicit
`key,value` TSV contract binding the input SHA256 and all method controls.
The contract retains `scope=TECHNICAL_ONLY_NOT_G0`; calculation does not grant
scientific authorization. Five outputs retain the complete scalar table,
parameter vectors, full RDS, log, and identity audit. Inputs and outputs are not
drop-in replacements for legacy native DataFrame nodes.

The scalar table uses `NA` for unavailable or nonfinite numeric slots. Directional
confidence limits also have explicit bound-type columns. To distinguish infinity,
NaN, NULL and missing values for every parameter, use the typed `parameters.tsv`
and full `statistics.RDS`; do not interpret the scalar table alone as lossless.

Primary wrapper tables preserve their declared row identity/order. Subsequent
DataFrame/Parquet materialization can reorder batches: join and validate by the
exact unique lexical `test_id`, never by row position. A literal ID `NA` is not a
missing identifier. Reordering is acceptable only when the complete ID set and
each associated value remain unchanged; missing, extra or duplicate IDs fail.

The supported input limit is 10,000 rows, except adjustment accepts up to 25,000
rows for complete transcriptome-sized families. `n_total` is explicit and cannot
be smaller than the input row count. Missing values follow official R semantics;
this is not a frozen-study NA-to-one adapter, donor qualification, or family
selection service. Callers must preserve the original raw statuses separately.

The original 4.6.1 profile retains the earlier explicit method branches,
parameter validation and no-overwrite controls; its changes were the pinned R
version and adjustment row limit. Version requalification uses independently recomputed official 4.6.1
results from the retained synthetic arguments, not copied 4.5.1 answers.
Large-family BH/BY/Holm cases and the new row-limit refusal are additional tests.
The host comparison has 168 executed cases: 127 complete official-reference
matches and 41 specific refusals. In this author version, the retained Wilcoxon
ties/zero exact-request cases now return valid exact results; their new expected
outcomes come from independent 4.6.1 calls, not from accepting wrapper output.
The old 4.5.1 outcomes and implementation remain unchanged. See
`evidence/r-stats-current-r-host-20261020.json` for the bounded proof identity.
Host, container, DAG, deployment and study qualification remain separate axes.
Do not infer a production or scientific certificate from this candidate README.

The bounded cached-container/isolated SDK follow-up covers the first successful
case of each operation, both new exact Wilcoxon cases, 25,000-row BH/BY/Holm and
the specific 25,001-row refusal. Eleven complete eight-node DAG outputs/readbacks
match the new host references; the negative case blocks all five downstream
nodes. Six installed stats function bodies/formals also match the host exactly.
Ten already executed DAGs were reused from a sealed failed parent batch; only
the two remaining DAGs were newly executed. The parent batch stays failed.
See `evidence/r-stats-current-r-sdk-20261020.json`. This is not a resident-daemon
execution/deployment proof. The source release is now `published` after these
bounded host/container/SDK checks; installation and resident loading must be
recorded separately. Publication does not migrate a frozen R 4.5.1 study profile
or certify all unknown inputs, R overloads or scientific uses.

## Explicit complete-pair intake policy (candidate extension)

`missing_policy=official` keeps the published behavior, including R's paired
removal of missing observations. It is not silently tightened for existing jobs.
The optional `strict_complete_pairs` policy is only valid for `t_test` in `paired`
mode. It also requires `expected_row_ids`, a canonical comma-separated list of
unique lexical IDs in the exact externally frozen pair order. Missing rows,
changed identities/order or an absent x/y value block the call before `t.test`;
no smaller complete-case sample or alternative test is substituted.

For valid complete inputs the numerical call remains unmodified official
`stats::t.test`. This policy is an explicit adapter precondition, not an official
R parameter or a claim of whole-domain equivalence. The original 168-case and
SDK evidence covers the original policy, not this new extension; the latter needs
its own before/after contract proof and deployment record before use.

The first contract-only actual-image proof now has ten candidate cases: three
successful complete `htest` objects identical to direct official calls, and seven
specific refusals. The original official-policy complete/missing controls remain
unchanged; eight baseline cases demonstrate absence of the newly requested
option, not eight defects in official R. One owned fixed-image container executed
both ten-case phases. See `evidence/r-stats-strict-pairs-20261021.json`. No new
full scheduler DAG, resident reload or scientific release is claimed here.

This addresses an intake requirement of paired B-SPEC contrasts without selecting
donors, signatures, directions, a software lock or a scientific qualification.
It does not fill the v4.3.2 template's missing pair IDs or runnable contrast lock.
A refused contrast must still be represented by the separate complete-family
workflow with raw P missing and the declared adjustment placeholder; this node
does not assemble a family or award G0.
