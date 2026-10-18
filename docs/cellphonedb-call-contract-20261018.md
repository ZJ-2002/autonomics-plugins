# CellPhoneDB call-contract repair

The driver previously filtered requested keyword arguments against the author API's signature. An incompatible installation could therefore silently drop interaction scoring, an explicitly supplied seed, or single-thread execution and still invoke the method.

The repaired driver binds the complete requested call before invocation and rejects incompatible signatures without dropping any argument. Its manifest now uses `script_file = "driver.py"`; source updates must not leave execution pointing at the old baked `/opt/autonomics/driver.py`.

Three counterexamples were reproduced against the original source. The same test module then passed nine focused checks: complete argument forwarding, explicit seed plus one thread, rejection of unsupported scoring/seed/thread arguments, rejection of missing required or positional-only arguments, variadic argument preservation, and unchanged unseeded author defaults. Tests use a recording entry point that stops before statistics; they are not official numerical benchmarks.

The official CellPhoneDB image and database digest remain unchanged. This release does not claim that the changed manifest has passed an actual isolated DAG or that the resident service has loaded it. Input semantics, output ownership, full author API coverage, study eligibility and scientific release remain separate requirements.

Hashes, bounded scope and sealed counterexample/regression identifiers are recorded in `evidence/cellphonedb-call-contract-20261018.json`. No credentials, private launcher logs or study payloads are included.
