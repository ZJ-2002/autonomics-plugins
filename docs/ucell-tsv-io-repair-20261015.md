# Official TSV UCell: destructive I/O reproduced and repaired

The opt-in `cachexia_ucell_official` TSV wrapper already used the official R
package, but that alone did not make its file handling safe. Three synthetic
counterexamples on the actual original source reproduced: deletion of existing
score/RDS/audit files and modification of an old log; deletion of an aliased
matrix input; and truncation of an input aliased as the log. No study input or
result was involved. The original source and failed outcomes are preserved.

## Repair, not a new statistical implementation

All six declared paths are checked before a log is opened. Outputs must be
distinct from inputs and each other, including normalized-parent aliases;
existing files and dangling output links are refused. Normal artifacts are
written into owned temporary directories, then published with non-overwriting
hard links. Ordinary rollback removes only published files with the recorded
device/inode, preserving a deliberately injected foreign replacement. Inputs are
hashed before/after scoring; changed inputs prevent result publication. Fresh
owned failure logs survive; an old log is not reopened or appended.

The exact `UCell::ScoreSignatures_UCell` call is byte-identical to the original
(SHA256 `7753d863082e755df4ced940e9fff6ef6a937e1adb43a2485e3b6fb0f1ccad63`).
Package UCell 2.16.0, image digest, manifest, two TSV inputs, four output ports and
the three explicit parameters are unchanged. Rust remains transport/scheduling;
the R adapter does not substitute a score formula or silently fall back.

| Port | Contract |
| --- | --- |
| Input 0 | Finite nonnegative gene-by-cell TSV; literal unique axes |
| Input 1 | Signature/gene TSV; signed members and official missing-gene policy |
| Output 0 | Cell score TSV with official `_UCell` columns |
| Output 1 | RDS: official score matrix, features and typed parameter metadata |
| Output 2 | Nonempty execution/failure log at a fresh owned path |
| Output 3 | Audit JSON: exact input/output hashes, axes, parameters and release flags |

## Actual current-engine and independent reference evidence

Twelve three-node/two-edge current-engine DAGs cover maxRank **1000/1500/2000**,
missing_genes **impute/skip**, negative weights **0/0.5/1/2**, reordered gene/cell
axes, up-only and negative-only signatures, signed/partial members and lexical
IDs. **24 input bindings and 48 declared output ports** match actual source and
live/published file bytes. The 12 complete RDS objects, **208 official score
values**, TSVs and complete audit schemas/identities match the independent raw
author-source UCell namespace. Runtime/dependencies are shared and disclosed;
this is not a new independent platform/download claim.

One additional actual invalid-policy DAG preserves its exact failed state/log
without normal results or fallback. Two additional graph preflight cases reject
an unknown parameter and disconnected signature port. Thus there are **13
executed method DAGs**, not 15 successful method runs.

The three original path-loss cases now refuse without damaging any protected
bytes. Sixteen additional exact-cause checks cover all remaining input/output
aliases, normalized-parent collision, missing paths, dangling/hardlinked output,
invalid parameters, failure at each normal-publication step, unowned replacement
preservation and deliberately changed input detection. Their fault injection is
limited to owned technical files, not scientific data. Staging directories are
removed on ordinary completion/error; no crash-resume guarantee follows.

## Corrections stay visible

- The first old-wrapper probe failed due to a container user-mapping error; it
  is not used as loss evidence. The corrected probe actually reproduced all
  three defects before the wrapper was edited.
- All twelve method DAGs succeeded, but the first reference verifier serialized
  JSON integer weights as R integer metadata, whereas the longstanding wrapper
  uses `as.numeric` double. Follow-up strict readback requires the original exact
  weight value and double schema, keeps every official score/feature object
  unchanged and does not modify reference files, relax numeric tolerance or
  rerun DAGs. The old verifier exit remains failed, not retroactively green.
- A test hardlink initially blocked strict archival. After actual zero exit,
  session-lease and inactive-unit/MainPID checks, an explicit recorded maintenance
  step materialized the owned alias as a separate identical-byte file. Source,
  result bytes and exit status were unchanged; archival then completed without
  weakening link/source checks. Future fixture code removes the verified toy
  alias before exit. The post-terminal maintenance receipt remains part of the
  proof, not a concealed change to scientific evidence.

The old immutable-script test is deliberately requalified to the newly proved
I/O revision. Its original Git import identity is retained, and the changed
wrapper/README/contract are bound to actual committed Git objects in the source
evolution ledger. Historical `official_container_v2.R` remains unchanged: its
old deletion-on-error assertion is obsolete and must not be treated as current
acceptance or silently refreshed into a passing historical claim.

## Release boundary

New wrapper SHA256: `0ee592ccb766d784451a8d429f13d4cda3d7d2ea774ad7397b3ba6915ed582fd`.
Engine: `db83a6bb9886e4b1a3c563bef9261df782a0050c`.
Cached official image digest:
`f5310020240016e9069783498aebbd1849c73c6ae4918058614803fe3b6bfca1`.

See [machine-readable evidence](../evidence/ucell-tsv-io-repair-20261015.json) for
archive seals, original/current source identities, actual cases, corrective
receipts and the separately recorded complete local source test result.
The complete required suite executes 214 tests with zero failures/errors/skips
and a matching catalog lock; it actually runs the three updated family contract
tests. Source evolution verifies 2,476 imported files, including 51 explicitly
recorded changes backed by real Git objects; the original import ledger is not
rewritten. These engineering checks are not scientific certificates.

This is scoped **technical I/O repair plus official method/port proof**, not a
new original function slot or blanket H5AD route certificate. Large-scale memory,
donor/species/background/coverage qualification, arbitrary package parameters,
clean/anonymous image installation, daemon loading, scientific signoff and G0
are not granted. No production configuration, frozen design, viewing history or
276/288/696 family denominator changes. Spatial B-S and GS01 stay unchanged.
