# Frozen whole-project read-only verification

This node executes the original `verify_g0_v432.audit(root)` on current content;
it does not replace it with a manifest-only check or operator-run workaround.
The agent builds the fixed DAG and calls `run_dag`. The terminal JSON reports
technical verification only: no new G0, scientific gate, signature, research
authorization, result reveal or ledger update. The existing original minimum
scope remains LEGACY; this node does not complete the formal scientific plan.

The whole approved local project is mounted read-only without copying its
23,669 frozen files (5,669,779,954 manifest bytes). The two file inputs are the
locked top-level `README_START_HERE.md` and a private operator registration.
`stage_in_mode=symlink` uses the existing runtime's identity parent-directory
bind. The wrapper refuses copies/remote fallback and checks actual kernel
mountinfo for the read-only ROOT and control directory, including descendant
mounts. Registration lives in a dedicated directory containing only its JSON;
never place it beside credentials, payloads or inside the frozen baseline.

The operator registers canonical ROOT/device/inode/owner/mode, the actual
manifest identity/size, and the three original module identities. Registration
does **not** establish full current verification. Every actual invocation runs
the original complete content/path-set checks and checks the pinned sources
again before publishing. The compiled `cache_policy="never"` blocks scheduler
reuse even for `run_dag(resume=true)`. Omitted cache policy in older plugins
retains their existing behavior. This plugin requires the corresponding core
release; an older parser must refuse its new field.

Source closure: `verify_g0_v432.py` -> `validate_runtime.py` ->
`followup_contracts.py`. All three SHA256/lengths are pinned to the original
manifest. Isolated `-I -S -B` execution compiles only those measured bytes.
The remaining import finder uses only startup image stdlib paths, even after
the original audit inserts the project directory into `sys.path`; project pyc
and shadow modules cannot replace code. The approved official Python amd64
`a66d3…` image is reused with no network, read-only rootfs, explicit CPU/RAM/PID
limits and 1,200-second timeout. No R/package installation is required.

Operator deployment, under managed lifecycle:

1. Create a persistent private control directory (0700) outside the baseline;
   run `tools/register_frozen_verifier.py --project-root APPROVED_ROOT --output
   PRIVATE_CONTROL/registration.json`. The CLI reads only metadata and the
   small pinned source/manifest/anchor files, writes one private0600 JSON, and
   outputs its actual SHA. Keep the registration out of Git/public evidence.
2. Pin that exact SHA in `nodes.command.env.EXPECTED_OPERATOR_REGISTRATION_SHA256`
   through normal reviewed immutable plugin source/validation/activation.
   The public template deliberately says `UNREGISTERED` and refuses execution.
   This is an operator deployment binding, never an agent parameter. Record
   the derivative source bytes and real Git identity; do not forge an upstream
   source digest/commit or modify an existing installed snapshot. No private
   physical path or registration payload belongs in published source.
3. Keep the existing `/research/current` local VFS whole-directory mount
   read-only; mount only the dedicated control directory read-only at
   `/research/verification-control/NAME`. Place the artifact prefix
   `/artifacts/frozen_project_verification` outside the frozen baseline and
   bind native run ownership normally. Do not add output files to the baseline.
4. Install the qualified core release and plugin with the existing validator,
   measured image catalog and immutable-source activation. The wrapper refuses
   missing/unpinned registration or changed namespace/source identity.
5. Generate the agent request with
   `tools/build_frozen_project_verifier_dag.py --registration-uri
   vfs:///research/verification-control/NAME/registration.json --output REQUEST`.
   Submit `dag_shell` dry-run then commit, and actually invoke `run_dag`.
   Confirm `frozen_v432_readonly_full_verify.reused=false` and read its genuine
   `technical-verification.json`. A nonzero/refused node is never a verification
   success; stale artifacts cannot substitute for this invocation.

Required release acceptance includes the real approved image and whole current
ROOT invocation under a managed cgroup, recorded container stop proof and
actual daemon History/output identity. The small SYN/source-loader tests are
engineering checks; they are not that acceptance or scientific qualification.
