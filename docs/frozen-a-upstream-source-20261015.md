# Frozen A upstream runtime and author-artifact identity

Subsequent evidence: the [direct raw/PLINK replay](frozen-a-input-qualification-20261015.md)
has completed. Its report also records a discovered scope-alias regression and
the expanded 22-guard candidate; the earlier cutoff below is preserved.

These records qualify source/runtime identities, not a completed upstream DAG,
production deployment, a new scientific observation, or G0. Existing B replay
and A harmonisation evidence retain their original identities and scopes.

## Actual completed checks

| Check | Actual evidence | Scope |
| --- | --- | --- |
| Official CPython runtime | Session `f65435f9ab8548d7bfcbe18e1247180e`, seal `ee5c7c2b914a174ad3f7248efcc1bd5a9e5908c86dc8ad164f52cddcb25fd127`; 37 archived members independently rehashed | Official image manifest/config and four installed layers inspected; one bounded container actually reported CPython 3.14.7/x86_64 and passed a standard-library smoke check. No study input or fit. |
| Frozen PLINK author binary | Session `d0ec748b477e4297aac69ec57b5c959d`, seal `b3b6aba624d6baea07163ff4a2b3804e9cb127e7a279611b4a580c46c24e48af`; four archived members independently rehashed | Downloaded author ZIP, extracted the bounded `plink` member without executing it, and compared its complete size/hash with the unchanged frozen binary. |

The runtime is
`docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d`,
config `sha256:ea130d51594b38acddd30f9f2542a38c37736000f1710fb8c1058b6c3e613f8c`.
The pinned [official image recipe](https://github.com/docker-library/python/blob/688a0b86bb44289df16a363e9f41d90514c1a5f9/3.14/slim-trixie/Dockerfile)
has SHA256 `4abd3e86a4f5f89e615405ce0cb90411a8164f14a4949a11818ce1490585e158`.
The pre-existing shared installation owner record was not rewritten, and prior
images were not removed. This is not a claim that the entire original host
environment is byte-identical to the image.

The [PLINK author page](https://www.cog-genomics.org/plink/1.9/) documents the
download bucket and historical build date. The dated
[author ZIP](https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_20231211.zip)
was actually fetched with HTTP 200: 8,953,953 bytes, SHA256
`1162eca207ecec12b03397a3a9be5eed0527f5d21c173dc24335340ddd191bc3`.
Its extracted binary is 41,730,792 bytes, SHA256
`03ed6dd8882fddee7a89396c59ea56e4b17bbc4411d3049910e5d713fc8a135f`,
exactly equal to the frozen `PLINK v1.90b7.2 64-bit (11 Dec 2023)` binary.
The dated URL was derived from the author's naming scheme and release history;
it is not claimed to be a current direct link or an immutable server object.
Downloaded ZIP/binary comparison scratch was retired by the managed session.

## New candidate: original raw QC and official LD qualification

`research-adapters/frozen-a-input-qualification` declares nine fixed file inputs,
twelve outputs and no analyst-selectable method parameters. It calls the two
unchanged frozen Python source functions and the pinned official PLINK binary;
it does not replace their algorithms with a Rust or Python statistical port.
It independently checks the complete expected within-window haplotype pair set,
coordinates, duplicates, missing pairs and the strict frozen R2 threshold.

Raw GWAS files are read-only sources, not replicated acceptance payloads. The
isolated DAG uses a temporary 66-file copy-on-write panel transport because its
strict cache excludes an embedded manifest; the separate pinned input manifest
and every panel payload remain verified. Reflink failure must refuse execution,
not silently copy gigabytes or hard-link canonical source inodes.

At an earlier checkpoint the candidate had only self-cleaning toy evidence.
That checkpoint has been superseded by the completed direct replay in session
`fe8d9c30ecfc46de9b1d38f81e3723be`: all seven byte-comparable frozen products,
26 official PLINK commands and twelve output ports were verified. See the
[scoped direct raw-qualification evidence](frozen-a-input-qualification-20261015.md).
This is direct execution evidence, not proof that the DAG or deployment passed.

The dedicated scopes and proof drivers are implemented in source. Full runner
compilation and execution of all **23** Rust guards, the seven-node
harmonisation DAG and the ten-node raw-qualification DAG remain pending.
Container resource peaks and production deployment also remain unproven.
Neither implemented source, a source test nor the runtime smoke result fills
those missing cells.

Production restart/hot reload remains prohibited while the user's research is
running. Unrelated active builds and protected caches are not stopped or erased
to make admission pass. Spatial B-S remains `CONDITIONAL_NOT_READY`, GS01 `OPEN`.
