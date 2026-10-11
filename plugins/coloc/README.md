# Official signal-aware coloc

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
    python -m unittest discover -s plugins/coloc/tests -v
