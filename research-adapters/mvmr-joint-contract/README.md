# Joint MVMR input candidates

Three separately declared stages build an exposure-only union, jointly clump it,
and align the two complete exposure sources and outcome to the selected alleles.
All stages require explicit frozen configurations and actual input hashes.
The LD node resides in `mvmr-joint-clump-contract`; union and harmonization have
no panel binding or hidden LD prerequisite. Panel-free builds must work without
an installed reference, while joint clumping must refuse a missing binding.

The supported union chooses candidates significant in either exposure and uses
the minimum exposure P, then registered exposure order, for the anchor. This is
an adapter policy requiring separate preregistration and review: v4.2.1 does not
automatically resolve that choice. There is no outcome port in union or clump.
Typed union receipts cannot impersonate single-GWAS normalization receipts.

Joint clumping calls the same accepted PLINK phased-LD/strict greedy routine as
single-exposure clumping. The default single-source path is unchanged. All 66
reference files bind by SHA/build/ancestry; diagnostic fast clump is not the
selection oracle. Reference absence and excluded instruments remain in ledgers.

Harmonization streams complete source row/identity checks, aligns selected rows
with official TwoSampleMR0.7.9, applies the plan's palindrome frequency exclusions,
and retains every original selected ID and per-source reason. Sign multipliers
are derived from allele/frequency transformations even when beta is zero.
No proxy/region filtering, coefficient estimate or scientific approval occurs.

The sign ledger does **not** transform or qualify a covariance matrix. Source
covariance needs an explicit bound orientation adapter/review before MVMR; a
dimensionally correct raw matrix is insufficient. Candidate bounds are 4096 LD
variants per chromosome and 4096 total joint-model tools; exceedance blocks,
never truncates or changes thresholds. Protected execution of these candidates
remains blocked pending full producer-chain and recovery qualification.

Generate and verify all wrappers with
`python -B scripts/build_mvmr_joint_wrappers.py --check`. Complete shared R sources
are embedded; top-level dispatch guards are preserved in a non-top-level loading
scope, and only the node's declared dispatcher runs.
