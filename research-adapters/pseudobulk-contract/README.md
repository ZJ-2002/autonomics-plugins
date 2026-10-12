# B raw-count aggregation candidate

This component sums raw RNA counts by an explicitly declared biological
observation and cell type. It does not select cells, annotate cell types,
normalize expression, select a contrast, run a differential model, freeze a
family, establish biological independence or grant G0.

Inputs are the frozen recipe plus six files in this order: MatrixMarket raw
counts, three-column 10x features, one-column barcodes, the original v4.2.1
27-column sample map, a complete cell map, and a metadata byte pack. All
consumed bytes and the actual Python/SQLite versions must match the recipe.
The recipe's `FROZEN` applies only to aggregation parameters. Formal execution
requires independent signed study/module/method/input admission.

The unit policy enumerates DONOR/ANIMAL/POOL definitions and explicit
observations. A biological member cannot appear in two independently named
units within the same original cohort. Technical libraries may share one
observation. Repeated timepoints retain the same biological unit while using
distinct observations. Cohorts, tissues, groups and timepoints cannot be
implicitly combined. Pools with unresolved membership are retained for
descriptive aggregation and explicitly excluded from resolved declared-unit
counts; declared identities never become scientifically verified N.

The cell map columns are `matrix_column_id resource_id sample_id library_id
cell_id cell_type observation_id include reason`, tab separated. Each matrix
column must appear exactly once, biological cell IDs must be unique, inclusion
is YES/NO, and exclusions require a reason. Every included library belongs to
one explicit observation. All planned observation/cell-type columns and all
RNA features remain present, including zero cells and zero counts. Zero-cell
columns are marked `ZERO_CELLS_NOT_INFERENTIAL`; they must not be treated as
observed all-zero biological expression in a downstream model.

Counts use general coordinate integer or integer-valued real MatrixMarket.
Negative, fractional, nonfinite, duplicate-coordinate and out-of-range counts
are rejected. Per-output sums cannot exceed 2^53−1, for exact R double-backed
integer interchange. Duplicate coordinates are rejected rather than silently
coalesced. Non-RNA feature exclusions and all cell QC decisions are retained.
Integer values alone cannot prove raw-count provenance: GB07 remains a
scientific/source qualification requirement.

The SQLite scratch database has an explicit page budget and bounded cache;
metadata files/rows have bounded readers. Matrix/cell/barcode data stream to
local scratch. A scratch database budget does not bound total output or all
filesystem consumption. The whole worker's disk/memory/time admission and
large-data resource qualification remain mandatory.

The component atomically publishes a complete internal bundle without
clobbering. The generated container entry point exposes six ports only after
aggregation succeeds; the normal container publisher must observe successful
execution before publishing these staged files. Failure/cancellation can leave
diagnostic workspace bytes, never qualified results. Partial staging must not
be mistaken for a completed formal artifact set.

`research_b_counts.py` prepares an unsigned proposal preserving original B
families, all G0-R/G0-B items and viewing history. Its DAG fragment wires seven
actual File inputs through `frozen_config_inputs`; it does not supply a B
hypothesis universe, differential model or sealed result decoder. This first
adapter accepts static qualified inputs; dynamic annotation/QC producers
require separate acceptance.

`manifest.toml` is an unregistered candidate using the actual cached OCI
manifest identity, not a newly executed/qualified pseudobulk image. The
original registry digest and cached reserialization digest are distinct. The
image's SQLite version must be measured before an executable software lock is
admitted. The current sandbox cannot satisfy the existing protected Podman
subordinate-UID boundary; no relaxed execution is accepted in its place.

Local synthetic tests include an independent R `Matrix` read/multiply oracle.
They qualify this aggregation component only. CI wiring is prepared; local
success is not a remote CI, container, method or biological acceptance.

Format reference: [NIST MatrixMarket formats](https://math.nist.gov/MatrixMarket/formats.html).
Method separation reference: [muscat official source and documentation](https://code.bioconductor.org/browse/muscat/).
