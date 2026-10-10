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
