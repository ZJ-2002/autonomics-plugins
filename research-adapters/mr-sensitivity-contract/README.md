# Frozen MR supporting sensitivities

Candidate plugin for the final v4.2.1 plan's supporting methods: weighted
median, MR-Egger slope/intercept, IVW/Egger heterogeneity, and IVW leave-one-out.
It uses the existing pinned TwoSampleMR 0.7.9 image. It is not registered in
production and does not grant scientific approval or study execution authority.

The seven File ports are the frozen supporting recipe, the actual parent MR
configuration, its harmonised table, complete variant ledger, estimates and
audit, and an explicit frozen applicability evidence file. Formal preflight and
the family compiler require all four parent outputs to originate from the same
`mr_frozen_harmonise_ivw` node and its configuration to be its actual input 0.
The native `frozen_config_inputs` binder can fill the six reserved content-hash
slots from those actual upstream files without changing scientific parameters.

The recipe fixes analysis identities, role `SUPPORTING_ONLY`, protocol 4.2.1,
seed, explicit nboot=1000, software lock, warning policy, six input hashes and
four applicability decisions. `QUALIFIED` is a supplied decision with bound
evidence, not a qualification performed by this plugin. Human method acceptance,
G0 and the signed execution contract remain separate prerequisites. No defaults
may authorize an unresolved applicability decision.

Output tables retain three estimate rows, two heterogeneity rows and all
retained variants' leave-one-out rows plus the all-instruments row. Zero or
insufficient instruments, unqualified/unresolved methods, official errors and
unaccepted warnings preserve NA rows and explicit reasons. `row_type`
distinguishes a genuine SNP named `All` from the overall row. Parent selection,
harmonization, estimates and primary P remain unchanged; support never chooses a
replacement primary P or changes family denominators. O3 never computes these
methods; O1/O2 support does not resolve overlap or qualify an MRlap primary.

Regenerate the self-contained entry point with
`python3 -B scripts/build_mr_sensitivity_wrapper.py`. Its `--check` mode rejects
stale bytes without writing. Loader and producer-lineage tests are in CI; actual
R numerical checks require the pinned image and are not satisfied by SkipTest.
Current component acceptance uses synthetic inputs only. A new frozen protected
worker, complete family execution and recovery qualification are still required.
