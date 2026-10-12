# `h5ad_subset_by_obs`: bounded engineering contract

This original canonical kind accepts H5AD at input 0 and selection Parquet at
input 1, publishing `output.h5ad` and `report.json` at output 0 and output 1.
The unchanged image is
`ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20`.
The injected implementation is `scripts/subset_by_obs.py`, not the historical
image-baked generic workflow. No other node's implementation changes here.

`join_column=cell_id` selects lexical `obs_names`, even if an obs column named
`cell_id` also exists. Otherwise the named obs column selects group membership:
one donor/group value may legitimately retain several cells. Input observation
order wins over request order. Numeric-looking IDs remain lexical: `001` is not
`1`. There is no cast, trimming, alias resolution or missing-value imputation.

The supported contract requires unique nonempty observation/variable axes and
unique nonempty lexical requests. All request values must match. Duplicate,
missing, unknown, numeric or control-character requests are refused, rather
than silently deduplicated/coerced/partially accepted. Group columns may repeat
values but must contain nonempty lexical strings throughout. These are explicit
wrapper admission rules, not a claim that AnnData itself imposes those rules.

The implementation delegates selection to official AnnData boolean slicing.
It preserves X, raw, layers, obs/var, obsm/varm, obsp/varp and uns under that
slicing operation. The only declared annotation change is replacing
`uns['subset_params']`, reported explicitly when already present. Preexisting
graphs, embeddings and statistical annotations are sliced, **not recomputed**.

The report distinguishes requested unique values from retained cells, preventing
the historical negative `missing_cells` value for group selection. Legacy
`requested_unique_cells` remains an alias for request count, not a donor or cell
replicate count; `requested_unique_values` is the unambiguous field. Output hashes,
input/selection hashes and the input-order cell ledger are recorded. Outputs are
staged and published without replacement, with inode-specific rollback on an
ordinary second-publication error. This is not crash-atomic transaction or resume.

The entire AnnData container is materialized in memory. No full-size memory or
throughput qualification is claimed. This is an identity-safe selection primitive,
not raw-count QC, pseudobulk, donor qualification, a normalization method or a
scientific gate. It grants neither study readiness nor G0.

Run `SUBSET_ASSURANCE_EVIDENCE=/new/path bash test_subset_assurance.sh` from a
complete pinned monorepo checkout. Missing image/dependency or any failed assertion
fails the entrypoint; no test is silently skipped. The direct author-reference
calls use the official AnnData/pandas packages already installed in the same
digest-pinned image, independently of the wrapper. This packet does not claim a
new download or independent installation of those packages.
The evidence packet additionally rechecks five inherited author payload sets and
a freshly downloaded official PyArrow wheel against the unchanged image. That
payload provenance check is distinct from the independent direct slicing call.

The legacy family-global model binding is still required by native registration,
although this node never opens or unpickles a CellTypist model. Native acceptance
therefore supplies and hash-verifies that unchanged binding. Removing this shared
family dependency is not part of this per-node repair.

Official selection semantics:
- [AnnData API](https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html)
- [pandas exact membership API](https://pandas.pydata.org/docs/reference/api/pandas.Series.isin.html)
