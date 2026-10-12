# sc_dense_ingest: exact count-table contract

The original published manifest explicitly calls the input a count matrix in its
description and documentation, and labels port 0 `count_matrix`. Its baked legacy
runner nevertheless accepted negative/fractional expression and copied it into a
`counts` layer. This repair applies the advertised count-matrix contract; it does
not redefine other expression-import nodes or certify raw biological provenance.

The original canonical kind, seven parameters, two output ports, pinned numerical
image, family-level panel and task resources remain unchanged. Only this node's
command now injects the tracked `scripts/dense_ingest.py`; the other family nodes
and baked workflow are unchanged.

- `genes_by_cells` is transposed to AnnData observations×variables; `cells_by_genes`
  is not transposed. Observation IDs are cells and variable IDs are genes.
- CSV quoting, gzip, named/custom separators and automatic CSV dialect detection
  are supported. Labels are literal strings, including leading zeros and `NA`;
  duplicate labels fail rather than acquire `.1` suffixes.
- Count tokens are parsed exactly into nonnegative int64. Finite integer decimal
  or scientific notation is accepted; negative, fractional, nonfinite, out-of-range
  and malformed counts fail. Values above 2^53 are not routed through float64.
- Headerless column IDs retain the historical `1..N` generation and are marked
  synthetic. This does not invent qualified biological gene or cell identifiers.
- The only filters are explicit Scanpy `filter_cells(min_genes=...)` followed by
  `filter_genes(min_cells=...)`. Defaults zero disable both. Exact counts are
  retained in both X and the subsetted `counts` layer; no mapping or normalization.
- Report schema 2 keeps legacy fields and adds full input/output/excluded axes,
  source hash, resolved dialect, synthetic-ID flags and qualification boundaries.
- Both output artifacts are staged before no-overwrite publication. Ordinary
  second-link failure rolls back only this run's inode-matching publication.
  This is not multi-file crash atomicity, persistent resume or scientific release.

Official contracts:
[AnnData observation×variable layout](https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html),
[Scanpy cell filter](https://scanpy.readthedocs.io/en/1.11.x/generated/scanpy.pp.filter_cells.html),
[Scanpy gene filter](https://scanpy.readthedocs.io/en/1.11.x/generated/scanpy.pp.filter_genes.html).
Actual verified versions are AnnData 0.11.4 / Scanpy 1.11.3 in the unchanged image.
This is a named engineering codec plus those explicit official APIs, not a claim
of equivalence to every author CSV reader or all possible expression scales.

For isolated verification, set `SC_DENSE_EVIDENCE` to a new directory and
`SC_DENSE_REFERENCE_LIBRARY` to an independently verified official Python prefix,
then run `bash test_dense_ingest_assurance.sh`. Missing prerequisites fail, not skip.
The reference subprocess checks its imports come from that read-only prefix and
constructs AnnData from independently specified fixture matrices, not node output
or the node parser. Whole HDF5 arrays, attributes, axes, metadata, counts and report
lineage are checked. Proofs are small scoped cases, not actual-study/full-scale or
resident-daemon acceptance. Package installation/identity must be separately
verified; a directory supplied to the test is not automatically trustworthy.

Formal study use still needs frozen raw-source, species/build/identifier semantics,
donor and library eligibility, discovery-universe rules and scientific QC choices.
The `gene_symbol` index name is preserved for interface compatibility but is not
a validation of symbol identity. GSE130563 log2 arrays are not count-matrix input.
Correct import of int64 does not certify downstream DESeq2 limits or inference.

The quote-character check uses `chr(34)` for compatibility with the archived
native SDK renderer, which misreads escaped quotes in otherwise valid Python.
The current owned engine already includes its escaped-quote fix (`73aa1137`),
and a separately compiled exact current renderer preserves the original script
byte-for-byte. This compatibility spelling does not imply the old SDK gained
that fix, nor does it substitute for current whole-engine/deployment acceptance.
