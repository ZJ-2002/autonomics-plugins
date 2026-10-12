# Original H5AD export interface assurance

`h5ad_export_matrix` remains one H5AD input, the original `layer` and `chunk`
parameters, and four output Files: nonzero expression Parquet, observation TSV,
variable TSV and log. The expression schema stays string `cell_id`, string
`gene`, float64 `value`. This is faithful selected-matrix transport, not a
normalization, count-provenance, species/gene mapping or statistical method.

Only the selected `X` or `layers/<name>` element and complete observation and
variable metadata are read. Plain layer names remain accepted; the documented
`layers/<name>` syntax now also works. AnnData's public `read_elem` and
`sparse_dataset` decode metadata and backed CSR/CSC storage; dense HDF5 datasets
are sliced by rows. No full-matrix fallback or transpose is guessed. Shape,
sparse pointers and indices, unique nonempty axes, and unambiguous metadata
headers are checked. All-zero/empty axes are valid transport, not inference.

Noncanonical sparse coordinates are coalesced and zeros eliminated, retaining
one row per nonzero matrix coordinate in cell-major/gene-major order. Integer
values must be exactly representable by the existing float64 port: representable
wide integers remain supported, while silent rounding is refused. Duplicate
integer coordinates use arbitrary-precision addition before checking final
float64 representability; sums overflowing the original storage dtype refuse
instead of emulating fixed-width overflow. Floating values,
including explicit NaN/infinities, are transported and counted in the log; they
are not certified estimable or biologically valid observations.

The complete axes in metadata disambiguate absent zero coordinates from explicit
NaN values. TSV uses Pandas' quoted output and preserves literal strings such as
`NA`, leading zeros, Unicode, tabs and newlines. The log retains metadata dtypes,
missing row masks, categorical levels/order and original index names. Readers
must use those masks rather than infer nulls from strings or erase empty values.
Existing metadata columns colliding with `cell_id` or `gene_id` refuse instead
of silently renaming fields. No donor identity is inferred.

All four outputs stage before publication. Input identity is checked before and
after computation. Existing/dangling/aliased output paths refuse; ordinary
publication errors remove only this invocation's already-linked output inodes.
This is no-clobber publication with ordinary rollback, not cross-file
crash-atomic commit, checkpoint recovery or an absolute full-scale memory bound.
Engine error reports/stderr must be retained for failed runs. Image/deployment,
global quotas, study locks and scientific/G0 approval remain separate gates.

`tests/test_export_assurance.py` requires the actual dependencies and executes
whole output comparisons and real entry-point refusals; dependency absence does
not become a passing skip. The reference directly invokes official AnnData
reading and Pandas serialization with independent full coordinate enumeration.
It is not a fresh complete software-stack installation or a statistical
algorithm certification. Structural/axis/metadata/integer checks are exact;
float transport is exact, including source-defined NaN masks.

Official API references:
- https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_elem.html
- https://anndata.readthedocs.io/en/stable/generated/anndata.io.sparse_dataset.html
