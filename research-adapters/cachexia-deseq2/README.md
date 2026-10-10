# Staged DESeq2 count-model contract

`cachexia_deseq2_de` calls DESeq2 1.50.2 / apeglm 1.32.0 in the immutable
image declared in `manifest.toml`. It does not reimplement the model and is
not installed in the resident daemon.

Inputs are a TSV count matrix (`gene_id`, then sample columns), TSV metadata
(`sample_id`, `condition`, independent-unit and covariate columns), and JSON:

```json
{
  "expression_scale": "raw_integer_counts",
  "count_source": "a separately verified raw-count input identity",
  "unit_column": "donor_id",
  "covariate_types": {"batch": "categorical", "age": "numeric"},
  "design_formula": "~ batch + age + condition",
  "expected_arm_counts": {"ctrl": 4, "case": 4}
}
```

Supply `condition_reference=ctrl`, `condition_test=case`, and
`covariates=batch,age` for this example. An empty covariate list requires an
empty `covariate_types` object and `design_formula="~ condition"`. Seed,
dispersion-fit method, shrinkage, alpha and single-thread execution remain
explicit manifest parameters. A requested dispersion fit that falls back to
another method is blocked rather than silently certified.

The five declared outputs are the result TSV, normalized-count TSV,
size-factor TSV, fitted DESeqDataSet RDS, and JSON audit. With apeglm, log2FC
and lfcSE describe the posterior shrinkage estimate; stat/P/adjusted P remain
the unshrunk DESeq2 Wald test. Independent-filtering/Cook/all-zero missing
values are retained. These gene-level adjusted P values are not the v4.1
frozen-family correction or a scientific nomination rule.

The stricter study wrapper rejects transformed/fractional counts, repeated
independent-unit IDs, undeclared covariate types, nonfinite values, changed
arm counts, rank deficiency and zero residual degrees of freedom. At least
three independently declared units per arm are required in this scoped
contract; this is not a universal DESeq2 requirement. Unit and raw-count
identity declarations do not themselves establish biological independence
or validate cell-to-donor pseudobulk construction.

On failure no analytic ports are retained; port 4 records `BLOCKED` and a
nonzero exit status blocks downstream nodes. An engine may preserve the
failed workspace without publishing the failed node's file ports.

Evidence entry point: `scripts/prove_cachexia_counts.py`; it freezes the
actual wrapper/reference sources, compares independent official API
outputs, tests the RDS readback, and exercises all five declared ports in
an isolated DAG. Same-image reference parity is not a host-independent
environment comparison, full-method-domain certification or research/G0
release. This route must not receive GSE130563 log2 RMA array values.

Official method documentation:
[DESeq2 vignette](https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html).
