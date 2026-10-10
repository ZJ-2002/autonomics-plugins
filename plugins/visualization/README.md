# visualization plugin

Terminal-only ggplot2 plot renderer, migrated from the hardcoded Rust
wrapper `crates/node-bundles/nodes-io/src/visualization_container.rs`
(kind `visualization_container` → plugin kind `visualization`) following
`docs/plugin-node-migration.md`.

## Layout

```text
visualization/
├── manifest.toml        # node contract: params, ports, image, resources
├── scripts/
│   └── render.R.sh      # the live render runner (staged, run by Rscript)
├── Dockerfile           # image provenance (build + push still via GHCR)
├── render.R             # the image-baked copy of the runner (see below)
├── test_visualization.sh # image baseline: build + render a small PNG
└── README.md
```

## The user-script channel (important)

The node renders a **user-supplied R script**, and that script is **not a
manifest parameter** and **not a `[nodes.command.files]` entry** — the
`files` map holds manifest-static inline text only, and a per-run user
script is dynamic content. It reaches the container exactly as in the
legacy wrapper:

1. The DAG author wires a File holding the R script into input port 1
   (label `r_script`); port 0 (label `data`) carries the plot-ready data.
2. `ContainerCommandNode` stages both input files and exports them as
   `AUTONOMICS_INPUT0` (data) and `AUTONOMICS_INPUT1` (R script) inside
   the container.
3. `scripts/render.R.sh` (run as `Rscript /work/.autonomics/script`)
   preloads the data as `df` and `source()`s the user script in an
   isolated environment, then requires it to have assigned `p` and saves
   it with `ggplot2::ggsave` as immutable `plot.png`.

The user script must be a single constrained ggplot2 layer chain:
`p <- ggplot2::ggplot(df, ...) + ggplot2::geom_*() + ...`.

## Image

`ghcr.io/auto-nomics/autonomics/visualization@sha256:ee9592b77bc5ea0cebfafafbe39550c377204019f451d7a37e13e4ce2e884f15`
(tag `0.1.0`; `rocker/r-ver:4.5.3` + arrow `23.0.1.2` + ggplot2 `4.0.3`,
pinned in the Dockerfile's `stopifnot` lines).

The Dockerfile still `COPY`s `render.R` into the image so the pinned
digest stays reproducible from this tree, but the baked copy is now
vestigial: the live runner is `scripts/render.R.sh`, staged per run and
inserted at `argv[1]` (`Rscript /work/.autonomics/script`). Rebuilding the
image does not require republishing the manifest; changing the runner no
longer requires rebuilding the image.

## Migration parity notes

- Byte-exact vs the legacy `container_spec`: image reference, output
  (`plot.png` / `png`), `timeout_secs = 300`,
  `artifact_prefix = /artifacts/visualization_container` (explicit, so it
  does not fall back to the derived `/artifacts/visualization`), isolated
  network, read-only rootfs, pull policy `missing`, and the resource
  profile `cpus 2.0 / memory 2Gi / pids_limit 256`.
- Env channel identical: `AUTONOMICS_VISUALIZATION_{DATA_FORMAT,WIDTH,
  HEIGHT,DPI}` with the legacy `Sys.getenv` reads and the identical
  five-way `switch` dispatch.
- Known deltas (all recorded in
  `crates/container-plugin/tests/visualization_migration.rs`):
  - Defaults render through serde_json, so `width` 8.0 reaches the
    container as `"8.0"` where the legacy Rust `f64::to_string` produced
    `"8"`. `as.numeric()` parses both identically.
  - The compiled command is `["Rscript"]` + the staged script path, where
    the legacy command was `["Rscript", "/opt/autonomics/render.R"]`.
  - The legacy spec's optional `cpus`/`memory`/`pids_limit`/
    `timeout_secs`/`artifact_prefix` spec fields are manifest-level now;
    the compiled param schema is closed (`additionalProperties: false`).
  - `data_format` is a required `string` param (v0 has no enum param
    type); unsupported values fail at run time in the `switch`'s
    `stop(...)` branch with the legacy message instead of at
    schema-parse time.
  - The legacy Rust wrapper pre-validated the user script with an
    R-token allowlist (`validate_plot_script`) before starting the
    container; the manifest DSL has no per-node execute hook, so that
    pre-flight rejection does not exist on the plugin path. The runtime
    `p`-assignment check in the runner and the container hardening
    (isolated network, read-only rootfs, PID/CPU/memory caps) still bound
    what a submitted script can do.
  - The legacy wrapper node was `is_terminal() == true` (the DAG rejected
    downstream edges); `ContainerCommandNode` defaults to non-terminal,
    and v0 manifests have no `terminal` flag, so graph-level terminality
    is not currently enforced for the plugin kind.
