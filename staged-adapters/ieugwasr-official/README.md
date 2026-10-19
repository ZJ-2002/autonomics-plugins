# Direct official ieugwasr adapter — not yet admitted

This adapter calls the installed author package `ieugwasr` **1.2.0**, without
rewriting its request batching, formatting, defaults, sorting or clumping.
It has no built image, plugin manifest, deployed registration or scientific
admission yet. Version checking is not a substitute for a locked package and
dependency identity. The host default package 1.1.0 is deliberately rejected.

`AUTONOMICS_INPUT0` is a JSON object containing exactly `operation` and `arguments`.
`AUTONOMICS_INPUT1` is an optional complete RDS data.frame, used only by `ld_clump_api`.
The standard output environment names are `AUTONOMICS_OUTPUT0` through
`AUTONOMICS_OUTPUT3`; no shortened environment aliases are assumed.
Output ports 0–3 are complete result RDS, typed data.frame projection JSON,
technical audit JSON, and execution log. The RDS preserves every author result
attribute and is authoritative. Projection rejects unsupported/list/classed
columns rather than silently flattening them. Any call or projection failure
prevents publication of all normal output ports. Logs/errors go to stderr on
failure, not a successful placeholder result.

| Operation | Exact author function | Important distinction from raw REST |
|---|---|---|
| associations | `ieugwasr::associations` | `variants`, author defaults and chunking; no REST `population` argument |
| phewas | `ieugwasr::phewas` | `variants`, `batch`, author p sorting |
| tophits | `ieugwasr::tophits` | `force_server`, kb=10000 default; no direct `preclumped` override |
| variants_rsid | `ieugwasr::variants_rsid` | author variant formatting; author empty-response error is preserved |
| variants_chrpos | `ieugwasr::variants_chrpos` | author typed variant formatting |
| ld_clump_api | `getFromNamespace("ld_clump_api", "ieugwasr")` | author internal helper; original data.frame rows/columns retained; all clump parameters explicit |
| gwasinfo | `ieugwasr::gwasinfo` | supplementary official metadata operation; not a search substitute |

`gwasinfo_search` is **not supported**: the existing SQLite keyword/sort/limit
extension has no matching author function. Fetching all metadata and inventing
a filter is not presented as official equivalence.

Only listed formal method arguments are accepted. Credentials, arbitrary `...`,
API endpoint overrides, native SQL, and raw REST parameter aliases are rejected.
The author package receives credentials through its normal environment path;
the adapter never reads or records token values. No network credentials are
needed for toy contract tests. This is a statement about explicit wrapper
behavior, not a proof that all author diagnostics are secret-free. Real
credential log-redaction and deployment qualification remain outstanding.

Publication is exclusive per file, with inode-identity rollback after partial
failure. This is not an atomic four-file transaction or protection against a
hostile actor replacing parent directories. Destinations must share a filesystem
with the private stage. Existing regular files and dangling links are refused.

References: [author query functions](https://github.com/MRCIEU/ieugwasr/blob/v1.2.0/R/query.R),
[variant functions](https://github.com/MRCIEU/ieugwasr/blob/v1.2.0/R/variants.R),
[LD clumping](https://github.com/MRCIEU/ieugwasr/blob/v1.2.0/R/ld_clump.R).

The accompanying tests inject a toy resolver to test transport/publication only.
They are not official numerical, network, image, DAG or deployment certification.
