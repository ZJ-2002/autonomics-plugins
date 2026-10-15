# Frozen A: official family adjustment

`frozen_a_family_adjust` is a zero-parameter research adapter, not a generic
multiple-testing API. It calls the unchanged frozen `adjust_full` definition,
whose numerical backend is official R/stats 4.6.1 `p.adjust`.

The four input files are `vectors.tsv`, `assembly.tsv`,
`assembly-receipt.json` and the original `g0_v432_methods.R`. All 564 assembly
rows and six vectors/840 rows are retained. Family sizes are 88/188/36/252;
edges receive BH and BY, paths BY. Raw NA remains NA in TSV and RDS. Only
`adjust_full` substitutes one for adjustment. No eligibility decision follows
from an adjusted value, including a placeholder q of one.

The upstream receipt must bind all nine frozen source declarations. This node
checks their exact names/sizes/hashes, but receives and independently hashes
only its four actual input files. It does not reopen the other upstream source
files or establish that receipt-declared family IDs equal the registries;
upstream assembly and downstream publication must perform those checks.

Outputs are `adjusted.tsv`, a complete `adjustment.RDS`, an input/output-hashed
`adjustment-receipt.json`, and `adjustment.log`. Publication is no-clobber.
Rollback only removes a confirmed published inode whose identity and content
still match; changed or foreign paths are retained. These checks are observation
checkpoints, not permanent tamper resistance or crash-atomic multi-file commit.

Two technical scopes are allowed: explicit synthetic BOUNDARY/INTERIOR cases,
and mechanical transport of the real all-missing ledger. The latter requires
all raw P values to stay missing. This node does not fit MR, assign the 275
pending overlap classes, modify frozen files, certify the entire original
boolean node, enable the conditional MVP branch, deploy production, or grant G0.

The [R manual](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)
documents `p.adjust`. The page is not an identity certificate for this runtime;
actual R/stats 4.6.1 and the pinned image must be independently checked. NA-to-one
is the frozen helper's policy, not an automatic behavior attributed to `p.adjust`.
