# LDSC: author runtime migration and corrected declared outputs

All three canonical entries (`ldsc_munge`, `ldsc_h2`, `ldsc_rg`) now invoke
unmodified CBIIT/ldsc at commit
`6c673952cee74bd5c57aef1555a03b1c015399a0`, not the retired refactored tree.
The two `ldsc_*_frozen_precision` entries use the same pristine runtime.
Its public immutable image is
`ghcr.io/zj-2002/ldsc@sha256:e98d2a89b0412384bbec1369250d935868a919f8a164c4ce55b282ac13495767`.
Publication changed the OCI manifest digest, not the measured image configuration,
author Python files or installed package identities. No environment was cloned,
image rebuilt, statistical formula translated or native fallback registered.

## Three real adapter defects

1. The declared h2/rg log names collided with the internal author log path.
   Actual execution failed with `input file is output file`; internal paths are
   now distinct and covered by declared-manifest-port tests.
2. The pristine image also contains legacy PATH aliases to broken refactored
   code. Each adapter now dispatches to the absolute measured author file under
   `/opt/cachexia-official-ldsc/`. Image source presence alone was insufficient.
3. The pristine rg method writes its inference output to stdout while creating
   an empty log. The adapter formerly replaced the real result with that empty
   file. It now publishes a nonempty author log when present, otherwise preserves
   author stdout, keeps stderr diagnostics, and rejects both outputs being empty.

**The earlier rg-positive claim in session
`e1b438845e764933965c82a231f95eba` is withdrawn:** three comparisons matched two
empty logs rather than the actual results. That archive remains unchanged and is
not counted as valid rg method evidence. The corrected verifier requires nonempty
complete output and actual inference markers; a regression rejects empty-equals-empty.

## Current independent proofs

| Entry | Author comparison | Scope |
| --- | --- | --- |
| ldsc_munge | 2 declared-port cases, 1,000 input rows each; all decompressed rows, N and signed Z equal | plain/gzip synthetic inputs |
| ldsc_h2 | 3 complete-output comparisons | plain/gzip, 20/200 blocks, explicit intercept/cutoff |
| ldsc_rg | 3 complete-output comparisons and 1 exact author failure | plain/gzip, nonpositive h2, incompatible allele |
| ldsc_h2_frozen_precision / ldsc_rg_frozen_precision | 5 full-object comparisons, 4 explicit refusals | fixed synthetic 22-chromosome panels and runtime |

The corrected canonical proof is session
`d75e5074142c4003b63c55cccb0472ff`, exit 0/CLEANED, manifest
`0c6341b5e372542a25d4e4f27bdd7038f9b481284ed06e2f4883f9b9dbc1fe4f`.
All three successful rg ports are nonempty (2,409 / 2,508 / 2,555 bytes).
The entire author output is compared, with only declared path substitutions and
three wall-clock timing lines normalized; numerical display lines are untouched.
Successful stderr warnings match the independent author invocation exactly.
The invalid-allele case preserves the author's actual exit 1 and complete ordered
diagnostics, including its secondary exception-formatting defect, without fallback.

Precision requalification compares 2,235 returned fields, including 1,693 finite
fields. Its method body is unchanged; full objects remain separate from rounded
CLI display logs. Display-log P values must not replace full-precision A_ARCH
family results. Eleven success, failed and superseded archives were independently
rehashed with exact manifest membership. Public metadata is in
`evidence/ldsc-author-runtime-migration-20261015.json`; private logs and raw
archives are not published.
All **174 required source/catalog tests** actually executed: zero failures,
errors or skips, exact required-test inventory and source lock matched. Test
session `f59f9e172e92458fb618d0000cd2c90b` exited 0/CLEANED; this is an engineering
check, not additional independent statistical certification.

## Not a production certificate

Official-method and declared-port proofs are **scoped synthetic evidence**.
Current-engine isolated DAG and resident-daemon deployment remain pending.
Actual research LD-score panel bundles are not qualified or substituted with the
different MRlap panel. Full frozen family eligibility, statistical assumptions,
resource admission, recovery and scientific review are not granted. The original
node denominator, frozen design, 276/288/696 and G0 remain unchanged.
