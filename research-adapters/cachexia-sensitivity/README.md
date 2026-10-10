# Official sensitivity routes — technical scope only

This staged local plugin calls unmodified CRAN **EValue 4.1.4** and **metap 1.14** on R 4.6.1. The image reference is content-pinned in `manifest.toml`; all source archives and dependencies are frozen by `prepare_cachexia_sensitivity_sources.py`. Nothing here grants production deployment, scientific input eligibility, G0, or equivalence for other functions in these packages.

## Input and output contract

Both nodes consume two Files: an effect JSON (`cachexia_evalue_official`) or a complete ordered component TSV (`cachexia_combine_pvalues_official`), and a frozen request JSON. The request pins input bytes, lexical IDs, full component count, method and auxiliary scientific role. No implicit parameter inference or method selection is allowed. See `scripts/cachexia_sensitivity_fixtures.py` for executable complete requests, including blocked examples.

Five declared ports, in order: **values.tsv**, **state.rds**, **audit.json**, **sensitivity.log**, **input_ledger.tsv**. The RDS retains the complete official object, classes/dimensions/attributes, input, arguments, warnings/messages and runtime. `values.tsv` retains every numeric field with a separate `FINITE/MISSING/NAN/POS_INF/NEG_INF` tag. Nonfinite output is preserved, not silently clipped or promoted to a finite estimate. `NONFINITE_OFFICIAL_RESULT` includes legitimate unavailable confidence bounds; it does not assert the point estimate is unavailable.

The typed companion uses Arrow 25.0.1 to preserve lexical axes, nullable numeric values, NaN/Inf tags and `source_position`. Native materialization need not preserve physical row order: all comparisons match the unique complete original ordinal. A failed contract removes normal analytic ports, retains the BLOCKED audit and declared log, and preserves any available full failed official state as diagnostic only.

## Method boundaries

- EValue supports the original candidate's scalar RR, OR, HR, OLS and standardized MD functions. Ratio estimates/limits are nonnegative and ordered; SE/SD/contrast cannot be silently ignored. OR/HR require explicit rare-outcome assumptions. OLS requires a positive outcome SD and explicit signed/zero contrast. `true` follows the official function's input scale, including standardized MD for OLS; do not rescale it as a regression coefficient. Official OLS delegates to MD, so its converted result semantics are retained alongside the original input measure. Zero ratios and official overflow/underflow remain tagged Inf/NaN.
- metap maps Fisher to `sumlog`, Stouffer to `sumz`, Tippett/min to `minimump`, max to `maximump`, and Wilkinson to `wilkinsonp`. Frozen weights, ranks, alpha and supported log-input/output conventions are explicit. Missing components propagate without calling a method on a reduced family. If official code omits a supplied component or recodes rank/weights, execution blocks; strict contract error behavior is intentionally not the permissive R API behavior.
- These combination methods assume independent continuous uniform null P-values. **metap's `maximump` computes an order-statistic omnibus P-value; it is not the study's primary path intersection–union raw `max(p_edge)`**. The plugin rejects primary-IUT roles and cannot replace the frozen custom IUT path route. E-values are sensitivity quantities, not proof of causal identification.

Official references: [EValue manual](https://cran.r-project.org/web/packages/EValue/EValue.pdf), [metap manual](https://cran.r-project.org/web/packages/metap/metap.pdf). API presence, a parsed manifest and host preflight do not constitute isolated DAG acceptance; only the later sealed proof ledger controls status.
