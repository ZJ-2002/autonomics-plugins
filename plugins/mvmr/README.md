# MVMR plugin

Canonical kind: `mvmr`. One instrument TSV File input; output ports 0/1
are `mvmr.RDS` / `mvmr.log`. This is a general official-package wrapper,
not a study-specific scientific permission or overlap assumption.

## Method and identity

MVMR 0.4.8, WSpiller/MVMR revision
`bceaa38088d093a5d30c713afb016e7fbc7ed2be`,
R 4.5.1, immutable image in `manifest.toml`. The pinned installed package
is independently compared with a fresh installation from that upstream
archive; the ten namespace function definitions match. Numerical calls
remain `format_mvmr`, `ivw_mvmr`, `phenocov_mvmr`, `strength_mvmr`,
`strhet_mvmr`, `pleiotropy_mvmr` and `qhet_mvmr`. No estimator is ported.

Author references:
- https://wspiller.github.io/MVMR/reference/format_mvmr.html
- https://wspiller.github.io/MVMR/reference/phenocov_mvmr.html
- https://wspiller.github.io/MVMR/reference/ivw_mvmr.html
- https://github.com/WSpiller/MVMR/tree/bceaa38088d093a5d30c713afb016e7fbc7ed2be

## Input and covariance contract

Unquoted rectangular TSV, distinct nonempty headers, finite effects,
strictly positive standard errors, distinct literal SNP IDs and a
full-rank weighted exposure design with positive residual degrees of
freedom. Literal IDs such as `001`, `1` and `NA` are not inferred as
numbers or missing values. Two or more exposures are required.
No harmonisation, clumping, SNP selection, imputation or mapping occurs.

Exposure arrays use the engine's opt-in `command.env_r_arrays` transport.
Names containing spaces, quotes, backslashes and Unicode retain their
boundaries. The script only parses a single `c(...)` expression of
character literals; it never evaluates that expression or falls back
to lossy space splitting. Both updated engine and plugin are required;
older engines reject the new manifest rather than silently degrading.

Covariance choices are explicit and mutually exclusive:

- `pcor`: row-major phenotypic correlation string, rows separated by `;`
  and cells by `,`, in `beta_xg` order. Dimension, symmetry, unit diagonal,
  range and positive semidefiniteness are checked before the official
  `phenocov_mvmr` call.
- `gencov_columns`: K*K columns in the same TSV, full row-major exposure
  order per SNP. Each finite symmetric positive-semidefinite matrix must
  have diagonal SE squared. These matrices are passed unchanged to
  official functions and recorded in the RDS.
- Neither: author's scalar `gencov=0` default, with an explicit warning.
  This is generic API behaviour, not evidence that a study has independent
  exposure estimates or scientific approval for zero covariance.

Scaled covariance checks use absolute correlation-space tolerance 1e-10,
and eigenvalue tolerance 1e-10 times exposure count. Matrices are never
clipped, repaired, averaged or replaced after failing validation.

The author IVW function does not use covariance to change its coefficients;
conditional-strength and heterogeneity functions do. `qhet=true` requires
`pcor`; arbitrary SNP covariance is not silently substituted. Qhet keeps
`CI=FALSE`, `ncores=1` and the author's development warning; no bootstrap
confidence-interval certification is claimed. Disabled diagnostics are
omitted, not fabricated as zero or NA.

## Outputs, tests and scope

The RDS contains complete official input/result objects plus exposure
order and covariance audit. The declared log begins before validation,
retains method warnings and `ERROR:` diagnostics. Nonfinite official
numeric results cause failure, not a successful artifact with Inf or NaN.
Existing outputs are
not overwritten. A result is staged and hard-linked only on successful
calculation; this is not transactional crash recovery of the result/log
pair.

`./test_mvmr.sh` runs the actual wrapper contract tests against the
manifest's locally cached immutable image, without network or a default
image build. Missing dependencies fail; they do not count as a skip.
`tests/compare_official.R` compares complete objects against a separately
installed author package, including SNP identities, ordering, covariance
and numeric fields, not just significance or final coefficients.

The local proof packet and public evidence card describe exact supported
test cases, source hashes and residual limitations. Synthetic/author
example parity and isolated DAG execution do not qualify a real study's
covariance source, eligibility, full method domain, resident daemon,
cache/resume behaviour, large-scale resource envelope or scientific G0.
A source publication is not an automatic production deployment.
