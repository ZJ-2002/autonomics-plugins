# MTAG Official: Explicit Four-Output Route

`mtag-official/mtag_official` packages the previously verified guarded MTAG
wrapper without changing its script, image, algorithm, parameters or file
formats. `reuse-lock.json` maps the retained source and execution evidence.

This is a generic two-trait operation, not a cachexia-specific statistical
model. Its fixed author version, Python2.7 dependencies, EUR LD panel and
48 supported flag combinations are implementation scope, not research
cohort or hypothesis-family settings. It contains no fixed study accession,
GWAS input identity, candidate list or scientific denominator.

## Interface

Inputs 0 and 1 are distinct, plain TSV GWAS files using the pinned author's
column convention. Outputs are:

| Port | File | Meaning |
| --- | --- | --- |
| 0 | `mtag_results.tar` | Complete unmodified mode-specific raw artifacts |
| 1 | `mtag.log` | Official execution log |
| 2 | `mtag_artifact_index.tsv` | Every raw artifact's name, size and SHA256 |
| 3 | `mtag_audit.json` | Parameters, input/panel/source identity and artifact mode |

Use the explicit canonical address. The existing `mtag/mtag` has a different
three-output contract; it is not an alias for this route. Existing callers
must explicitly rewire outputs, selecting any needed trait tables from the
raw bundle using the artifact index. Equal-h2 meta mode produces one meta
table rather than two trait tables; no absent result is fabricated.

The frozen `cachexia-mtag/mtag` entry and its existing DAGs remain unchanged.
The diagnostic prefix `MTAG_ACCEPTANCE_BLOCK` is retained byte-for-byte for
compatibility; it does not select a research project.

## Operational Boundaries

The script rejects official caught-error logs despite exit zero, missing or
wrong-mode artifacts, invalid numerical fields and output collisions. Its
observed input/panel hashes are not a frozen research approval. The pinned
author CLI declares `time_limit` but does not consume it in the optimizer;
the plugin timeout, not that option, is the wall-time boundary.

This source promotion is not proof that the new address is loaded or executed
by the current daemon. Reuse retained numerical and SDK evidence only within
its recorded scope; perform the new address's registration/routing check
after controlled publication. No default enablement or production/scientific
release is granted by this directory.
