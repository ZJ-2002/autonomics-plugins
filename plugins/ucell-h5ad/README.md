# Canonical H5AD UCell

This generic plugin owns the original `h5ad_ucell_score` kind. It migrates
that kind from the single-cell family without changing its `gene_sets`
JSON-string parameter, H5AD input, output H5AD/report ports, artifact prefix,
timeout or 2CPU/8Gi/shm1Gi declaration. Install the new family explicitly;
an old single-cell-only installation does not load this implementation.
No frozen production profile or daemon is changed by source publication.

The Python wrapper preserves the H5AD object and hands X to the actual
UCell 2.16.0 R package. It does not implement an approximate rank formula.
The frozen image combines the original official R environment with the
existing Python3.11/AnnData0.11.4 payload; its OS is Ubuntu24 rather than
the old Python image's Debian12. Other single-cell nodes keep their image.

The explicit package defaults are maxRank1500, w_neg1, missing_genes impute,
average ties, SerialParam and no score-column suffix. Official maxRank is
capped by the number of matrix genes. These defaults are a technical recipe,
not a frozen study choice. X is selected explicitly; raw/layers are not
selected or normalized silently. Rank-background effects, including flat
small matrices, remain the official behavior rather than being interpreted
as biological activity. Signed members follow official positive-minus-negative
semantics, including zero negative-only default scores, not invented reverse
enrichment. Biological negative-control programs are not synonymous with
negative signed arms.

Identifiers retain lexical values such as `0001`, `NA` and Unicode. Missing
genes remain in the official impute calculation and are listed in the report.
No gene/species mapping is performed. Empty/unmatched/ambiguous signatures,
nonfinite or non-R-double-compatible integers, invalid axes and output/score
collisions fail. At least one matching gene per program is required. Ordinary
second-publication errors roll back; crash-atomicity/resume is not promised.
All remaining AnnData/raw/layer/graph/metadata contents follow normal AnnData
serialization. R scoring is cell-blocked with full gene backgrounds; this
does not certify whole-H5AD memory at study scale or donor-level inference.

`test_assurance.sh` requires a new `UCELL_H5AD_EVIDENCE` and independent
source-installed `UCELL_H5AD_REFERENCE_R`. Run it from the complete pinned
plugin monorepo: tests reuse the unchanged single-cell whole-object comparison
helper. Required author/mathematical comparisons and refusals cannot skip.
The retained source archive hash is pinned; failure to fetch a fresh primary
archive is not called successful downloading. Scope evidence must distinguish
fresh source installation, namespace equality and actual output comparisons.

Source/interface/isolated-DAG proof is not biological calibration, signature
specificity, scale/species/gene-background or donor eligibility, reference
validation, full-scale/resident deployment, global quotas/cache/recovery,
scientific implementation lock or G0. Registry authentication may be needed;
a public source repository does not imply anonymous container availability.
