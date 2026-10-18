# Existing H5AD metadata I/O repair: evidence reconciliation

`h5ad_obs_to_dataframe` belongs to the engine, not this plugin repository.
It is native metadata transport, **not a Rust statistical-method port and not
a direct invocation of AnnData**. Its statistical-official layer is
`NOT_APPLICABLE`; this record must not be advertised as official-package
replacement or full AnnData equivalence.

The 2026-10-12 repair is already published in
[`ZJ-2002/autonomics`](https://github.com/ZJ-2002/autonomics/blob/e28f58a32d0eda996fde0b6644421fd889bc750e/crates/node-bundles/nodes-io/src/h5ad_obs_to_dataframe.rs).
The current module has the same SHA256. All three called path-resolution
function bodies also match the tested published versions, although unrelated
parts of the shared source file have changed. The old priority ledger still
pointed to the preceding unrepaired module; this reconciliation fixes that
accounting gap without repairing the same node again.

Reused sealed evidence covers 16 complete typed schema/value/SQL cases,
20 specific refusals, four path-namespace cases, ten executed unit tests and
seven actual factory/scheduler DAGs (four successful, three failed as expected).
The 432-file main packet and 1,196-file reference dependency are rehashed,
including actual outputs and original reference fixtures. No package environment
is copied or reinstalled, and no build, method calculation or DAG is repeated.

The typed reference uses the frozen AnnData 0.11.4/Pandas/PyArrow environment.
Two deliberate normalizations remain explicit: categorical dictionary keys
are canonical Int32, and an empty stored string category retains Utf8 rather
than adopting Arrow's null type inferred from no values. Category values,
levels/order, lexical IDs such as `1` versus `001`, and missingness are checked
under those conventions. This is not a claim of byte-identical author schemas
for every encoding or version. See the [AnnData format specification](https://anndata.readthedocs.io/en/stable/fileformat-prose.html).

This does not qualify annotations, donor independence, current complete engine
dependencies, a resident daemon, full-size workloads, all encodings/compressors,
sparse/multidimensional obsm, Zarr or scientific admission. Production and G0
remain unchanged. The four added Python tests check this card's declarations,
not the underlying scientific or data-format computation.

Evidence: `evidence/h5ad-obs-source-reconciliation-20261019.json`.
