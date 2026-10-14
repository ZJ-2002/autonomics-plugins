# Current fixed engine: official regression proof

Exact compiled candidate: `9a8514ad9103797861dc3a8cb23c987cb3a2db43`, engine
parent `3b0dc962b93fcd5f899d64696d1f4636ed1a3158`. Only the explicit synthetic
official-lm DAG example was added. All 5,497 committed source files matched
before/after compilation. The executable is permanently preserved once, and
execution uses a hash-checked, temporary executable copy because archived files
are intentionally non-executable. Shared caches are retained, not cloned.

**46 actual current-engine DAGs passed: 17 positive, 29 refusals.** Each has five
nodes/four edges, uses ContentRequired inputs, serial/nonincremental execution,
and calls official R rather than native statistical code. The existing sealed
independent reference packet was fully rehashed, not recomputed or modified.
All 17 materialized terminal files and complete RDS models were compared again;
39 coefficient rows, covariance, missing/special-value kinds and sample identity
were retained. 85 declared published outputs were independently rehashed.

## Two real interface findings, not suppressed

1. The current engine's default input staging uses symlinks. This plugin rejects
   them by contract. Its manifest now explicitly declares `stage_in_mode="copy"`.
   The R method code was not changed, and scientific input safety was not weakened.
2. Current work FileRefs intentionally continue to point at persistent work
   files; `artifact_prefix` publishes additional copies rather than rebinding
   every DAG output to VFS. The verifier initially assumed the old VFS/reference
   convention and failed after all five nodes had succeeded. It now checks both
   the live owned work files and the unique real published copies, exact bytes,
   declared formats/sizes and any declared hash. Independently computed hashes
   are not fabricated into a report whose metadata content_hash is null.

Disposable container workspaces now live in TMPDIR, while mandatory published
outputs remain in permanent evidence. The first failed run accidentally placed
its reconstructable work cache there: every cache file and symlink target was
preserved in a checked tar plus a disposition record after its exact service and
containers were stopped, then only that disposable directory was removed.
Its original failure exit remains 1. A nested-lock recovery call also failed;
the subsequent normal sweep completed without rerunning the computation.

Successful current packet: session `be163ad7b44040b4b6ba5125f9c041fc`, exit 0,
CLEANED, manifest `9e885ab79d89cb30794b7b5f2395f63bf05d2ca6e932d3f4b517e1a70fbd0011`.
It contains approximately 1.39 MiB/563 mandatory technical files, not a new full
environment or numbered private vault. Full identities and all preserved failed
attempts are in `evidence/r-stats-lm-current-engine-20261014.json`.
All 148 required source/catalog tests passed without failures, errors or skips.

## Scope remains explicit

This closes the current fixed engine's isolated DAG layer for the unchanged
ordinary-regression method and explicit copy transport. It is not resident
daemon loading, persistent/cross-process recovery, current deployment, arbitrary
lm formula branches, real-donor qualification, a signed study contract or G0.
Transient work-ref lifetimes are not called durable study-result references.
No frozen study files or 276/288/696 family denominators changed; the original
FUNC_linear_regression slot and fixed 120-candidate denominator do not increase.
