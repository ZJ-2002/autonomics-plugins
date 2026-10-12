# Fixed core B state R method candidate

This candidate manifest registers only official singscore (6 inputs, 5 outputs)
and explicitly frozen unadjusted Welch/paired contrasts (6 inputs, 4 outputs).
It accepts no arbitrary script, image, library, statistical-model or threshold
override. Score audit/RDS ports are 3/4; contrast audit/RDS ports are 2/3.
Each node uses two CPUs, eight GiB, 256 PIDs, an isolated network, read-only
root, no pulls and the fixed vanilla R launcher.

The pinned local OCI candidate is `e2097dd2ea87845952eb39e565b43ec9ff10ba9a3cbf5692f18ded03303fb913`.
R 4.6.1 and singscore 1.32.0 use complete fixed entry sources. XML 3.99-0.25,
stringi 1.8.9 and RSQLite 3.53.3 were rebuilt offline in the authenticated base;
stringi uses bundled ICU 74.1. This differs from the original host native-library
environment. Complete dependency distribution provenance remains unqualified.

The generators `build_b_state_score_wrappers.py` and
`build_b_state_contrast_wrappers.py` write both the canonical entries and these
identical mirrored sources. Their `--check` modes reject drift. Actual loader
and manifest ABI tests register all five preparation/method kinds and reject
node-level overrides.

Private actual-container component evidence is retained in
`results/research-execution-20261010/b-state-method-oci-candidate-v2`:
19 official tests, no skips, 59 actual image calls and both baked entries'
success/refusal paths. An independent Python/SciPy verifier checks 756 scored
rows and 83 official t tests, with maximum difference about 6.22e-15.
Earlier ABI, storage and operator-checker failures are retained separately.
The first candidate's native ABI rejection remains permanent evidence.

This is not a complete protected B family or worker acceptance, a substitute
for UCell/covariate/mixed/microarray routes, a real clinical decision, a B-SPEC
approval, an original-family freeze or production deployment. All 74 real G0
items remain OPEN. Scientific and technical reviewers are not yet designated.
