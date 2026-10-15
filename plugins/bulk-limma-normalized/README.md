# Normalized log2 bulk limma

Install this family explicitly to expose
`bulk-limma-normalized/bulk_normalized_design` and
`bulk-limma-normalized/bulk_normalized_limma` in the TUI DAG. It reuses the
byte-identical existing `b-bulk-limma-contract` numerical component. The DESIGN
and LIMMA wrappers explicitly read port zero; LIMMA adds actual result/RDS
output hashes. Its new digest-pinned R4.6.1 / limma3.68.5 / statmod1.5.2 image
copies only the two frozen installed packages over the existing MRlap base.
`reuse-lock.json` preserves original and adapted source hashes. The shared
image supplies the dependency environment; plugin scripts are separately
bound source files.
The image must be present in the runtime's configured store; installation
does not pull it or prove its current presence. The former protected-store
image observation does not establish a new runtime store's availability.
Actual offline import and eight synthetic R calls verified the exported
`723904…` manifest, config, ordered layer identities, package paths and Imports.
The sealed software archive is retained once; import it with
`skopeo copy --preserve-digests oci-archive:ARCHIVE containers-storage:localhost/autonomics/frozen-b-normalized:v432-export-verified`.
The destination store must match the runtime's configured store. The original
archive's source annotation names a prior transport identity; `podman load`
rejects it, so use this explicit destination without changing the archive.
See `docs/frozen-b-environment-admission.json` for reviewed identities and scope.

This method accepts normalized log2 expression, including RMA microarrays.
Use the existing `bulk-rnaseq/limma_voom` family for its documented count
contract. This family checks exact package versions, all original gene rows,
sample identities, independent-unit declarations, fixed covariates and
`eBayes(trend=TRUE, robust=TRUE)`. The denominator is the reference group;
the estimated coefficient is numerator minus denominator. It retains
constant and non-estimable rows with missing p values and writes the official
R fit object. After the unchanged fit, the LIMMA entry computes the two
complete-vector `q_BH` and `q_BY` columns through official R4.6.1
`stats::p.adjust`, with `n` equal to all retained rows and non-estimable raw
p values represented by 1 only for adjustment. Raw missing values remain
`NA`. The audit's `family_adjustment` records the backend, R/stats versions,
methods, total row count and missing-value policy; output hashes bind the
adjusted table and original fit RDS. The RDS remains the fitted limma object,
not a claim that it contains an adjustment object. The downstream frozen
family validates and consumes these official columns; it must not replace
them with its own multiple-testing algorithm or pool the three models.

Port publication refuses existing destinations and symlink ancestors.
Failure rollback compares device/inode/owner and expected SHA256 before removing
its own published links, preserving a foreign replacement instead of
unconditionally unlinking that pathname. Each link and the completed port
set are checked again before success. These checked-process failure tests
do not establish crash-atomic publication or protection against every
adversarial replacement after an identity check. Expected identities and content
hashes for the entire private bundle are fixed before the first output link;
each port and the complete published set are checked again. A same-inode edit
is neither accepted as the original result nor deleted by rollback.

| Node | Input ports, in order | Output ports |
| --- | --- | --- |
| `bulk_normalized_design` | bound config JSON; expression TSV; genes TSV; samples TSV; decisions TSV | audit JSON |
| `bulk_normalized_limma` | the same five files; actual DESIGN audit JSON | results TSV; audit JSON; official RDS |

The input configuration is the strict component schema, **not** a project's
`B_ANALYSIS_CONFIG.json`. For the current locked legacy project, use the
`frozen-b-project` intake and its `tools/build_frozen_b_project_dag.py` entry;
the generated graph supplies all five bound inputs and actual DESIGN receipt.
The older
`research-adapters/b-bulk-inputs-contract/b_bulk_frozen_inputs` prepares its
nine original source/design inputs into expression, genes, samples, decisions,
method-template, family-proposal and input-preparation outputs. Bind the four
actual TSV SHA256 values in the template's `input_sha256` before DESIGN.
The original governance compiler stays active. The full-family
`research-adapters/cachexia-contracts-v432` stage must retain every registered
member and apply BH/BY with missing p values counted as 1 in the denominator.
Those older ZIP/governance adapters apply to their separate contracts and
are not substituted for the current project's legacy intake.

For the locked GSE130563 design, the required contract is all 23786 genes,
17 case and 5 control assays, `~group+age+sex`, rank 4 / residual df 18,
limma3.68.5, trend and robust TRUE, and source RMA log2 expression without
renormalization. Clinical labels and covariate levels must come from the
locked source maps; this plugin does not infer them. Frozen inputs and methods
remain external to this source release.

The frozen project permits LEGACY_EXPLORATORY evidence and has a null
scientific signature. TUI registration, toy method validation and successful
software execution do not upgrade that history or grant formal scientific
authorization. Audits retain the component's false source-qualification,
independence, family-freeze, approval and formal-authority fields.

For an installed source profile, use a full reviewed Git revision and
`subdir = "plugins/bulk-limma-normalized"`. Its existing digest is a local image
reference; publishing this source does not publish a registry image.
Run the bounded, entirely synthetic host method check with the existing library:

```sh
python3 -B /path/to/core/scripts/research_validation_session.py run -- \
  python3 -B plugins/bulk-limma-normalized/tests/run_method_toy.py \
  --library /existing/R_library \
  --frozen-code /frozen/project/02_EXECUTION/g0_v432_methods.R
```

The check requires a managed session, records inputs and results as permanent
technical evidence, and fits no study assay. It checks independent least-squares
coefficients, full row retention, constant-gene NA, exact locks, real DESIGN
receipt binding, official RDS contents and scale/software rejection. It also evaluates the verbatim frozen numerical block in a separate SYN
process and compares primary, unadjusted and therapy_sensitivity beta/SE/df/CI/p, constant-row NA and each separate complete BH/BY family.
The whole original frozen program and its study authorization guards are not
executed by that parity test. It does not independently qualify the
empirical-Bayes prior or the real source.

`tests/run_publication_io.py` separately exercises the real R entry with a
synthetic stub method to isolate output safety. It first reproduces the old
foreign-replacement deletion, then checks normal publication, existing
outputs, dangling links, input aliases, owned rollback and foreign
replacement at two publication windows, plus six same-inode content-edit
controls (early port, final port, earlier port at the final link, and late
failure). This I/O proof is not the numerical
method proof. The unchanged original 25-gene, three-model method test still
compares beta/SE/df/CI/p and complete BH/BY vectors against the verbatim
frozen R numerical block and reads the actual RDS in the locked environment.
Candidate-source validation does not restart or hot-reload a running study.
