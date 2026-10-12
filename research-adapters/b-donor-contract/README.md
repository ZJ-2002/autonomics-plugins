# B donor-level model candidate

This component prepares a fixed DESeq2 Wald analysis from the actual raw-count
producer, and performs donor-level design checks. The candidate manifest now
declares the eleven-input/five-output `b_donor_frozen_inputs` preparation node
using the authenticated cached Python digest. It is not deployed as a
qualified container plugin. No R method image digest is invented. There is no
substitute negative-binomial implementation, scientific signature or G0 PASS.

`scripts/research_b_donor_inputs.py` verifies all six count output identities
against the actual count audit and rechecks the original sample-map/metadata
bytes. It retains every RNA gene, observation and inclusion/exclusion decision.
Cell-QC rows are streamed through a bounded SQLite database, using the count
recipe's explicit cache/scratch limits. Library-level clinical covariates must
agree within an observation. Missing values are retained; conflicting values
are rejected. It publishes the complete preparation set without overwriting.

The candidate DAG fragment binds the actual count/features/QC/column/audit
ports and the count producer's original sample-map and metadata inputs. The
native `frozen_config_inputs` node binds four actual model input hashes. Both R
stages consume those same files, and the model depends on the actual design
audit. The R model entry point recomputes its entire design and verifies that
audit's config, inputs, software, formula and lack of authorization before
fitting. This is component verification; server-side admission of this producer
and full B-family lineage integration remain separate work.

The two fixed R entry points are:

```text
Rscript --vanilla donor.R DESIGN config counts genes samples decisions new-output
Rscript --vanilla donor.R DESEQ2 config counts genes samples decisions actual-design-audit new-output
```

The config requires protocol 4.2.1, `DESEQ2_WALD`, explicit cohort/species/
tissue/site/cell-type/time scope, unpaired or paired design, effect direction,
covariate types and factor levels, cell minimum, family unit minimum, QR
tolerance, dense allocation bound and exact software versions. Its `FROZEN`
field describes fixed parameters; it confers no scientific authorization.
The publication utility's actual GNU `mv` binary hash is also locked.

The design stage counts declared biological units, not libraries/cells.
Repeated units cannot count as independent replicates. Paired units require
one observation per arm; incomplete pairs are not silently discarded.
Unresolved pools, zero-count libraries, missing covariates, rank deficiency and
zero residual degrees of freedom retain a non-estimable design. One unit per
arm is descriptive; two are explicitly low precision. Three or more only
establish matrix identifiability: they do not establish power or primary
scientific confirmation. Metadata declarations still require genuine donor
identity and scientific review.

The method candidate invokes official `DESeq2` with frozen dispersion and
size-factor choices, Wald testing, explicit direction, no independent
filtering, no automatic replacement and no automatic dispersion-fit change.
Unapproved warnings and absent/version-mismatched packages block publication.
All-zero genes and unavailable tests retain their registered rows with NA P.
Candidate family P is separate from supportive raw P and follows the frozen
unit minimum. Full BH/BY requires the complete multi-contrast registered family;
this producer performs no per-contrast replacement for that correction.

Permanent tests execute real R model-matrix/QR checks, same-source QA receipt
checks, full NA-row transport, dependency-absence rejection, complete source
preparation, no-clobber/concurrent publication and actual DAG port bindings.
The design tests do not constitute positive DESeq2 numerical acceptance.
The default vanilla library search has R/Matrix/jsonlite but does not include
the full Bioconductor library installed separately at `~/R/library`. That
library was subsequently discovered, explicitly snapshotted and used to
compile the verified official DESeq2 1.52.0 runtime source in an independent
source copy with user profiles disabled. Seven explicit-library numerical
regressions now exercise the actual model, an independent official-package
reference, the independent Wald P identity, paired models, low-precision raw
P versus family P, complete single-unit NA rows and mutated-QA rejection.
Official coefficient convergence is required before a finite P can qualify;
an actual-fit diagnostic fault verifies that failed convergence is rejected.
An actual count/metadata/QA/model component chain collapses twelve technical
libraries and 120 synthetic cells into six declared donors before fitting;
all 128 genes are retained and checked against the direct official reference.
They fail if their explicit method library is absent; they never skip as PASS.
This is local synthetic numerical component evidence. Dependency distribution
archive provenance, a protected image, full B family and formal scientific
acceptance are still unqualified.
Official DESeq2 1.52.0 Git runtime source bytes have been acquired from
`thelovelab/DESeq2` commit `16aeab6d6158bd8cbb8e98764c2f33399b1a3fd3`.
The complete Git tree metadata and each fetched runtime blob are checked;
unfetched documentation/data/test blobs are explicitly listed. This is a Git
runtime subset, not the complete Bioconductor release archive.

Required next steps are complete dependency provenance and pinned official
method-image construction, container numerical and failure qualification,
accepted container entry points, full B-family enumeration and
lineage/sealing integration, resource admission and genuine signed G0 review.
The protected runtime's subordinate-ID restriction remains enforced.
All 74 actual design G0 gates remain OPEN; reviewers have not been selected.

Generated fixed entries `run-inputs.py`, `run-design.R` and `run-deseq2.R`
embed the complete verified component source. Generate or check with
`python3 -B scripts/build_b_donor_wrappers.py [--check]`. Local actual-entry,
official numerical-entry and Rust loader/compiler checks are described in
`docs/audits/research-execution-2026-10-07/B_DONOR_FIXED_ENTRIES.md`.
The R entries now have a separate built image candidate and method manifest in
`study_plugins/b-donor-method/`. Actual image/runtime qualification and
protected worker registration remain required; successful local entries do
not remove them.

Official method and raw-count guidance:
[DESeq2](https://bioconductor.org/packages/release/bioc/html/DESeq2.html),
[DESeq2 vignette](https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html).
