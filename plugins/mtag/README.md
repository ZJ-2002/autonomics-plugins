# mtag plugin

Migrated from the legacy `mtag_container` wrapper in nodes-io. One
directory = one plugin family = one git-able unit.

## Layout

- `manifest.toml` — node kind `mtag`: params, ports, panel binding,
  image provenance
- `scripts/h2.sh` — the execution script, referenced relatively and
  inlined by the loader at startup
- `Dockerfile` — image build provenance (moved verbatim from
  `containers/mtag/`; the build context is this directory, since the
  Dockerfile COPYs `mtag/…` paths; build + push still via GHCR)
- `.dockerignore` — moved verbatim
- `mtag/` — vendored upstream JonJala/mtag source as plain files (the
  embedded `.git` was stripped per the plugin-migration workflow; the
  upstream commit is pinned in the Dockerfile
  `org.opencontainers.image.revision` label, the manifest `upstream`
  field, and `test_mtag_containers.sh`)
  - `mtag/ld_ref_panel/eur_w_ld_chr/` — the official 1000G EUR
    eur_w_ld_chr w-LD scores used to build and publish the catalog
    bundle `wjixiang/catalog-mtag-ld-ref-1000g-eur-w-ld` (input to the
    panel-publishing flow only; runtime panel mounts resolve through
    the catalog, never this tree)
- `make_baseline_fixture.py` — deterministic two-trait baseline
  generator for the end-to-end test
- `test_mtag_containers.sh` — image + panel + E2E baseline; `root=`
  repointed to this directory. The catalog and Rust-E2E steps invoke
  cargo, so run it from the autonomics workspace checkout (the cargo
  invocation targets `nodes-io --test container_file_flow
  real_catalog_backed_official_mtag_runs_in_podman`, which still
  registers the legacy wrapper factory until the wrapper is deleted)
- `fixtures/` — generated baseline notes (outputs are not committed)

## Provenance

- Image: `ghcr.io/auto-nomics/autonomics/mtag@sha256:28ac0a0a0ee741340390b7588bf8ba36e6b316d62adc0cab7fd4494f5dd6a90c`,
  tag `1.0.8`, from `Dockerfile` (base `python:2.7.18-slim-buster`
  with a `bitarray==0.8.1` builder stage).
- Upstream: [JonJala/mtag](https://github.com/JonJala/mtag) 1.0.8 at
  revision `9e17f3cf1fbcf57b6bc466daefdc51fd0de3c5dc`; license GPL-3.

## Migration parity

The golden test (`crates/container-plugin/tests/mtag_migration.rs`)
compares the compiled `ContainerCommandSpec` against the legacy Rust
wrapper: image, outputs, panel bundle, resources, timeout, and command
are equal; the script differs structurally (env-driven optional flags
instead of Rust string building) but preserves the exact official
invocation tokens and flag order. Deliberate deltas:

- **Kind rename**: `mtag_container` → `mtag`; the artifact prefix
  follows the kind (`/artifacts/mtag_container` → `/artifacts/mtag`).
  DAG specs referencing the old kind must be regenerated.
- **`timeout_secs` / `artifact_prefix` are node-level constants**
  (3600 s, `/artifacts/mtag`) instead of per-instance spec params; the
  legacy spec accepted per-node overrides, the plugin DSL does not.
- **Params travel via env** (`MTAG_*`). `time_limit_hours` and `tol`
  always render (defaults 1.0 and 1e-6); the six official boolean
  flags are `optional = true` and are tested with `[ -n "$VAR" ]`, so
  an omitted param means the flag is left off exactly like the legacy
  `if spec.force { push("--force") }`. Nuance inherited from the
  ldsc-munge pattern: explicitly submitting `false` renders `"false"`
  (non-empty) and therefore appends the flag — the schema steer is to
  omit a flag rather than submit `false`.
- **Cross-field rule via the DSL**: `equal_h2 = { requires =
  ["perfect_gencov"] }` — the compile-time `check_requires` gate
  enforces the legacy `validate()` rule ("equal_h2 requires
  perfect_gencov") at spec-compile time; mtag is the first family to
  use the gate, so no script-side guard exists.
- **Numbers render with the serde_json spelling**: `1.0` → `"1.0"`
  (legacy `format!` produced `"1"`), `1e-6` → `"1e-6"` (legacy
  produced `"0.000001"`). Equal after float parsing, which is what the
  official argparse `float` does (documented pitfall 8).
- **No gzip stanza, on purpose**: the legacy mtag script passed both
  inputs straight through (no `decompress_gzip_inputs` helper), so the
  plugin script does too — plain TSV is expected, unlike ldsc.
- **validate() coverage**: `time_limit_hours`/`tol` finite and > 0 →
  `exclusive_min = 0.0`; `timeout_secs > 0` and the absolute
  `artifact_prefix` are enforced by loader validation; two File inputs
  and the three outputs match the legacy port layout and formats
  (`mtag_results` × 2, `mtag_log`).
- **Test-script deltas**: `root=` repointed to this directory; the
  `git submodule update` guard and `git -C … rev-parse` commit probe
  were replaced by a static upstream pin (the vendored `.git` is
  stripped); the dead `AUTONOMICS_MTAG_IMAGE_PREFIX` export was
  dropped (no reader anywhere in `crates/`).
