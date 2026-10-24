# A carrier concordance V1 — independent read-only candidate

This utility checks the saved `mr` table of the retained R 4.6.1 /
TwoSampleMR 0.7.11 wrapper object against its complete TSV. It does not run MR,
change the existing intake, register a node or issue scientific authorization.
It is not a generic decoder for arbitrary RDS objects or MRlap results.

## Exact comparison contract

Two canonical ordinary files are bound by their complete SHA256 values. The
request has exactly `schema`, `scope`, `tsv_sha256`, `rds_sha256` and `selectors`.
Schema is `A_TWOSAMPLEMR_CARRIER_CONCORDANCE_V1`; scope is
`CARRIER_CONCORDANCE_ONLY_NOT_PRIMARY_AUTHORITY`. Every selector contains exactly
`id.exposure`, `id.outcome` and `method`. All original rows must be covered once,
with unique selectors; selection is not based on row order or significance.
The CLI rejects duplicate JSON keys and unknown authority/eligibility fields.

The R reader requires the recorded wrapper/package versions, thirteen exact
column names, the expected character/numeric types and the existing exploratory
missing-primary/family-one representation. It uses the same official R
`write.table(..., sep="\t", quote=FALSE, row.names=FALSE, na="NA")` operation
as the source writer. The complete resulting TSV must match the input bytes,
including every row, column, identifier, numeric spelling and missing marker.
There is no fitted tolerance or significance-only comparison.

**This proves concordance at the original TSV serialization precision, not
binary64 equality of a decimal TSV with the full-precision RDS.** The original
RDS remains separately hash-bound. A future use requiring lossless numerical
extraction must explicitly use the method object's full-precision fields; this
utility does not invent them from rounded text, authorize a primary P value or
replace the frozen scientific contract. The receipt states this limitation.

Files are read into a self-cleaning temporary namespace for decoding; originals
are checked again after comparison. Each input is limited to 32 MiB. This is not
certification of concurrent adversarial replacement, arbitrary object sizes or
all future R environments. Only trusted, identity-checked RDS inputs are in scope.

## Completed incremental proof

Six unittest methods pass. Their checks include correct toy concordance,
wrong exposure/outcome/method, duplicate and shortened selectors, rehashed
numeric/missing/column mutations, SHA/scope/authority overrides and duplicate
JSON keys. They use only toy R objects, not statistical fitting.

One already-seen X01→M06 carrier is read and compared: the original 718-byte TSV
and 6,888-byte RDS from archive `5981e37694a1481f9a04ff26e1ee2876`. All three
saved result rows serialize identically. No MR function or old DAG is rerun.
The other two missing historical carriers remain NOT_LOCATED; no new search or
recalculation is performed. Their absence is not filled with this result.

- Final session: `5d2f350634cc48308f1fab102e048b33`.
- Manifest seal: `361fb35885afa48629f9a127ffd43e382d24618204d9696f2d4ecc7aa44a7736`.
- Member: `permanent/a-carrier-concordance/verification.json`.
- Verification SHA256: `a4c58ee08d492a9829aac4b5ad29e4f1cd07b31d1b3b9fed769c4d6bf02f6a34`.
- Source hashes are recorded for `concordance.py`, `decode.R` and
  `test_concordance.py`; the existing host Rscript binary is also hash-bound.
- Worker/launcher exit 0; CLEANED. README is a post-proof documentation increment.

Use the CLI inside the managed validation lifecycle. Supply `--tsv`, `--rds`,
`--request` and a fresh `--output` receipt path. It writes no updated input,
estimate, frozen decision or approval. Production installation and integration
into a future explicitly versioned intake are not claimed by this candidate.
# Later lossless derived-carrier export

`export_precise.py` and `export_precise.R` add a separate
`A_PRECISE_MR_CARRIER_EXPORT_V1` contract. This is not a change to `verify()` or
the original serialization-only receipt. The old TSV is still not claimed
binary64-exact. The exporter first requires the complete original RDS object
schema, versions, exploratory role, missing primary and exact original TSV
serialization. It exports six numeric columns with 17 significant digits and
independently reloads every value in R, comparing all IEEE binary64 bytes with
the original RDS via `writeBin`. Character axes/order and missing-primary cells
are also checked. No rounding tolerance or method/P-value selection is used.

