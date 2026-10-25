# Hash-only binder precision repair

The binder claimed that only `input0_sha256` and `input2_sha256` changed, but its
`jsonlite::write_json(..., digits=NA)` could also round numeric method-contract
values. Local reproduction demonstrated `1.0000000000000002` becoming `1` and
the maximum finite binary64 value becoming a decimal that reads as infinity.
This violates the binder contract independently of any scientific model fit.

The only production-code change is the bind-mode resolved-contract writer:
`digits=NA` becomes `digits=17`. Neither `hlme`, `predictY`, `summarytable`,
method parameters, package dependencies, authorization, nor audit-only JSON
writers are changed. The original script SHA256 is
`92bedf32d5c48070df0354b0ee08c0d0f64e0fcb7cf44d7abd0da2945a0d43d8`;
the repaired script SHA256 is
`15e7a0516716420198fa80652777696040d422d0437c45dfaa9dd6d51ba2e1e0`.

`tests/test_lcmm_bind_precision.py` has three self-cleaning toy cases. It parses
the actual source and executes its binding branch and actual validation/hash
helpers, without loading lcmm or evaluating the package/version guard or fit
branches. This is a binding-block regression, not a full container/runtime
execution proof. No fake lcmm package or model output is supplied.

The tests compare the complete parsed request before and after binding, allowing
exactly the two declared source-hash replacements. They additionally check that
all three input bytes/hashes are unchanged, that the audit lists precisely the
two fields and that its output hash matches the resolved contract.

- Precise nested numeric values and adjacent binary64 values: old source fails,
  repaired source passes.
- Maximum finite, minimum normal and subnormal values: old source fails,
  repaired source passes. These are transport stress cases, not newly approved
  lcmm parameter ranges.
- String/boolean/integer/nested array/empty array/JSON null preservation: both
  sources pass.

Direct unittest execution completed with three cases, no skips and zero
failures after repair. No scientific fit, network request, production change,
study admission or G0 grant occurred. JSON lexical spelling is not preserved,
and JSON signed-zero behavior is not claimed as a new guarantee.

The prior publication proof and prior merged ledgers remain historical. The
current source-pinned `tools/prove_lcmm_combined_pipeline.py` and
`tests/test_lcmm_publication_binding.py` now check the repaired wrapper identity.
The latter additionally reconstructs the old exact source hash by reversing
only the reviewed binding-writer change, and checks today's public manifest
instead of its obsolete localhost-image identity. All five adjacent unit guards
pass. This is not a new execution of the combined fitting pipeline. Existing
CRAN `source-plan.json` locks source archives, not this wrapper, so it needs no
archive-hash change. Shared quality inventories, source catalogues, deployment
pins and resident activation are left to the integrating owner.

`tests/bind_precision_acceptance.py` in this adapter is a prepared managed-proof
driver. It rechecks the exact old source reproduction, the three fixed cases,
five adjacent guards and source identities. Its existence alone does not imply
that this managed proof has executed or obtained a session seal.
