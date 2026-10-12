# Original rank_genes_groups assurance scope

The canonical kind keeps the original four parameters (`groupby`, `method`,
`reference`, `n_genes`) and three File ports (marker Parquet, report, H5AD).
It invokes Scanpy 1.11.3's actual `tl.rank_genes_groups`, not a replacement
statistical implementation. All four original methods are covered: `wilcoxon`,
`t-test`, `t-test_overestim_var`, `logreg`.

The original recipe always used `use_raw=False`. The dedicated entry makes this
explicit: it selects `X`, no layer, no feature mask, all declared groups, signed
ranking rather than absolute scores, no `pts` and no Wilcoxon tie correction.
Author defaults for BH and estimator arguments remain unchanged. No automatic
normalization, log transformation, donor model, reference change or method
fallback is introduced. Scanpy expects log expression; actual scale admission
is separately required. Unused raw/layers remain in the H5AD but are not ranked.

Selected sparse X must have canonical unique coordinates. This prevents an
actual observed author sparse-variance failure on noncanonical data: the same
two-row mathematical matrix produced variance -2 through duplicate CSR entries
but variance +2 after dense reconstruction. The entry refuses instead of
silently coalescing potentially overflowing data or calling it a valid test.
Source cell/gene IDs must be unique, real expression finite, groups identified,
and reference present. Actual author singleton/unsupported input failures remain
failures, not success with empty output.

All original numerical result fields remain in `uns['rank_genes_groups']` and
the complete H5AD is preserved, including CSC input format. The tidy view retains
original group/gene/rank/score/P column names and adds available official
`logfoldchange`. Logreg has coefficients, not gene P values; no P columns are
invented. The report lists full tested X-gene universe, its hash, actual versus
requested top-n width, returned/unreported IDs in source order, all observed
group counts, official missing/infinite numeric masks and warnings. Top-n is a
reported view, not feature filtering or a new multiplicity denominator. The
official gene-wise BH is per group for methods returning P values, not the
study-wide cell/tissue/contrast family. Logreg performs no P-value correction.

These are CELL-level exploratory markers, not donor/animal disease inference.
No claim of independent biological replication, qualified input scale, model
calibration, complete B discovery or G0 follows from successful computation.
Logistic convergence warnings remain visible and do not establish a valid fit.
When a source has old rank results, only that fixed uns key is overwritten and
reported; new output files never overwrite historical artifacts.

Three-file publication stages all outputs and verifies source identity before
exclusive links. Ordinary write/link failures remove only owned outputs; error
reports/stderr must be retained. This is not power-loss atomicity, persistent
checkpoint recovery, full-scale resource or current resident deployment proof.

`tests/test_rank_container.py` uses a separate unmodified author import prefix,
direct official calls and `get.rank_genes_groups_df`. Comparison covers whole
AnnData/HDF5, exact integer/ID/NA axes and complete tidy tables. Structured
floating fields use 1e-12 absolute and zero relative tolerance; this is not a
blanket every-platform guarantee. Tests fail on missing dependencies, never skip.

Official API: https://scanpy.readthedocs.io/en/1.11.x/generated/scanpy.tl.rank_genes_groups.html
