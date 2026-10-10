# Isolated raw-count preparation contracts

All three nodes are staged, require content identity and explicit source/scale
attestations, and never grant study qualification or G0. A layer called counts
does not authenticate its biological origin.

| Node | Inputs | Outputs | Bounded definition |
|---|---|---|---|
| `cachexia_pseudobulk_counts` | H5AD, frozen JSON | Counts, donor metadata, donor eligibility ledger, cell ledger, audit | Sum raw counts across libraries into one donor per explicitly selected cell type; Scanpy sum/reference scope only |
| `cachexia_h5ad_export` | H5AD, frozen JSON | Nonzero Parquet, full obs/var axes, audit | Engineering transport; not a statistical method |
| `cachexia_h5ad_qc` | H5AD, frozen JSON | Counts-only H5AD, prefilter cell metrics, post-cell-filter gene ledger, audit | Official Scanpy calculate_qc_metrics plus explicitly frozen filter sequence; not complete preprocessing |

Aggregation does not treat cells or libraries as independent units. `sample_id`
equals `donor_id` within the one frozen cell type, so downstream models can check
independent units without reverse-parsing a concatenated ID. Conditions and
declared covariates must be constant across each donor, including other cell
types/libraries. Missing labels block rather than disappear. All planned donors
remain in the eligibility ledger, including low-cell and no-target donors.
No gene filtering occurs during aggregation. Individual and aggregate counts
must fit int32 for the downstream DESeq2 interface; overflow is rejected, not
wrapped. Allocation of the dense aggregate is limited to 20 million entries.
This is not an out-of-core or whole-cohort performance guarantee.

Export reads both X and named layers through h5py/AnnData disk-backed objects;
no full-layer fallback is permitted. Unique lexical axes and complete obs/var
tables allow reconstruction of implicit zeros. Missing coordinates do not mean
biological missingness. Integer expression outside exact float64 range blocks;
raw counts additionally require nonnegative int32-compatible integers. Existing
cell_id/gene_id metadata columns that collide with axis headers block.

QC requires a raw layer and explicit mt/rb gene IDs, not guessed species/symbol
regex defaults. Stored sparse zeros are eliminated before detection counts.
Zero-total percentages remain undefined and those cells drop. Gene detection
is calculated after cell filtering. Thresholds are frozen in the JSON; they are
synthetic technical settings unless approved separately for a real tissue and
platform. The output has selected raw counts in X and layers/counts, with obs,
var and audit provenance; other layers, embeddings and uns are intentionally
not retained. This limited rewrite is not normalization, batch integration,
cell-type annotation, doublet detection or ambient-RNA correction. Official QC
loads the selected sparse matrix into memory; a 4Gi declaration does not prove
adequate resources for a real dataset.

Negative runs remove partial analytical ports and retain BLOCKED audit JSON in
the container workspace. Isolated harness DAG success does not demonstrate
resident-daemon installation, durable recovery or scientific readiness.
