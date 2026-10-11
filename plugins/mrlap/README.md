# Official MRlap plugin

`mrlap_official` invokes the unmodified author R package, not the native Rust
`mrlap` approximation. Native Rust `mrlap` remains FORBIDDEN for this study.
The unified provider is `ZJ-2002/autonomics-plugins`, subdirectory `plugins/mrlap`.
Installation requires an explicitly pinned monorepo revision; publication
does not update a running daemon or grant scientific admission.

## Contract

One node computes one edge. Inputs are exposure GWAS TSV, outcome GWAS TSV,
and an explicit instrument rsID list, on ports 0, 1, and 2 respectively.
Outputs are port 0 `mrlap_summary.tsv`, port 1 `mrlap.RDS`, port 2
`mrlap_result.txt`, and port 3 `mrlap.log`. The RDS is the untouched complete
author result, including retained IV identities and harmonised input data.
The summary is a derived table, not another author API or a retention port.

The script requires all ports, regular input files, distinct nonexistent
outputs, single-line nonempty trait labels, valid LD/HM3 paths, a unique
nonempty instrument list, and a lexical integer seed in 1..2147483647.
It refuses non-estimable primary inference before writing analytical results.
This is not atomic multi-output publication or a concurrent output lock.

`do_pruning=FALSE`, `user_SNPsToKeep`, and the author defaults are fixed.
This route does not expose the pruning branch or the full MRlap API.
Namespace loading precedes RNG freezing; immediately before the author call,
the script uses Mersenne-Twister/Inversion/Rejection and the submitted seed.
Identical byte output is an environment-specific claim, not a promise across
R versions, BLAS implementations, input basenames, or platforms.

## Fixed environment and reference

The manifest retains image digest
`sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d`,
MRlap 0.0.3.3, GenomicSEM 0.0.5, TwoSampleMR 0.7.11, R 4.6.1, and reference
BLAS/LAPACK 3.12.0. Exact source archive identities are in the evidence card.
The installed packages lack `RemoteSha`; version strings alone are not the
source proof. Fresh separately installed SHA-locked author sources and all
220 defined namespace functions are compared, in the same fixed R image.
This is independent author-source execution, not an independent platform.

The local registered LDSC bundle is
`ZJ-2002/catalog-mrlap-ldsc-eur-w-ld-hm3-no-mhc`, with digest
`sha256:c1bdd30eabb9d821fe06ff5647bf6a08f9db29f80223762cfc6b3eb285c6d065`.
Isolated tests verify payload identities and materialize a separate cache.
Historical claims about a private image, pending local materialization, or a
required central-index PR are withdrawn. The current tests use a cached
image and local bundle; they do not prove a fresh public installation.

TwoSampleMR declares `ieugwasr >= 1.2.0`, whereas this image has 1.1.0.
The tested offline three-edge route works; general dependency compatibility
is NOT certified. The manifest/image license label is container metadata,
not a claim that MRlap's DESCRIPTION license (`GPL-2 | file LICENSE`) is GPL-3.
No legal compliance certification is granted.

## Verification commands

Run `tests/test_boundaries.py` against the actual pinned image with a fresh
`MRLAP_BOUNDARY_EVIDENCE` directory and the required local reference assets.
It must execute all 22 cases; missing resources are failures, not skips.
Run `python -m unittest discover -s plugins/mrlap/tests -p test_summary.py -v`
for the 12 mandatory comparator cases. Run Rscript on
`tests/test_result_guards.R scripts/mrlap.sh` for 21 production-source
result validation checks; these are not author method simulations.

`MRLAP_CONTAINER=1 bash plugins/mrlap/test_mrlap_official.sh` replays the
three previously seen frozen edges. `MRLAP_EVIDENCE` optionally specifies a
new output directory; all outputs and logs are retained, including failures.
The default image comes from the manifest digest, not a mutable local tag.
The strict comparison checks schema, edge identity, completeness, finite
values, and the original absolute tolerance of 1e-12.

## Interpretation and remaining limits

MRlap standardizes effects as Z/sqrt(N). Its estimates and instrument subset
must not be interchanged with conventional TwoSampleMR IVW estimates.
With pruning disabled, 39/39/475 supplied instruments become 7/7/97 retained
allele-compatible common instruments in these inputs; this is NOT evidence
of internal LD re-pruning. The author result omits `rg_se`, so the historical
51-entry comparison means 48 finite comparisons plus 3 explicitly missing
entries, not 51 numeric matches. Missing values are not coerced to zero.

The complete three-edge RDS comparison and isolated native DAG evidence are
limited to the declared inputs and environment. A staged input basename
changes the author's `GName` attribute; references use the same basename and
compare entire RDS bytes, without silently discarding attributes.
The data were previously viewed: this is technical reproduction, not new
independent scientific replication. No G0, full API/domain, statistical
calibration, cohort/ancestry/build/scale eligibility, complete study family,
production deployment, registered output content hashes, cache invalidation,
global resource ceilings, or persistent recovery is certified.
