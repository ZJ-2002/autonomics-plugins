# singscore plugin (B-SPEC main score, WO step 4 follow-up, 2026-10-06)

Official Bioconductor **singscore** as the v4.0 B-SPEC main score
(plan section 5 / L780: rankGenes with AVERAGE ranks + simpleScore with
known directions). Until the review correction, the matrix wrongly had
z-mean as the NP06-09 main contract - z-mean is sensitivity analysis
only. This family implements the specified main-score method, not scientific
eligibility or deployment approval. The current v4.3.2 plan retains the
average-rank, non-stable-reference, known-direction, centered contract.

## Layout

- `manifest.toml` - node kind `singscore_bspec`: 3 file inputs
  (expression matrix TSV in frozen matrix-id space, gene set TSV
  gene/direction{up,down}, samples TSV sample/group), 3 outputs
  (score TSV sample/TotalScore/group, RDS, log); **parameter-free by
  design** (the technical interface fixes functions; no tunables that could become
  results-shopping handles)
- `scripts/singscore.sh` - pure R (mrlap.sh pattern); refuses any
  gene-set id missing from the matrix rows (mapping is the upstream
  study-plan contract, this node never maps or invents ids);
  rankGenes(tiesMethod="average") set EXPLICITLY because the package
  default is min-tie while the plan mandates average ranks
- `Dockerfile` - rocker r-ver 4.6.1 + Bioc 3.23 channel + singscore
  1.32.0 (verified against bioconductor.org/packages/3.23; first build
  pinned a guessed version - corrected), CRAN support stack on the same
  2026-09-13 snapshot as the MRlap image; zlib1g-dev/libgsl-dev for the
  XVector/Biostrings compile chain; stopifnot on the package version
- `test_singscore_hostref.R` - host-side golden (fixtures + official
  package run in the host library Bioc 3.23/singscore 1.32.0) against
  which the container script output must match to ~1e-12

## Current Interface Contract

IDs are literal strings: `001`, `1` and `NA` are distinct. Matrix gene
and sample IDs must be nonempty and unique. All expression entries must
be finite numeric values. No imputation, normalization, ID conversion or
matrix-row dropping occurs in this node.

Metadata must contain exactly one row per matrix sample, with nonempty
group labels. Scores preserve matrix column order; groups are attached
by ID after scoring and never affect ranks or scores. Signatures must
already be in matrix-ID space, nonempty and deduplicated across both
directions. Up-only and bidirectional signatures are supported; down-only
is explicitly unsupported. The official full rank matrix, every score
and dispersion column remain in the RDS. Nonfinite TotalScore is an
execution error, not a valid score or a zero.

Malformed TSV, missing members and inconsistent samples fail with a
diagnostic log. Existing normal outputs are not overwritten; fresh score
and RDS outputs are staged before no-replacement hard-link publication.
This is a local container-filesystem boundary, not a transactional pair
or a cross-backend/crash-recovery guarantee. Network is isolated, pull
policy is never, and the manifest declares 2 CPUs / 2 GiB per container.
This does not establish a global host concurrency or memory budget.

## Technical Verification

Run `python3 plugins/singscore/tests/test_contract.py` from the monorepo
with Podman and the exact manifest digest cached. Missing prerequisites
fail rather than skip. The suite covers official rank and complete RDS
score/dispersion agreement, up-only/bidirectional signatures, ties,
lexical IDs, axis permutations, one sample, invalid input, and existing
output protection. Fixtures are synthetic technical data, not study
eligibility or new biological evidence.

`python3 -m unittest tests.test_singscore_comparison -v` checks the smoke
verifier. NaN/Inf, duplicate/extra/missing IDs, empty tables and absent
logs cannot pass. `test_singscore_smoke.sh` now obtains its image from the
digest-pinned manifest rather than an overridable mutable tag.

Numerical agreement must specify the reference environment. The bundled
host-reference generator still requires a matching host R/package; a
container-based direct official call is not a host run. A fresh install
from the official Bioconductor 1.32.0 source provides a separate reference
without importing this node's parser or scoring wrapper.

## Scientific and Deployment Gates (not granted by these tests)

1. Verify the running implementation's manifest, script and image identity
2. Scope-qualified numerical, interface and actual DAG evidence
3. Study-plan inputs: frozen per-signature gene sets in matrix-id space
   (entrez `_at`) + dataset-common background definitions - the mapping
   must use current reviewed mapping evidence; historical tables do not
   independently authorize a scientific freeze
4. Deployed acceptance + matrix row before any B-SPEC run claims

## Boundaries

- Scores are not cell counts or absolute activity; cross-platform or
  cross-background comparability requires the separately frozen common
  background (plan section 5).
- This reproduction validates the RUNNER and the official package path,
  not any biological claim; SC04 (per-sample scoring, no label-aware
  training) is structural in the script contract.
- singscore does not replace UCell/pseudobulk/original-author methods
  frozen for core B; original-author methods remain pre-registered
  sensitivity analyses.