The result is a **new derived carrier**, not a recovered historical TSV, an
independent scientific result or a primary-eligibility receipt. Other object
schemas, MRlap objects, finite primary results and new methods are not supported.
The function returns payload/receipt; its CLI writes only to a new canonical
output directory. Failures never overwrite the source or an existing output.

Six new toy regression tests pass, including nontrivial precision/tiny P values,
wrong identities, altered TSV with a matching supplied hash, incomplete/duplicate
selectors, invalid roles/primary promotion and symlink refusal. One already-seen
X01-to-M06 RDS/TSV pair is converted: all three methods and **18 numeric cells**
roundtrip bit-exactly. Twelve cells parsed from the old reporting TSV differ
from the corresponding RDS values; this is ordinary reporting serialization
precision loss, not proof that the original MR computation was wrong. Original
files remain unchanged. No MR, fit, hypothesis test or DAG is executed.

Final managed session `8e224edc8e0b477cb584fb560dd9c08c`, manifest seal
`046e3200a5a3f851655ab672bffc64bf49e2a7e3b4d3cdd0de1b61620c563827`.
Member `permanent/a-precise-carrier-export/verification.json`, SHA256
`028521ffb1581e27a4211c111bf5a363a704bc20faca1b345772c8c449ee9f1b`.
It retains tested sources, six actual test logs, request, complete new carrier,
readback receipt and original input identities. Worker/launcher exit 0, CLEANED.
README is a post-proof locator. Private scientific carriers are not published.

The existing V1 intake itself still binds opaque RDS and is not silently
upgraded by this separate tool. Source-ID/status normalization and an explicit
intake connection were pending at the export-only increment; the later bounded
connection is recorded next. Two other historical full-precision carriers
remain NOT_LOCATED; finite-primary qualification, production and G0 are unchanged.

## Later X01/M06 technical intake connection

`prepare_intake.py` provides an explicit, separate known-seen O2 derivation,
not a general result-to-analysis mapper. `prepare()` verifies all nine frozen
sources, the exact two decision files and four unchanged V1 implementations.
Only A_X01_M06 is supported; both accessions come from the hash-locked input
card. The predefined IVW selector and original analysis-level bounded-date
view history are required. There is no choice based on P or significance.

It runs the lossless conversion, preserves all original lexical fields, and
appends the explicit analysis ID and technical `ESTIMATED` state. This state
means that a bound complete official result object supplied an estimate, not
primary eligibility. Its new request uses the existing V1 schema without
loosening any rule. A separate derivation receipt records the original RDS/TSV,
view history, exact frozen mappings, new byte identities and actual creation
time. The historical date bounds the analysis identity, not creation or first
viewing of these newly derived bytes. No old history file is edited.

Four new mapping tests pass. The unchanged V1 intake and official R chain then
actually consume this one already-seen real result, producing 564 family rows,
840 vector/adjustment rows and all six complete RDS vectors. Host session
`f5c2be348df84007a81bdd837e27b299`, seal
`c995974c38d90444617b639fffde60f9f4c7bb74a676caf380ba44c07de8b433`;
`permanent/a-precise-actual-intake/verification.json`, SHA256
`bceea1d5a982528a3caea24ec1a10a78ea62facffce493678da527d7e5fad883`.

The same derived input then runs through the original explicit-File bridge,
fixed Python/R images and exact compiled SDK 864b3a75: **22 nodes, 24 edges,
seven captured output Files**. Complete family/vector/adjusted TSVs match the
host chain; a separate isolated R reader opens every vector in the new RDS and
checks all 840 ordered values. Session `48d345ca1154409f9e19a2c2c2cc6700`, seal
`4d9d2767bf74f1c19d319d6a92bdf6d6dc490706de436629eae47e8960094563`;
`permanent/a-precise-native-intake/verification.json`, SHA256
`83379c863fa8613b41a6b2056a8b1e26291371785538dabbbd11d773f0e8b5ee`.
Both workers/launchers exit 0, CLEANED. The already-proved missing-File negative
case is reused, not rerun. Host normalization precedes this DAG; it is not
misrepresented as an additional native node or a production gateway submission.

No MR fit runs. Primary P remains missing and the adjustment placeholder remains
1, with 275 pending decisions and one locked O2 row. These placeholders are not
scientific negative results. Production registration/activation, finite-primary
admission and the two missing historical carriers remain unresolved. This is
technical input/SDK transport evidence, not full A or G0 scientific acceptance.
