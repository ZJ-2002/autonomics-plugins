# Direct Open Targets reference acquisition: running, not yet qualified

The official documentation recommends [data downloads](https://platform-docs.opentargets.org/data-access/datasets)
for systematic access; it provides partitioned Parquet. A complete independent
file reference is being acquired because the preserved live pagination control
returned duplicate IDs and incomplete unique membership. This does not silently
deduplicate that response, declare it fixed, or replace a frozen study source.

## Exact bounded scope

The protocol consumes the already sealed 26.09 resource audit, not newly guessed
URLs or mutable latest-version listings. It requests all 14 `association_overall_direct`
partitions, all three `target` partitions and the one `disease` file:
**18 files / 867,128,423 exact compressed bytes**. These are complete raw files,
not row samples. Datasource/datatype breakdowns and indirect datasets are outside
this acquisition and receive no implied completeness claim.

Every request requires the exact official HTTPS origin/path, stored ETag,
Last-Modified and length, HTTP 200 and identity encoding. Redirects, ranges,
changed/truncated/overlong bodies and non-Parquet framing are refused. The driver
uses one request per file, a two-second interval and no automatic retry/fallback.
Partial transfers remain disposable scratch; a complete verified file publishes
without overwrite into required permanent evidence. SHA256 is measured while
streaming: it is not mislabeled as an author-published checksum. A conservative
20-GiB free-space check precedes network access; no environment is cloned.

The acquisition is managed session `3a35db8dda8e44018860e7e1895e9c7d` and remains
running at this protocol publication. **There is no terminal acquisition seal or
source-PASS receipt yet.** Do not rerun it merely because observing the handle
times out. After authoritative completion, rehash the complete archive and then
verify every partition schema, complete control membership, annotations, score
and novelty semantics. File acquisition alone is not a working source node,
GraphQL equivalence, a production deployment or scientific release.

Seven new source/unit checks cover request identity, toy complete/truncated/
overlong/invalid bodies, refusal to overwrite and strict software-record parsing.
The complete required local source suite is **226 tests**, zero failures/errors/
skips, matching catalog lock. These are not 226 method/node certificates. See
[protocol evidence](../evidence/opentargets-direct-source-acquisition-protocol-20261015.json)
for source hashes, exact prior resource identity and completed audit/test seals.

## Uploaded template and active study records are different surfaces

The uploaded ZIP remains exactly SHA256
`4c5af762ab1e9768a24b9446827ea367176a80407862cfc10ca09a95f44f1151`.
A separate read-only comparison of its 18-row software template against the
active project's 18-row software record identifies **six evolved rows**. The
active record includes minimum-scope QC, TwoSampleMR 0.7.11 and normalized-bulk
limma 3.68.5 locks, an MRlap not-enabled decision, and synthetic-only UCell/
singscore program branches. This audit observes those records; it does not
validate their entire approval chain or grant a new scientific signature.

Existing matching source routes include `plugins/twosamplemr-v432-a` and
`plugins/bulk-limma-normalized`. Their existence is not proof of current image
availability, daemon loading or full method qualification. In particular, the
generic TwoSampleMR 0.7.9 and count/voom limma 3.66.0 scopes cannot be relabeled
as those project-specific versions or used to replace a normalized-array model.
The active software records are not overwritten with blank uploaded templates;
neither surface is changed. No cohort expression/GWAS result is read or fitted
by this software metadata audit.

The three remaining historical source routes (literature search/fetch and
Open Targets associations) retain their actual unresolved scopes. This document
does not reclassify all other nodes as production-certified, alter the original
120-slot denominator or erase historical pending states. Spatial B-S remains
CONDITIONAL_NOT_READY and GS01 OPEN. Frozen families 276/288/696, source selection,
viewing history and G0 remain unchanged.
