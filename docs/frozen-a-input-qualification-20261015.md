# Frozen A raw-input and official PLINK replay

## Completed direct evidence

Session `fe8d9c30ecfc46de9b1d38f81e3723be` is terminal `CLEANED`, with an
integer worker exit of zero and manifest seal
`603b93a279e42c97e029454e418219d0e5f8cb149904fbbfd5057803d85e7193`.
Root and an independent reviewer rehashed all 46 archived members
(4,025,394 bytes). The reviewer checked actual products, command receipts,
reference bytes and archive members, not just the driver's summary.

| Requirement | Actual result |
| --- | --- |
| Runtime and tool | Official CPython 3.14.7 image and author-artifact-matched PLINK 1.90b7.2; unchanged frozen Python functions |
| Raw input traversal | 8,086,215 X rows and 39,824,509 M rows, recorded in the actual QC output |
| Interface | Nine input roles and twelve nonempty readable output files |
| Frozen products | All seven byte-comparable products equal the complete canonical files |
| PLINK execution | Thirteen clump and thirteen haplotype-LD commands; all actual exits zero and original argv preserved apart from explicit private I/O prefixes |
| Retained instruments | Exactly 39 |
| Complete LD check | Eleven expected within-10-Mb pairs, all present once with matching coordinates; finite R2 in [0, 0.001), maximum 0.000912602 |
| Original tool artifacts | 104 ordinary tar members, 3,133,031 payload bytes, every member rehashed and twelve raw LD reports parsed independently |
| Failure behavior | Changed configuration exits exactly 2 with the specific size-mismatch diagnostic and no normal outputs |
| Source preservation | Original inputs, all 66 panel payloads, candidate source and shared installation owner rechecked unchanged |
| Full frozen verifier | Actual exit zero; passed/read-only, no errors, 46,786 hash checks and 23,669 unique files |
| Worker lifecycle | Two recorded container intents, both independently matched to stopped records with remaining count zero; temporary session retired |

The original QC and LD JSON files have private command paths, so they are not
claimed byte-identical. Their complete non-command scientific fields match the
canonical JSON. Independent command comparison normalizes only the explicitly
different project/panel I/O prefixes. Raw data, the panel and copied executable
are not included in the permanent result archive.

The two-GiB container limit is declared and used, but this archive does not
provide a container peak-memory time series. Do not describe it as a measured
peak or as proof of global concurrency/resource isolation across other sessions.

## Scope-boundary regression discovered before DAG acceptance

Independent review found that the planned runner's synthetic path rejected
fixed family display names but not renamed manifests retaining fixed kinds.
This could bypass its real-source capsule/topology gate. No new DAG had been
accepted under that candidate, and this does not alter the direct replay above.

The actual old Rust function was extracted without translating its logic and
tested using the existing locked dependency cache. Session
`167fe2a8216b448c87fe0ee01d4d4d8d`, seal
`41caa3e1931b9f04f8f3cefd2bd6509beee2ec72feaebe052dee206eae85ca58`,
preserves the complete old probe and eleven rehashed members. Its regression
test really failed with exit 101: the renamed family admitted a fixed kind.
The session worker's zero exit means the expected counterexample was captured,
not that the old guard passed.

The repair checks the job's kinds and the parsed primary/additional manifests,
rejecting the four frozen-specific kinds in synthetic scope while retaining
legal normalized-bulk toy methods. Session
`38fdcb1e3ddd4a14b27cc62ad60b999f`, seal
`cce311baa61a199bbca6f67cc8cdf91eaf59c6698f46608644cd68929c5da919`,
contains eleven independently rehashed members and two actual passing extracted
Rust tests. It is a focused regression proof, not a full runner build.

The focused alias-repair snapshot SHA256 is
`9b809a50af7219f407dc457e50544aeb1bd6c2d480d63ff6cf33b6e52cd94580`.

An additional staging review identified a separate transport problem: a staged
symlink to a scratch input which itself points outside the mounted scratch
parent is dangling inside the container. A 32-byte, two-container controlled
experiment reproduced `ENOENT` for that old mount pattern; direct binding of
the canonical parent produced the exact bytes and refused writes with `EROFS`.
Session `cecbd8ea34b44a54b04a765a3500b917`, seal
`3ef9639ac112d9138289f64d73da4007c05a7cf41d64b240b9fe9185af5674b7`,
contains seventeen independently rehashed members and two stopped containers.
This is container visibility evidence, not actual VFS/DAG evidence.
The pinned engine already has an optional canonical-source resolution flag;
the original raw manifest does not enable it. This finding concerns that
specific default staging pattern, not absence of the optional engine feature.

The planned raw DAG now uses nine fixed read-only canonical-parent VFS mounts,
with port-specific paths; it creates no scratch aliases to raw inputs and does
not copy them into permanent evidence. The current probe SHA256 is
`81b0816929a585b159aaeb8c9cdeea8b8a0c93b340c2c3ae38ccaebe0e4475c9`.
The required full guard inventory is **23**, retaining the previous twenty,
adding two alias regressions and one canonical-source/port-role regression.
Full compilation and execution of all 23, the
seven-node harmonisation DAG, and the ten-node raw-qualification DAG remain
separate pending requirements. An occupied build slot is not waived or treated
as a successful build.

## Not granted

This proves the fixed X01/M06 direct raw-to-LD technical route only. It does not
run allele harmonisation, MR, MRlap, proxies, MVMR or the complete 276-edge and
288-path families. It does not assign the other edges' O classes, authorize a
new scientific analysis, certify production loading, or grant G0.
Production restart/hot reload remains unauthorized while research is running.

See also [runtime/author source identity](frozen-a-upstream-source-20261015.md)
and [the separately completed minimum B replay](locked-b-replay-and-index-20261015.md).
