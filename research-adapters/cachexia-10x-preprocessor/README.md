# Scoped raw 10x preprocessor repair

This staged plugin keeps the original four File inputs and two output roles for
MatrixMarket inspection/ingestion. It is **not installed in production** and does
not implement annotation, doublet/ambient-RNA removal, batch integration, or a
complete single-cell analysis workflow.

The guard imports the baked `preprocess.py` only after checking its exact source
hash and frozen package versions. It fixes lexical metadata/companion-table
handling, reads only a bounded diagnostic preview, and explicitly invokes the
official `read_mtx(dtype="float64")` API. Raw-count ingest rejects fractional,
negative, nonfinite, out-of-range or structurally inconsistent values before
calling the unchanged official cell-then-gene filters and optional cp10k/log1p.
Both each input count and each cell library total must fit the exact Float64
integer range. Duplicate coordinates remain valid and are handled by the
official loader; they are not silently dropped by the guard.

Inspect deliberately does not read/validate the matrix body. Its report records
`body_verified=false` and its H5AD has `X=None`; do not treat it as analyzable
expression or QC approval. Missing metadata values are preserved, not scientifically
qualified. Gene symbol disambiguation retains the official AnnData behavior and
the input `gene_id` column; it is not a mapping or annotation decision.

Output paths must be distinct and fresh. The report records the actual H5AD hash,
not a stale or self-referential report hash. Primary analysis thresholds, input
identity qualification, organism/platform QC, and downstream donor models remain
the responsibility of the frozen research contracts.

Evidence: `results/cachexia-v4.1/tenx-preprocessor-proof-v3-20261008/` and
`docs/audits/cachexia-v4.1-2026-10-07/TENX_PREPROCESSOR_FIX_PROOF.md`.
Eight complete pinned-package host H5AD replays pass. Actual native DAGs reach
the container-create boundary but fail at the current newuidmap capability gate;
**no normal container DAG, resident deployment or G0 certification is granted**.
