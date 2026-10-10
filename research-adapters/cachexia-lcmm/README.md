# Frozen technical LCMM adapter

This staged plugin calls the unmodified official **lcmm 2.2.2** package on **R 4.6.1**. It is not deployed in the resident daemon and is not an official certification of the original Rust bundle or the entire package API.

## Interfaces

| Kind | Input0 / Input1 / Input2 | Outputs |
|---|---|---|
| `cachexia_hlme` | lexical complete-observation TSV / frozen JSON / technical receipt for ng=1 or complete converged single-class RDS initializer | numeric summary, complete RDS bundle, audit, log, original row ledger, subject bijection |
| `cachexia_hlme_predict` | complete converged fit RDS / frozen JSON / typed newdata TSV | same six outputs, including full official prediction object and original newdata rows |
| `cachexia_hlme_compare` | first complete fit RDS / frozen JSON / second complete fit RDS | same six outputs, retaining both complete fits, requested criteria, prescribed model IDs and output model order |
| `cachexia_lcmm_bind_contract` | upstream input0 / frozen JSON placeholder template / upstream input2 | resolved JSON, binding audit, log |

Every source file is content-hashed. Patient IDs are exact lexical strings, including leading zeros and literal `NA`; an explicit first-observation bijection supplies the numeric subject field required by `hlme`. No subject IDs are inferred from float casts. Numeric and factor fields have explicit ordered schema and levels.

All formulas, class counts, covariance choices, initialization, convergence thresholds and seeds are frozen. Allowed complete-observation models explicitly choose ng and NONE/BM/AR correlation. Multi-class initialization must use a converged ng=1 fit on exactly the same data, schema, subject map, fixed/random specification and correlation. There is no automated class selection, fallback optimizer, missing-value deletion or conversion of failed convergence into usable coefficients. Nonconvergence preserves an extra `failed_fit.rds` in the failed run directory, not a declared successful analytic port.

`predictY.hlme(draws=TRUE)` in this frozen release produces analytical mean ±1.96 SE bands; these are not individual prediction intervals, Monte Carlo draws or authorized real-time forecasts. Official matched calls remain in the RDS because prediction reads them. Official `summarytable` sorts models by class number; `result_model_ids` records the corresponding frozen ID order independently of its call-derived display labels. BIC, entropy, ICL and class percentages are descriptive, not biological-subtype evidence.

The typed companion plugin verifies the successful upstream summary/audit and materializes nullable float64 values plus exact string coordinates through Parquet. Complete official fit objects, including covariance, posterior probabilities, random effects, data, calls, RNG and lineage, remain separately available for independent review. Only calls/formula environments and elapsed wall runtime are excluded from numerical repeat comparisons, not removed from archived objects.

## Boundaries

Input role is restricted to synthetic technical qualification. v4.1 B-T trajectory/class-comparison modules remain conditional/default OFF. Real cohort eligibility, times and landmark rules, missingness/death handling, multi-start scientific selection, class-size/uncertainty rules and G0 are not filled in by this adapter. Complete RDS and audit hashes establish execution identity, not security certification of arbitrary forged/untrusted RDS. The local image is not a portable production release. Resident deployment, global concurrency/resources and persistent cache/recovery remain separately unaccepted.

Official archive: <https://cran.r-project.org/src/contrib/lcmm_2.2.2.tar.gz>.
