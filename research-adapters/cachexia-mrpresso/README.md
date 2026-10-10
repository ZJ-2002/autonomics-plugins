# Official MR-PRESSO, frozen technical staging

This invokes the unmodified official `mr_presso` at commit
`3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87`. Actual R package version is
`1.0`; the historical image/manifest label `1.0.0` is not its package version.
The locally cached image digest differs from the uncached production manifest.
Neither installation nor official equivalence of that old image is implied.

Input 0 is a SNP-indexed TSV containing exactly declared outcome/exposure beta
and SE columns. Input 1 is a 17-key frozen contract: schema_version, scope,
test_id, input_sha256, input_role, effect_scale, alignment, beta_outcome,
sd_outcome, beta_exposure, sd_exposure, outlier_test, distortion_test,
signif_threshold, nb_distribution, seed, missing_policy. Exposure column lists
are comma-separated safe formula identifiers, never ambiguous space-joined
arrays. Scope is TECHNICAL_ONLY_NOT_G0; role is SYNTHETIC_TECHNICAL_INPUT or
LEGACY_SEEN. The preharmonised conventional-beta declaration is an upstream
source attestation, not independent allele/ancestry/build/scale qualification.

No default method choices or seeds are inserted. Missing/nonfinite/underflowed effects,
nonpositive SE, zero first-exposure effects, singular leave-one-out designs,
duplicate SNPs, inadequate SNP/simulation count and unreachable outlier
resolution block. Distortion without outlier testing is rejected rather than
pretending it ran. There is an explicit 250-SNP, four-exposure,10000-simulation
resource domain. These checks do not change the official numeric algorithm.

Five ports: complete typed long result table, entire original official RDS,
nonempty log with all warnings, complete SNP ledger, hash/status audit. Official
`<1/NbDistribution` and Bonferroni-censored P strings remain bounds, never zero
or exact P. Official unestimable corrected rows remain missing. A missing outlier
table distinguishes tests not requested from the official global-test gate;
it is not promoted to "no outliers". No SNP is automatically removed or promoted
to a main result. Failure removes analytic outputs and retains diagnostics.

Summary numeric columns require explicit SQL NULL/double casts after lexical TSV
readback. Textual censoring and missing-kind fields remain lexical; an exact-P
consumer cannot turn a censored bound into a primary exact P. Numeric summaries
are serialized with 17 significant digits and the complete RDS remains authoritative.

MR-PRESSO Raw uses its own weighted model. It is a sensitivity result, not the
plan's multiplicative-random-effects primary IVW or an MRlap fallback. No frozen
family denominator, primary-P selection, cohort eligibility, MVMR covariance,
power guarantee, production installation, persistent recovery or G0 is granted.
