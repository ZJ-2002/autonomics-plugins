# Unchanged A real-intake official adjustment stage

This installable family exposes the same pinned `adjust_real.R` stage as the
earlier explicit-File DAG candidate. It is not a new correction algorithm.

| Input | Meaning |
| --- | --- |
| 0 | Full ordered vectors TSV |
| 1 | Original assembly receipt |
| 2 | Frozen `g0_v432_methods.R` File |
| 3 | Pinned `adjust_real.R` File |

The shell verifies both executable R source hashes before calling Rscript and
stops on an R failure. Outputs 0/1/2 are `real-adjusted.tsv`,
`real-adjustment.RDS` and `real-adjustment.json`. No host script lookup, new
numerical formula or implicit scientific authorization is introduced.

The exact image is pinned in `manifest.toml`: official R/stats 4.6.1 with
jsonlite. Runtime limits are one CPU, 1 GiB, isolated network, read-only root,
pull-never and PID limit 64. The companion bundle adapter supplies the four
literal Files; its README records the sealed 3-node/5-edge native DAG proof.

The prior six-vector/840-value RDS readback is independent retained evidence;
the bundle DAG additionally compares complete family/vector/adjusted TSV bytes.
These are limited technical proofs, not authorization for arbitrary receipts,
new finite primary results, independent replication, current daemon submission
or G0. Do not replace a study-selected node without its existing contract review.
