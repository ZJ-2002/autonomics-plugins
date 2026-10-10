# HyPrColoc plugin

The family also exposes `cachexia_hyprcoloc_official`, an opt-in six-input
research-contract route. It calls the same digest-pinned official package;
the legacy `hyprcoloc` node and its input contract remain unchanged and are
not certified by this addition. The strict route requires ordered SNP effects,
trait identities, a frozen hash/method contract, trait correlation, overlap,
and signed LD. It publishes the complete typed result, RDS, log and ledgers.
It must not infer unknown covariance, call a missing result negative, or grant G0.

The scope and independently rebuilt official comparisons are recorded in
`ZJ-2002/autonomics` at `docs/audits/cachexia-v4.1-2026-10-07/HYPRCOLOC_NODE_PROOF.md`.
Publication does not update any deployed `plugins.toml` pin. Upstream rapid
sensitivity with `reg_steps > 0` remains blocked because of its known defect;
no full-domain, `cred.sets`, `sensitivity.plot`, or production-daemon acceptance
is implied.

Manifest plugin for official R `hyprcoloc` (Foley and Staley, version 0.0.2,
commit `0348bbd`) on the Podman-backed DAG runtime.

Reference: <https://jrs95.github.io/hyprcoloc/>

## Layout

```text
hyprcoloc/
  manifest.toml           # node contract: params, ports, image
  Dockerfile              # image provenance (build + push via GHCR)
  scripts/hyprcoloc_runner.R
  test_hyprcoloc.sh
  fixtures/test-summary-stats.tsv
  README.md
```

The image contains only the official R package and its pinned runtime
(CRAN snapshot 2025-06-15, with the upstream-recommended RcppEigen
0.3.3.9.3). No LD matrix, trait-correlation matrix, GWAS summary statistics,
or user data are baked into the image.

## Build, smoke, publish

```sh
./test_hyprcoloc.sh
```

The script builds `localhost/atc/hyprcoloc:0.0.2` and smoke-tests it with
Podman. `manifest.toml` pins the published digest.

## Contract

One SNP-aligned tab-separated File in; the official result table, the full
R result object, and an execution log out. The node delegates all numerical
analysis to `hyprcoloc::hyprcoloc()` and reimplements nothing.

The legacy wrapper generated the R script in Rust (a string template with
conditional optional arguments). The plugin ships the equivalent as
`scripts/hyprcoloc_runner.R`: every parameter travels through
`HYPRCOLOC_*` environment variables, and the conditionals the v0 manifest
DSL cannot express — the optional official arguments (`trait.subset`,
`reg.thresh`, `align.thresh`, `prior.12`), the cross-field trait
validation, and the branch-and-bound threshold floors — live in the script
with the legacy error semantics. The failure point moves from registry
build to container start, exactly as in the deseq2/mrpresso/mvmr
migrations.

`traits` encodes the legacy `Vec<TraitSpec>` as one
`name,beta,se,binary_outcome` row per trait in the official matrix column
order, rows joined by `;`. Trait names and column names must not contain
`,` or `;` — the same serialized-string trade the deseq2 covariates and
mvmr pcor migrations made for list-valued params.

## Migration parity

Migrated from the hardcoded wrapper
`crates/node-bundles/nodes-io/src/hyprcoloc_container.rs` (kind suffix
`_container` dropped, artifact prefix renamed to match). Image, command,
outputs, env defaults and the unset resource knobs are byte-identical to
the legacy `container_spec`; the script keeps the legacy semantic markers —
asserted by `crates/container-plugin/tests/hyprcoloc_migration.rs`. The
image digest is unchanged.
