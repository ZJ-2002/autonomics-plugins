Opt-in v4.3.2 contract adapter; official family correction source candidate.

The five original kinds, ports, complete ordered IDs, NA-to-one adjustment
vector, execution statuses, family denominators and eight-column family.tsv
are preserved. BH and BY now invoke official stats::p.adjust with explicit n
in a separate fixed Rscript --vanilla program. R and base stats must both be
4.6.1. Any missing R, wrong version, timeout, exit/stderr or output-contract
failure blocks correction; no Python statistical fallback exists.

complete_family(..., method=..., receipts=None) still returns ordinary rows.
An optional receipts list captures actual method/n, ordered-ID and raw/status
identities, exact stdin vector bytes, actual q/stdout hashes, fixed R program
SHA256 and measured Rscript SHA256. The original audit port receives these
receipts for family and paths. Missing rows retain NOT_RUN/raw NA/adjustment 1;
NOT_RUN and FAILED keep the family INCOMPLETE. Prior per-contrast q columns
are never inputs to full-family correction. The two full B families must each
use their own complete registered member vector; the separate 23,786-gene
LEGACY model denominators do not redefine those full families. The two path
families likewise use separate full BY vectors.

CANDIDATE.json records that no child image has been built or accepted. The
manifest image reference is deliberately retained byte-for-byte from the old
source: it is a historical Python runtime and cannot satisfy the new R check.
It is not a runtime claim for this changed adapter; do not load/deploy it.
shared-image-sources/official-r-stats-python/Dockerfile derives from the exact
measured 78f195... base, which has R/stats 4.6.1 but no Python. It only adds
python3-minimal and libpython3-stdlib, prohibits package upgrades, and checks unchanged R package
versions plus R/stats/BLAS/LAPACK library bytes. A future controlled build must
measure the actual child digest and software before replacing the manifest
reference once. Neither a candidate tag nor a guessed child digest is used.
python3-minimal alone did not provide decimal; the explicit stdlib package
corrects that dependency. This revised recipe has
not yet been built or accepted, and no failed-attempt image digest is assigned.

The original research-adapters/cachexia-contracts source remains unchanged.
Select exactly one admitted adapter profile; no research adapter is enabled
by the default catalog. CACHEXIA_ACTIVE_PROTOCOL selects matching rule bytes;
TECHNICAL_CONTRACT_PASS is not scientific G0, family freeze or disclosure.

Self-cleaning tests use host R/stats 4.6.1 for actual toy/reference correction.
These are no longer stdlib-only statistical tests. CI explicitly requests exact R/stats 4.6.1 and checks both versions; missing
or wrong R fails the required suite rather than skipping native cases.
The setup action accepts an exact r-version per its official documentation:
https://raw.githubusercontent.com/r-lib/actions/v2/setup-r/README.md
This workflow edit is prepared; remote CI execution/download has not been
verified here. CI has not built or accepted the candidate container. No real study data or
scientific result is recomputed by these tests.
