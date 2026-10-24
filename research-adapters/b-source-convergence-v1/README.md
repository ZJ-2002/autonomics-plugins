# B source convergence: published release versus local draft

This is an audit/tooling candidate, not a loadable scientific plugin. It does
not change method implementations, production pins, scientific locks or G0.

## Historical comparison, followed by an actual published repair

The immutable comparison parent is plugin commit
`233b5c4eabe31a121420bcd5c738edf9cfb48b5c`. Across test modules it finds:

| Relation | Modules | Disposition |
|---|---:|---|
| Identical | 106 | Reuse exact source identities |
| Local only | 8 | Unpublished features; review before publication |
| Published only | 4 | Preserve in release; do not delete to match the draft |
| Same path, different bytes | 6 | Explicit forward merge needed; retain both identities |

The six API-parser modules in the previously executed 41-case increment still
match their retained source hashes, and none of its recorded tool dependencies
changed. That execution is reused, not repeated. The local draft still declares
282 required IDs while discovering 1252; all 282 are found, but 970 others are
not registered. It is not a release candidate. No local draft, source-lock,
catalog, Git HEAD or shared index is overwritten by this audit.

The comparison also finds a genuine **published** gate defect: 1220 tests are
discoverable but only 1186 are registered. The 34 omissions belong to conditional
registry bindings, DESeq2 restoration, two MRlap-reference suites, MSigDB role
controls and seen-real A replay. Discovery is not execution.

This published defect is subsequently fixed at
`4379823f629c7377e4cd7c5c8f2ce9901f3a0661`: all 1186 existing IDs remain, all
34 omissions are added, the B inventory's quality member is rehashed, and only
that source-lock member is updated in the catalog. The new required set exactly
equals the retained published discovery set: **1220**, with no removed IDs.
The exact-set/no-skip gate is not weakened. Other catalog and scientific fields
are preserved; no production restart is needed for this metadata-only change.

Fourteen unit definitions reuse identity-bound original execution records.
Twenty specifically selected toy/metadata cases obtain durable execution/source
binding: 18 seen-replay cases and two MSigDB role controls, all passing with no
skip. They do not invoke MR, official R fitting, HTTP, containers or scientific
inputs. This does not claim that all 1220 tests were executed in this batch.

## Evidence

Comparison session `8c87eb3afad44c5d82e86ca603589b5b`, seal
`09642d7c01e16b8f233be74f705433618a0c55e2724b28de2de1eec3b3646506`:
`permanent/b-source-convergence/verification.json`, SHA256
`90d704bb16334a94ba8c7a952de54cfd771c00800c510a73e6c5042f9efea036`.
The same directory contains exact module decisions and discovery-only ID lists.

Gate closure session `5c99043cfe33491e9ac73bd59361aef3`, seal
`e0ebfdb56ea1e92f504ba4d8dd337a1d997c8fdeeb451a5d3af4b6c4f9256d2d`:
`permanent/published-test-gate-closure/verification.json`, SHA256
`09ea9b387ab550ad4b5436729640fff5577918743b3fdc1add0586d29aa99ebd`.
It records all 34 IDs, the 14 reused definitions/receipts, 20 actual executed IDs
and source identities, and exact candidate metadata hashes. Both final workers
and launchers exit 0, CLEANED. README is a post-proof documentation increment.

Two initial audit attempts, `e69618e26c4446a8b4d38fd610a0f882` and
`a96b8d3a6e464eff9622008099770444`, remain failed at the source-snapshot budget
guard, before collection/execution. The successful snapshot excludes vendor
archives, payload fixtures and build logs rather than increasing the budget.
It is a filtered public-source view, not a complete test-execution environment.
Its temporary 3366 files/66,037,268 bytes are cleaned; no dependency environment
or private vault is cloned or retained.

## Remaining local integration boundary

`CONVERGENCE_PLAN.json` and `convergence.tsv` retain per-module decisions. Do not
apply the old restore-162 patch or replace the entire local tree from main.
The eight unpublished modules and six changed modules require explicit review
against their implementation changes before any future release; the four public
modules must not disappear. This audit does not approve those drafts or certify
the full release suite. Actual study/data qualification remains separate.

`analyze.py` intentionally targets the immutable historical parent above. It is
not a periodic health check of later main, and its historical 1186/1220 finding
must not reopen the already-published repair. Required proof archives are local.
