# Frozen two-exposure MVMR candidate

This candidate calls official MVMR 0.4.8 at
`bceaa38088d093a5d30c713afb016e7fbc7ed2be`. Its offline image combines
the unchanged official MVMR image with fixed jsonlite 2.0.0 and digest 0.6.39
libraries. It requires R 4.5.1 and never pulls during execution.

Seven File ports contain the explicit frozen method recipe, joint instrument
table, covariance recipe, per-SNP matrices, preparation receipt, actual source
evidence pack, and joint identity record. The evidence pack retains original
source bytes as hexadecimal, with the original SHA256; it cannot approve their
scientific adequacy. Exposure and SNP ordering, actual SE diagonals, matrix
symmetry/PSD, every input SHA and receipt flag are checked again in the container.

The method emits two coefficient rows, two conditional F rows, one pleiotropy Q
row, an audit and original results RDS. Weak or unresolved covariance retains
computable coefficients. Unresolved provenance prevents conditional F and
pleiotropy calls. Empty, insufficient and rank-deficient inputs retain complete
NA rows and explicit reasons. No source is selected from its P value, and no
primary P or scientific direct-effect qualification is supplied.

The generic old MVMR plugin and this candidate remain blocked at the protected
worker entry point. Numerical component acceptance does not supply the missing
actual joint selection/harmonization/covariance producer chain, enumerate the
dynamic A_SPECIFICITY_MVMR family, pass GA08, authorize G0, or grant deployment.
Actual protected-worker integration/recovery and independent signed reviews
remain required. Core single-variable MR does not inherit this module's block.

Regenerate the complete wrapper with
`python3 -B scripts/build_mvmr_contract_wrapper.py`; `--check` validates bytes
without writing. Actual R regressions live in `scripts/tests/test_mvmr_contract.py`.
A missing R/package skip is not numerical acceptance.
