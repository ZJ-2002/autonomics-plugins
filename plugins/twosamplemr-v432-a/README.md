# Frozen v4.3.2 A numerical adapter

`twosamplemr_v432_a_exploratory` accepts the project's already independent,
action-2 harmonised dotted-column TSV. It preserves input row order and values,
does not load the catalog's 503-person PLINK panel, and never calls MRlap.
The pinned existing image supplies official TwoSampleMR 0.7.11 and R 4.6.1.
Runtime version checks reject another environment.

The fixed seed, official default 1000 bootstrap replicates, methods and call
sequence reproduce the numerical `run-A` body of frozen `g0_v432_methods.R`
(SHA256 `f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd`).
The adapter emits all five frozen MR tables plus the consumed input, complete
RDS, execution log and SHA256-bound provenance. Main rows carry `p_primary=NA`, `p_for_family=1`, and
`EXPLORATORY_OVERLAP_UNRESOLVED`; registered regional sensitivities retain their
frozen labels and primary NA. IVW is official `mr_ivw`, including its
multiplicative random-effects overdispersion and underdispersion SE floor.

This adapter implements the numerical steps only. It does not qualify LD,
reapply source filters, verify all frozen bytes, sign a scientific contract,
or authorize a study run. Before real input execution the caller must complete
the existing project's frozen verifier, signed execution and resource admission
requirements. Its technical toy validation is not a G0 PASS. Do not change the
frozen files to make the adapter runnable. The input guards check the narrow
trait, qualified-row, EAF, INFO, F and position contract; they cannot independently
prove prior LD qualification or scientific authorization.

The unrelated generic `twosamplemr` plugin remains version 0.7.9. Select this
distinct kind for the frozen v4.3.2 A numerical contract.

Input ports are: qualified TSV, frozen A config JSON, frozen certificate JSON,
R dependency lock TSV, and method proof JSON. The proof supplies `scope`, an
ordered four-element `input_sha256` array, `scientific_code_sha256`, `R` and
`TwoSampleMR`. `FROZEN_V432_A_LEGACY` requires the exact frozen bytes and 39
rows. `SYNTHETIC_METHOD_TEST` requires synthetic config/certificate markers,
`scientific_authorization_granted=false`, and the generating script's SHA256;
the real frozen input is explicitly rejected in that mode. Runtime provenance
binds all five supplied files. Neither scope grants formal scientific admission.
`contracts/frozen-method-proof.json` provides the content pins for port 4;
it is an identity proof, not an execution signature or permission grant.

Technical acceptance (no study data): from the Autonomics checkout run
`python3 -B scripts/research_validation_session.py run -- python3 -B /absolute/path/to/plugins/twosamplemr-v432-a/tests/run_acceptance.py`.
It uses the cached image with no pull/network and archives input contracts,
source hashes, actual image/software identity, under/overdispersion equation
checks, direct official full-sequence parity and seven negative contracts to
`AUTONOMICS_VALIDATION_PERMANENT`. All containers run attached and are registered
with the session's Podman ownership wrapper and stopped-worker audit. A successful
toy run does not execute the real frozen 39-SNP MR.
