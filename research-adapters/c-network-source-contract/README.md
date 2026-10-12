# Physical-source normalization candidate

`c_network_source_normalize` converts a complete content-bound STRING physical
gzip to the original v4.2.1 edge schema and an explicit complete graph background.
It does not infer experimental literature/assay identity from `combined_score`.
The six fixed inputs are configuration, original design ZIP, gzip, human
protein-to-gene mapping, detection/expression background and evidence annotations.
They are all SHA256/byte-bound before use and rechecked before publication.
The ZIP is content-bound here; the protocol compiler separately verifies its
original delivery and semantics.

The configuration must name the concrete release, score threshold, projection
and deduplication rules, complete input identities, actual Python and converter
source identities, and all source IO/decoded-byte/row/SQLite budgets. There is
no implicit threshold, selection of significant edges or budget truncation.
SQLite is private temporary staging. Its declared limit covers the database,
not total workspace usage; full source/output IO budgets are separate.

Every raw protein has one explicit human gene mapping in the detection
background. Every raw protein pair has an evidence annotation, including
threshold-excluded and projected self pairs. Symmetric scores must agree.
Ambiguous mapping, missing/orphan/duplicate annotations, conflicting primary
lineages or malformed gzip block the entire conversion. Selected annotations
must declare `EXPERIMENTAL_OBSERVATION_DECLARED_NOT_VERIFIED`. Aggregated,
predicted or text-mining rows cannot masquerade as experimental observations.
Below-threshold and projected self pairs are counted. Selected annotations
are deduplicated by unordered gene pair and declared lineage, keeping the
lexicographically first primary identifier. Original source identity and
deduplication counts remain in the audit. Degree counts unique neighbours;
multiple annotations do not inflate degree or certify independent replication.
All background nodes, including isolates and non-detectable nodes, remain.

Conversion reads and validates the entire gzip/mapping/evidence source with
bounded chunks/rows and database indexes. It atomically publishes a new complete
three-file bundle: `network-edges.tsv`, `network-nodes.tsv`, `source-audit.json`.
The fixed embedded wrapper applies the declared child address-space limit and
links exact output ports from this verified bundle. Port linking failure fails
the node; production artifact admission still requires the real engine to
publish no normal outputs from a failed node.

Normalization schema 2 additionally requires both expected normalized source
identities before compilation. These are source preprocessing identities,
not expected statistical findings. The converter checks exact SHA256 and byte
counts before publishing any normal output. Schema 1 remains exploratory and
cannot feed the new formal-entry conversion route. `compile_source_dag` checks
the complete original method preparation, original archive, exact normalization
declaration, all six distinct admitted source leaves and complete output/method
budgets, then replaces only the two source leaves with the fixed converter.
Original per-analysis recipes retain the exact normalized source identities.

The service calls the native C/source lineage check before DAG construction.
It reads actual admitted template, normalization declaration and original
recipe-bundle bytes, checks complete raw-source identities, requires the exact
same converter ports at binder and method, and verifies every original recipe
against the predeclared converted graph and actual seed file. Lossless shared
background bytes and noncanonical original literal recipes remain supported.
Malformed/duplicate metadata, changed source identity, missing recipes or audit
bindings, hybrid static/generated inputs and orphan converters are rejected.
The normalized edges/nodes and source audit must be named sealed outputs.
This structural check runs inside the existing authorization path, after G0
authorization and before loaded-method and resource verification; it cannot
replace either. Real source/experiment lineage and scientific approval remain
external signed inputs.

Regressions exercise real host conversion, embedded entry and child resource
limit, including 45,000 synthetic aliases/lineages and files beyond 16 MiB.
These records are synthetic capacity evidence, not independent experiments or
a qualified real STRING release. The candidate image is pinned but not qualified
by host tests. Loader validation does not execute OCI. No deployment, resource
admission, biological lineage verification, scientific sign-off, G0 grant,
family freeze, protected-worker acceptance or formal authorization follows.

`scripts/tests/prepare_c_network_source_host_pipeline.py` builds an explicitly
synthetic host fixture from the actual design bytes. Its converter feeds the
native binder and fixed method directly; the declared original recipes retain
the exact expected normalized source hashes. It exercises the production candidate
compiler; actual protected worker/image and real source qualification remain
required before formal admission.

Build and checks:

```sh
python3 -B scripts/build_c_network_source_wrapper.py --check
python3 -B -m unittest discover -s scripts/tests -p test_c_network_source_normalization.py -v
cargo test -p container-plugin --lib c_network_source_candidate --locked
```
