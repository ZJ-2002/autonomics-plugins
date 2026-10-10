# Frozen survey staging routes

Nine statistical nodes call unmodified CRAN survey 4.5 on R 4.6.1: mean,
variance/covariance, quantile, GLM, t-test, post-stratification, raking,
calibration and weight trimming. An explicit design constructor and hash-only
contract binder complete the execution graph.

Every statistical operation consumes a complete official survey design RDS,
not just updated weights. Post-stratification/calibration variance information
and domains therefore remain available to downstream analyses. The constructor
freezes types, lexical row identity, stages, FPC, weights/probabilities and
lonely-PSU policies. The binder changes only an explicitly unresolved upstream
SHA256; it never selects methods, parameters, rows or scientific eligibility.

Ports are defined in `manifest.toml`. All methods require exact JSON keys and
synthetic technical scope. Results preserve the full official RDS, numerical
missingness/infinity state, diagnostics and original row universe. Statistical
success is neither CHARLS/ELSA/NHANES eligibility nor G0. The local image is not
a portable published deployment. Arbitrary forged/untrusted RDS safety, the full
official API domain, global resources and resident recovery are not certified.

The proof driver and independent official-source reference installation must
complete before any acceptance status is granted. The host preflight is only
an implementation check, not official or DAG acceptance.
