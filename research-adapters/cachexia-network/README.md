# Staged cachexia network contracts

This family is isolated from production plugins and is not scientific release.

| Node | Inputs | Outputs | Proof scope |
|---|---|---|---|
| `cachexia_network_distance` | Connected physical unweighted edge TSV, registered S/T sets TSV, frozen JSON | Distances TSV, audit JSON | Author toolbox closest and pooled separation **distance functions only** |
| `cachexia_network_null` | Same edges/sets, eligible background TSV with expression/detectability strata, frozen JSON | Results, all draws, matching ledger, audit | Custom study joint-stratified null; **not** author degree-only randomization |
| `cachexia_string_physical_filter` | Physical links gzip, protein info gzip, frozen JSON | STRING-ID edges, protein info, audit | Offline STRING 12.0 combined-score format/filter contract, not download authentication |

All inputs require content hashes and provenance attestations. Attestations do
not authenticate the biological source. Graphs must already be connected;
largest-component selection, symbol mapping and eligibility are not invented.
Missing seeds retain every registered test row with raw NA, rather than silently
shrinking a set or a family. The custom null additionally requires eligible
seeds and exact degree/expression/detectability quotas. Insufficient pools yield
NOT_ESTIMABLE; no bin widening occurs. All registered original seeds are excluded
from controls. S/T draws are independent: observed between-role overlap is not
preserved. This convention must be approved before real study use.

Freeze B (at least 10,000), seed, degree-bin width, exact test IDs and resolution/
worst-case MC-SE budgets **before** any results. Each test uses an ID-derived RNG
stream. Both inclusive empirical tails use `(hits + 1)/(B + 1)`; reported MC SE
is an approximate tail-probability SE, not the SE of mean distance. Exact 95%
binomial intervals concern the uncorrected exceedance probability, not family
significance. Zero null SD leaves z missing, not falsely z=0. Adjustment inputs
are 1 for unestimable tests; this family does not perform family correction.

STRING combined scores are confidence scores in 0..1000, not edge effect sizes.
Physical combined-score files do not imply experiments-only evidence. Preserve
STRING protein IDs even when preferred names collide. Reciprocal equal-score
edges collapse, conflicting duplicates block, and self-loops drop with counts.
Source release/URLs/hashes must match; functional or channel-specific substitutes
are rejected. No gene-to-protein mapping is supplied by this family.

Shortest paths use a bounded 128-source BFS cache, not a full all-pairs matrix.
The 1 CPU/2 GiB declaration and small-graph tests are not a performance guarantee
for a full human network. Resident-daemon deployment, real graph/background
qualification, candidate enumeration, family FDR and G0 remain unproved.
