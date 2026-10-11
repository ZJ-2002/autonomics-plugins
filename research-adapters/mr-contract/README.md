# Frozen official MR adapter — qualification candidate

This candidate executes official TwoSampleMR harmonization exactly once, then
uses its frozen `mr_keep` rows for official `mr_ivw` or limited-instrument
`mr_wald_ratio`. It does not register a production plugin or grant scientific
permission. The image is independently pinned; it differs from the MRlap
environment and must not be described as the same software lock.

Inputs are four admitted File artifacts: configuration JSON, independently
selected exposure instruments TSV, normalized outcome TSV and upstream
selection evidence JSON. TSV columns are exactly `snp`, `chr`, `pos`, `beta`,
`se`, `effect_allele`, `other_allele`, `eaf`, `pval`. Both coordinates refer to
the same frozen build and ancestry. Source normalization, duplicate/locus
resolution and outcome extraction must have their own acceptance evidence.
This adapter accepts complex-trait instruments only; correlated/cis methods
need separate qualification. No significance threshold is weakened.

The selection evidence binds the selected exposure bytes, original full
exposure bytes, exact ordered instrument IDs, clumping parameters, tie order,
panel manifest and selection execution evidence. The entire evidence JSON is
hashed as an actual input. These fields are necessary bindings, **not proof**
that clumping was correct or exposure-only. Their referenced artifacts and
actual upstream execution must be independently accepted in the signed method
contract. An invented completion JSON cannot provide that acceptance.
The current candidate therefore does not close the full A preprocessing chain.

All selected instruments remain in the harmonized table and exclusion ledger,
including missing direct outcome variants, coordinate/allele mismatches and
palindromes. Raw frequency bounds 0.42–0.58 are inclusive. Frequencies are
compared after official allele alignment, with only a machine precision margin
at the prespecified maximum difference 0.10. Proxies are unsupported in this
primary adapter. F approximations are reported, not a declaration of validity.

Main estimates retain qualified MHC and TERT variants. Both leave-region-out
sensitivities use pre-frozen build-specific intervals and annotation identities.
Intervals in synthetic fixtures are fictional and cannot be reused in a study.
One or two instruments remain limited support, without a complex-trait
confirmatory P. O0 may supply the prespecified IVW primary P after usual
eligibility; O1/O2 keep IVW as a parallel/exploratory result and never substitute
it for MRlap. O3 supplies no estimate. This adapter supplies no family correction,
MRlap diagnostics, Egger/median/leave-one-out qualification or scientific review.

`scripts/mr.R` is the sole method source. Run
`python3 scripts/generate_mr_contract_wrapper.py` after editing it; the generated
wrapper includes its exact bytes and invokes `Rscript --vanilla`. The loaded
wrapper hash, raw manifest hash and pinned image are bound by the engine's
method identity. Container outputs are published only after successful exit.

`scripts/tests/test_mr_contract.py` checks synthetic variants, independent IVW
formulas, complete exclusion universes, frozen overlap policy and no-clobber
failure behavior. A missing official package is an explicit skip, never method
qualification. Actual OCI qualification must run all tests without skips.
