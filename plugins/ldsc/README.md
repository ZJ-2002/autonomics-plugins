# ldsc plugin

Migrated from the legacy `ldsc_h2` wrapper in nodes-io (M5 pilot). One directory = one plugin family = one git-able unit.

## Layout

- `manifest.toml` — node kind `ldsc_h2`: params, ports, panels,
  image provenance
- `scripts/h2.sh` — the execution script, referenced relatively and
  inlined by the loader at startup

## Install

```sh
export AUTONOMICS_PLUGIN_ROOT=/mnt/projects/node-plugins
cargo test -p data-engine --features bundle-plugin   # wiring test
```

Enable `bundle-plugin` on the `data-engine` dependency and the runtime
picks this directory up at startup.

## Migration parity

The golden test (`container-plugin/tests/ldsc_migration.rs`) compares the
compiled `ContainerCommandSpec` against the legacy Rust wrapper's output:
image, panels, outputs, resources, and env are equal; the script differs
structurally (env-driven optional flags instead of Rust string building)
but preserves the exact official invocation semantics, including gzip
input handling.

## Munging original input assurance (2026-10-12)

`ldsc_munge` passes the actual source with `--sumstats` and transports the
manifest's uppercase environment keys to exact official hyphenated options
(`--N-col`, `--N-cas-col`, `--N-con-col`, `--n-min`, etc.). Values stay separate
argv elements. The original `.log` is published once; separate process
diagnostics are forwarded to the runtime stderr stream. Gzip inputs are
materialized in the private workspace before the official reader.

The source/sign convention can be explicitly specified with `signed_sumstats`
(e.g. `Z,0`) or `a1_inc`; they require scientific review for each source. The
legacy `a1_is_a2` field has no corresponding official parser option: a true
request is rejected, preserving old spec parsing without inventing semantics.
The original CLI splits header names on whitespace; literal argv transport
does not make whitespace-bearing column headers scientifically supported.

Eight required offline tests exercise every exposed argument, gzip, presence
flags, failures and literal transport. Separate measured container evidence
checks complete 1,000-SNP plain/gzip tables against direct official CLI output
in the pinned image, including IDs, N and signed Z. It uses a private writable
Podman root with a read-only additional image store, no network, and bounded
CPU/memory. Run explicitly:

```sh
python -B plugins/ldsc/tests/run_munge_container_assurance.py \
  --output /absolute/new-private-evidence-directory \
  --shared-image-store /absolute/existing-image-store
```

Evidence: `evidence/canonical-ldsc-munge-original-input-v1-20261012.json`. This
is scoped munging input/CLI parity using synthetic GWAS. It does not qualify
h2/rg inference, complete LD panels, the full A_ARCH pipeline, G0 or formal
research. Current h2/rg outputs remain formatted logs, not full-precision
numeric result tables for confirmatory family correction.

The h2/rg wrappers also publish the actual official `.log` instead of an
empty stdout capture, create private gzip materialization directories, and
keep optional arguments as separate argv elements. RG's known swallowed
component-exception marker is converted to a failed node while retaining
its diagnostic log. Six additional required offline wrapper tests cover
these semantics; they are not h2/rg numerical method qualification.

## Actual inference runtime defect (2026-10-12)

A subsequent actual container probe found the pinned image's CLI references
`estimate_h2`/`estimate_rg`, but its refactored module exposes
`estimate_heritability`/`estimate_genetic_correlation`. Calling those exposed
functions directly then fails chromosome-split panel lookup. Therefore the
existing h2/rg log kinds are not numerical-ready; their previous shell tests
only checked transport/log handling. Actual munging parity remains scoped to
munging. The image is preserved, not relabelled as repaired.

The separately opt-in `plugins/ldsc-precision` family reuses the previously
acquired pristine CBIIT runtime with full-precision objects and scoped actual
container parity. It still requires complete88-pair/native lineage, real
panel/method acceptance and scientific gates. See
`evidence/canonical-ldsc-inference-runtime-blocked-20261012.json`.
