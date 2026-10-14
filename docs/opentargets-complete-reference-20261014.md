# Complete disease associations: official source still fails the control

The remaining original Open Targets association source cannot be accepted as a
complete disease download merely because a small page, transport or graph runs.
The old 2026-10-11 audit recorded duplicate targets across official pages. This
new independent **single pass** rechecked the same already-seen MONDO_0004975
technical control, not a new scientific dataset or native Rust statistical method.

Actual primary API metadata remained equal before/after: API 26.9.0/data 26.09.
Five official pages returned the declared 12,918 rows, but only **12,882 distinct
target IDs**: **36 IDs repeat across page indices 3 and 4**. Complete raw requests,
responses, metadata and per-ID page/offset/score positions are archived. Nothing
was deduplicated, the denominator was not shrunk and requests were not retried
until a favorable result appeared. The old 38-duplicate observation is retained
as historical evidence, not relabeled as the new count; a backend cause is not
proven by tied scores alone.

Session `0679e78e0f4140e08ecf2aa659303016` exited 0/CLEANED because the audit
completed and archived its **negative** source result. That is not source
completeness PASS, native-node/DAG acceptance or G0. The permanent source packet
is about 4.61 MiB/25 files; its temporary workspace is removed. Exact identities
and truthful status are in `evidence/opentargets-complete-reference-20261014.json`.

The complete disease route remains PENDING/NOT_READY. The existing SDK's
duplicate-member rejection must not be weakened. Do not replace it by a small
page, silently drop repeated targets, reduce the expected count, change disease
selection or substitute a different release to make the report green.

## Appropriate next engineering branch

The author documents direct GraphQL access for individual entities and official
partitioned Parquet data downloads for more systematic access. An official bulk
alternative is therefore a legitimate branch to **audit**, not a method or
scientific contract to silently choose. Before a new source route could qualify,
it needs an explicit release/schema, direct/indirect score interpretation, entity
annotation joins, complete membership/count identity and resource budget, plus
independent comparison and scientific review where required. No bulk dataset was
downloaded or selected in this recheck; frozen study configuration is unchanged.

Rust may remain HTTP/typed-I/O glue here: the scores are supplied by the official
service, not a reimplemented native statistical estimator. The Python reference
calls that same primary endpoint directly and does not bypass scientific gates.

Primary author documentation:
- [GraphQL API](https://platform-docs.opentargets.org/data-access/graphql-api)
- [Official datasets](https://platform-docs.opentargets.org/data-access/datasets)
