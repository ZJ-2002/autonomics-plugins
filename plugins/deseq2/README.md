# deseq2 plugin

Migrated from the legacy `deseq2_container` wrapper in nodes-io. One
directory = one plugin family = one git-able unit. The original
container-era README moved with the build tree as
`container_README.md` (verbatim, modulo its now-regenerated kind and
`$AUTONOMICS_IMAGE_PREFIX` spellings — image references are self-contained
digest pins since the prefix's removal).

## Layout

- `manifest.toml` — node kind `deseq2_de`: params, ports, image
  provenance, resources
- `Dockerfile` — image build provenance (moved verbatim from
  `containers/deseq2/`; build + push still via GHCR)
- `deseq2_runner.R` — the baked runner, `COPY`-ed to
  `/opt/autonomics/deseq2_runner.R` by the Dockerfile; the manifest
  declares no script, only `interpreter = "Rscript"` plus fixed argv
- `test_deseq2.sh` — full image baseline (build, run the pasilla model
  twice, checksum-compare against the fixture baseline, independently
  recompute size factors / normalized counts, negative-path checks);
  `root=` repointed to this directory
- `test_deseq2_fixture.sh` — fixture validation without R or Podman;
  `root=` repointed, fixture directory env-overridable
- `test_deseq2_data_boundary.sh` — asserts the image carries no pasilla
  fixture and no `/panels`; moved verbatim
- `container_README.md` — the original containers/deseq2/README.md

**Fixtures did not move.** The pasilla fixtures remain in the autonomics
repository at `containers/deseq2/fixtures/` because still-live nodes-io
Rust tests read them there (`wgcna_container.rs`,
`limma_voom_container.rs`, `bulk_rnaseq_real_podman.rs`, and the legacy
`deseq2_container.rs` integration test until that wrapper is deleted).
The moved test scripts default `DESEQ2_FIXTURES` to the repository path
and accept an override.

## Provenance

- Image:
  `ghcr.io/auto-nomics/autonomics/deseq2@sha256:8b2e2a78d87293e6cae6dbed2e283dff1dd8461a7f993cb347ca9810698b2b3e`,
  tag `1.50.2`, from `Dockerfile` (base `rocker/r-ver:4.5.3`, itself
  digest-pinned).
- Upstream: official Bioconductor
  [DESeq2](https://github.com/thelovelab/DESeq2) 1.50.2 source tarball
  (sha256 `514f23ae8d274623d80978c30bfa1c6566acd98188bf1aa563970959ea59522f`,
  revision `d90821a`) installed into Bioconductor release 3.22; license
  LGPL-3.0-or-later.

## Migration parity

The golden test (`crates/container-plugin/tests/deseq2_migration.rs`)
compares the compiled `ContainerCommandSpec` against the legacy Rust
wrapper (`nodes-io/src/deseq2_container.rs`): image, command, outputs,
resources, timeout, env keys/values, and the script-less shape are
byte-equal. Deliberate deltas:

- **Baked runner preserved as argv.** The legacy wrapper passed
  `["Rscript", "--vanilla", "/opt/autonomics/deseq2_runner.R"]` with
  `script: None`; the manifest expresses exactly that with
  `interpreter = "Rscript"` and `argv` (the DSL's baked-runner shape).
  Parameters travel through the `AUTONOMICS_DESEQ2_*` environment
  variables, so the pinned image needs no rebuild per invocation.
- **Kind rename**: `deseq2_de_container` → `deseq2_de`; the artifact
  prefix follows the kind (`/artifacts/deseq2_de_container` →
  `/artifacts/deseq2_de`), the same rule the ldsc/mrpresso/mvmr
  migrations applied. DAG specs referencing the old kind must be
  regenerated. Note the run report produced inside the pinned image
  still carries `"node": "deseq2_de_container"`; that string is baked
  into the runner and changes only with the next image build.
- **`timeout_secs` / `artifact_prefix` are node-level constants**
  (3600 s, `/artifacts/deseq2_de`) instead of per-instance spec params;
  the legacy spec accepted per-node overrides, the plugin DSL does not.
- **`covariates` shape change**: the legacy spec carried a string array
  and Rust joined it with `","` into `AUTONOMICS_DESEQ2_COVARIATES`. The
  v0 env renderer space-joins arrays, while the baked runner splits the
  variable on commas (`strsplit(value, ",", fixed = TRUE)`), so the
  manifest declares a plain string carrying the comma-separated list —
  byte-identical env for every legacy-legal input (legacy covariates are
  simple R identifiers, which never contain commas or spaces). Same
  serialized-string pattern as the mvmr `pcor` migration. The runner
  re-validates duplicates, reserved names, R-identifier shape, and
  column existence.
- **`fit_type` loses its enum**: the v0 param vocabulary has no enum
  type (it arrives with the panel-selection wave), so it is a string
  with default `parametric`; the runner rejects anything outside
  `parametric`/`local`/`mean` with the legacy message.
- **Validation moved into the runner**: the DSL cannot express
  `condition_test != condition_reference` or the covariate identifier
  rules; the baked runner enforces them (and rank-deficiency, data
  shape, sample-set equality) with the legacy error messages. The
  failure point moves from registry build to container start. The DSL
  carries what it can: `alpha` strict (0, 1) via `exclusive_min` /
  `exclusive_max`, `threads` pinned to exactly 1 via `min = max = 1`.
- **Resources pinned**: 2 CPUs, `4Gi` memory, pids limit 256, `1Gi`
  shm, isolated network, read-only rootfs, pull policy `missing` —
  the legacy wrapper's exact defaults; the manifest relies on the
  hardened defaults for the three boolean/enum fields.
- **Ports**: the two labeled input ports (`count_matrix`,
  `sample_metadata`) carry over exactly. Output ports gain file-stem
  labels (`results`, `normalized_counts`, `size_factors`,
  `deseq2_dataset`, `run_report`) because the manifest pipeline always
  names output ports; the legacy ports were unlabeled — the same
  accepted delta as the mvmr migration.
