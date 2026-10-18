# CellPhoneDB call-contract repair

The driver previously filtered requested keyword arguments against the author API's signature. An incompatible installation could therefore silently drop interaction scoring, an explicitly supplied seed, or single-thread execution and still invoke the method.

The repaired driver binds the complete requested call before invocation and rejects incompatible signatures without dropping any argument. Its manifest now uses `script_file = "driver.py"`; source updates must not leave execution pointing at the old baked `/opt/autonomics/driver.py`.

Three counterexamples were reproduced against the original source. The same test module then passed nine focused checks: complete argument forwarding, explicit seed plus one thread, rejection of unsupported scoring/seed/thread arguments, rejection of missing required or positional-only arguments, variadic argument preservation, and unchanged unseeded author defaults. Tests use a recording entry point that stops before statistics; they are not official numerical benchmarks.

## Owned output publication

Two additional counterexamples reproduced overwriting a prior result table and prior provenance. The author method now writes into a private, temporary subdirectory of the SDK workspace. Only a complete set of six nonempty, regular official tables and the generated provenance can be published. Destinations are linked exclusively without replacement; failed publication rolls back only files whose device/inode identity still matches this run. Existing files, dangling links, prior timestamped results and foreign replacements are preserved.

Eleven focused tests cover successful byte-preserving publication, existing table/provenance refusals, a dangling destination, unrelated timestamped files, missing/duplicate/symlink author tables, author failure, publication failure and foreign-replacement-safe rollback. The original nine parameter-forwarding checks still pass on this exact driver.

## Actual SDK and limitations

The fixed, already installed CellPhoneDB 5.0.1/database image is unchanged. A synthetic 240-cell fixture exercises the current source-mounted wrapper through the cached, hash-bound SDK: all seven declared ports are materialized, with explicit seed 7, one author thread and 100 iterations. A corrected fault-injected graph refuses an existing output before the author method and preserves the foreign file.

The original harness attempted to identify its negative control from the input pathname, but the SDK normalizes mounted input names. That attempt therefore ran the author method rather than injecting a foreign file, and the harness failed. Its worker exit 1 is retained, including the unintended additional synthetic method run. Only the negative control was corrected and rerun; the successful positive graph was reused, not recomputed. No failed worker is relabelled as successful.

This is the sealed SDK build, not the resident daemon. The managed parent has a 2 GiB limit; the original node declaration remains 4 CPUs/16 GiB. No resource setting is silently overridden, and this small exercise does not certify the full declared scale, all input semantics or all author API branches. No study eligibility or scientific release is granted.

Hashes, bounded scope and sealed counterexample/regression identifiers are recorded in `evidence/cellphonedb-call-contract-20261018.json`. No credentials, private launcher logs or study payloads are included.
