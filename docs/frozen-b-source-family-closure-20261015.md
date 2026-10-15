# B source intake and family contract closure

This follows the A/B candidate `646ab3c22f4dfb2002138d1f2718ff47122a8538`,
not a new scientific analysis or a production cutover. The operator explicitly
requested that the running daemon must not be restarted. The previous candidate's
numerical and publication checks do not certify these newly tested contracts.

## Source intake

The old intake collected all nineteen complete files before rejecting a wrong
first source hash. Its individual 64 MiB limit did not impose an aggregate limit;
nineteen maximum-size inputs would exceed the manifest's 1 GiB memory allowance
even before parsing. This is a budget inconsistency, not an observed cohort OOM.

The revised intake checks aggregate stat sizes before opening payloads, streams
each identity in frozen input order and rejects the first mismatch immediately.
Only after all identities match does it collect bounded payloads. It verifies
descriptor/named-file metadata and content again during collection and rehashes
sources before returning. Individual source files, total source bytes and expanded
matrix bytes each have a 64 MiB engineering bound. These are not a measured or
guaranteed process-memory peak, an atomic filesystem snapshot, or protection
against future source changes after return.

All three intake receipts also retain the actual independent-unit IDs in sample
order. This does not infer donor IDs or change sample selection. A read-only stat
review found the actual nineteen frozen files total 17,177,368 bytes; their bytes,
scientific parameters and frozen locks were not modified.

## Family transport

The candidate accepted altered or absent source provenance and authorization
flags, malformed estimated effect/SE/df/CI fields and extra certification columns
when result hashes were recomputed. Correct p/q checks alone did not reject these
counterexamples. The new mechanical checks must bind the complete source receipt,
actual model and independent-unit axes, producer schema and status-specific
numeric contract. They must not infer scientific permission from successful
transport or recompute official adjusted values in Python.

The numerical backend remains official R/limma and `stats::p.adjust`. Origin
contracts and input schema checks are engineering validation, not an independent
reimplementation of those methods. Non-estimable official diagnostic values must
not be silently replaced with fabricated finite estimates.

## Qualification boundaries

Self-contained toy sources have their own actual source identities. Tests must
not substitute real study hashes into invented receipts, bypass production
guards, or relabel old Python-adjusted real results as official R outputs.

No real cohort was refitted for this closure. The previous real full-transcriptome
results do not contain the new official-adjustment receipt. A complete current
production-kind B intake/design/limma/family DAG and current daemon loading remain
separate unfinished acceptance items. Production configuration, study G0 status,
scientific signatures, viewing history, family denominators and conditional
module readiness are unchanged.

## Executed evidence

- Published-baseline family: ten malformed origin/result cases actually returned
  success. Session `dfcc2637f1a348fc97c501cb5d67863f`, manifest
  `bc5184a44c700beadad2d5ab982fb384947f2340128aca7ee2c3293c53fc5935`.
- Published-baseline intake: five tests executed, including three failed assertions
  and one missing-field error demonstrating the old contract gaps; the retained
  mutation refusal already passed. Session `26941e3ec0af4469a5e93fd12042341c`, manifest
  `eb7d59ed1552bbe8697ecf8fe67fbee9dd19596bee4ade0e608047dce032526c`.
- Repaired intake: all five tests executed without failure, error or skip.
  Session `f61522489e95407a8beb7a04be70adfd`, manifest
  `f45cc09cd889179e6984224d8b26679b78005a38134cc74422edb58fc787112b`.
- Real official host R toy: nineteen self-contained source files, actual intake,
  three fixed models, 25 genes including one constant row. All effect/SE/df/CI/p
  and complete official BH/BY comparisons to the unchanged frozen numerical
  block passed with the original tolerances. RDS readback and declared refusal
  controls also passed. Session `4ae9e57cb7984b70bf84c1ad326c6208`, manifest
  `b29f8435db5c2e31f994604c0c2496b3fa2650dda95f859abe0c463fba6e578c`.

The root reviewer rehashed every member of these sealed archives and checked the
real R proof's source bindings against the current source. Both inlined entry
scripts were regenerated and the twelve existing plus ten new focused tests
all passed. The toy R test exercised `CONSTANT_EXPRESSION`, not actual R generation
of `OFFICIAL_LIMMA_NONFINITE_OR_ZERO_PRECISION`; that second reason's diagnostic
preservation currently has mechanical fixture evidence only. No claim of an
independent empirical-Bayes prior validation is made.
