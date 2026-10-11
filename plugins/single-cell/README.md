# single-cell plugin

Migrated from the legacy `single_cell_container` (10x preprocessor) and
`single_cell_h5ad` (ten H5AD workflow variants) wrappers in nodes-io. One
directory = one plugin family = one git-able unit, one image
(`single-cell-preprocessor`), eleven `[[nodes]]` entries.

## Layout

- `manifest.toml` — the eleven-node contract: params, ports, panel, image
  provenance
- `scripts/run_workflow.py` — shared runner shim for seven H5AD nodes;
  rebuilds the legacy `params.json` from `SC_P_*` env vars and execs the
  workflow runner baked into the image
- `Dockerfile`, `.dockerignore`, `requirements.txt`, `preprocess.py`,
  `workflow.py` — the image build tree, moved from
  `containers/single-cell-preprocessor/`
- `preprocess.py`, `workflow.py` — the two baked runner programs
  (`/opt/autonomics/preprocess.py`, `/opt/autonomics/workflow.py`)
- `test_preprocess.py` — unit tests for `preprocess.py` (`pytest`)
- `test_single_cell_preprocessor.sh`, `test_single_cell_workflow.sh` —
  real-Podman image baselines (build + inspect/ingest + QC/embed/subset)
- `IMAGE.md` — the runner-level contract inherited from the container
  README (env vars, file inputs/outputs, inspect vs ingest semantics)

## Nodes

| kind | operation | timeout | resources | outputs |
| --- | --- | --- | --- | --- |
| `single_cell_preprocessor` | inspect/ingest (MatrixMarket) | 3600 | 2 CPU / 8Gi / shm 1Gi | `preprocess_report.json`, `preprocessed.h5ad` |
| `h5ad_qc_filter` | `qc_filter` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `h5ad_pca_neighbors_umap_leiden` | `pca_neighbors_umap_leiden` | 7200 | 4 CPU / 16Gi / shm 2Gi | `output.h5ad`, `report.json` |
| `h5ad_celltypist_annotate` | `celltypist_annotate` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `h5ad_subset_by_obs` | `subset_by_obs` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `sc_dense_ingest` | `dense_ingest` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `h5ad_rank_genes_groups` | `rank_genes_groups` | 3600 | 2 CPU / 8Gi / shm 1Gi | `rank_genes_groups.parquet`, `report.json`, `output.h5ad` |
| `h5ad_cluster_mean_expression` | `cluster_mean_expression` | 3600 | 2 CPU / 8Gi / shm 1Gi | `cluster_mean_expression.parquet` |
| `gene_set_score` | `gene_set_score` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `h5ad_marker_annotate` | `marker_annotate` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |
| `h5ad_ucell_score` | `ucell_score` | 3600 | 2 CPU / 8Gi / shm 1Gi | `output.h5ad`, `report.json` |

Every node runs isolated (no network) with a read-only root filesystem and
`PullPolicy::Missing`, exactly like the legacy wrappers.

## Execution shape

### Embedding assurance candidate (2026-10-12)

`h5ad_pca_neighbors_umap_leiden` runs the tracked, injected
`scripts/embedding.py`, not the legacy baked branch. Its canonical kind,
ten parameters, two outputs, timeout and 4CPU/16Gi declaration remain
unchanged. This resource ceiling is not a laptop budget or deployment approval.

The recipe uses centered ARPACK PCA even when `scale=False`, then neighbors
explicitly from the first requested `X_pca` components, spectral two-dimensional
UMAP, and weighted undirected igraph Leiden with two iterations. `min_dist=0`
is valid. Requested PCA width is never silently reduced. Seurat HVG operates
on log-counts: newly normalized counts require `log1p=True`; with both
preprocessing flags false the caller must qualify already-logarithmized counts.

