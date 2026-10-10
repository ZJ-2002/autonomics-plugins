# Bounded content hashing repair

This staging adapter leaves the resident plugin and daemon unchanged. It pins an
already cached local image (Python 3.11.17, blake3 binding 1.0.10), not the unavailable
production manifest digest. It retains the four-column hash table and two outputs.

Repairs: reject zero/negative input counts, empty/duplicate/unknown algorithms,
noncanonical or out-of-budget chunks; bound chunks to 1–32 MiB; require a regular
stable input, publish the table atomically and retain nonempty failure diagnostics.
Zero-byte input files remain legitimate. Input and output paths must differ in
both resolved path and existing file identity; hard-linked diagnostic paths must
not truncate the staged input. Invalid colliding paths retain stderr, not an
unsafe log file that would overwrite input bytes.

The SDK manifest currently only accepts `file`; graph validation does not accept
`file_set` on that port. Consequently the old FileSet claim is NOT certified.
Multiple independent File inputs can instead use separate nodes in a DAG. This is
an explicit orchestration change, not proof of a production FileSet interface.

Hashes describe the staged bytes and staged filename. They do not independently
verify an expected frozen hash, prove source authenticity, force downstream gates,
certify arbitrary concurrent mutation resistance, or award `FILE_VERIFIED`/G0.
Only the algorithms and bounded tested interface receive scoped technical proofs.
