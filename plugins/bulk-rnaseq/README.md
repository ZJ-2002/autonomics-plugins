# Bulk RNA-seq plugin: original restoration and bounded assurance

This family restores original `limma_voom` and `wgcna` addresses from
`auto-nomics/bulk-rnaseq-plugin` revision
`178e71c7cc8d82f9f4bacd16f009530c7813e717`, not a research-specific replacement.
Source publication and registration do not grant production deployment,
scientific release or G0 approval.

## Exact environment and method

R 4.5.3; official SHA-locked source archives for limma 3.66.0, edgeR 4.8.2,
statmod 1.5.2 and WGCNA 1.74; Bioconductor 3.22. See
`source-archives/SHA256SUMS`, `Dockerfile` and `build-image.R`. The installed
dependency census is retained in the image. Build dependencies use the
declared frozen CRAN snapshot.

The original image could not be pulled (`manifest unknown`); it is not
certified. The repaired owned image has a separate immutable digest in
`manifest.toml`.

The limma wrapper calls official `DGEList`, `filterByExpr`, optional
`calcNormFactors(method="TMM")`, `voom`, `lmFit`, optional `contrasts.fit`,
`eBayes` and `topTable(adjust.method="BH")`. Quantile normalization occurs
inside `voom(normalize.method="quantile")`, not by replacing E after weights
have already been calculated. No author statistical function is reimplemented.

## Input contract and five outputs

Input 0: literal TSV, `gene_id` then unique sample columns; finite,
nonnegative, exactly representable integer counts at most 2^53-1.
Input 1: literal TSV, `sample_id` then requested metadata columns.
Sample sets must match exactly; metadata aligns to matrix sample IDs.
Literal `00001` and a gene named `NA` are preserved. Ragged rows, duplicate
or empty IDs, missing model values, nonfinite numbers, zero libraries,
singular designs and zero residual degrees of freedom are refused.

Categorical models use `~ 0 + outcome + covariates`; `contrast_levels`
is comma-separated `reference,test`. Effect direction is test minus
reference. Continuous models use `~ outcome + covariates`, reporting the
continuous outcome coefficient. `contrast_var` must equal `outcome_var`.
Legacy covariate convention: all-finite numeric tokens become numeric,
otherwise R treats the column as categorical. Numeric category codes
require approved upstream encoding; this wrapper does not freeze study types.

Normalization: `tmm` (default), `quantile`, or `none`. Threads: 1.
`alpha` is an annotation, not a filter; all retained genes are returned.

| Port | Output | Meaning |
| --- | --- | --- |
| 0 | results.tsv | Gene IDs, logFC, AveExpr, moderated t, P.Value, adj.P.Val, B |
| 1 | voom_weights.tsv | Retained genes × labelled samples, official weights |
| 2 | normalized_expression.tsv | Retained genes × samples, official voom E |
| 3 | contrast_summary.tsv | Model, direction, normalization, dimensions, threshold |
| 4 | run_report.json | Versions, input/output MD5s, dimensions, complete kept/excluded gene ledger |

BH covers only `filterByExpr`-retained genes, not a frozen study family.
Filtering does not authorize removal of study IDs or changes to family
denominators. Log2 RMA arrays are not counts. Donor independence, model
selection, eligibility and spatial null models are not established here.

## Invocation and publication guarantees

`script_file` records script identity. The launcher
`/opt/autonomics/Rscript-vanilla` ensures `--vanilla` is an interpreter
option when the engine inserts the script at argv[1]. Host and baked
scripts must match; editing host source without rebuilding is not deployment.

All five destinations must be distinct, writable and absent, including
dangling symlinks. Calculation uses private staging; publication refuses
overwrite and ordinary errors remove this run's published files.
This is not a multi-file atomic transaction, concurrent-writer lock,
SIGKILL recovery system, or daemon cache certificate.

## Mandatory local tests

```bash
LIMMA_BOUNDARY_EVIDENCE=/absolute/new/evidence-directory bash test_smoke.sh
```

Runs real digest-pinned containers against the baked runner. Never
auto-builds, pushes, changes deployment configuration, reads `.env` or
skips missing dependencies. Failed runs preserve diagnostics.
Independent official-package numerical comparisons and native DAG proofs
are separate; smoke success alone does not certify all method branches.

## WGCNA remains pending

`wgcna_runner.R` is byte-for-byte restored original source. Package
installation is not numerical or workflow acceptance. The historical
manifest has one expression input, not its legacy optional metadata port.
This limma repair provides no WGCNA certification or module release.
