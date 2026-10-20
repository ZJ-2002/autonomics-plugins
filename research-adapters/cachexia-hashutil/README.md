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

## Published-image repair (2026-10-21)

The manifest now pins the existing published `ghcr.io/zj-2002/biotools-py`
digest `7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5`.
The former localhost digest no longer resolves through the deployed image store.
Both original manifest byte hashes are retained and identify the same image
configuration `1f0e8211dfaf55e337a0675e0fdda403f50f56a77e032d748103e407f6342595`,
including the same ordered uncompressed layer identities. Their compressed layer
descriptors differ; this is not a claim that the two transport manifests are
byte-identical. No method script, package installation or algorithm was changed.

This utility accepts staged regular files; it does not require a synthetic study
label. Its location under `research-adapters/` does not itself make content
hashing a study-specific statistical method. Exact local image availability,
loaded source identity and the retained bounded method/DAG proofs must still be
checked separately before software admission. A manifest repair alone does not
mean that the running daemon has loaded it. Expected-input authorization,
scientific eligibility and G0 remain outside this utility.
