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

- Image: `ghcr.io/zj-2002/mrpresso@sha256:5ecce3690fc69a051483463c7697df3147772c2cc69a171c5d83784b238a9ca8`,
  actual package `MRPRESSO 1.0` on `R 4.5.1`, from the fixed-author-source image.
- Upstream: [rondolab/MR-PRESSO](https://github.com/rondolab/MR-PRESSO)
  at revision `3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87`, installed from
  source; license GPL-3.

The former `auto-nomics` reference was absent from both inspected local
backends. The selected reference is already installed, is the reference
expected by the engine migration test, and resolves to the same image
configuration and layers as the existing official research-adapter image.
The installed method's complete function body and formals were compared
with the author's exact source at the pinned commit. No image was rebuilt,
pulled or substituted merely because it had a similar package name.

This corrects image availability only. The one-input/two-output wrapper is
not certified by the two-input/five-output research adapter's proof. Its
space-joined array transport and output-overwrite behavior remain separate
review items; this image repair does not close the entire node or grant
scientific use. The label `1.0.0` describes the image, not the official
package version, which is `1.0`.

The global test is always computed by the author function. `outlier_test`
controls the subsequent individual-SNP test, not whether to run the global
test. `distortion_test` concerns the change in the causal estimate after
outlier removal and is effective only when outlier testing is active; it
is not a covariate balancing test.

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
  `strsplit`. This is lossless only when every element contains no spaces;
  the current schema does not enforce that restriction. Lossless array
  transport remains an open wrapper repair, not an assumed property of
  every GWAS input column.
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
