# GEO/SRA resource contract

These are engineering source nodes, not statistical estimators. Official-method
certification is **NOT_APPLICABLE**; successful transport is not study admission.
All original input counts, output paths/format labels, resource declarations and
existing required parameters remain unchanged. Two optional parameters are additive.

| Kind | Inputs → outputs | Source and interpretation |
|---|---|---|
| `geo_series_matrix` | 0 → `series_matrix.txt.gz`, `geo_fetch.log` | Original gzip bytes; complete CRC, requested GSE identity and balanced matrix tables checked. Optional `matrix_file` explicitly names an accession-specific platform file. Default still requests only the original canonical filename. |
| `geo_soft` | 0 → `family.soft.tgz`, `geo_fetch.log` | Official `GSE*_family.soft.gz`, retained verbatim. The legacy `.tgz` output is gzip SOFT text, **not tar**; format tag remains `geo_soft`. |
| `sra_runinfo` | 0 → `runinfo.tsv`, `geo_fetch.log` | Official backend CSV transformed losslessly to quoted TSV strings. `Run` must be unique and the requested run/experiment/study must match each row. This is not the Run Selector clinical table. |
| `geo_suppl` | 0 → `suppl_file`, `geo_fetch.log` | Original bytes of the explicitly named supplementary file. The fixed output basename is not renamed. Gzip CRC is checked for `.gz` files; other internal formats are not certified. |

NCBI documents [the backend endpoints](https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/):
`run_new` returns XML and is not the production RunInfo table. The corrected
`runinfo` endpoint provides run attributes. NCBI distinguishes its
[download metadata tables](https://www.ncbi.nlm.nih.gov/sra/docs/sradownload/);
neither table automatically establishes a clinical donor.

For a GSE RunInfo request, only explicit SRA study relations in official self-SOFT
are eligible. A unique relationship can be technically resolved, with its exact
relation lines, response SHA256, URL and selected SRP recorded. Missing or multiple
relations fail unless additive `sra_accession` selects a member of that official
set. Direct SRP/SRX/SRR requests remain direct. Unsupported PRJNA is not silently
substituted. A research must independently freeze and qualify the exact resource.

GEO matrix and SOFT downloads preserve compressed raw bytes. Historic non-UTF8
payload identifiers are structurally tokenized through byte-preserving Latin1,
not transcoded or renamed. This does not certify downstream expression decoding.
GEO text lines above 64 MiB and GSE self-SOFT responses above 4 MiB are outside this
implementation's engineering bounds and explicitly refused.

HTTP responses must retain an allowed NCBI HTTPS host and identity content
encoding. Permanent errors, empty or incomplete bodies, HTML, malformed CRC or
structure, unsafe file names, query mismatches and existing output paths are
refused. New failures retain a nonempty diagnostic log and remove partial payloads.
Owned temporary/diagnostic files are exclusively created and identified from their
actual descriptors. Duplicate descriptors retain owned inodes until cleanup, avoiding
inode reuse being mistaken for ownership. Retry/relation/final cleanup removes only
matching owned regular files; foreign regular/symlink replacement is preserved and
refused. Owned readers/log writers compare no-follow descriptor identities before
reading/truncating. Every matrix table requires its complete sample header.
When a `!Sample_geo_accession` row is present, its unique sample identities and
order must match its corresponding following table header. Conflicting or
unconsumed metadata rows fail. Each explicit metadata row is consumed locally;
the next table without metadata retains the pre-existing structural-only subset,
without inferring that another block has the same sample axis. Logs distinguish
bound tables from tables lacking this metadata. Synthetic multiple-block support
does not certify official multi-platform matrix assembly or clinical interpretation.
Individual hard-link publication is no-overwrite, not a multi-file transaction or
crash-recovery protocol. Identity-check then unlink does not eliminate hostile
TOCTOU; concurrent same-path runs and external directory replacement are unqualified.
Diagnostic-write exhaustion or a replaced foreign log cannot promise a new owned
nonempty diagnostic port; visible failure is preferred to overwriting foreign bytes.

Existing payload/log paths are never overwritten; their refusal is emitted on
stderr because replacing the old diagnostic would violate that contract.

The fifth shared-script kind `geo_suppl_list` retains its existing approximate
size/404-empty contract; listing sizes are not expected payload byte counts.

Independent format evidence uses exact public NCBI bytes and the unmodified
[Biopython Bio.Geo author parser](https://biopython.org/docs/1.86/api/Bio.Geo.html),
version 1.86. Biopython is **not** NCBI author software or GEOquery. Known
GSE130563 resource replay is historical technical reproduction, not independent
new scientific evidence. No expression hypothesis test is performed here.

Current source-node script tests are distinct from compiled renderer, isolated
DAG, resident-daemon deployment, end-to-end workflow and scientific approval.
The old frozen renderer rejects a legal embedded script; the historical candidate
`22da3a71` has a whole then-current `container-plugin` thin compilation and actual
isolated source-node DAG with 5 positive / 3 refusal cases, under the original
manifest contracts. Those records bind the old script, not the subsequent host-only
header/ownership repair. New script identities need fresh fixed-image/declared-port
execution before inheriting current execution qualification. Remaining
dependencies are immutable frozen SDK components, not a current whole-engine build.
The tested supplementary file is only 216,692 bytes; its original `1g` resource
declaration is not certification for arbitrary large supplementary files. Observed
cgroup peaks are sampled high-water values, not guaranteed complete final peaks.
Disk metadata exhaustion is infrastructure failure, not an algorithm defect or a
successful test. Resident-daemon deployment and formal study admission remain
**OPEN**. This document grants no G0 release.
