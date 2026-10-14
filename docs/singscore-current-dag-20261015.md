# Singscore: official package and complete current-engine DAG proof

`singscore_bspec` calls the author package **singscore 1.32.0**, Bioconductor 3.23,
R 4.6.1, through the unchanged digest-pinned container and method adapter.
There is no native Rust scoring implementation or statistical fallback in this
technical probe. Rust provides file references, declared-port transport,
scheduling and run reports, not a substitute score formula.

## Contract and actual proof inventory

| Port | Meaning |
| --- | --- |
| Input 0 | Finite expression matrix TSV; unique literal gene and sample IDs |
| Input 1 | Unique, already-mapped signature genes with explicit up/down direction |
| Input 2 | Exactly matching sample/group metadata, attached only after scoring |
| Output 0 | Score TSV: sample, TotalScore, group; matrix sample order preserved |
| Output 1 | Full RDS list: official ranks, complete simpleScore object, joined scores |
| Output 2 | Nonempty method/version/execution log |

The fixed method calls `rankGenes(tiesMethod="average", stableGenes=NULL)` and
known-direction, centered `simpleScore` with `stats::mad`. Average ties are an
explicit plan setting, not a claim that the package's default is average.
Up-only and bidirectional signatures are supported; down-only, absent members,
duplicate/overlapping IDs, malformed input and nonfinite values are refused.
No study-specific mapping, normalization, coverage threshold or background is
silently invented. The parameter-free node rejects undeclared parameters.

All **31 original contract cases** remain accounted for: **30 current-engine DAG
replays plus one direct no-clobber check**. The author package example adds one
DAG. Thus the actual total is **31 four-node/three-edge DAGs**, not 32: **10
successful graphs and 21 exact method refusals**. All **93 input bindings** matched
the full sealed source bytes; all **30 successful declared output ports** matched
their live/published files and formats/sizes. Invalid method inputs preserve the
exact frozen reason and log, without publishing normal score/RDS results.

The existing-file test is explicitly direct, using the current image and actual
declared ports: its sentinel remains byte-identical and no RDS is published.
It is not mislabeled as a DAG case; the engine owns and resets its task scratch.
Two additional graph controls refuse an unknown parameter and a disconnected
metadata port before normal scoring, with exact causes and no normal outputs.

## Independent reference and full-object comparison

The old independent official-source reference was not regenerated or edited.
Its complete seal was rechecked: **907 files / 205,782,032 bytes**. The current
manifest, scoring script, original test contract and original RDS reader remain
byte-identical to that reference's source identities.

The original RDS reader compares full rank and simpleScore objects plus score
TSV, but checks only the joined RDS sample column. That gap is not hidden:
the separate new `verify_singscore_joined.R` now checks all **10** positive
outputs using `identical()` on the entire RDS list. Joined score values/groups,
names, types, classes, row names and attributes must match the independent
official object plus frozen metadata. TSV IDs/groups are exact; its finite
numeric values keep the existing absolute tolerance of `1e-12`.

Six actual mutant RDS files are rejected: changed group, changed TotalScore,
extra list field, changed data-frame class, changed row name and nonfinite score.
This readback did not rerun scoring/DAGs, modify sealed originals or loosen a
golden/tolerance. An initial graph-control verifier had the wrong expected
diagnostic format; its failed verification archive is preserved. The corrected
check requires the exact analysis-node/port-2 error or the exact method guard.

## Reproducibility and boundaries

Built/run engine: `db83a6bb9886e4b1a3c563bef9261df782a0050c`.
Executable SHA256: `9dae47f22c5feeca79dd005ede43c16349b3b362530646e2220fcb8d40bc0069`.
The probe is the already-published generic engineering entry; no new engine build
or scientific kernel change was required here. Its scientific factories are the
explicitly loaded plugin, not native estimators.

All six referenced current archives have been rehashed, including the initial
failed control-verifier session. Local required source tests are **202 executed,
zero failures/errors/skips**, with the catalog source lock matching. Managed
sessions finished and cleaned disposable scratch; mandatory receipts remain in
permanent archives. Public records contain code and curated technical identities,
not private launcher logs or study payloads. See the machine-readable
[evidence](../evidence/singscore-current-dag-20261015.json) for archive seals,
case enumeration, source hashes and all explicit limitations.

Status is **ACCEPTED_SCOPED_TECHNICAL_CURRENT_GENERIC_ENGINE**, not certification
of all package branches, expression scales or future environments. Real cohort
eligibility, species/member mapping, common background and coverage, donor-level
inference, biological specificity, production daemon loading and signed research
contracts are separate. No deployed configuration, frozen study design, viewing
history, original node denominator, 276/288/696 family or G0 status is changed.
Spatial B-S remains CONDITIONAL_NOT_READY and GS01 remains OPEN.
