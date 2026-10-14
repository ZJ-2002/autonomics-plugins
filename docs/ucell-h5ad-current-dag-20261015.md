# UCell H5AD: official scoring and current-engine complete-object proof

The original candidate `FUNC_h5ad_ucell_score` now has an actual fixed **current
engine** proof, supplementing—not rewriting—the earlier sealed SDK proof. Its
canonical kind remains `h5ad_ucell_score` in `plugins/ucell-h5ad`.
The scoring adapter and manifest are unchanged. It calls official **UCell 2.16.0**
`ScoreSignatures_UCell`; no Rust estimator or legacy rank approximation is used.

## Inputs, outputs and fixed official scope

The one file input is H5AD, explicitly `X`, with finite real values, exact
R-double integer representation and unique lexical cell/gene axes. The required
`gene_sets` JSON parameter preserves signed `+/-` members. No species mapping,
normalization, missing-member deletion or eligibility decision is invented.

Output port 0 is `output.h5ad`: official scores added to `obs`, explicit
`ucell_params`, and otherwise preserved AnnData contents. Port 1 is `report.json`:
exact axes, requested/present/missing members and arms, parameters, summaries,
official batch/table/code hashes, runtime packages and external output identity.
The report does not grant scientific release or implementation locking.

Fixed official settings are maxRank 1500 (capped by gene count), w_neg 1,
missing_genes impute, average ties, SerialParam/ncores 1, chunk.size 100 and no
score-column suffix. Negative-only signatures follow official zero-clipped
positive-minus-negative semantics, not invented reverse enrichment.

## Complete original inventory, not selected easy cases

All **54** original method/boundary cases are accounted for:

| Actual route | Cases | Result |
| --- | ---: | --- |
| Current two-node/one-edge DAG, valid | 20 | Whole author objects and reports match |
| Current DAG, invalid method input | 26 | Exact refusal and no normal output |
| Missing required gene_sets parameter | 1 | Exact graph preflight refusal |
| Direct filesystem/fault-injection checks | 7 | Exact refusal, source/sentinel preservation |

The **46 executed DAGs** have **46 verified input bindings** and **40 successful
declared output ports**. Positive cases include dense/CSR/CSC, boolean/integer/
float matrices, close doubles and signed integer limits, lexical IDs, reordered
axes, tied/flat/rank-cutoff/boundary cases, unrelated raw data, previous parameter
metadata, one cell/program and multiple batches.

The seven direct checks cover existing H5AD/report, dangling output, output alias,
input overwrite, injected second-link publication failure and injected R failure.
They are explicitly not mislabeled as DAG cases. Input bytes remain unchanged;
existing sentinels remain unchanged; ordinary failed publication rolls back.
The owned dangling toy fixture is removed only after recording its unchanged
target so that the permanent archive does not retain an unresolved fixture link.
No crash-atomicity or persistent-resume claim follows from these checks.

Two additional current graph preflight checks reject an unknown parameter and
the disconnected input port using exact node/parameter/port diagnostics.

## Whole-object author comparison and preserved failures

The independent author source/package, mathematical reference and old outputs
were not regenerated. The original seal is fully rechecked: **1,901 files /
108,033,663 bytes**, ten exact internal links and three declared negative dangling
fixtures. The separate final-verification file is bound by its own exact hash,
not silently exempted as an arbitrary extra file.

All **20** current positive H5AD objects match the sealed independent-author
objects: `X`, axes/metadata, layers, embeddings/loadings, cell/gene graphs, `uns`
and raw objects, plus the entire HDF5 hierarchy, attributes and dataset dtypes.
**148,165 finite values** are checked; integer identities are exact and floating
comparisons keep atol `1e-12`, rtol zero. Complete reports match the old sealed
reports except their output-file identity, which is independently remeasured
against each actual current H5AD. No arbitrary report fields are dropped.

Two technical verifier failures remain visible, not relabeled as passing runs:
the first attempted to exclusive-create the same progress checkpoint twice;
the second completed all DAG cases and comparisons but could not write the reader
report under the container user mapping. The follow-up uses `--userns=keep-id`,
rehashes the unchanged sealed DAG stage, re-reads its 20 objects readonly and
executes the seven pending direct cases. **It does not rerun those DAGs, invent a
successful old worker exit, modify a golden or overwrite the earlier archive.**

## Identity, lifecycle and non-release boundaries

Engine: `db83a6bb9886e4b1a3c563bef9261df782a0050c`.
Executable SHA256: `9dae47f22c5feeca79dd005ede43c16349b3b362530646e2220fcb8d40bc0069`.
Official image digest: `e18149dc957c70161029c3451584d7285ab08af2174926c593b8ae285f2dd133`.
No engine/image rebuild or copied dependency environment was needed. All managed
sessions have terminal records; disposable scratch is cleaned and permanent
proofs remain. The complete local required source suite executes **208 tests,
zero failures/errors/skips**, with matching catalog lock.

See [machine-readable evidence](../evidence/ucell-h5ad-current-dag-20261015.json)
for exact case enumeration, six archive seals, source hashes, failure provenance
and remaining limits. This supplements the old scoped card rather than changing
historical baseline counters or claiming an additional original function slot.

This is **ACCEPTED_SCOPED_TECHNICAL_CURRENT_GENERIC_ENGINE**. maxRank 1000/2000,
smoothing and other parameters require their own route/proof. The sibling TSV
wrapper is a different contract, not automatically certified. Real study species,
expression scale/background, coverage, cell/donor eligibility, actual full scale,
anonymous image installation, daemon loading, scientific contracts, global quotas
and persistent recovery remain separate. No deployed configuration, frozen
family, viewing history, 276/288/696 denominator or G0 status changes. Spatial B-S
remains CONDITIONAL_NOT_READY and GS01 remains OPEN.
