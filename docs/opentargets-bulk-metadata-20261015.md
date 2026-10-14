# Open Targets 26.09: bounded bulk-resource and schema audit

The author's [download documentation](https://platform-docs.opentargets.org/data-access/datasets)
provides partitioned Parquet datasets for systematic access. This audit examined
official directory listings, exact file HEAD identities and one footer per dataset.
It did not download association rows, select a study source or implement scoring.

| Official direct dataset | Partitions | Exact compressed bytes |
| --- | ---: | ---: |
| association_overall_direct | 14 | 839,148,848 |
| association_by_datasource_direct | 14 | 861,231,637 |
| association_by_datatype_direct | 15 | 860,236,411 |
| target | 3 | 21,633,117 |
| disease | 1 | 6,346,458 |

The 47 files total **2,588,596,471 bytes**, approximately 2.41 GiB. This is a
remote compressed-size audit, not local downloaded space or an execution peak
budget. Every file's HEAD URL, length, ETag and Last-Modified are archived.
Five sample metadata footers total 32,590 bytes. Range requests require exact
HTTP 206/Content-Range/ETag and bounded lengths; a full-file fallback is forbidden.

Official PyArrow **25.0.1** read the five metadata-only containers, using an
already cached digest-pinned image with networking disabled. No dependency
environment was cloned and no data-row reader was called. Sample association
schemas include `diseaseId`, `targetId`, `aggregationType`, `aggregationValue`,
`associationScore`, `evidenceCount`, `timeseries` and `currentNovelty`.
Target/disease samples contain the expected annotation IDs and names.
Field presence does **not** prove GraphQL equivalence, annotation completeness,
direct/indirect interpretation, null handling or unique complete membership.
Only one partition schema per dataset was examined, not all 47 schemas.

## Preserved failure and minimal repair

The first metadata run successfully acquired all resource identities and sample
footers, but the container could not read a private mode-0700 directory. Its
worker exit remains 1; all 33 files/114,050 bytes remain sealed. The driver now
uses `--userns=keep-id` and the operator UID/GID, not world-readable permissions.
Six unit tests cover range rejection, bounds, private-directory/image identity
and full sealed-archive verification, including retaining the original failed exit.

The final repaired run consumed the complete hash-checked original metadata
archive, copied only small verified metadata into its own permanent evidence,
and ran the reader offline. **Zero network requests were repeated.** It did not
rerun or relabel the old failed job. Final session
`5addbe9b7690453b84ee54154486ab42` exited 0/CLEANED, preserving 25 technical
files/97,019 bytes. All manifests and their exact file membership/content hashes
were independently rechecked; identities are in
`evidence/opentargets-bulk-metadata-20261015.json`.
All 157 required source/catalog tests actually ran, with zero failures, errors
or skips; the source lock matched. These are not 157 scientific certifications.

The preceding [official live pagination failure](opentargets-complete-reference-20261014.md)
is unchanged. Bulk complete-source qualification is **PENDING**. No native
statistical method, daemon loading, full disease DAG, new function slot, formal
research authorization or G0 is claimed. Frozen study configuration and
276/288/696 family denominators remain untouched.
