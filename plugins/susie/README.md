# susie plugin

Official susieR fine-mapping (`susie_rss`), migrated from the hardcoded
Rust wrapper `crates/node-bundles/nodes-io/src/susie_rss_container.rs`
(kind `susie_rss_container` → plugin kind `susie_rss`) following
`docs/plugin-node-migration.md`.

## Layout

```text
susie/
├── manifest.toml            # node contract: params, ports, panel, image
├── scripts/
│   └── run_susie_rss.R.sh   # the live runner (staged, run by Rscript)
├── Dockerfile               # image provenance (build + push still via GHCR)
├── run_susie_rss.R          # the image-baked copy of the runner (see below)
├── susie_ld_query.py        # image-baked signed-LD query helper (still live)
├── fixtures/
│   └── chr21.sumstats.tsv   # chr21 smoke-test locus (snp/chrom/z/n)
├── test_susie_rss.sh        # image baseline: build, verify, push, smoke-test
└── README.md
```

## The signed-LD panel

The node queries signed LD pairs from the
`wjixiang/catalog-mixer-g1000-eur` catalog bundle, mounted read-only at
`/panels/mixer_ref`. The runner reads
`/panels/mixer_ref/stage_flat/chr@.bim` and
`/panels/mixer_ref/ld_mixer/1000G.EUR.chr@` — the mount path is
load-bearing. The panel is shared with the mixer family but bound by this
plugin independently (each plugin binds its own panels; the images
differ). The roughly 254-SNP `.snps` extraction lists in the panel are
mixer leftovers and are not an alignment constraint.

## The runner channel

The image bakes `/opt/susie/bin/run_susie_rss.R` and
`/opt/susie/bin/susie_ld_query.py`, but the **live runner is
`scripts/run_susie_rss.R.sh`**: the baked R runner adapted verbatim,
staged per run by `ContainerCommandNode` and executed as
`Rscript /work/.autonomics/script`. The Python LD-query helper has no
plugin-side copy in the execution path — the runner still calls the
image-baked `/opt/susie/bin/susie_ld_query.py`, which links against the
image-baked `libbgmg.so`.

Every parameter travels through the same `SUSIE_*` environment variables
the legacy `container_spec()` set; the runner reads each with
`Sys.getenv` + default, so an empty value means "use the default" exactly
like the legacy wrapper omitting the variable. Rebuilding the image does
not require republishing the manifest; changing the runner no longer
requires rebuilding the image.

## Image

`ghcr.io/auto-nomics/autonomics/susie@sha256:8a72a443461add5c94c4907f9a1d6106b989850e93217a95587d9095542febe8`
(tag `0.16.6`; susieR `0.16.6` @ `ef213fe` on `rocker/r-ver:4.5.1`, with
gsa-mixer `2.2.1` `libbgmg` for the LD query — pinned in the Dockerfile).

## Migration parity notes

- Byte-exact vs the legacy `container_spec`: image reference, the three
  outputs (`susie_rss.tsv` / `susie_rss`, `susie_rss.RDS` / `r_rds`,
  `susie_rss.log` / `susie_rss_log`), `timeout_secs = 1800`,
  `artifact_prefix = /artifacts/susie_rss_container` (explicit, so it does
  not fall back to the derived `/artifacts/susie_rss`), the single panel
  bundle (`wjixiang/catalog-mixer-g1000-eur` at `/panels/mixer_ref`),
  isolated network, read-only rootfs, pull policy `missing`, and no
  resource overrides (the legacy spec left cpus/memory/pids unset).
- Env channel identical: the eleven `SUSIE_*` keys plus `SUSIE_N`.
- The `susieR::susie_rss(...)` call, the panel mount paths, the LD-query
  invocation, and the TSV/RDS/log output layout are token-identical to
  the baked runner.
- Known deltas (all recorded in
  `crates/container-plugin/tests/susie_migration.rs`):
  - The compiled command is `["Rscript"]` + the staged script path, where
    the legacy command was `["Rscript", "/opt/susie/bin/run_susie_rss.R"]`.
  - Defaults render through serde_json, so `r2_min`/`check_null_threshold`
    `0.0` reach the container as `"0.0"` where the legacy Rust
    `f64::to_string` produced `"0"`. `as.numeric()` parses both
    identically (documented pitfall 8).
  - The legacy wrapper omitted the `SUSIE_N` key entirely when `n` was
    absent; the manifest's optional param renders an empty value. The
    runner's `nzchar(Sys.getenv("SUSIE_N", unset = ""))` treats both
    identically ("read the n column").
  - `estimate_prior_method` and `z_method` are plain `string` params (v0
    has no enum param type); the legacy `validate()` membership checks
    moved into the runner with the byte-identical error messages
    (`estimate_prior_method must be one of: optim, EM, simple`,
    `z_method must be one of: wald, score`). The failure point moves from
    registry build to container start, exactly as in the
    deseq2/visualization migrations. All numeric and integer bounds
    (`l >= 1`, `coverage/min_abs_corr/r2_min` in `[0, 1]`,
    `scaled_prior_variance > 0`, `max_iter >= 1`, `timeout_secs >= 1`,
    absolute `artifact_prefix`) stay at compile time through the manifest
    DSL.
  - The legacy spec's `artifact_prefix` and `timeout_secs` spec fields are
    manifest-level now; the compiled param schema is closed
    (`additionalProperties: false`).

## Test

```sh
./test_susie_rss.sh   # builds, verifies the panel + image, pushes, smoke-tests
```

The golden parity test lives at
`crates/container-plugin/tests/susie_migration.rs` (skipped when this
directory is absent; `NODE_PLUGINS_ROOT` overrides the checkout root).
