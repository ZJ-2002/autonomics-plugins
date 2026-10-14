# Current-engine official R statistics: prepared, not accepted

This is the preserved preparation/failure checkpoint. The subsequent fixed
engine's complete 164-case result is now recorded in
[the current proof](current-r-stats-engine-proof-20261015.md). Pending statements
below describe this earlier checkpoint, not the latest isolated-DAG status.

The guarded R/stats 4.5.1 method entry remains the already requalified SHA256
`1ef00d41e6cb1b5a4870b5018dcfe28329bb0e9156d65e5fbfc6362aa4ef7d51`.
This next phase uses its sealed independent 164-case reference, not freshly
selected scientific data or a native Rust estimator.

The explicit engine example registers only the six declared official methods
and four engineering I/O factories. Every generated job has eight nodes/seven
edges: two immutable inputs, official R, explicit all-string TSV ingestion,
raw Parquet, typed SQL projection, typed Parquet ingestion and a materialized
terminal TSV. Numeric NA becomes typed NULL; lexical `NA`/`0001` IDs remain
strings. An explicit frozen identity ordering retains, rather than filters,
all members. ContentRequired, serial, nonincremental technical scope is required.

The first exact candidate `2f5dbf63b59a1ed4444ea288130c1b7bc6f9b5cf` compiled
successfully from parent `e6689238abf9aa9ea93559a997774b5d642cccdd` with only
the explicit example added. All 5,504 committed source files matched before/after;
958 compiler artifacts were recorded. Build session
`8454bd56043b48b4be4405daddd4a186` exited 0/CLEANED, manifest
`a217d2b3be17c27c0a6d000da8ae8a7177637cc810c9c21958a28ca26b3afb5d`,
executable SHA256
`bde7125488a5d638d353a5ecd8a8c4e438bf6a32d8ada0bfd2a0cf7f757d97f1`.
This uses an existing canonical compiler cache, not a copied dependency environment.

## A real shared I/O defect, not a missing package

The first job's eight nodes all succeeded, but its materialized header contained
`?table?.test_id` and analogous qualified textual columns, violating the declared
output contract. Adding explicit SQL aliases alone did not fix it. The failure
was traced to the committed `dataframe_to_file::normalize_string_views`:
its Utf8View-to-Utf8 cast did not explicitly preserve the original field name.
A local, previously unpublished fix already added that alias. It now also has
an end-to-end qualified-frame/real-TSV regression assertion. Do not normalize
the verifier's observed headers to make the defective output appear correct.

The two actual failed evidence sessions remain unchanged:
- `6500cdb58d244effa5abf81c534baf3a`, exit 1/CLEANED, manifest
  `71a8be3a1ebd54bae98e47a6b67991581dae77147078694a03660d2c70c7d525`.
- `c2272ed91083433b9cac2f3d0cb07dce`, exit 1/CLEANED, manifest
  `03846c4717e8aab87f2e17d63ca23fa613acf03c70563460491348a893c6a4d1`.

The first sink-regression build compiled the executable but its new unit test
used incorrect NodeInput/NodeReporter constructors. That build remains failed,
not accepted; the test now uses the actual API. An attempted downstream run
without a successful build record also failed before DAG execution and is
preserved. These are engineering failures, not scientific results.

## What must still be demonstrated

The sink-fixed candidate must pass its real regression, then every one of the
164 current-engine DAG cases must execute, materialize or retain its expected
failure diagnostics, preserve the five declared output copies, and reread the
complete independent RDS objects. Actual current deployment and frozen-study
family/eligibility checks remain separate and ungranted.

Four added source tests check all six generated method graphs, complete schemas,
literal/missing/Boolean values, frozen ordering without member filtering and
rejection of historical binaries/metadata-only hashing. Source tests or a build
alone are not DAG acceptance. No 120-slot denominator, frozen study file,
276/288/696 family, B-S/GS01 status or G0 is modified.

All 165 required source tests actually ran with zero failures/errors/skips and
a matching release lock in session `442ed9d747a9409888af82144c9da6c6`, manifest
`8efc46f14e3b170b9614a5ef64191b15bbaecd069ab5b8ad421db52202a23c74`.
This source result does not supersede the preserved failed DAGs or grant the
still-pending sink regression/current complete DAG layer.
