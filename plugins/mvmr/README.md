# mvmr plugin

Migrated from the legacy `mvmr_container` wrapper in nodes-io. One
directory = one plugin family = one git-able unit. Panel-free family:
MVMR needs no reference data bundles, so the manifest declares no
`[[panels]]` (the loader documents mvmr as a legitimately panel-free
family).

## Layout

- `manifest.toml` — node kind `mvmr`: params, ports, image provenance
- `scripts/mvmr.R` — the execution script (R, run by `Rscript`),
  referenced relatively and inlined by the loader at startup
- `Dockerfile` — pinned official MVMR 0.4.8 image build (rocker/r-ver
  4.5.1 base, upstream source tarball at revision `bceaa38`)
- `test_mvmr.sh` — image baseline: builds the image and smoke-tests the
  official package against `fixtures/rawdat_mvmr.csv`
- `fixtures/` — vendored test data for the image baseline

## Install

Development checkout at `/mnt/projects/node-plugins/mvmr`; the runtime
loads every subdirectory with a `manifest.toml` from the plugins root
(`~/.autonomics/plugins`, or `AUTONOMICS_PLUGIN_ROOT`, or the explicit
`plugins_root` argument of `build_default_registry_with_container_execution`).

## Migration parity

The golden test (`autonomics` repo,
`crates/container-plugin/tests/mvmr_migration.rs`) compares the compiled
`ContainerCommandSpec` against the legacy Rust wrapper's contract:
image, outputs, timeout, and artifact prefix are asserted directly; the
script is asserted on semantic markers. Structural deltas, all
deliberate:

- **Kind rename**: `mvmr_container` → `mvmr` (plugin convention drops
  the `_container` suffix); `artifact_prefix` follows the kind
  (`/artifacts/mvmr`, legacy default was `/artifacts/mvmr_container`).
  DAG specs referencing the old kind must be regenerated.
- **Params via env**: the legacy wrapper baked every parameter into the
  R program with Rust string-building (empty env); the plugin renders
  `MVMR_*` env values and the script reads them with `Sys.getenv`.
  String arrays (`beta_xg`, `sebeta_xg`) render space-joined and are
  rebuilt with `strsplit`; booleans render `true`/`false` and convert
  with `as.logical`; optional params render as empty strings and test
  with `nzchar`. Column access uses `data[[name]]` (identical to the
  legacy `data$name` codegen, robust to non-syntactic names).
- **Diagnostic dispatch**: `strength`/`strhet`/`pleiotropy`/`qhet` stay
  booleans; the legacy compile-time choice between the upstream call and
  `NULL` became a script-side `if (flag) MVMR::… else NULL`. Result-slot
  semantics are unchanged (assigning `NULL` drops the slot, exactly like
  the legacy emitted `result$x <- NULL`).
- **`gencov` is gone as a param**: the legacy field was
  `#[schemars(skip)]`, had to be zero, and the R code ignored its value
  (`gencov <- 0` or `phenocov_mvmr`). The plugin derives gencov from
  `pcor` presence only, which is everything the legacy path supported.
- **`pcor` serialization (DSL gap)**: the v0 param vocabulary has no
  number-matrix type, so the legacy nested-array `pcor` travels as a
  row-major serialized string (rows `;`-separated, entries `,`-
  separated, e.g. `1,0.25;0.25,1`). The script rebuilds the exact legacy
  `matrix(..., byrow = TRUE)` construction and re-implements the legacy
  validation (square, finite, symmetric, unit diagonal, and
  `qhet requires a pcor matrix`). Replace with a structured param type
  once container-plugin grows one.
- **Validation moved into the container**: legacy `validate()` ran at
  DAG build time; its checks (non-empty columns, equal-length exposure
  vectors, pcor shape) now run at the top of the script with the same
  failure messages. `beta_xg`/`sebeta_xg` equal-length and `qhet ⇒ pcor`
  are cross-field rules the DSL cannot express (`requires` gates bools
  only), so they live in the script.
- **Output port labels**: legacy ports were unlabeled; manifest ports
  always carry labels, and both file stems are `mvmr`, so the outputs
  declare explicit `result` / `log` labels.
- Everything numerical — `format_mvmr` input construction, the upstream
  `ivw_mvmr` / `strength_mvmr` / `strhet_mvmr` / `pleiotropy_mvmr` /
  `qhet_mvmr` / `phenocov_mvmr` calls, the `sink`/`print` log epilogue,
  `saveRDS` output, and the output file names (`mvmr.RDS`, `mvmr.log`)
  — is byte-faithful to the legacy program.
