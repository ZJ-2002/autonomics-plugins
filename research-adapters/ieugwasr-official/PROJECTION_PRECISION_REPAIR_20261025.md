# Typed JSON precision repair

## Reproduced defect and minimal source change

The complete author RDS was correct, but the typed JSON projection used
`jsonlite::write_json(..., digits=NA)`. With jsonlite 2.0.0 this does not mean
lossless binary64 serialization: `1 + .Machine$double.eps` became `1`, while
`.Machine$double.xmax` became a rounded decimal that read back as infinity.
Consequently, the prior wrapper evidence does not establish lossless finite
numeric values in that JSON artifact.

Only the projection writer changes, from `digits=NA` to `digits=17`. The schema,
author call, request validation, dataset columns, complete RDS, failure
propagation, and four-port publication remain unchanged. The dispatcher SHA256
after this change is
`06941831dbdb1b9ebd91f71605593c38c5255beaf241ead3fb85a05202096d44`.

JSON is not a substitute for the complete RDS: signed zero may be normalized by
a JSON reader. The new signed-zero case checks preservation in RDS, not a false
claim of signed-zero JSON round-trip equivalence. Unsupported object/list
columns remain fail-closed rather than being silently flattened.

## Incremental proof

Three self-cleaning toy cases execute the actual dispatcher functions and
four-port writer, with a local resolver returning a toy author-shaped object.
No real credential is loaded, no API request or scientific model is executed.

- Adjacent binary64 values around one and arbitrary 17-digit positive/negative
  doubles are compared after JSON readback using exact eight-byte values.
- Maximum/minimum normal and positive/negative subnormal finite doubles are
  compared the same way; finite values must not become infinity.
- NA, NaN and both infinities retain distinct explicit states. Column storage,
  data.frame class, reverse donor row names and complete RDS are checked.

The managed proof reconstructs the exact historical dispatcher bytes with SHA256
`b2d1c715a182b9d5630b42598e29649bf82f024cb568b00b1e3d01cc77a9dafe`,
then reproduces two failures among the three cases. This is explicitly a
reconstructed-source reproduction, not a rewrite of historical evidence. The
current dispatcher passes all three cases without skipped tests.

Session: `0db2de250fa0438aa6f657516264c585`.
Manifest seal:
`c7779112e670571b2fdfef479417c04ae7e88a4fa923e7839d02fc48870ed199`.
Member: `permanent/ieugwasr-projection-precision/verification.json`.
Member SHA256:
`6affb406e2699d86abebc0fe8acb81478c79eca93b55c11ab5e370aa4e99bf19`.
Worker and launcher exited zero; the session is CLEANED.

Source files and identities are recorded in the verification member. The new
case file is `tests/test_ieugwasr_projection_precision.py`; the managed driver
is `research-adapters/ieugwasr-official/tests/projection_precision_acceptance.py`.

## Reuse and remaining deployment work

The six operation contracts still reuse the official-package call and complete
RDS evidence recorded in `DEPLOYMENT_CANDIDATE.md`, notably session
`a00366403b624c888c5561aa8a447335`. Those operations were not rerun. Metadata
authentication and shared credential/network tests do not establish six new
authenticated endpoint executions or a live clumping run. Missing new endpoint
observations must not be mislabeled as a demonstrated algorithm failure.

The deployment candidate is historical: its older PID, engine and policy
PENDING statements are not today's runtime assessment. The current resident
reconciliation has the six official bindings registered at their pinned
implementation; registration is still not per-operation execution. This repair
changes the script identity, so current-loader authorization and source pins
must be reviewed together by the integrating owner. This proof performs no
manifest change, private-policy edit, service restart, deployment, source push,
study qualification or G0 grant.

Only the active dispatcher is repaired. The old staged adapter and its old
source hash remain historical reference evidence and must not be silently
rewritten. Other JSON audit or contract outputs need separate semantic review;
they are not bulk-replaced by this change.
