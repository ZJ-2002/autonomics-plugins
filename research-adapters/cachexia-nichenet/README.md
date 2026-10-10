# Frozen official NicheNet manual profile

This isolated adapter is not a production replacement or formal research release.
It calls unchanged official `nichenetr` 2.2.0 at
`f9906f3a51ddc09405a04ece9de375688e03facb` using the full human nsga2r priors from
DOI `10.5281/zenodo.7074291`. The image digest is fixed in the manifest.

Three inputs are a **standard cells-by-genes H5AD**, one-gene-symbol-per-line
frozen target set, and a mandatory 31-key JSON contract. Raw/log1p input scale,
axes, metadata, source identities, sender/receiver, expression percentage,
background coverage, rank/tie/alias policy and all prior hashes are explicit.
No orientation guess or normalization is made. Sparse duplicates are summed
according to logical matrix semantics and structural zero coordinates removed;
source bytes remain immutable and content-hash-bound.

The reader respects custom `_index`, categorical and string metadata, and the
rhdf5 dimension convention. Equal gene/cell counts never justify guessing or
transposing the already genes-by-cells R dense array. Missing metadata, malformed
sparse structure, invalid expression, wrong source identity, pooled tissues and
unqualified scientific requests fail closed with structured audit and log.

The human alias converter is the official package function. It preserves unknown
symbols as upstream does; this adapter does not invent an ortholog or current
HGNC adjudication. Alias collisions are explicitly blocked instead of silently
summing normalized/log expression. Complete original genes and mapping/eligibility
states remain in the gene ledger.

The actual method uses official matrix `get_expressed_genes`, receiver expressed
targets as background, an explicitly frozen target/background intersection and
coverage minimum, pairwise sender-ligand/receiver-receptor eligibility,
`predict_ligand_activities(single=TRUE)`, AUPR-corrected ranking, average tied rank
and **all ties at the top-N boundary**, followed by official weighted target and
receptor links. Target universe members outside the background stay recorded;
they are not silently removed from the original set identity or family.

Eight outputs retain every scalar of all official/raw/ranked/top/link tables;
complete input/mapped matrices, full priors, method/RNG/warnings/request state;
audit/log; complete cell/donor/tissue, gene/mapping, original target-set status and
complete prior ligand candidate/status ledgers. Official NA target/weight link
placeholders remain typed missing, not zero or an invented edge.

This predicts prior-based regulatory compatibility, **not** donor disease effects,
circulating arrival, cross-organ transport, source specificity or causal efficacy.
It does not replace CellChat, CellPhoneDB or a donor-level contrast. Real source,
species/ID/scale/contrast/family eligibility, mouse priors, Seurat/spatial/multiple
sender contexts, multiple-ligand modeling, prior reconstruction, full-scale
resources, resident daemon, global quotas, recovery and G0 remain unqualified.

Official source/API and prior references:
https://github.com/saeyslab/nichenetr/tree/f9906f3a51ddc09405a04ece9de375688e03facb
https://zenodo.org/records/7074291
