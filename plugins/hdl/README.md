# hdl plugin

Official HDL-L (R package `HDL` 1.4.3, zhenin/HDL @ `e6b055d`) as a
manifest plugin family with two node kinds sharing one image and one UKB
panel binding:

| kind | legacy wrapper | run shape |
| --- | --- | --- |
| `hdl_l` | `hdl_l_container` | one official `chr`/`piece` block per run |
| `hdl_l_scan` | `hdl_l_scan` | every block on one `chr` (optionally subset via `pieces`), loop stays script-side |

## Layout

```text
hdl/
├── manifest.toml          # family image + hdl_ref panel + both [[nodes]]
├── scripts/
│   ├── hdl_l.R            # region run (interpreter Rscript)
│   └── hdl_l_scan.R       # chromosome scan with the per-chr/piece loop
├── Dockerfile             # rocker/r-ver:4.5.1 + HDL 1.4.3 (fetched from
│                          # the pinned upstream tarball at build time)
├── .dockerignore          # excludes the vendored reference checkout
├── HDL-L/                 # vendored upstream source (reference copy)
├── test_hdl_l_podman.sh   # image smoke + nodes-io integration test
└── README.md
```

Image: `ghcr.io/auto-nomics/autonomics/hdl@sha256:cbce3f3e4037b8c53c59275240f4449f2041de39aa95a4b5d9e588b9a75b18ea`
(digest identical to the one the legacy wrappers pinned via
`registry_image("hdl", …)`). Provenance and version pins are documented in
the autonomics repo's `docs/container-node-migration.md` (HDL 1.4.3,
data.table 1.18.4, dplyr 1.2.1, GPL-3.0-or-later).

Panel: one shared `[[panels]]` binding `hdl_ref` →
`wjixiang/catalog-hdl-ref-ukb-eur` mounted at `/panels/hdl_ref`
(`LD/*_LDSVD.rda`, `LD/HDLL_LOC_snps.RData`, `bim/*.bim`). This is the
dedicated UKB EUR SVD/BIM package; the LAVA and generic 1000G PLINK
bundles are not interchangeable, exactly as the legacy wrappers enforced.

## Migration parity notes

Golden test: `crates/container-plugin/tests/hdl_migration.rs` in the
autonomics workspace (image/outputs/panels/timeouts byte-exact; script
assertions semantic).

### Parameter channel

The legacy wrappers inlined spec values into a generated R script via
`format!` (strings through Rust `{:?}`, i.e. the exact quoting the
template renderer now applies for non-`sh` interpreters). The plugin ships
one static script per kind and moves every parameter through the
`HDL_L_*` / `HDL_L_SCAN_*` environment variables declared in
`manifest.toml`; the script parses and validates them in a preamble. The
`HDL::HDL.L(...)` call shape, argument order, output wiring
(`AUTONOMICS_OUTPUT0/1/2`), `read_sumstats` column checks, panel
integrity checks, and (for the scan) the whole block loop are kept
token-identical to the legacy generated scripts.

### Compile-time vs script-side validation

The manifest DSL expresses everything the legacy `validate()` could,
except three checks that moved into the R preamble with the legacy error
messages:

1. trait-name emptiness after trimming (`trait1_name and trait2_name
   cannot be empty`);
2. the `fill_missing_n` vocabulary (`median`/`min`/`max`) — the v0 param
   vocabulary has no enum type, so the value is a plain optional string;
3. `pieces` positivity / integer shape / duplicate-freedom — the legacy
   `Option<Vec<u32>>` has no DSL equivalent (only `string_array`), so the
   blocks travel as numeric strings space-joined into `HDL_L_SCAN_PIECES`.

Numeric bounds (`chr` 1–22, `piece` > 0, `n0` ≥ 0, `nref` > 0,
`eigen_cut` ∈ [0,1], `alpha` ∈ (0,1], `lim` > 0) are enforced twice: at
compile time by the manifest bounds (with schema exposure to the agent)
and again in R as defense in depth.

### Deliberate contract deltas

- **Kinds** drop the `_container` suffix (`hdl_l_container` → `hdl_l`);
  `hdl_l_scan` was already suffix-free. DAG specs referencing the old
  kinds must be regenerated.
- **Artifact prefixes** follow the ldsc precedent and are kind-derived:
  `/artifacts/hdl_l` and `/artifacts/hdl_l_scan` (legacy defaults were
  `/artifacts/hdl_l_container` and `/artifacts/hdl_l_scan_container`).
- **Float spellings in env**: the renderer emits the serde_json/ryu form
  (`0.0`, `335272.0`, `1.522997974471263e-8`, `true`/`false` lowercase)
  where the legacy `format!` printed `0`, `335272`,
  `0.00000001522997974471263`, `TRUE`/`FALSE`. The R preamble parses both
  to identical values.
- **Scan failure semantics** unchanged: failed blocks are logged to the
  official log and skipped; the combined TSV, RDS list, and summary
  footer are emitted exactly as before.

## Image build

```sh
./test_hdl_l_podman.sh            # builds + smoke-checks + runs the
                                  # nodes-io integration test
./test_hdl_l_podman.sh RUN_TEST=0 # image build + version smoke only
```

`test_hdl_l_podman.sh` builds from this directory (no repo layout
assumed) and, for the integration-test leg, `cd`s into the autonomics
workspace (`AUTONOMICS_REPO_ROOT`, default
`/mnt/projects/autonomics_projects/autonomics`) where the
`container_file_flow` live tests still reside until the Rust wrappers are
deleted.

## Publish checklist

1. `rm -rf HDL-L/.git` — the vendored upstream checkout still carries its
   own `.git`; commit it as plain files or clones of this plugin will
   lack the payload (the `.dockerignore` already excludes it from builds).
2. `git init --initial-branch=main && git add -A && git commit`.
3. `gh repo create auto-nomics/hdl-plugin --private --source=. && git push -u origin main`.
4. Pin the commit SHA in `~/.autonomics/plugins.toml`
   (`name = "hdl"`, `git = …`, `rev = <sha>`).
5. Add the family to `plugin_wave_e2e.rs::FAMILIES` with kinds
   `["hdl_l", "hdl_l_scan"]` and re-run the wave e2e.
6. Delete `hdl_l_container.rs` / `hdl_l_scan_container.rs` in the
   autonomics workspace per the migration checklist (lib.rs `pub mod`
   lines, register blocks, `bundle_bound_nodes.rs` and
   `container_file_flow.rs` references).
