# Original DESeq2 plugin

This family retains the canonical `deseq2_de` kind, two File inputs, seven
parameters and five File outputs. It is not the research-specific
`cachexia_deseq2_de` replacement. Numerical-method, engineering, isolated-DAG
and research-contract evidence are separate; technical agreement does not
grant production deployment, study eligibility or G0.

## Method and input/output contract

Input 0 is a rectangular raw-count TSV with literal `gene_id` and sample
columns; input 1 is a TSV with literal `sample_id`, exactly the submitted
two `condition` levels and any declared covariates. Sample identities must
match exactly; metadata is reordered to the count axis. Empty/duplicate IDs,
malformed rows, embedded controls and missing model values are rejected.
Counts must be nonnegative exact integers within R's 32-bit integer range.
Normalized, log/RMA, CPM and fractional tximport values are not raw-count inputs.
Numeric-looking covariate columns are numeric; other columns are factors.
Users must verify this inference against their frozen scientific model.

The official DESeq2 1.50.2 package fits `~ <covariates> + condition`,
reference-before-test, with `parametric`, `local` or `mean` dispersion fits.
Official automatic parametric-to-local fallback is retained and separately
reported as the actual fit type. Independent filtering and Cook filtering
are enabled. The default is apeglm 1.32.0 shrinkage; `none` returns MLE values.
Non-syntactic condition levels use the official sanitized coefficient name.

| Port | Artifact | Meaning |
|---|---|---|
| 0 | results.tsv | All input genes; baseMean, log2FoldChange, lfcSE, stat, pvalue, padj |
| 1 | normalized_counts.tsv | Counts divided by official size factors, original axes |
| 2 | size_factors.tsv | Official sample-level size factors |
| 3 | deseq2_dataset.rds | Fitted official DESeqDataSet, not the shrunk result object |
| 4 | run_report.json | Actual model/fit/package identity, full gene ledger and checksums |

With apeglm, log2FoldChange and lfcSE are posterior estimates, whereas stat,
pvalue and padj remain the unshrunk official Wald tests. Do not reconstruct
the Wald statistic from posterior effect/uncertainty. Official missing P and
independent-filter-only missing padj are distinguished; no study family or
frozen denominator is inferred from the retained subset.

Existing outputs, including dangling links, are refused. Five outputs are
privately staged and published only after calculation; ordinary errors roll
back this invocation's published files. This is not atomic multi-file
publication, concurrent-writer isolation or SIGKILL/restart recovery.

## Implementation identity and reproduction

The repaired image is pinned in `manifest.toml`; R 4.5.3, DESeq2 1.50.2 and
apeglm 1.32.0 are retained from the actually pulled original provider image
`ghcr.io/auto-nomics/autonomics/deseq2@sha256:9bd9a2e95a59d7a1725351b99fe188a71202a68a7255830213fe39a226e7864f`.
`Dockerfile` is historical upstream recipe provenance, not the repair build.
Use `Containerfile.assured` to rebuild the repair over that immutable base.
`Rscript-vanilla` and `script_file` preserve vanilla invocation through the
engine's argument insertion; the actual baked and submitted script identities
are checked separately. Resources remain 2 CPUs/4 GiB, threads=1, five outputs,
isolated networking and read-only root filesystem. These do not prove global quotas.

Official reference archives:
- DESeq2 1.50.2: `514f23ae8d274623d80978c30bfa1c6566acd98188bf1aa563970959ea59522f`
- apeglm 1.32.0: `90e1e687252378ce1ba2e11dd5bd6f1580e0359d45ba41cceec204faeef1c4d7`

Fresh source installations, called independently from the wrapper, are the
numerical reference. They share the container R/other dependencies: this is
not independent BLAS validation, full DESeq2 API equivalence, inference
simulation or real-study eligibility. The author pasilla data are technical
benchmark inputs, not independent cachexia research evidence.

Run the mandatory retained-evidence checks:

```sh
DESEQ2_EVIDENCE=/absolute/new-proof-directory \
DESEQ2_REFERENCE_LIBRARY=/absolute/fresh-official-library \
bash test_deseq2.sh
```

The CLI requires both official reference packages and an immutable real image;
missing dependencies fail, never skip. It verifies baked-source identity,
fixtures, 55 baked-runner boundaries and 26 fresh-author cases including all
dispersion/shrinkage branches and the official pasilla data. It never builds
an image automatically or deletes its evidence. Historical
`fixtures/pasilla_baseline.json` and `container_README.md` are retained
provenance, not the current numerical oracle. The data-boundary check covers
/work, /opt, /tmp and /panels only; official package example datasets in
/usr/local/lib/R/site-library/DESeq2/extdata are present and declared.

### Fit policy and fitted-object evidence

`fit_policy=exact` is the default: the runner checks the actual official
DESeq2 dispersion fit before publishing outputs and rejects an automatic
change from the requested fit type. A protocol that explicitly permits the
official fallback can use `fit_policy=native`; the report records both requested
and actual fits and the policy. Selecting `native` does not amend a frozen
research contract or certify an analysis.

`deseq2_dds_diagnostics` accepts the fitted DDS on port 3 and its run report on
port 4 from one identified `deseq2_de` run. It verifies the report's DDS checksum,
axes, package version and actual fit, then reads official results without
refitting. Its table retains all DDS genes, missing raw P values and explicit
NA reasons, original gene/fitted/final dispersions, maximum Cook's statistic,
unshrunk Wald MLE/SE and 95% normal intervals, and diagnostic BH/BY
with missing P replaced by 1. These are diagnostic full-DDS corrections, not
authorization of a study hypothesis family. A third output retains the complete original gene-by-sample Cook's assay.
Unknown missing-P causes or missing fitted-object diagnostics reject publication. Shrunk apeglm coefficients must not be substituted for these MLE
intervals.

Use a concrete full run ID when exporting method evidence. On engines supporting
identity-bound export, supply `expected_run_id` and `expected_snapshot_id` to
`dag_export_run` with `format=crate`. This delivers fitted objects, captured logs,
task manifests and the recorded run report; `format=prov` references files rather
than delivering their bytes. Historical runs without recorded argv remain
historical records without argv. Logs are the runtime's captured streams and may
be subject to its capture limit.

The additional managed synthetic regression is
`tests/test_method_evidence.py`. Set `METHOD_EVIDENCE_ROOT` to a new directory
under `AUTONOMICS_VALIDATION_PERMANENT`, and optionally declare the existing
Podman backend in `METHOD_CONTAINER_BACKEND_JSON`. It exercises a 2,001-gene,
4+4-sample strict-parametric fixture, reordered metadata, reversed effect/CI,
complete-gene official R BH/BY, missing-P readback and report/DDS mismatch.
Reversal is checked exactly on the same DDS; independently relevelled fits
are compared to fresh official fits with their own parameterization. Any
observed relevelled-fit differences are reported, not hidden by relaxing the
official-parity tolerance. It
uses the same pinned dependency image with the declared current source scripts;
it does not claim that the runner baked into that image has changed, nor that
a separately built numerical environment was tested. Scientific eligibility,
batch acceptance, T05, multiplicity continuity and reviewer signatures remain
independent requirements.
