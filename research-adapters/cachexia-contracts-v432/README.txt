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

CANDIDATE.json records the measured child image and the completed generated-data
container acceptance. The manifest now pins the published immutable digest,
which was pulled back from the registry and checked against the measured local
manifest/config and six official R reference comparisons.
shared-image-sources/official-r-stats-python/Dockerfile derives from the exact
measured 78f195... base, which has R/stats 4.6.1 but no Python. It only adds
python3-minimal and libpython3-stdlib, prohibits package upgrades, and checks unchanged R package
versions plus R/stats/BLAS/LAPACK library bytes. The controlled build measured
the child runtime before registry publication. A tag is a distribution
convenience; execution identity uses image.reference's fixed digest.
python3-minimal alone did not provide decimal; the explicit stdlib package
corrects that dependency.

Twelve actual DAG cases covered all five node kinds, 276 edges, 288 paths,
all four correction families, palindrome/signature guards and failed-node
propagation. Ten complete vectors matched official R. Native container
inspections checked the manifest's one CPU, 1 GiB memory, 128 PID, isolated
network and read-only root limits. All owned test containers were stopped.
The measured engine revision was 4ceefbd821baab8deebb070645a2fb8b1fa8e1ba;
this acceptance does not qualify a newer daemon or formal worker. Their
verification and operator profile selection remain separate prerequisites.

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
verified here. Local container acceptance is not a remote CI pass. No real study data or
scientific result is recomputed by these tests.
