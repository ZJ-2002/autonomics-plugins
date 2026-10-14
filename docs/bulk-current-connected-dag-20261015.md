# Pseudobulk → official DESeq2/limma: current connected DAG proof

The existing quoted-TSV producer/consumer repair now has a **fixed current-engine
connected proof**, not just separate node runs or the older SDK evidence.
No scientific method script, image, model parameter, frozen input, numerical
golden or tolerance was changed in this work.

## Actual methods and interfaces

| Kind | Role and inputs | Declared outputs |
| --- | --- | --- |
| pseudobulk_counts | H5AD raw-count engineering aggregation by donor × celltype; explicit X/layer and group rules | counts TSV, sample/condition TSV, log |
| deseq2_de | Official DESeq2 1.50.2; count matrix and sample metadata; these cases use mean dispersion fit/no shrinkage | results, normalized counts, size factors, DDS RDS, report |
| limma_voom | Official limma 3.66.0 + edgeR 4.8.2; same counts/metadata; these cases use categorical ctrl/case and TMM | results, voom weights, normalized expression, contrasts, report |

Pseudobulk SUM is mechanical data aggregation using official SciPy sparse
operations plus engineering grouping/integer/identity guards, not a Rust
statistical implementation. Earlier Scanpy `get.aggregate` comparisons are
independent reference evidence; **this node does not execute Scanpy**, and that
distinction is not relabeled to make an “official” claim.

All three methods exchange raw File ports. Quoted TSV uses double quotes,
doubled embedded double quotes and literal string identities. No generic
DataFrame inference step can silently convert `0001` or interpret `NA` here.
This specific raw-file chain does not certify every CSV/DataFrame bridge.

## Two complete graphs, plus failure propagation

Both the simple and quoted/Unicode/NA/leading-zero fixtures run as actual
**four-node/five-edge** DAGs with three separately pinned plugin manifests.
The graph is one H5AD File reference → pseudobulk → both DESeq2 and limma.
All **10 input bindings** match actual source edges and complete staged bytes;
all **26 live/published output ports** match declared names, formats, sizes and
contents. Complete pseudobulk counts and metadata match the original decoded
fixture, including donor keys, sample/condition alignment and gene order.

The two graphs reproduce **19,250** independent author numeric table fields at
the unchanged method-specific tolerances: DESeq2 atol/rtol `1e-10`, limma
atol/rtol `1e-12`; IDs, shapes and NA masks remain exact. Four complete method
reports retain all semantic fields after their actual file MD5 identities are
independently checked and only file receipt paths/hashes normalized. Exact
contrast ledgers also match. Independent R parsing checks **18 TSVs**. The two
DDS readbacks check **26,900 numeric fields**, all assays, row/column identities,
colData, model matrix, size factors, mcols and dispersion fit type—not every
possible S4 environment/slot or every DESeq2 model configuration.

References are reused unchanged, not regenerated: both prior complete packet
seals (151 and 258 regular files plus their declared links) and all **80**
decoded/independent-author fixture payloads are rehashed. This is inherited
independent author evidence, not a claim of a fresh installation/download.

The current pseudobulk image additionally executes its entire **41-case**
contract suite: **20 successful exact grouping/identity comparisons and 21
specific refusals**. This retains integer-overflow, noncanonical sparse,
noninteger opt-in, missing labels, ID collision, all quoted-ID cases and ordinary
no-overwrite/rollback checks; an owned dangling toy fixture is recorded and
removed before archival, not left as a broken permanent dependency.

An additional actual NaN-count producer failure returns exit 2, preserves its
cause and releases no normal results; **neither downstream statistical method
executes**. Technical failure cannot be reinterpreted as missing-but-successful
science or silently switch estimators.

## Reusable multi-manifest engineering entry

The probe extends the previous file-backed loader with explicitly hash-bound,
uniquely named additional plugins. Every script is checked and inlined from its
pinned family. Engineering-factory replacement and duplicate method ownership
are refused. Additional plugins with panels are explicitly unsupported by this
technical entry; primary synthetic panel support stays separately guarded.

Nine actual extra-manifest preflight refusals cover wrong manifest/name/script
identity, repeated plugin, duplicate kind, engineering-name collision, script
traversal, unsupported extra panel mapping and non-array declaration. The prior
six primary guards also pass on the new binary. One already-qualified no-panel
BH transport graph remains byte-identical; it grants no new R method certificate.

Built engine: `4ceefbd821baab8deebb070645a2fb8b1fa8e1ba`.
Executable SHA256: `bbc1a387b508ba05c50e79eb95b3dc15f87cf274a6e2c3983bcd320246339481`.
All **5,523** committed source identities match before/after compilation.
Engine publication `c17d7a2dd6e55112bee7f40db95f66d62a4c3e5c` changes only
`crates/container-plugin/examples/official_plugin_dag.rs`, preserves the peer
parent and the actual built candidate, and does not push a private native-OLS
HEAD. The helper registers engineering factories and pinned external methods,
not native statistical estimators; it is not an all-entrypoint scientific gate.

The old LDSC proof still names its original engine and source. Its exact probe
bytes are checked against the actual Git publication
`4b1f4ede93a403fb49ce280528baa465b1c78b74`; they are not silently rebound to the
new mutable helper. No old numerical golden, method code or tolerance changes.

## Lifecycle and limits

Both complete graphs and their R reader actually exit zero. Initial archival
was held because the standalone reader inherited its image root USER and wrote
one technical JSON as host subuid 100000 despite keep-id. Under the session
lease, an explicit maintenance step verifies the inactive unit/MainPID zero,
workspace identity and the exact regular file, then corrects only that owner
using `chown --from`. Bytes, inode, mode, source and exit are unchanged; a
separately archived receipt records the correction. Future reader calls also
set the operator UID/GID explicitly. Recovery does not rerun computation or
invent success. All **seven sessions for this work** are now terminal/CLEANED;
an unrelated session's HOLD is neither deleted nor called resolved.

The complete required local source suite executes **219 tests**, zero
failures/errors/skips, with matching catalog lock. See
[machine-readable evidence](../evidence/bulk-current-connected-dag-20261015.json)
for exact sources, cases, receipts and archive seals. Raw study payloads,
credentials, private launcher logs and local archives are not published.

These are bounded technical proofs for three existing original kinds, not three
new function slots. Real raw-count identity/layer, donor and cohort eligibility,
sample-library rules, frozen discovery universe, contrasts/families, complete
scientific implementation locks and deployment remain separate. No production
configuration, historical 120-slot count, 276/288/696 denominator, viewing history
or G0 changes. Spatial B-S remains CONDITIONAL_NOT_READY; GS01 remains OPEN.
