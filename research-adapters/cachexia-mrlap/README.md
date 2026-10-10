# Frozen official MRlap, isolated staging

This is a separately named study adapter, not a production plugin installation.
The fixed image calls official MRlap 0.0.3.3 with GenomicSEM 0.0.5 and
TwoSampleMR 0.7.11. Those are not the standalone TwoSampleMR family's 0.7.9
environment. Reference BLAS/LAPACK and RNG identity matter for Monte Carlo SE/P.

Inputs 0/1 are the frozen full exposure/outcome GWAS feeds; input 2 is the unique
rsID list; input 3 is an explicit key/value frozen contract. Every required key
is enforced by the script. Hashing failure, changed feeds/IVs/panel bytes,
noncanonical or out-of-range integer seed, unknown keys, changed canonical
method parameters, altered N, pruning, and blank/duplicate IVs block execution.
The LD-panel mount is fixed by the declared catalog binding; all 49 manifest
files are content-verified and all 45 required LD files must be present.
No unverified panel selection or online fallback exists.

Ports 0..5 are the legacy-compatible 17-number summary, full official RDS,
printed result, nonempty log, identity/status audit, and complete requested-IV
retention ledger. The official absent rg_se stays NA; no uncertainty is invented.
Unavailable correction is NOT_ESTIMABLE, not substitution of the naive IVW P.
Retained SNP exclusion reasons are not fabricated. Duplicate rows in the
authorized legacy GWAS feeds remain unchanged; this is not general GWAS QC.

Scope is TECHNICAL_ONLY_NOT_G0 and results remain LEGACY_SEEN. The authorized
39/475 requested lists and 7/7/97 official retained counts are reproduction
inputs/outcomes, not new scientific evidence. MRlap standardizes Z/sqrt(N), so
its effect/IV set is not the conventional TwoSampleMR estimand. This adapter
does not assemble the 276/288 families, adjudicate overlap eligibility, change
their denominator or grant G0. Real study enablement, all MRlap parameter
branches, deployment/recovery, and global resource limits remain separate.
