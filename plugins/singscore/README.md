# singscore plugin (B-SPEC main score, WO step 4 follow-up, 2026-10-06)

Official Bioconductor **singscore** as the v4.0 B-SPEC main score
(plan section 5 / L780: rankGenes with AVERAGE ranks + simpleScore with
known directions). Until the review correction, the matrix wrongly had
z-mean as the NP06-09 main contract - z-mean is sensitivity analysis
only. This family is the main-score route: loading + smoke + acceptance
are its gates, all open below.

## Layout

- `manifest.toml` - node kind `singscore_bspec`: 3 file inputs
  (expression matrix TSV in frozen matrix-id space, gene set TSV
  gene/direction{up,down}, samples TSV sample/group), 3 outputs
  (score TSV sample/TotalScore/group, RDS, log); **parameter-free by
  design** (G0 freezes functions; no tunables that could become
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

## Gates (open)

1. Image digest pin + push (ghcr.io/ZJ-2002/singscore-official)
2. Container-vs-host golden smoke PASS
3. Study-plan inputs: frozen per-signature gene sets in matrix-id space
   (entrez `_at`) + dataset-common background definitions - the mapping
   v2/v3 closure tables feed this but the scientific freeze is G0-side
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