Existing `X_pca` skips normalization/HVG/scaling/PCA, even with no gene matrix.
Its upstream method, cell origin and unused data are not scientifically
qualified by this node. The report separates stored and used PC widths and
records performed stages, full feature retention, package versions and hashes.
Critical matrices must be finite; pre-existing opaque metadata follows AnnData.
Single-thread author kernels and integer seeds in the author RNG domain make
the frozen same-platform numerical comparison reproducible. This is not a
cross-platform distributional guarantee or a reference cell-type calibration.

The mandatory test entry is `test_embedding_assurance.sh`, with new
`EMBEDDING_EVIDENCE` and exact `EMBEDDING_REFERENCE_LIBRARY` paths. It exercises
both exact neighbors and a passively observed 9,000-cell PyNNDescent path.
The driver optionally takes an explicit author PBMC3k raw benchmark; neither
synthetic donors nor that benchmark are a qualified disease cohort.

No resident deployment, study counts/species/donor independence, HVG/cluster
threshold lock, statistical biological claim, global budget/cache/recovery or
G0 is granted. Normal publication does not overwrite and rolls back a second
link failure; this is not crash-atomic publication or persistent resume.

### QC assurance candidate (2026-10-12)

`h5ad_qc_filter` uses the tracked, injected `scripts/qc_filter.py`, not the
legacy baked workflow branch. Its address, eight parameters, H5AD input,
two output ports and declared resources remain unchanged. The image is
unchanged from the preprocessor assurance candidate.

The explicit recipe uses Scanpy 1.11.3 `calculate_qc_metrics` with X,
`qc_vars=["mt", "rb"]`, `percent_top=None`, `log1p=False`, `use_raw=False`
and no layer. It applies cell filters before gene-detection filters in
retained cells. Both bounds are inclusive; zero disables upper count
bounds, and 100 disables percentage bounds. Zero-library percentages
remain officially undefined (NaN in H5AD); active percentage bounds drop
those cells. Strict JSON records undefined summary fields as null.

Patterns match `var_names` case-insensitively, not an inferred symbol,
species or annotation column. Integer X is promoted to int64 with exact
row/column overflow checks. Sparse coordinates are summed and explicit
zeros removed before detection. Fractional nonnegative X is accepted by
the API, but this does not establish that the input is raw counts.
Neither raw nor a `counts` layer is selected silently. AnnData subsetting
preserves its official raw/layer/graph semantics; derived graphs and
embeddings are sliced, not recomputed or scientifically requalified.

The output preserves full cell/gene exclusion ledgers and hashes. Existing
outputs are refused; ordinary second-publication failures are rolled back.
This is not crash-atomic publication, persistent resume or a study QC lock.
The scientific implementation lock, donor/animal independence, species,
count scale, thresholds, resource-scale deployment and G0 remain ungranted.

Run `QC_EVIDENCE=<new-directory> QC_REFERENCE_LIBRARY=<official-library>`
`bash plugins/single-cell/test_qc_assurance.sh`. Required synthetic author
comparisons and refusals cannot silently skip. The test driver also accepts
an explicit author PBMC3k raw H5AD benchmark, which is not a study cohort.

### Preprocessor assurance candidate (2026-10-12)

`single_cell_preprocessor` retains its four File inputs, two File outputs,
five parameters, artifact prefix and resource declarations. The manifest now
injects the tracked `preprocess.py`; a candidate image also bakes identical
bytes. `Containerfile.assured` overlays the immutable deployed image without
changing its Python dependencies or baked H5AD workflow. This is deliberately
not the older `Dockerfile`, which copies the unqualified host workflow.

The wrapper explicitly selects official `read_mtx(dtype="float64")`, not
Scanpy's float32 default. Its `ingest` means file import, not the distinct
reference-mapping algorithm `scanpy.tl.ingest`. It validates complete coordinate bodies in ingest,
rejects negative/nonfinite values, and limits integer total mass to 2^53 to
guarantee lossless conversion and duplicate-coordinate summation. Finite
nonnegative real matrices remain supported; ingestion does not establish that
their values are suitable raw counts. Filter order is cells then genes, with
optional official total normalization to 10000 and natural log1p. All feature
types remain present unless gene filtering removes them; no implicit
`read_10x_mtx(gex_only=True)` is substituted. Empty filtered axes fail.

