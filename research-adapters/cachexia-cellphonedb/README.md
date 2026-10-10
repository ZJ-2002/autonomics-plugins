# Scoped official CellPhoneDB adapter

This is an isolated acceptance route, not a silent replacement of the deployed
`cellphonedb_statistical_analysis` wrapper or scientific release of the v4.1 study.

The unmodified official CellPhoneDB 5.0.1 package and curated human database v5.0.0
are pinned together by the OCI digest in `manifest.toml`. Proof independently
downloads the official wheel and DB, compares all package Python files and DB
bytes, installs the wheel into a fresh namespace, verifies the actually loaded
module path, and directly invokes the official API. It does not import this
adapter into the reference calculation.

Inputs are the full human H5AD matrix and a mandatory frozen JSON contract.
`raw_counts` plus scoring is rejected unless full-library `cp10k_log1p` is
explicitly requested. `log1p_cp10k` passes through without renormalization.
Raw statistics without scoring is a distinct explicit method request. Zero
libraries, missing metadata, malformed sparse axes, unqualified research input,
pooled tissues and a donor-based null are blocked with retained audit/log files.
Valid sparse duplicate coordinates are coalesced according to matrix semantics.
Human identifiers are explicit `hgnc_symbol`, `gene_name` or `ensembl`; the
adapter does not invent orthologs or synonyms.

The official testing seed is frozen with one worker. All 21 API arguments are
explicit and the signature is checked; unsupported arguments are not dropped.
Subsampling, microenvironments and active-TF/CellSign execution are disabled.
The official disabled CellSign `pd.DataFrame` class sentinels (not empty table
instances) are retained unchanged in the full state and separately named in audit.

Eight declared outputs preserve every returned table scalar, complete official
result/debug/RNG/warnings state, audit and log, original cell/donor/tissue and gene
ledgers, all DB interaction/group-pair candidates including unreturned/masked
states, and actual upstream files. A threshold-masked P=1 is not silently recast
as an estimated clinical effect. The family ledger is not multiplicity correction.

This method tests cell-type specificity using cell-label shuffling, **not** donor
inference, disease-vs-control effects, cross-organ transport, circulation or
causality. Bounded synthetic DAG proof does not qualify real input scales,
research eligibility, full-scale resources, resident daemon deployment,
recovery/global quotas or G0. The dense official reader is bounded at two million
input matrix elements for this acceptance route.

Official method and scale documentation:
https://cellphonedb.readthedocs.io/en/stable/RESULTS-DOCUMENTATION.html
