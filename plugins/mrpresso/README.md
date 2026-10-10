# mrpresso plugin

Migrated from the legacy `mrpresso_container` wrapper in nodes-io. One
directory = one plugin family = one git-able unit.

## Layout

- `manifest.toml` — node kind `mrpresso`: params, ports, image provenance
- `scripts/mrpresso.R.sh` — the R script (referenced relatively and inlined
  by the loader at startup; the `.sh` suffix is a family naming convention,
  the content is R and the interpreter is `Rscript`)
- `Dockerfile` — image build provenance (moved verbatim from
  `containers/mrpresso/`; build + push still via GHCR)
- `test_mrpresso.sh` — image smoke test (`root=` repointed to this
  directory)
- `fixtures/summary_stats_headers.csv` — sample sumstats header fixture
  (moved verbatim; referenced by no Rust test)

## Provenance

- Image: `ghcr.io/auto-nomics/autonomics/mrpresso@sha256:a3c467…7e2a4`,
  tag `1.0.0`, from `Dockerfile` (base `rocker/r-ver:4.5.1`).
- Upstream: [rondolab/MR-PRESSO](https://github.com/rondolab/MR-PRESSO)
  at revision `3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87`, installed from
  source; license GPL-3.

## Migration parity

The golden test (`crates/container-plugin/tests/mrpresso_migration.rs`)
compares the compiled `ContainerCommandSpec` against the legacy Rust
wrapper: image, outputs, resources, and command are byte-equal; the
script differs structurally (env-driven instead of Rust string building)
but preserves the exact `MRPRESSO::mr_presso` call, the `sink`/`print`
log epilogue, and the `saveRDS` artifact. Deliberate deltas:

- **Kind rename**: `mrpresso_container` → `mrpresso`; the artifact prefix
  follows the kind (`/artifacts/mrpresso_container` → `/artifacts/mrpresso`).
  DAG specs referencing the old kind must be regenerated.
- **`timeout_secs` / `artifact_prefix` are node-level constants** (900 s,
  `/artifacts/mrpresso`) instead of per-instance spec params; the legacy
  spec accepted per-node overrides, the plugin DSL does not.
- **Params travel via env** (`MRPRESSO_*`). String arrays are space-joined
  by the env renderer and re-split in R with a single-space `fixed = TRUE`
  `strsplit` — the exact inverse of the join. Array elements containing
  spaces cannot round-trip; GWAS effect/SE column names never contain them.
- **Booleans** render as `true`/`false` and are read with `as.logical()`,
  which accepts both spellings, matching the legacy embedded `TRUE`/`FALSE`.
- **Numbers** are read with `as.numeric()`; R parses the rendered literals
  identically to the legacy embedded literals.
- **Validation moved into the script**: the legacy Rust `validate()`
  checks the DSL cannot express (non-empty `beta_outcome`/`sd_outcome`,
  `beta_exposure`/`sd_exposure` equal non-empty lengths) are enforced by
  `stop()` guards with the legacy error messages; `min_len = 1` on the
  arrays and the `signif_threshold`/`nb_distribution` bounds cover the
  rest. The failure point moves from registry build to container start.
- **Bound nuance**: legacy code accepted `signif_threshold` in `[0, 1]`
  (its error message said `(0, 1]`); the manifest encodes the code, not
  the message: `min = 0.0, max = 1.0`.
