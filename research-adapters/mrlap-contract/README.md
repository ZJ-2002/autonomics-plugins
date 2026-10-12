# Frozen official MRlap candidate — not admitted for formal execution

This adapter supplies the official MRlap computation and one explicitly marked
completion of the frozen direct-IV applicability check without a fit. It does not approve
G0, LD reference applicability, normalization, sample overlap, instrument
selection, diagnostics or a scientific conclusion. Eligible O1 analyses remain
blocked in the formal worker until the full adapter, producer binding and method
acceptance are qualified. Native Rust MRlap remains forbidden.

The ten inputs are frozen config, complete normalized exposure GWAS, complete
normalized outcome GWAS, complete sample-size source, selected exposure source,
selected outcome source, actual upstream harmonic ledger, actual upstream MR
audit, LDSC panel manifest and actual upstream bound MR config. The native DAG
must prove the same upstream producer supplied ledger/audit/config; the R
transport alone cannot establish this from caller-supplied JSON. Nine actual
input hashes are required in the frozen config. Config hashing is separate and
the engine binds every output to its immutable artifact/checkpoint identity.

Input GWAS columns are exactly `snp,chr,pos,beta,se,effect_allele,other_allele,eaf,pval`.
This candidate supports unique autosomal biallelic rsIDs, EUR and GRCh37. It
blocks duplicate IDs, malformed values, altered selected subsets and missing
source identities. It does not turn an instrument-only table into a full GWAS.
CONSTANT or complete PER_SNP N must have a frozen provenance definition;
case-control traits require integer total N and log-odds beta, rather than
effective N or odds ratios. MRlap returns standardized observed Z/sqrt(N)
effects; these are not interchangeable with the other adapter's raw beta scale.

At least three accepted direct upstream IVs are required for a statistical fit.
After every ten-input, original-parent, full-GWAS/N, panel-content and software
check has passed, an actual upstream retained direct-IV count of zero, one or two
publishes a complete `NOT_ESTIMABLE` MAIN row with method `NONE`, reason
`INSUFFICIENT_FROZEN_DIRECT_IVS` and all coefficients/P values missing. Its audit
states `method_executed=false` and `method_status=NOT_APPLICABLE`, binds the same
real parent hashes and exact threshold/count, and leaves LDSC diagnostics null.
This is the only no-fit route. Missing/unlicensed sources, wrong hashes,
contracts, panels, N, coverage, environments or arbitrary method errors stay
blocked. A genuinely empty selected table from an actual clump is supported;
an empty full GWAS is rejected. Pruning is disabled
and the exact qualified upstream IV universe must survive the official method.
All selected rows remain in the retention ledger, including upstream exclusions.
MAIN does not remove MHC or TERT. With `do_pruning=FALSE`, official MRlap ignores
its internal `MR_*` selection options, including reverse selection. Its allele
matching does not complement strands. Raw IV allele orientation, signed effects
and standard errors must therefore agree with upstream harmonization; an
incompatible strand or palindrome orientation blocks rather than being silently
treated as the same absolute effect. An independently admitted normalization
route is needed to support those inputs.

Prospective full-GWAS/HM3 and actual post-munge cross-trait SNP minima, diagnostic
bounds and exact warning allowlist must be frozen explicitly. The latter count
comes from the actual official LDSC log. All 45 required no-MHC HM3/22 LD-score/
22 M_5_50 files are content-checked. Panel names alone do not prove ancestry or
build. Missing diagnostics and malformed corrected quantities block. Finite
official estimates that fail applicability are NOT_ESTIMABLE with primary P=NA;
they never fall back to observed IVW P. Raw quantities stay in private outputs.

Outputs retain the same five-port ABI: MAIN estimates, full selection retention,
execution audit, R result and deterministic diagnostic tar. A fit contains the
original official result/logs. A no-fit completion contains a clearly labelled
applicability-only RDS and only `not-applicable.json` in the tar; it never invents
an official result or LDSC logs. Scripts use fixed RNG
and one BLAS thread. `mrlap.R` is the sole source; regenerate its byte-bound shell
entrypoint with `python3 -B scripts/generate_mrlap_contract_wrapper.py`.

The original registry digest `78f195b8...cd063d` is currently unavailable, even
through the existing authenticated route. A controlled OCI export of cached
config `29415250...ea84c` has a distinct digest `e6e10cdd...925434`, explicitly
recorded in this candidate. The export is not relabeled as the old registry
manifest. The pinned image runs R4.6.1, MRlap0.0.3.3, GenomicSEM0.0.5 and
TwoSampleMR0.7.11. Its seven relevant MRlap/GenomicSEM function bodies and formals
match the fixed official source revisions. This does not qualify its full
dependency stack or resolve reference-BLAS/other-environment parity.

`scripts/tests/test_mrlap_contract.py` covers preflight failures and an optional
real serialized official diagnostic fixture. Missing R dependencies or that
fixture are explicitly reported as unqualified skips. Software discovery and
wrapper/manifest tests are not method acceptance. The isolated overlay probe is
component-only; the formal runtime's storage policy has not been changed.

The aggregation candidate `frozen_mrlap_request` binds seven actual MR/MRlap
ports per O1 edge. The recipe compiler checks their causal clump, harmonization,
config-hash binder and audit lineage before emitting an O1 batch. The native
node rechecks producer bytes, the same supported parent protocol, full retained IV IDs, frozen diagnostic criteria
and primary-P provenance. It preserves the parallel IVW P, including when the
corrected result is rejected, without using that IVW P for the O1 family. Each
batch is limited to 36 edges/252 input ports; complete original families remain
unsplit for correction. This engineering integration is not scientific method
admission or qualification of a newly frozen worker binary.

The collector accepts the sole no-fit route only when its actual harmonic
ledger and parent MAIN count prove fewer than three direct IVs, the frozen
threshold is exactly three, full preflight coverage is demonstrated, all MRlap
statistics are missing, and no official retained IVs/diagnostics are claimed.
`completed_adapters` records successful adapter/QC completion; the separate audit
retains `method_executed=false` so it cannot be mistaken for a statistical fit.
