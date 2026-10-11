# Official coloc: original ABF and signal-aware SuSiE

## Original single-causal-variant ABF

`coloc_abf` restores the original canonical interface alongside
`coloc_susie`: one combined TSV File, flattened `dataset1_*` and
`dataset2_*` mappings, and two File outputs (full author RDS and log).
It calls `coloc::coloc.abf()` from the pinned coloc 5.2.3 stack; no
numerical approximation or replacement implementation is introduced.
Original wrapper provenance is recorded in
`provenance/coloc-abf-original-source-20261011.json`.

Use beta plus **variance of beta**, not SE, or the pvalue/MAF/N
approximation. The latter requires the case fraction for case-control
traits and loses information about imputation uncertainty. Quantitative
traits without a supplied phenotype SD use the author's MAF/N-based
SD estimation. SNPs are literal identifiers, including leading zeros and
the string `NA`. Both datasets need complete rows in the single input
table; differently sized datasets cannot be represented by missing-value
padding. The author merges common SNPs, including reordered or partial
overlap. This merge is not an allele/build/ancestry eligibility check.

H0 means neither trait is associated; H1/H2 only trait 1/2; H3 distinct
causal variants; H4 a shared causal variant. `SNP.PP.H4` is conditional
on H4, not a marginal SNP probability or FDR. The single-causal-variant
assumption is not a substitute for signal-aware colocalization and cannot
establish a three-trait bridge from arbitrary pairwise results.

Default priors are p1=p2=1e-4 and p12=1e-5. The exact v4.3.2 p12 grid
1e-5/1e-6/1e-4 has synthetic numerical comparisons, not a frozen research
family or scientific release. Author prior adjustment is retained.
Duplicate headers, absent mappings, ragged rows, invalid or non-finite
numbers and aliased/existing outputs are refused. The existence check
is not an atomic multi-output transaction or a concurrent write lock.

`evidence/canonical-coloc-abf-20261011.json` records 43 wrapper cases
(19 complete independently constructed author-result comparisons and
24 targeted refusals), four compiled original-interface tests without
dependency skips, and ten isolated native DAG submissions (six successful
executions, two execution failures and two preexecution refusals).
The shared `coloc_susie` implementation also retains its 32 passing
regression cases. These checks do not certify latest coloc 6.x, the full
author API, statistical calibration, real regions, resource scale,
resident deployment, cache invalidation, persistent recovery or G0.

Reproduce ABF tests with a new evidence directory and the independently
installed author library; absent dependencies fail rather than skip:

    ABF_TEST_EVIDENCE=/fresh/abf-cases \
    ABF_REFERENCE_LIBRARY=/proof/official-library \
    python -m unittest discover -s plugins/coloc/tests -p 'test_abf_contract.py' -v

    ABF_TEST_EVIDENCE=/fresh/abf-boundaries \
    ABF_REFERENCE_LIBRARY=/proof/official-library \
    python -m unittest discover -s plugins/coloc/tests -p 'test_abf_boundaries.py' -v

Author documentation: https://chr1swallace.github.io/coloc/articles/a02_data.html
and https://chr1swallace.github.io/coloc/reference/coloc.abf.html.
Their current-version API is not a certification of this fixed 5.2.3 wrapper.

## Signal-aware SuSiE

`coloc_susie` is a general-purpose four-input node, not a cachexia-only
method. It calls author `coloc::runsusie()` and `coloc::coloc.susie()`.
The pinned stack is coloc 5.2.3 and susieR 0.14.2 in an existing digest;
this is not a claim about latest coloc 6.x or susieR 0.16.6 compatibility.
It is distinct from single-causal-variant `coloc_abf` and does not replace it.

Read the manifest for every input column, parameter and declared port.
The two complete signed LD matrices are oriented using explicit counting
alleles. Every input SNP is retained, in the frozen common order. Matrix
provenance and build/ancestry/participant qualification remain external
scientific responsibilities; values alone cannot establish these facts.

Outputs are full signal-pair summaries, per-variant conditional-on-H4
results, full RDS (both datasets, both untouched official fits and author
result), and diagnostics. No credible sets is a tagged non-estimable
result, never an imputed H4 of zero. Official prior adjustment remains
author behavior and the full returned priors remain in the RDS.

The default bounded iteration budget is 100 with no automatic extension;
pass an approved larger value explicitly. The sharing-prior default is
the author 5.2.3 default 5e-6, not a substitute for a study's frozen prior
grid. The manifest's defaults are not research approval.

The existing `research-adapters/cachexia-coloc` is already in the unified
repository and is preserved. This new canonical family removes neither
that historical adapter nor its records. No automatic deployment occurs.

Independent proof is recorded in `evidence/canonical-coloc-susie-20261011.json`:
32 wrapper cases, 161 namespace-function definitions checked against fresh
author packages, 16 complete official workflow-object/TSV comparisons, and
seven native DAGs (three successful executions, four targeted refusals).
One successful DAG is explicitly non-estimable because it has no credible
sets; successful execution is never equated with a positive finding.
The native runner uses the sealed current container-plugin component with
an immutable SDK, not the resident daemon or whole current engine.
Its output report has metadata fingerprints without content hashes; this
proof independently hashes the materialized files and their retained copies,
but does not claim that the engine's output-hash registration is complete.
Formal research, deployment, latest-version/general-domain certification
and scientific signoff remain ungranted. No G0 is implied.

Reproduce package-dependent cases only with the required independent
reference library and author fixture supplied; missing evidence is fatal,
not a dependency skip:

    COLOC_TEST_EVIDENCE=/fresh/cases \
    COLOC_REFERENCE_LIBRARY=/proof/official-library \
    COLOC_AUTHOR_FIXTURE=/proof/author-fixtures \
    python -m unittest discover -s plugins/coloc/tests -p 'test_contract.py' -v
