# mrlap plugin (WO-R-02, scaffold 2026-10-06)

Containerized **official R MRlap** — the release path for the A-family
sample-overlap-aware MR correction. The native Rust `mrlap` node carries
documented, unvalidated deviations from the official pipeline
(`crates/node-bundles/nodes-mr/src/mrlap.rs:10`: M definition, jackknife
blocks, fixed EUR panel, EAF palindrome handling) and is FORBIDDEN from
the formal chain until certified (node acceptance matrix row 3). This
family is row 4: `mrlap_official`.

## Layout

- `manifest.toml` — node kind `mrlap_official`: one edge per instance,
  three file inputs (exposure TSV, outcome TSV, instrument rsID list),
  four outputs (17-field summary TSV, RDS, print text, log), seed param
  default 1, LD/HM3 panel paths
- `scripts/mrlap.sh` — pure R script (harmonise.sh pattern) porting the
  frozen canonical `WOE4_mrlap_seed_rerun.R` (canonical v2): RNGkind +
  per-edge `set.seed(seed)` immediately before `MRlap()`,
  `do_pruning = FALSE` fixed, `user_SNPsToKeep` from port 2, defensive
  `g()` summary builder (absent quantity stays NA, never 0)
- `Dockerfile` — R 4.6.1 base; method packages pinned to the exact
  commits recorded by the seed1 acceptance host library (MRlap @660f026
  sha256:42e74c0c…, TwoSampleMR @d4df219/0.7.11 sha256:a203d741…,
  GenomicSEM @da95d431/0.0.5 sha256:cf5f1a7f…); support stack from the
  2026-09-13 CRAN snapshot (same as the twosamplemr family image);
  build-time stopifnot on all three versions
- `test_mrlap_official.sh` — parity gate: replays the three seed1 edges
  (XM/XY/MY) and compares every summary field against the frozen
  `WOE4_mrlap_summary_seed1.tsv`

## Deploy gates (open — DO NOT add to plugins.toml until all closed)

1. ~~Image digest pin~~ CLOSED: `manifest.toml` pins
   `ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3…063d` (reference-
   BLAS 3.12.0 rebuild, matching the host kernel of the seed1 acceptance;
   the first OpenBLAS build moved the two bootstrap-aggregate columns by
   ~1e-9/1e-8 — seed determinism itself confirmed byte-identical in the
   OpenBLAS build). Remaining sub-item: the ghcr package is private
   (fine-grained token cannot flip visibility; owner one-click in the
   web UI, same debt class as the 8 repushed org mirrors).
2. LD panel registration HALF-CLOSED: the 211 MB panel (22 per-chromosome
   LD-score gzips + M_5_50 + `w_hm3.noMHC.snplist`, seed1 content
   identity, digest `sha256:c1bdd30e…d065`) is published to
   `ZJ-2002/catalog-mrlap-ldsc-eur-w-ld-hm3-no-mhc` and materialized in
   the local panel cache (marker + manifest verified by
   `autonomics-catalog list`). Two follow-ups: the package repo's root
   index.json carries registry form (`repositories:[self]`, written by
   `catalog publish` before it dies on the central-index commit) while
   `install`/`validate_package_index` requires `repositories:[]` — the
   API commit attempt was silently discarded by the hub endpoint, fix
   needs a token with proper package write or an LFS-free git push; and
   the central registry `wjixiang/catalog-index` (other owner) needs a
   `create_pr=1` PR listing the new bundle.
3. **Container parity**: `MRLAP_CONTAINER=1 test_mrlap_official.sh`
   green against the digest-pinned image, plus a deployed-DAG reproduction
   of the three edges, before the matrix row flips to ACCEPTED.

## Boundaries

- MRlap standardizes `Z/sqrt(N)` internally and its HM3 IV subset differs
  from the conventional IVW sets — the summary columns must never be
  subtracted from or compared "better/worse" against `twosamplemr` family
  outputs; they are separate conventions (seed1 acceptance §"不应称为…").
- TwoSampleMR 0.7.11 here vs 0.7.9 in the twosamplemr family image are
  independently recorded environments; no cross-validation between them.
- Effects are on standardized scales; NA-vs-NA comparisons stay honest.
- Dependency declarations are NOT validated by design: `install.packages`
  with `repos = NULL` (the pinned-commit tarball path) skips version
  checks, so TwoSampleMR 0.7.11's declared `ieugwasr >= 1.2.0` coexists
  with the CRAN snapshot's 1.1.0 exactly as in the host acceptance
  library. The frozen offline three-edge path is what this image
  reproduces and certifies; nothing here is a general
  dependency-compatibility claim.
- M/Y frozen feeds carry duplicate rsID rows (multi-allele
  representations); the plugin preserves input bytes and does not
  constitute general QC acceptance.
