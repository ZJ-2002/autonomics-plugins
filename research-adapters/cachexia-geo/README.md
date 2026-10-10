# Frozen NCBI transport adapters

These four staged node kinds replace specific GEO/SRA transport defects; they
are **not installed in the resident daemon** and do not certify the original
wrappers, a statistical package, clinical eligibility or G0.

| Kind | Required selection | Payload output |
| --- | --- | --- |
| `cachexia_geo_series_matrix` | Exact GSE/platform matrix filename | Unchanged `.txt.gz` |
| `cachexia_geo_soft` | Exact `<GSE>_family.soft.gz` | Unchanged SOFT gzip |
| `cachexia_geo_suppl` | Exact safe supplementary basename | Unchanged opaque bytes |
| `cachexia_sra_runinfo` | Exact SRP/SRX/SRR, or independently qualified GSE link | Full-field CSV-to-TSV conversion |

Each node accepts **one File**, a frozen TSV with `key` and `value` columns.
The complete 19-key schema is `KEYS` in `scripts/fetch.py`. Both frozen raw
SHA256 and byte count are mandatory before retrieval; live source changes do
not update the contract automatically. Standard CSV quoting with tab delimiter
preserves the JSON-valued `expected_runs` and `expected_runinfo_columns` fields.

All nodes declare five ports: payload, nonempty log, JSON audit, HTTP-attempt
TSV, and unchanged raw source. SRA port 4 is official RunInfo CSV; port 0
preserves every field string as TSV, including empty values, `NA`, leading zeros,
quoted tabs and newlines. RunInfo is **not** Run Selector's different metadata
schema, and neither establishes clinical donor independence.

Transport checks include exact size/hash, bounded raw streaming, complete status
200, identity HTTP encoding, narrow same-resource HTTPS redirects, complete gzip
CRC/expanded budgets, requested series identity, ordered matrix table markers,
and complete frozen SRA header/run set. These are not a complete GEO expression
parser, archive extractor or normalization method. Failed calls remove their own
partial/payload/raw files and retain diagnostics. Existing output paths, including
dangling symlinks, are not overwritten. Fatal process/host failure and shared-path
persistent recovery remain separate unproved engine concerns.

No automatic platform selection, GEO-to-SRA mapping, clinical interpretation,
imputed missing fields, updated data acceptance or research release is allowed.
The proof-only transport-fault prefix under `study_plugins/tests/` is not part of
this manifest or production adapter API.

Primary references: [GEO downloads](https://www.ncbi.nlm.nih.gov/geo/info/download.html),
[SRA backend endpoints](https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/), and
[RunInfo vs Run Selector metadata](https://www.ncbi.nlm.nih.gov/sra/docs/sradownload/).