Barcode TSV is literal one-column text; feature TSV has two or three
rectangular columns. Cell metadata is strict quoted CSV/TSV with unique
headers and exact barcode membership. Literal identifiers, original symbols,
officially de-duplicated variable names and excluded axes remain traceable.
Inspect does not validate matrix values and its `X=None` H5AD is not
analysis eligible; all input bytes are nevertheless stream-hashed.

The report is schema 2.0: consumers must account for full axis ledgers,
technical-only eligibility and the absence of a recursive self-report hash.
The H5AD's hash is in the JSON; the caller records the report hash externally.
Existing output files/directories/dangling links are refused. Two outputs are
privately staged with ordinary-error rollback, not a crash-atomic transaction,
concurrent-writer protocol or persistent restart guarantee.

The candidate requires fresh independent author-wheel comparison, actual
baked-runner boundaries, original manifest compilation, isolated native DAG
execution and requalification of the shared `gene_set_score` image identity.
No complete-family, installed-daemon, full-scale, scientific or G0 acceptance
is implied. Nine other H5AD workflow implementations remain unqualified.

Retained, mandatory local tests (no GitHub Actions credit required):

```sh
SINGLE_CELL_EVIDENCE=/absolute/new-evidence-directory \
SINGLE_CELL_REFERENCE_LIBRARY=/absolute/fresh-official-wheel-directory \
bash test_preprocess_assurance.sh
```

Install AnnData 0.11.4 and Scanpy 1.11.3 independently from hash-verified official
PyPI wheels with `pip --no-deps --target`, while retaining the frozen numerical
runtime. The reference subprocess imports only those fresh author packages,
not the node source. Shared numerical libraries are not an independent BLAS
validation. Absence of a required image/reference is a failure, never a skip.

### Scoped scoring repair (2026-10-10)

`gene_set_score` now injects `scripts/score_genes.py` directly instead of
executing the older scorer baked into the image. This is necessary: editing
the repository's `workflow.py` alone cannot change a digest-pinned runtime.
The image, family panel, input/output ports and other ten node contracts
are unchanged. The scorer calls official Scanpy 1.11.3 with explicit
parameters, selects the raw gene axis when raw exists, does not clamp
`ctrl_size`, and preserves nonfinite official scores rather than silently
dropping cells from summary statistics. It rejects duplicate axes, output
column collisions and invalid signatures/seeds.

The supported wrapper requires two distinct present genes per signature;
this is not a claim to support every official Scanpy input or parameter.
Contract tests are `python -m unittest discover -s tests -p
'test_score_genes_contract.py' -v`. Run `tests/test_score_genes_container.py`
inside the manifest's pinned image for official-package comparisons.
These tests do not certify the complete family, the resident daemon, or
scientific interpretation. In particular, the legacy `h5ad_ucell_score`
implementation is not certified as official UCell. The family-level
CellTypist panel is still a deployment prerequisite for all nodes.

- `single_cell_preprocessor` is a **script-injected** node: the compiled argv
  is `python` plus the tracked and staged `preprocess.py`, and the
  five params travel through the same `AUTONOMICS_SINGLE_CELL_*` env vars
  the legacy wrapper set. The inspect-vs-filters cross-field rule is
  enforced inside `preprocess.py`, so no DSL-side validation is needed.
- Nine H5AD nodes are **script-injected** nodes with one shared shim;
  `gene_set_score` injects its dedicated official-package wrapper instead.
  The compiled command is `python` plus the staged shim (the legacy shape
  was `python` plus the staged `workflow.py` — byte-identical argv, a
  different program at argv[1]). The shim writes `params.json` to
  `/work/.autonomics/files/params.json` (the legacy path) from typed
  `SC_P_<KIND>_<name>` env vars (`INT`, `NUM`, `BOOL`, `LST`, `JSON`,
  `STR`; empty means unset and the workflow applies its own default), then
  runs `/opt/autonomics/workflow.py` from the image via `runpy`, so the
  Python implementation is the digest-pinned one, not a plugin copy.

