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

The historical upstream image could not be pulled during the limma review
(`manifest unknown`); it is not certified. For WGCNA, the unchanged original
runner was subsequently recovered and executed from the immutable owned
1.0.3 image. Its actual counterexamples are retained separately. The repaired
1.0.4 image has a separate immutable digest in `manifest.toml` and preserves
the limma runner and package environment; twenty limma author cases were
revalidated after this shared-image change. GHCR package visibility remains
private: authenticated retrieval is verified, anonymous availability is not.

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

## WGCNA original-node repair and bounded qualification

The original `wgcna` kind, one File input and six File outputs are retained.
Input 0 is a literal gene-by-sample TSV: `gene_id` followed by unique sample
columns, finite continuous normalized expression, not a raw-count method.
The runner cannot infer provenance, normalization, donor independence or
study eligibility from numeric values. Metadata remains legacy direct-script
behavior only, not a second declared DAG input. It requires an exact sample
set, aligns to expression order and refuses eigengene column collisions.

The original seven controls remain: signed/unsigned network, Pearson/bicor,
minimum module size, deep split 0–4, merge cut height, target block size and
threads. Integer controls now reject fractional or overflowing values.
`max_block_size` is an official target, not a guaranteed memory ceiling.
Additional explicit controls are `power=0`, `power_cutoff=0.85`,
`max_p_outliers=1` and `seed=54321`. Positive `power` is an explicitly supplied
fixed value; zero requests the official `powerEstimate`. Failure to estimate
does not silently substitute threshold 0.8 or power 1. Failed official
computation retains a separate diagnostic RDS and publishes no normal ports.
Selecting a fixed power is a scientific decision outside this technical proof.

The wrapper calls official `goodSamplesGenes`, `pickSoftThreshold`,
`blockwiseModules`, `adjacency`, `signedKME` and `labels2colors`; statistical
functions are not reimplemented. Correlation options are consistent across
all stages. Official QC-excluded genes retain rows with true missing kME;
grey/unassigned genes are not counted as assigned modules. R RNG kind and
initial/terminal state are recorded.

Wrapper choices are not all package defaults: network defaults to signed
instead of unsigned, `minModuleSize=30`, `mergeCutHeight=0.25` instead of 0.15,
`pamRespectsDendro=FALSE` instead of TRUE, numeric labels, powers 1–10 and
12–30, and TOM type matching network type. These explicit choices are compared
against the official package with identical arguments, not declared to be the
only scientifically valid settings. The bicor default `maxPOutliers=1` is
preserved for compatibility; the author FAQ recommends 0.05 or 0.1 in relevant
settings. Study configuration must decide, not silently choose for significance.

| Port | Output | Corrected meaning |
| --- | --- | --- |
| 0 | soft_threshold.tsv | Actual official fit indices and explicit chosen power |
| 1 | adjacency_stats.tsv | Real within-block offdiagonal adjacency summaries and full-value hashes, not module sizes |
| 2 | tom_stats.tsv | Per actual saved TOM block, real overlap summaries and full-value hashes, not guessed block counts or net object bytes |
| 3 | modules.tsv | Complete original gene IDs, labels/colors, QC/grey status and official kME |
| 4 | module_eigengenes.tsv | Original sample axis and official MEs; optional metadata is direct-script only |
| 5 | run_report.json | Canonical identity, inputs/outputs, full axes, QC masks, actual block memberships, RNG, versions and boundary |

The output formats retain their names, but adjacency/TOM column schemas are
intentionally corrected. Consumers of the former erroneous tables must adapt.
TOM summaries come from the actual saved official TOM used in clustering;
temporary full TOM files are removed after publication. Summaries are
within-block, not a claim to a full cross-block adjacency/TOM. All six output
destinations must be absent, distinct and writable. Ordinary failures roll
back this run's publication; SIGKILL, concurrent writers and multi-file atomic
transactions remain unqualified.

```bash
WGCNA_EVIDENCE=/absolute/new/evidence-directory \
WGCNA_REFERENCE_LIBRARY=/absolute/fresh-author-library bash test_wgcna.sh
```

The mandatory local suite uses the actual baked runner and a separately
installed five-package author library. No missing dependencies, empty cases,
or absent images count as PASS. Full numerical/reference and native-DAG
evidence is indexed by `evidence/canonical-wgcna-v1-20261012.json`. Technical
qualification is bounded; full WGCNA API, independent runtime, inferential
calibration, real-study eligibility, full-scale resources and resident daemon
deployment are not granted. Coexpression is not causality or trait testing.

Author sources: [WGCNA manual](https://cran.r-project.org/web/packages/WGCNA/refman/WGCNA.html)
and [author FAQ](https://edo98811.github.io/WGCNA_official_documentation/faq.html).
