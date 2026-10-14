# LDSC declared panels: content and structure, not scientific eligibility

Both repositories declared by the canonical plugin are publicly accessible at
the immutable revisions recorded here. Their complete packages were downloaded
once, with two bounded transfer workers, into mandatory managed evidence rather
than a new dependency environment or numbered vault. The **88 files total
26,093,666 bytes**. Every object size/hash, the canonical unsigned catalog digest
and the exact chromosome/file inventory were verified. No production cache index,
plugin binding or frozen study configuration was changed by these tools.

| Declared package | Immutable repository revision | Content digest | Verified files |
| --- | --- | --- | ---: |
| wjixiang/catalog-ldsc-ref-ld-1000g-eur-basic | 02ed9238d391d6acd855f99e7529515619f91f5f | sha256:6468558bcf37cb2cbf276efe3c6f07b165bf88ea09427f0087c5cdcb504ac4e6 | 66 |
| wjixiang/catalog-ldsc-w-ld-1000g-eur-hm3-no-mhc | c00f382ddf7bb6d089388fd4c8f7285d9a1cc313 | sha256:61d606846e70a9c8dea979fd5e882b163550bc9f427a6979d0692bd716a7e6a9 | 22 |

Primary manifest sources are the immutable
[reference manifest](https://huggingface.co/datasets/wjixiang/catalog-ldsc-ref-ld-1000g-eur-basic/resolve/02ed9238d391d6acd855f99e7529515619f91f5f/v1/sha256-6468558bcf37cb2cbf276efe3c6f07b165bf88ea09427f0087c5cdcb504ac4e6/manifest.json)
and
[weight manifest](https://huggingface.co/datasets/wjixiang/catalog-ldsc-w-ld-1000g-eur-hm3-no-mhc/resolve/c00f382ddf7bb6d089388fd4c8f7285d9a1cc313/v1/sha256-61d606846e70a9c8dea979fd5e882b163550bc9f427a6979d0692bd716a7e6a9/manifest.json).
Public copies of those factual inventories are retained under
`provenance/ldsc-declared-panels/` and tested against their published digests.

## Complete payload structure

An offline second pass rehashed the complete sealed download and read every
decompressed score row across all 22 chromosomes. It verifies the exact basic
`CHR SNP BP L2` schema, chromosome labels, positive coordinates, finite scores,
unique SNP IDs within/across chromosomes, and single-annotation positive M and
M_5_50 counts with M_5_50 not exceeding M. It does not mutate score values or IDs.

- Reference panel: **1,190,321** unique SNP rows.
- Weight panel: **1,187,349** unique SNP rows.
- Shared IDs: **1,187,349**, with identical coordinates for every shared SNP.
- Reference-only IDs: **2,972**; weight-only IDs: **0**.

The unequal axes remain visible. No rows were discarded or silently intersected
to make the packages appear identical. Full per-chromosome counts and source
identities are in `evidence/ldsc-declared-panel-resources-20261015.json`.

Download session `66c189d36d4144fe805ec617b8314244` exited 0/CLEANED; manifest
`b1034169ef0230f4c7ca66da2abe55e2611113a6617ff11ea2d8ecd24a65b6c2`.
Current offline structure session `c18caf1159704b58862f42fe2c2c8780` exited
0/CLEANED; manifest
`186f8fb295c330c8d686fff74ff8f5967d2341a11dec5cace256658c690f9bec`.
Both discovery/manifest archives and both payload/structure archives were
independently rehashed, including exact membership. Raw reference payloads and
private launcher records are not published to Git.
All 184 required source tests ran without failures, errors or skips; the exact
test inventory and source lock matched. Six resource-focused tests additionally
cover canonical live manifest digests, current evidence/source binding, altered
inventories, unsafe identities, duplicate/nonfinite score rows and conflicting
coordinate axes. These tests do not certify the biological source selection.

## Explicitly unproven

The manifests declare EUR and GRCh37, but do not establish independent author
distribution provenance or sample/ancestry eligibility. A matching checksum
proves these exact catalog bytes, not that a catalog maintainer selected the
correct scientific reference. These packages are not substituted with the
different MRlap panel. Published availability is not actual engine-cache
registration or materialization in a DAG.

Therefore author-distribution equivalence, frozen reference selection, real-data
end-to-end computation, current isolated DAG, resident deployment and G0 are
**not granted**. The separate synthetic nine-case DAG candidate remains pending
its controlled compilation. Scientific inputs, candidate families and the
276/288/696 denominators remain untouched.
