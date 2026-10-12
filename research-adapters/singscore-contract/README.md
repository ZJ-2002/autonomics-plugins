# Frozen singscore scoring adapter — method qualification pending

This is a scoring implementation under development for the original B-SPEC
contract in `bmc4.2.1.zip`. The manifest is an isolated qualification candidate;
it has not been installed into the production daemon. No method has been
scientifically accepted for formal execution, and no G0 is passed here.

`Rscript --vanilla scripts/score.R CONFIG MATRIX SIGNATURES SCORES COVERAGE AUDIT`
uses official `singscore::rankGenes` and `singscore::simpleScore`. The local
SYNTHETIC tests require explicit package availability; absent packages are
reported as skips. Software versions are checked against the supplied frozen
configuration, and matrix/signature content against SHA256 before scoring.

The adapter requires already qualified human gene-level TPM, length-adjusted
expression or microarray input. It performs no normalization, probe mapping,
cross-study batch correction or signature selection. A common ordered gene
background and ordered sample universe are mandatory. Incomplete/nonnumeric
expression backgrounds are rejected; no zero fill or silent rank background
change occurs. Such data need separately qualified preprocessing/missingness
handling. Only up-only and up/down signatures are supported at this stage;
down-only signatures are blocked pending a separate method acceptance.

The original four program IDs and all signature members, including absent
members, remain in the coverage report. The adapter applies the study's
80% total coverage, five measured members and 80% in each nonempty arm rules.
Insufficient signatures retain every sample with NA and a recorded reason.
Inputs marked TEMPLATE_NOT_RUNNABLE are refused; their original version 3.9
inside the final delivery is not silently rewritten.

Scores are not donor counts, effect estimates or cell abundance. The separate `scripts/contrasts.R` implements the five frozen donor-level
Welch/paired contrasts, confidence intervals and the complete 20-member BH/BY
family. It requires explicit case/reference sample sets, verified donor counts
and reasons for every excluded sample, refuses duplicate independent donors,
and aligns paired observations by donor ID. SC04 retains low-precision
support-only status and excludes samples outside its frozen pairs. Missing
scores and degenerate variance retain NA/adjustment P=1 rows; they do not select
a replacement test. Native source files and the pinned container still need
formal method acceptance; local algebraic fixtures are not that acceptance. A pinned container/environment, signature
source identities, accepted preprocessing, actual sample map and independent
scientific review are also required.

The Dockerfile now builds official singscore 1.32.0 from its exact Bioconductor
3.23 source archive (SHA256
`b4ffcbcb215ec99b9c8159bcf47cebba02517ff2c76c6aebabd2d7848298fd5a`),
using R 4.6.1 and a fixed CRAN snapshot. Build dependencies are checked before
installation succeeds. The resolved package inventory and session identity
are recorded inside the image. Software acquisition/building is a separate
stage; scientific execution never installs packages or pulls images.

An actual isolated image was built and inspected by content digest
`sha256:442ba1128697740289d709a8c6e75e1f2620a3d105954ca8dfddf562a89853d7`.
All eight synthetic regressions then passed inside that pinned image with
zero skips. An independent verifier confirmed all 21 container calls, exact
baked adapter hashes, package/source identities, network=none, read-only root,
CPU/RAM/PID limits, parent cgroup membership and no residual containers.
Evidence is in
`results/research-execution-20261007/singscore-oci-preparation-v1/ENVIRONMENT_QUALIFICATION.json`.
These tests qualify this software environment on synthetic inputs, not real
expression/signatures/donors, G0 or scientific conclusions. Original failed
builds and the first transport failure remain in the evidence batch.

The wrappers explicitly choose `Rscript --vanilla` and the image's baked
adapter. Loaded wrapper/manifest identity and the pinned image bind the full
command and adapter bytes. The candidate image currently exists in an
isolated local store; deployment must transfer and verify those exact bytes
before admission. The manifest is not a placeholder for a future image.

For a fully frozen DAG, downstream configurations may predeclare null hash
slots for upstream results. The `frozen_config_inputs` native IO node fills
only those slots using actual streamed SHA256, without changing any other
parameter. It accepts canonical JSON with status FROZEN, emits a separately
hashed derivation audit and grants no authorization. Scientific choices must
be complete and approved before this recipe is frozen; the original
TEMPLATE_NOT_RUNNABLE inputs remain unusable.

Primary API documentation:
[official Bioconductor manual](https://bioconductor.org/packages/release/bioc/manuals/singscore/man/singscore.pdf)
and [maintainer source](https://github.com/DavisLaboratory/singscore).
The package's default tie method is min; this study explicitly requires average.
