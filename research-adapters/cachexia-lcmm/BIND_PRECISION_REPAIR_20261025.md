# Hash-only binder precision repair

The binder claimed that only `input0_sha256` and `input2_sha256` changed, but its
`jsonlite::write_json(..., digits=NA)` could also round numeric method-contract
values. Local reproduction demonstrated `1.0000000000000002` becoming `1` and
the maximum finite binary64 value becoming a decimal that reads as infinity.
This violates the binder contract independently of any scientific model fit.

The first repair changes only the bind-mode resolved-contract writer:
`digits=NA` becomes `digits=17`. Neither `hlme`, `predictY`, `summarytable`,
method parameters, package dependencies, authorization, nor audit-only JSON
writers are changed. The original script SHA256 is
`92bedf32d5c48070df0354b0ee08c0d0f64e0fcb7cf44d7abd0da2945a0d43d8`;
the binder-only repaired script SHA256 is
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

The earlier `tests/bind_precision_acceptance.py` prepared a managed proof of the
three binder cases and five adjacent guards. The subsequent version below adds
the request-audit case; it does not rewrite any prior session evidence.

## Subsequent request-audit precision repair

The non-bind technical audit still serialized its embedded `request_json` with
`jsonlite::toJSON(..., digits=NA)`. Although the complete RDS remained intact,
the recorded method-request copy could round the same precise input values.
One additional toy case extracts and evaluates the actual audit-list assignment
and the actual outer audit writer from the R AST. It writes and rereads both
JSON layers, checking adjacent binary64, maximum finite, minimum normal and
subnormal values, nested arrays, null, strings and logical values. It also checks
the referenced output hashes and the full RDS, including signed zero. No lcmm
fit, predict or compare function executes.

That case fails against the exact binder-only source above, then passes after
changing only the embedded request serializer's `digits=NA` to `digits=17`.
The outer audit writer is unchanged. The current script SHA256 is
`6a8b110fcaeebe5a64ab378f807777547907f222099783b5b62aa8c4e3db62f9`.
The identity guard checks reversal of the audit repair back to `15e7a051...`,
then reversal of the binder repair back to `92bedf32...`; no historical
artifact is edited. The current managed driver covers four precision cases and
five adjacent guards, with a separately recorded one-case failure reproduction
against the binder-only source. An initial local test-scaffold run omitted a
helper and failed before the target assertion; it is not counted as the
serialization-defect reproduction or as a passing test.

Managed session `20696b49d33c4fcf8d61fdc8093d4151` completed with worker and
launcher exits zero and CLEANED state. Its manifest seal is
`e9ffe97da664a51109901cd763f6c837f53b4c37cc61d4f7cfead9d7e4cc230a`;
member `permanent/lcmm-bind-and-audit-precision/verification.json` has SHA256
`ce2df06628cde59917f0564f80f6c2b6f9bdff20567439c6038c4d47802f90fe`.
That member records the four fixed cases, five passing guards, exact source
identities, and the one-case reconstructed old-source failure. This is not a
full container or resident-DAG proof and grants no scientific qualification.
