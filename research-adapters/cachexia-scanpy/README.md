# Frozen Scanpy/AnnData workflow adapters

This staged manifest is not registered in the resident daemon. It covers five
explicit candidate roles, not all single-cell preprocessing or biological cell
annotation. The image pins Scanpy 1.11.3 and AnnData 0.11.4, with frozen numerical
dependencies. Cell-level marker and cluster summaries are descriptive/exploratory,
never donor-level B inference, pseudobulk replacement or G0.

| Node | Inputs | Method / output H5AD |
| --- | --- | --- |
| `cachexia_sc_dense_ingest` | Matrix TSV, contract JSON, full cell metadata TSV | Explicit orientation/axes/scale; AnnData with unchanged values, no normalization |
| `cachexia_h5ad_subset` | H5AD, contract JSON, string `cell_id` Parquet | Official AnnData exact-cell slicing; all requested IDs must exist and be unique |
| `cachexia_h5ad_embedding` | H5AD, contract JSON | Official normalization/log, HVG, PCA, neighbors, UMAP and Leiden; no stale PCA reuse or silent dimension clipping |
| `cachexia_h5ad_rank_genes` | H5AD, contract JSON | Official four supported marker methods; full `uns` object and all marker numerical fields |
| `cachexia_h5ad_cluster_means` | H5AD, contract JSON | Official aggregate `mean`/`count_nonzero`; all-gene library totals precede selected-gene summaries |

Each node declares five ports: `result.parquet`, `output.h5ad`, `audit.json`,
`scanpy.log` and `gene_ledger.tsv`. Primary Parquet specifies string identities,
Int64 counts/ranks and nullable Float64 statistics explicitly. Numerical official
NaN or absent fields become typed NULL; full H5AD `uns` preserves the original
objects, including NaN/Inf. Literal string `NA` and leading-zero cell/gene/group
identities are not numerical missingness. Logistic marker ranks have no invented
P values or hidden fallback.

The exact 17-key JSON schema is `KEYS`, with complete mode-specific `PARAMS`,
in `scripts/workflow.py`. It freezes full ordered cell/gene axes, raw input hashes,
layer and scale, matrix/input-byte budgets, descriptive role, and every supported
method parameter. There are no runtime method defaults. Third-file hashes are
required only for ingestion/subsetting; other modes require `NOT_APPLICABLE`.

Embedding retains all genes using an explicit HVG mask, preserves untouched
count layers/unrelated slots, and creates `cachexia_model_log1p` before optional
scaling. Previously produced PCA/graph/result fields are rejected until explicitly
qualified outside this adapter; they are not silently reused. Available HVGs must
support the exact requested PCA dimension. The returned modeled `X` is not a
replacement for untouched counts in differential inference.

Subset output follows declared input-cell or selection order. AnnData slices
aligned arrays, raw observations and pairwise graph submatrices; the latter are
not recomputed graphs. Nonunique donor/metadata joins are not cell-ID selection.
Cluster means operate on qualified nonnegative values and canonical sparse
coordinates; stored zeros do not count as expressing cells. Empty categorical
levels are not observed cell groups. Selected gene lists do not shrink the
normalization denominator. Unknown axes/groups/genes, missing labels, bad scales,
nonfinite values, sparse duplicate coordinates and observed logreg nonconvergence
block the call, remove its analytical outputs and preserve diagnostics.

No annotation threshold, donor/cohort eligibility, scientific family, contrast,
integration/batch correction, doublet/ambient-RNA strategy or G0 is inferred.
Large-scale peak memory, process-fatal diagnostics, persistent recovery and actual
resident deployment require separate acceptance.

References: [Scanpy 1.11.3 source](https://github.com/scverse/scanpy/tree/1.11.3/src/scanpy),
[AnnData 0.11.4 source](https://github.com/scverse/anndata/tree/0.11.4/src/anndata).
