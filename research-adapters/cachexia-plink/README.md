# Study-contract PLINK2 clumping adapter

This is a staging adapter, not a resident plugin replacement. It uses the unmodified
official PLINK2 a.6.26 release binary, hash-checked at runtime, inside the already
pinned TwoSampleMR image. It does not call TwoSampleMR or compute an MR estimate.

Four inputs: an explicit SNP/P report, a 21-key frozen contract, byte-identified
active v4.1 execution rules and a frozen panel manifest. The SDK's materialized
cache need not contain its source manifest; the separately identified manifest is
used to check every mounted payload file. The contract declares hashes, ancestry/build labels,
chromosomes, layout, thresholds, thread/memory budgets and method conventions.
The real-panel binding names the original catalog. Synthetic acceptance panels use
an explicitly distinct fixture manifest and namespace, not an official-catalog alias.
All 66 BED/BIM/FAM panel files must match the frozen manifest and declared metadata.
This checks declared compatibility, not independent biological source eligibility.

The original migrated wrapper writes repeated chromosome-prefixed headers and does
not normalize its advertised CSV layout. Here CSV is explicitly parsed; clumps are
merged with a single header; every requested variant and chromosome is accounted for.
Missing P, duplicate IDs, schema/coordinate/identity mismatches and parameter changes
are rejected, not silently discarded. Empty eligible sets retain a complete ledger.

The plan's strict P threshold is applied before PLINK. Original P values are not
jittered. Extracted BED variants are sorted with official `--sort-vars ascii` so
PLINK's P/variant-index tie order follows P/chromosome/position/ASCII ID. This
version requires regular sorted PGEN output; direct sorted BED output fails.
Genotypes are converted using official `--make-pgen` and read with `--pfile`. Official
phased LD among selected nearby indices is checked strictly against the frozen r2
threshold; nonfinite or boundary-ambiguous report values block rather than pass.
The p2 option governs SP2 reporting, not the primary LD or significance threshold.

Seven outputs: selected indices, full clumps, chromosome ledger, official raw archive,
nonempty log, hash/status audit, complete requested-variant ledger. Failed runs remove
analytic outputs but retain log/audit. Raw archive preserves official preprocessing,
clumping and selected-LD artifacts; it does not rewrite the reference panel.

This does not certify source authenticity, actual study ancestry/build/effect-scale
eligibility, arbitrary PLINK options/versions, sample-overlap decisions, full-scale
resources, family creation, persistent resume, resident deployment or G0. Only the
explicit plan-contract route and measured official method scope may be accepted.
