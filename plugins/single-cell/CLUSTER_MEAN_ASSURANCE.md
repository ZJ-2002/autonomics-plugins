# `h5ad_cluster_mean_expression`: descriptive aggregation contract

This original canonical kind retains one H5AD input and one Parquet output,
the original `groupby`, `genes:string_array`, `normalize` and
`include_percent_expressed` parameters, the same resources and timeout, and the
unchanged single-cell image digest. Its injected implementation is now
`scripts/cluster_mean_expression.py`, not the historical generic baked workflow.

The table retains `cluster`, `gene`, `mean_expression` and optional
`pct_expressed` columns. Clusters are sorted by their original string-converted
labels; genes retain requested order, or input var_names order for an empty list.
Unused categorical levels do not create empty groups. Missing/empty group labels
are rejected, rather than silently becoming a synthetic `nan`/blank cluster.

## Official calculations and input scale

The implementation invokes Scanpy 1.11.3 `pp.normalize_total` (when selected) and
`get.aggregate(func=['mean','count_nonzero'])`. Inputs are represented as float64;
sparse coordinates are coalesced and stored zeros removed before aggregation.
Finite real numeric matrices, unique nonempty cell/gene identities and complete
requested genes are required. Integer entries outside the exactly representable
float64 integer domain are refused rather than silently rounded.
Noncanonical integer coordinates are checked with exact Python integer sums
before float64 coalescing; a coordinate sum outside that domain is also refused.
Boolean duplicate coordinates coalesce in their original boolean dtype, matching
the sparse boolean matrix's logical value rather than counting a repeated stored
`True` as an additional expression unit.

- `normalize=none` uses X as supplied, including finite signed expression values.
- `normalize=cp10k` preserves the original preference for `layers['counts']`,
  falling back to X only if that layer is absent. It requires nonnegative
  count-like values and finite positive cell totals over **all input genes**.
  Official normalization to 10,000 is performed before selecting reported genes.
- Raw is never a fallback and is not used in calculation.
- `mean_expression` is the cell arithmetic mean on that chosen scale.
- `pct_expressed` is 100 times the fraction of **nonzero** values after sparse
  coordinate coalescing. It is not a calibrated biological detection threshold;
  for signed/log2/centered inputs nonzero does not imply expression presence.

This is descriptive cluster-level output, **not** donor-by-celltype pseudobulk
raw-count summation. Cells are not declared biological replicates, no disease
contrast/SE/P is estimated, and donor eligibility or study scale is not certified.
It must not replace a donor-level differential-expression branch.

## Interface repair: lossless gene-array transport

The public `genes:string_array` parameter is unchanged. The original whitespace
environment remains for compatibility, but the script uses the additional
`[command.env_r_arrays] SC_P_R_ARRAY_GENES='genes'` helper. The engine serializes
members as JSON string literals inside `c(...)`. Python removes that fixed
envelope and performs strict JSON array decoding; it never evaluates code or
invokes R. This preserves empty lists, whitespace, quotes, backslashes, Unicode
and punctuation within gene identities. The helper requires an engine supporting
the previously validated lossless array interface; actual compiled native DAG
tests exercise it, rather than manually populated smoke-test environment alone.

## Output and engineering scope

The sole Parquet artifact embeds UTF-8 JSON under schema metadata key
`autonomics_cluster_mean_report`. This additive metadata records chosen source,
full-background rule, exact request, group cell counts, cell ledger, input hash,
package identities, warnings and scope boundaries without adding another port
or changing table columns. Output hashes are recorded externally by DAG evidence
to avoid a self-referential Parquet hash.

The input is materialized in memory; no full-size memory or performance acceptance
is claimed. Output is staged, fsynced and linked without replacement. No cache,
crash-recovery, persistent-resume or resident-daemon certification is inferred.
The existing family-global model binding remains an infrastructure registration
dependency, not an aggregation method input; no model is opened or unpickled.

Run `CLUSTER_MEAN_ASSURANCE_EVIDENCE=/new/path bash test_cluster_mean_assurance.sh`.
Missing image/dependency or failed assertion fails the mandatory entrypoint;
nothing is silently skipped. Direct reference calls independently use the
official installed APIs, and a separate Python mathematical calculation checks
means/nonzero percentages. They do not call the production aggregation helpers.
This packet claims neither a new independent package installation nor scientific
release or G0.

Official API definitions:
- [Scanpy aggregate](https://scanpy.readthedocs.io/en/stable/generated/scanpy.get.aggregate.html)
- [Scanpy normalize_total](https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.normalize_total.html)
