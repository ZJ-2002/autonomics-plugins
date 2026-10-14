# Current LDSC DAG candidate: not yet executed

The [author-method migration](ldsc-author-runtime-migration-20261015.md) is
complete within its recorded synthetic scope. This separate candidate closes the
next engineering layer; **it is not yet an isolated-DAG or deployment proof**.

## Fixed test inventory

The candidate replays all nine already sealed author cases without regenerating
their expected results: three h2 successes, three rg successes, one actual author
rg failure and two full-row munging successes. It loads the canonical manifest,
requires its exact hash and each actual script hash, and registers no native
statistical factories. Published ports must be nonempty, match the live owned
container files and retain their declared formats, sizes and any content hash.
The author failure must remain failed, keep its actual exit code/diagnostics and
publish no normal result. No old runner may substitute for the new compilation.

Synthetic panels receive explicitly different `autonomics-technical/*` identities.
The harness checks the original panel declarations before replacing only their
bundle identities. Strict panel materialization binds every manifest byte and
listed object. Both original and effective manifest hashes are reported. This
tests the engine's panel-binding path, **not the availability or eligibility of
the canonical research panels**. The substitution is never a production edit.

Whole author logs are compared with explicit path and timing substitutions.
Only the known twelve-column rg summary table permits path-width-induced padding
differences; every scientific token stays exact. Empty outputs and truncated
summary rows are rejected. Munging compares every decompressed byte with the
sealed independent author output, not merely row counts or significance.

## Source and execution

- `tools/probes/official_ldsc_dag.rs`: engineering-only isolated registry/DAG.
- `tools/build_current_ldsc.py`: exact committed engine export, locked offline
  compiler build, canonical target reuse and durable executable provenance.
- `tools/prove_current_ldsc.py`: complete sealed-reference replay and actual
  published-port/failure preservation checks.

Build through the canonical managed entry, using `--profile build`; the example
source is `tools/probes/official_ldsc_dag.rs`. The builder accepts the explicit
engine repository, parent commit and an existing canonical target. A successful
build record and matching executable are mandatory before invoking the proof.
Run the proof through the managed entry too; do not manually populate its
validation environment or bypass a busy build slot.

At preparation, another independently owned managed build was confirmed live.
The attempted second build was correctly denied before creating a workspace.
The other build is not stopped, exempted, relabeled as stale or run concurrently.
No LDSC candidate compilation, numerical DAG replay or production transition is
claimed from this denial. The next step is compilation after that slot is free.

All **178 required source tests** executed with zero failures, errors or skips;
the exact required inventory and source lock matched. Four new tests cover
summary-token preservation, truncated rows, synthetic panel manifest identities
and live/published port mismatches. Rust formatting/parser checks and Python
driver import/help checks pass. They do not replace Rust type checking, the nine
actual DAG executions, real-panel qualification, resident deployment or G0.

Source-test session `32923d43333b469fab93114631e4e3af` exited 0/CLEANED;
manifest `f6b22f400f7e19aa65cb625d9f2395953301bc0f59a1a5c69ae04dbaa5adeb5b`.
The original requirement denominator and frozen scientific configuration remain
unchanged. Current candidate status: **PREPARED / BUILD_AND_DAG_PENDING**.
