# LDSC declared panel files match the versioned author distribution

The exact **88 declared data files** now have an independent origin comparison,
not merely agreement with their catalog maintainer's checksums. Their raw bytes,
including the compressed score-file bytes and both M definitions, match the
versioned [S-LDSC reference deposit](https://zenodo.org/records/7768714) by
Steven Gazal (ORCID `0000-0003-4510-5730`, DOI `10.5281/zenodo.7768714`).
The primary record identifies both original archive names and published checksums.

| Author archive | Published MD5 | Independently measured SHA256 | Declared data files |
| --- | --- | --- | ---: |
| 1000G_Phase3_ldscores.tgz | e4352ccf778f296835d73985350a863b | 470fe954080ba164f6b18ca2be8f8a6e2585d983b4a248556b5ffff2c3d0145f | 66 |
| 1000G_Phase3_weights_hm3_no_MHC.tgz | a98ac0f089ee285177544a3e6e721ca3 | d3e29112c64766dcee0ad9ec69ebda3d24cbe29ddb559d75443b10bcf8756c91 | 22 |

Each downloaded archive matches its published size/MD5. Every selected tar member
then matches the catalog object's complete size/SHA256; this is not only a
container checksum comparison or a few sampled rows. No tar member is extracted
to a filesystem path. Unsafe links, traversal paths, duplicate names, missing
members, changed bytes and arbitrary unreviewed extras fail closed.

## The initial failure stays a failure

Session `2b38d75f6c9948288d2912797eb1a935` exited 1 because the first author
archive additionally contains 22 chromosome-generation logs. The original
classifier rejected them rather than silently ignoring them. They are not omitted
scientific score rows, and are not additional annotations or replacement M counts.

After enumerating the actual complete archive, the checker was revised to classify
the explicitly named chromosome-generation metadata separately, preserve every
such file and record its size/hash. All 88 declared data comparisons remain
mandatory and byte-exact; arbitrary extras still fail. A new test exercises this
distinction. The old failure and its archive remain unchanged.

The new proof reused the first **complete checksum-verified download**, from its
exact sealed failed-session archive. It did not infer a previous successful exit,
rerun a scientific computation or redownload that object. It separately downloaded
the missing weight archive. All 22 additional logs are preserved with the new
proof; no raw archives or launcher logs are published to Git.

Current proof session `125e793f27214d0b9df05b48e634597f` exited 0/CLEANED;
manifest `51635e219b89483c3217826a2e0cb72043dfae71da9092bd8dd7b56c37354879`.
The new proof, first failed attempt, metadata, source-lineage and source-test
archives were independently rehashed, including exact membership. All **193
required source tests** ran without failures, errors or skips; the required
inventory and source lock matched.

## Precise qualification boundary

This closes the previously unproven **selected author-distribution origin** of
the two fixed catalog packages. Historical resource-only records remain unchanged;
they are superseded on this one point, not rewritten into broader certificates.
The [original project's CBIIT maintenance link](ldsc-upstream-maintenance-lineage-20261015.md)
is independently pinned as a separate software-lineage observation.

It does **not** select these panels for a scientific study, certify all author
distribution versions, make the two SNP axes equal, approve the unpartitioned
reference/weight recipe or substitute the different MRlap resource. The 2,972
reference-only SNPs remain visible. No production cache registration, frozen
configuration, G0 or current DAG/deployment acceptance is granted here.

Full machine-readable member identities and scope are in
`evidence/ldsc-author-reference-equality-20261015.json`.
