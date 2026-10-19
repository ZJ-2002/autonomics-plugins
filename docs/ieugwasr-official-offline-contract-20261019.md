# ieugwasr 1.2.0 direct-call adapter: offline contract evidence

The new `staged-adapters/ieugwasr-official` is a standalone R adapter, not an
installed plugin: no container digest, manifest, resident registration or DAG
qualification is claimed. Existing raw REST nodes remain distinct. It does not
replace them silently or increase the accepted-node count by itself.

The registry's `research-adapters/` namespace requires a real manifest and image
identity for every entry. This implementation stays in the explicitly unregistered
staging namespace until those exist; the catalog checks are not weakened. Moving
the R entry and author harness into staging preserves their exact source bytes.

## What executes author code

The fixed official ieugwasr 1.2.0 package is called for `associations`, `phewas`,
`tophits`, `variants_rsid`, `variants_chrpos`, internal `ld_clump_api`, and
supplementary `gwasinfo`. The first six address pending routes; the seventh is
metadata retrieval, **not** a substitute for keyword search. There is no matching
author `gwasinfo_search` function; this adapter rejects it explicitly.

Only the HTTP transport is replaced by recorded, explicitly synthetic responses.
The real author request construction, association chunking, PheWAS sorting,
top-hit preclumped selection, variant formatting and LD subset logic execute.
Complete wrapper RDS objects, including classes, row names and attributes, are
`identical` to direct author returns for all seven operations. Requests also
match. An empty variant response preserves the author's error; HTTP 401 remains
an error rather than an empty successful result. These are offline package
controls, not proof of live API authentication, current API contents or uptime.

Nine separate self-cleaning toy controls cover argument forwarding, full-object
preservation, typed missing/nonfinite states, projection failure, invalid inputs,
and exclusive output publication. Their injected resolver is an engineering
fixture, not author computation. The four standard output ports contain RDS,
typed JSON, audit JSON and log; unsupported projection columns fail closed.

## Runtime identity and JIT correction

The single retained author package is 27 files / 85,082 bytes, not a copied R
environment. The existing host runtime has 1,056 verified file bindings.
Validation explicitly uses the locked shared library and `R_ENABLE_JIT=0`.

The initial default-JIT check failed at its final namespace serialization
assertion, after object/request comparisons had succeeded. Diagnosis preserved
that failure: JIT=3 changed serialized representations of 13 functions while
formals, deparsed bodies and namespace environments stayed identical; several
functions gained bytecode. The original harness, with no assertion deleted or
weakened, passes under explicit JIT=0 with all 41 author functions unchanged.
This environment setting freezes the validation representation; it is not a
change to the author package or an excuse to relabel failed sessions successful.

The source-bound diagnostic and unchanged-harness success are sealed in session
`ca36c8b4d60f4888a594b98344eed6ee`, seal
`7a01209735d72068346f8452e93d6cfb0280f0213dd0597dbea2c12f3cc41d63`.
No credentials or live study queries were used, no container was created, and no
scientific/G0 approval or complete method-domain certificate is granted.

Next: build and pin the actual dependency image, connect declared file ports to
the engine, qualify an isolated DAG and credential/log handling, and independently
approve the research input/use contract. Raw REST and author R return semantics
must remain distinguishable throughout that transition.