## Install

```sh
export NODE_PLUGINS_ROOT=/path/to/autonomics-plugins/plugins
cargo test -p container-plugin --test single_cell_migration
```

Declare the plugin in `~/.autonomics/plugins.toml` (pin `rev` to a commit
SHA once published):

```toml
[[plugin]]
name = "single-cell"
git = "https://github.com/ZJ-2002/autonomics-plugins.git"
rev = "<commit sha>"
subdir = "plugins/single-cell"
```

## Historical migration parity

The following describes the pre-repair baseline at `1d681eac`. The scoped
scoring repair deliberately changes `gene_set_score`'s injected script and
seed bounds, so the old eleven-node byte-equivalence statement is not an
acceptance claim for this revision. Preprocessor injection, output schema and
shared image identity also deliberately change; the other nine workflow
interfaces are preserved, not numerically certified.

The golden test (`container-plugin/tests/single_cell_migration.rs`) compares
each compiled `ContainerCommandSpec` against the legacy Rust wrapper output:
image, panels, outputs (path + format + order), resources, timeouts,
artifact prefixes, and argv are byte-exact; scripts are compared
semantically. Deliberate deltas, all preserving runtime behaviour:

- **Per-instance `artifact_prefix`, `timeout_secs`, `cpus`, `memory`,
  `pids_limit` params are gone.** The manifest DSL carries them as static
  node fields (set to the legacy defaults); the plugin schema no longer
  accepts per-instance overrides.
- **`gene_sets` / `marker_sets` are JSON strings, not objects.** The v0
  param DSL has scalar types only (the coloc flattening precedent). The
  shim `json.loads` them; malformed JSON fails at runtime instead of at
  spec build.
- **Enum params became strings** (`operation`, `metadata_separator`,
  `orientation`, `method`, `normalize`): the workflow runners enforce the
  same value sets the legacy Rust `validate` did, now at runtime.
- **`include_percent_expressed` defaults to `true`.** The legacy Rust spec
  declared `false`, but the params.json it shipped never materialized
  Rust-side defaults, and `workflow.py` applies `True` — the plugin keeps
  the effective value.
- **`h5ad_celltypist_annotate` takes its model from the catalog panel**
  (`wjixiang/catalog-celltypist-models-pan-immune` mounted at
  `/panels/celltypist_model`) instead of an optional second input port:
  the DSL cannot declare optional inputs or per-node data bundles. The
  shim injects the mounted model as the legacy `AUTONOMICS_INPUT1`.
  Dropped with it: `use_catalog_model` (always true now),
  `model_bundle` (fixed by the family panel), and `model_path` (arbitrary
  host paths cannot be staged by the manifest pipeline).
- **`sc_dense_ingest` input is now a required port** and the `path`
  param is gone: optional input ports and host-side file resolution have
  no manifest equivalent, so the matrix must arrive through the port.
- **Output ports gained labels and formats** (derived from the declared
  outputs); the legacy ports were bare Files.
- **Cross-field validation moved into the runners** (nonempty patterns,
  positive bounds, enum membership, nonempty gene sets): the same rules
  the legacy `validate` enforced, now enforced where the value is
  consumed.

The family panel (CellTypist model) is attached to all eleven nodes
because the DSL binds panels per family, not per node — the ldsc munge
precedent; ten of the nodes never read the mount.

## Build and baselines

```sh
test_single_cell_preprocessor.sh    # image build + inspect/ingest baseline
test_single_cell_workflow.sh        # image build + qc/embed/subset baseline
pytest test_preprocess.py           # preprocess.py unit tests
```

`SINGLE_CELL_PRODUCTION_BASELINE=1 test_single_cell_preprocessor.sh` adds
the deterministic 20,000-gene by 50,000-cell gzip MatrixMarket header-only
baseline. Set `BUILD_IMAGE=0` to reuse an existing local tag.
