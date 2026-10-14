# Full-B normalized microarray method ABI candidate

This independent research adapter preserves the standard full-B method ports:
DESIGN takes config/expression/genes/samples/decisions and emits audit.json;
LIMMA adds the actual same-source DESIGN receipt and emits results.tsv,
audit.json and official.rds. The underlying `bulk-limma.R` and its embedded
wrapper payload are verbatim from `b-bulk-limma-contract`. The wrappers only
make input/output port zero explicit. They do not add the LEGACY family
transport audit field or reinterpret any supplied configuration.

The exact existing 723 image supplies R 4.6.1, limma 3.68.5 and statmod 1.5.2.
Changing the dependency image requires source-bound ABI and method review;
previous 693 acceptance cannot be transferred by matching version strings.
The runtime checks every supplied package version, original full gene order,
config/input hashes, fixed trend/robust policy and actual DESIGN receipt.
Constant and non-estimable genes stay in the original denominator. Full-family
BH/BY remains the downstream registered-family compiler's responsibility.

`tools/b_normalized_contract_binding.py` builds only an unsigned software
selection from exact request/template/gene-registry/source-assay bytes. It
requires explicit source RMA log2 microarray identity; log2 values alone do not
establish the assay. The existing full registry compiler must still validate
all members, source metadata and admissible contrasts. The candidate always
reports execution_ready=false and lists missing native method/source/worker,
resource and signed-contract checks. No metadata flag or SYN receipt grants
those checks. Do not load automatically or alias `bulk_normalized_limma` as a
formal producer. Counts, voom, DESeq2 and the disabled B_PRIMARY_STATES rows
are untouched.

See CORE_MAPPING.txt for the scoped core integration points. This adapter and
its numerical SYN evidence are software engineering work, not scientific G0
or whole-study acceptance.
