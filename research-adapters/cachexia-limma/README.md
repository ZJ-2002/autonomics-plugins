# Staged limma/voom count-model contract

`cachexia_limma_voom` delegates to official limma 3.66.0, edgeR 4.8.2 and
statmod 1.5.2 on R 4.5.3. The manifest pins a local, offline-built image;
it is not a published replacement for the historical bulk-rnaseq image
and is not registered in the resident daemon. Checksummed official source
archives and build logs reside in the count-proof workspace.

The three inputs are the raw-integer count TSV (`gene_id`, sample columns),
metadata TSV (`sample_id`, outcome, independent-unit and covariate columns),
and a JSON contract with `expression_scale`, `count_source`, `unit_column`,
`covariate_types`, and an exact `design_formula`. These fields have the same
meaning as `../cachexia-deseq2/README.md`.

For `outcome_var=condition`, `contrast_var=condition`,
`contrast_levels=ctrl,case`, `covariates=batch,age`, use
`design_formula="~ 0 + condition + batch + age"` and
`expected_arm_counts={"ctrl":4,"case":4}`. The contrast is case minus ctrl.
For continuous `outcome_var=score`, `contrast_var=score`, set
`outcome_mode=continuous`, empty `contrast_levels`,
`design_formula="~ score + batch + age"`, and `expected_n=8` instead of
arm counts. The score is an explanatory variable for gene expression,
not an expression-derived substitute for the outcome qualification.

`edgeR::filterByExpr` determines the model's retained gene set, recorded
alongside every excluded ID. TMM delegates to `calcNormFactors`; quantile
delegates to `limma::voom(..., normalize.method="quantile")`, so expression
and mean-variance weights come from the same official pipeline. It never
replaces `v$E` after computing weights from a different expression scale.
Fits use `lmFit`, then `contrasts.fit` when categorical, then `eBayes`.

Five outputs: result TSV, voom-weight TSV, normalized-expression TSV,
contrast-summary TSV, and JSON audit. `topTable` BH values apply to its
retained gene set, not automatically the v4.1 predeclared hypothesis family.
Filtering is not permission to delete failed/unestimable family members.

This wrapper deliberately supports only raw integer counts and uniquely
declared independent units, not all valid inputs accepted by official voom.
The minimum sample counts and rejection guards are a scoped study contract,
not official defaults. A log2 array requires the separately reviewed array
model route; normalized arrays must not pass through this count workflow.
No cell-to-donor pseudobulk aggregation, biological unit validation,
sample-qualification review or scientific/G0 release is performed here.

Proof entry point: `scripts/prove_cachexia_counts.py`; independent official
APIs run in the same pinned image, with frozen source snapshots, declared
ports, materialized readback and rejection DAGs. This is not host parity,
resident-daemon deployment certification or blanket limma equivalence.

Official method documentation:
[limma manual](https://bioconductor.org/packages/release/bioc/manuals/limma/man/limma.pdf),
[edgeR manual](https://bioconductor.org/packages/release/bioc/manuals/edgeR/man/edgeR.pdf).
