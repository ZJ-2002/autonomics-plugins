# Frozen marker-mean annotation adapter

This is the original single-cell plugin's user-defined available-marker arithmetic
mean heuristic, not an official statistical cell-type method. The statistical
official layer is **NOT_APPLICABLE**. It must not substitute for CellTypist,
UCell, singscore, `scanpy.tl.score_genes`, pseudobulk or donor-level inference.

Two Files are required: an H5AD and an exact 24-key frozen request. Marker order,
occurrence multiplicity, full ordered axes, input content hash, namespaces,
expression layer/scale, all-gene normalization, coverage, group universe/counts,
threshold, tie rule, Unknown label and non-candidate-driven annotation basis are
explicit. No mapping, raw fallback, group discovery, imputation or scientific
defaults are inferred. Documentation of a non-candidate-driven basis is not
independent certification of the specimen's annotation eligibility.

Scores are arithmetic means of frozen present marker occurrences. Missing
occurrences are recorded and checked, duplicates preserve their original
weight. For groups, average the cell scores before choosing a label; ties select
the first frozen marker set. A score must be strictly greater than `min_score`.
An Unknown group safely uses each cell's own maximum for its selected score;
known group assignments use each cell's score for the group-selected signature.
The single-signature margin is its score, explicitly distinguished from a
top-minus-runner-up margin. `__group__` is a valid marker name without collision.

`log_cp10k` calls Scanpy 1.11.3 normalize_total then log1p on qualified raw counts
and the entire matrix. `none` leaves the explicit scale untouched. All values
must be finite; raw counts must be nonnegative integers. Normalized log1p CP10k
is checked over every cell, without densifying sparse matrices. No double log
transformation is permitted.

Seven declared ports contain full cell-by-signature Parquet, preserved H5AD,
audit JSON, nonempty log, complete occurrence ledger, request ledger and typed
group-by-signature Parquet (including the empty per-cell table). Failure retains
a valid request ID and diagnostics without publishing normal results. Existing
output files and reserved result namespaces are never overwritten.

The image is the unchanged original content-pinned single-cell image. Validation
is an isolated real DAG plus independent scalar arithmetic and official Scanpy
normalization replay, not a resident daemon deployment, container-storage repair,
global resource guarantee, biological annotation accuracy or G0 scientific pass.
