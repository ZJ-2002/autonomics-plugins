# Singscore: repaired publication and complete scoped requalification

`singscore_bspec` calls official **singscore 1.32.0 / R 4.6.1**. Its three
File inputs are expression, already-mapped directional signature, and exact
sample/group metadata; its three File outputs are scores TSV, full RDS and log.
The matrix column order is preserved. Groups are attached to results, not used
to calculate scores. Mapping, cohort eligibility, coverage and scientific
signature validity are separate study contracts.

The fixed interface explicitly calls `rankGenes(tiesMethod="average")`, as
required by this study, rather than pretending the author's min-tie default is
the same convention. It supports up-only and bidirectional signatures;
down-only, missing matrix genes, malformed identities and existing outputs
remain explicit refusals. This is not qualification of the whole author API.

## What changed

The scientific block's 31 expressions and its two input helpers are unchanged.
Only output publication and ownership handling were repaired: exclusive
writers, content-bound post-link/final checks, rollback restricted to confirmed
owned products, staging identity checks, and verification of the third log
port. Foreign replacements or changed file contents are not silently accepted
or deleted as ordinary rollback. No global hostile-TOCTOU or multi-file atomic
transaction guarantee is claimed.

## Actual official and DAG evidence

- All original cases were retained: 31 real four-node/three-edge DAGs, comprising
  ten successes and 21 specifically attributable author-interface refusals.
- All 93 input bindings, 124 task receipts and 30 normal output ports were
  verified. Two additional graph-construction refusals did not execute a method.
- Ten complete RDS objects match the original independently frozen official
  references; six deliberate comparator mutants are rejected. Complete TSVs
  and logs also match the unchanged previous results.
- The installed official namespace's 31 functions, five `rankGenes` method
  definitions and four `simpleScore` method definitions match the independently
  installed reference. No replacement golden or new scientific fit was invented.
- The existing-output control preserves the foreign artifact. All 33 owned
  method/direct/readback container intents have stopped on the same backend.
- All 907 reference members / 205,782,032 bytes, method sources, seven small
  proof-helper sources and their snapshots pass the final identity checks.
  The repaired publisher has 16 self-cleaning regression tests; the independent
  proof driver has 27. These are not counts of certified research nodes.

Proof session: `ee6cd74da6de4d619479e3e6e15bdf70`; manifest SHA256:
`e92dafd684c631efd5cc9ac391e1058207d7f70112f8dc38b66b77ce9ce2764c`.
The 1,122 members / 1,825,248 bytes were independently rehashed after cleanup.

## Honest limits and failed attempts

The explicit cached default rootless backend is proven for these synthetic
cases, not an anonymous pull, clean install, whole-cohort scale test or resident
daemon execution. The frozen generic SDK is commit
`4256643c55ae6fb50e8c867069330ed6ac2b4bc0`, executable SHA256
`636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b`,
with 23 actual guards; it is not represented as the latest production binary.

Manifest resources were not changed: two CPUs and `2g`. In this SDK, `2g`
means **2,000,000,000 bytes**, not 2 GiB. The managed parent is 2 GiB. Native
task resource leases remain empty; manifest fields and sampled memory are not
promoted to full-scale resource certification or a continuously observed peak.

Two earlier failed archives remain failures. The first rejected container
creation because the proof proxy confused SI and IEC memory units, and its
runner postcheck mixed identity-record schemas. The second completed two real
method DAGs but failed when the progress writer exclusively recreated the same
checkpoint. The final driver uses distinct per-case checkpoints and writes the
aggregate once. Neither earlier worker exit is rewritten as zero.

No real study input, production service, frozen signature decision, family
denominator or G0 status changes. B-S remains `CONDITIONAL_NOT_READY`, GS01
remains `OPEN`, and the study-specific B-SPEC eligibility is not granted by this
synthetic technical proof. See the [machine-readable evidence](../evidence/singscore-publication-requalification-20261015.json)
for exact source, image, build and proof identities. Private logs and study
payloads are not published.
