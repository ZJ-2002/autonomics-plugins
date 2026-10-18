# MICE wrappers and typed boundary: ownership repair

The four official statistical alternatives remain fixed to `mice` 3.19.0 and
their original author image. The analysis and hash-binder entry points now write
privately, publish with exclusive links and roll back only paths still owned by
the invocation. Existing files, dangling links and input aliases are refused.
Statistical helpers stay in their original global environment; only the physical
writer entry changes. The hash binder still preserves all other raw JSON bytes.

The existing PyArrow type boundary receives the same ownership repair, retaining
the original conversion and validation body. Its output paths are passed as
private arguments, not redirected through changed method parameters. The image,
manifest, masks, factor labels, numerical schema and row/variable coordinates
remain unchanged. Missing values do not become zero.

## Current evidence

- Nine R dangling-output failures and four actual-image Python failures are
  preserved as pre-fix counterexamples.
- Twenty-six actual R protection controls pass. Thirteen actual PyArrow-image
  controls pass, including real null/factor-label/leading-zero-ID serialization,
  existing/dangling paths, invalid input, aliases, audit races and foreign
  replacement during rollback. Their container is observed stopped.
- Thirty pre-existing R helper ASTs remain identical. The typed writer body is
  AST-identical after removing only its old environment-based output assignment;
  its conversion/validation algorithm does not change. Five binding tests pass.
- These controls execute no MICE imputation or completion. Current connected
  author-package DAGs and RNG/full-object comparisons remain pending.

The frozen synthetic examples and unmodified independent author entry are reused
for the next replay. The completion case should consume a newly computed parent
`mids`; references should rebuild from original data and frozen requests. Do not
make old execution metadata appear equal by adding date exclusions or weakening
the existing full-object comparison. The present repair is not that future test.

The [author documentation](https://amices.org/mice/reference/mice.html) currently
describes development version 3.19.10; the installed frozen 3.19.0 package and its
source/help remain authoritative for this route. No MAR/MNAR, stationarity,
longitudinal eligibility, actual missingness contract, production deployment or
G0 is granted. B-S stays `CONDITIONAL_NOT_READY`, GS01 stays `OPEN`, and
276/288/696 remain unchanged.
