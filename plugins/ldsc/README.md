# ldsc plugin

## Official runtime migration (2026-10-15)

Current scope, corrected-output proof and withdrawn historical claims are recorded
in [the migration audit](../../docs/ldsc-author-runtime-migration-20261015.md).

The current manifest uses the unmodified author runtime at
`ghcr.io/zj-2002/ldsc@sha256:e98d2a89b0412384bbec1369250d935868a919f8a164c4ce55b282ac13495767`.
It is the publicly published equivalent of the previously measured pristine
image: the image configuration, all Python source files and package identities
are unchanged. CBIIT/ldsc source is fixed at
`6c673952cee74bd5c57aef1555a03b1c015399a0`, with its
[GPL v3 license](https://github.com/CBIIT/ldsc/blob/6c673952cee74bd5c57aef1555a03b1c015399a0/LICENSE).
The Dockerfile deliberately reuses that immutable runtime; it does not build
the retired refactored `ldsc-python3/` tree. That historical source remains for
provenance, not active method execution. No statistical formula is rewritten.

The base also contains legacy PATH aliases. They are not an official-method
reference: all three adapters explicitly invoke `python` with the measured
`/opt/cachexia-official-ldsc/ldsc.py` or `munge_sumstats.py` path. Mere presence
of pristine source in an image does not prove that its default CLI dispatches
to that source. Runtime inspection and numerical references must bind the
actual dispatched file, not just the image name or version banner.

Old-image inference failures remain genuine failed evidence. A digest change
does not certify these wrappers: all three entrypoints need the new runtime's
actual independent CLI parity and separate engine/deployment checks. The h2/rg
ports remain raw logs, not full-precision inferential tables; A_ARCH family P
must use the explicit full-precision route, not values parsed from display logs.
Actual reference-panel eligibility and study authorization remain independent.
The current adapter also preserves author stdout when the author-created log
is empty, rejects a successful exit without any result, and retains separate
author stderr diagnostics. Earlier empty-log comparisons did not establish rg
output correctness and are explicitly superseded by the migration evidence.
Historical installation/migration and 2026-10-12 evidence below retain their old
scope; they are not current-runtime certificates.

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
