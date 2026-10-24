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
