# Official OpenGWAS deployment candidate — 2026-10-23

Status: **PENDING main-session approval and production deployment**. These files
prepare the existing shared credential integration for this plugin; they do not
install anything, run statistical methods, or grant study eligibility/G0.

## Exact candidate and resident identities

The existing manifest and dispatcher remain byte-identical to the sealed author
method and authenticated metadata proofs. Their SHA256 values are respectively
`7611d0a7ea4efd229c75ec1f114d9871b9420509e1eb62aaa52f4063a634094e`
and `b2d1c715a182b9d5630b42598e29649bf82f024cb568b00b1e3d01cc77a9dafe`.
Image: `ghcr.io/zj-2002/ieugwasr-official@sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395`;
config: `38114ac009e0d023c262aa1b67eb459127810a345507b95cbc96ba515e9f5a2e`.
Author revision: `0c5b4cc6bc5e675afe222262950c8bb488f8d2f3`, ieugwasr 1.2.0.

Reuse the already built engine at source revision
`864b3a75a5e27c81cba0d78cbe834e796f51df26`, SHA256
`c0d7394f214a79c8d83222cd0ae651febfb48dd30d660c10edbb164ad2367224`,
from session `0f2306f2331345b7be15d657b4228eb3`, seal
`9243c8d26912ae028b2bf5f7befcf05ad799de77fce76d60e871d99f1c459945`,
member `permanent/sjtu-release-collection/autonomics`. No new large build is
needed. The matching loader consumer has SHA256
`e289d372b8d0abd84e4371ce48b9091eb41965d5de1985865286a2f5bb09537a`,
from session `3de5533e881144d1b1643c4fd648ef7b`, seal
`835bcb4368da6bccf05abf5dac61e51f88e71cfafa510851d2d6ac99d0082314`.
Its separately compiled example source SHA256 is
`290e615b725b7e663ed1449e415f9499dfd4203e5993fc460cdc7cd3f48db272`.
Do not confuse the example consumer with the production engine executable.

Read-only observation: gateway at `127.0.0.1:8765`, PID 439501, production
engine SHA256 `5a3131bedb394043045b4f11ae541c183cecf3cc36069e188cc981e9d64aea27`,
release `v0.1.0-static-ports.20261021.commit-66c70841-launcher-0a2b87e1`.
The plugin is registered without loader error at plugin revision
`3568272020d75be43d004f6b59f47fc9bec2e718`; both candidate kinds are visible.
This registration does not establish that the older process implements the
new private-environment channel. The owner policy file was absent.

## Minimal install differences (all PENDING)

1. Stage the verified existing engine into a durable release, retaining the
   current release for rollback. The installed launch.py already matches the
   published launcher source; retain those verified bytes. Launcher source
   `scripts/research_preview_launch.py` SHA256:
   `c0a142a9a4b1264208c8b4c3c6ac15b44ebd0979c200142225188b75f56d2a60`.
   Preserve the established service's state/data paths and gateway port; do not
   start an isolated profile or migrate database files as part of this change.
2. After reviewing any existing policy, install
   `plugin-private-environment.candidate.json` at the service HOME's
   `.autonomics/plugin-private-environment.json`, owner uid, mode 0600, nlink 1,
   in an owner-controlled directory (not group/other writable). The exact loader
   accepts only these two plugin kinds, the specified manifest/script/image
   identities, and the name `OPENGWAS_JWT`. Never place a credential value in this
   file or in a manifest. If the file now exists, compare and review; do not
   overwrite concurrent changes. No plugin source pin change is necessary:
   existing loaded manifest/dispatcher bytes are the authorization identity.
3. Use the reviewed launcher's existing `credentials_environment` path: inherited
   private `OPENGWAS_JWT` takes precedence, then its private credential file
   selected by `--env-file PATH` (default `~/Work/autonomics/.env`). The existing
   parser rejects unsafe mode, links, duplicates, control characters and file
   replacement. `OPENGWAS_TOKEN` is a distinct native-node setting; this candidate
   does not silently convert it to the R author's `OPENGWAS_JWT`. If only TOKEN
   exists, the official node must refuse until the operator supplies JWT through
   the existing private mechanism. Do not put values in service unit text,
   request JSON, argv, public configuration, shell tracing or evidence.
4. Install the reviewed qualified router (source SHA256
   `ec6f7fcec1c93d08c1baec68c3d034e8180dd110f2e295e2331c4e77da581eb9`)
   and explicitly add only the exact ieugwasr image reference to
   `drop_host_proxy_for_images` in the reviewed owner profile. This yields
   `--http-proxy=false` on this image's create/run operations. Do not disable
   host proxies globally or add host networking. Reconcile current directory,
   mount UUID/subvolume, complete ordered RootFS/config and retained publication
   proof before approving the post-boot store identity. The current shared
   profile SHA256 is
   `641dac9f9b7c414db8032be8fbc20d13fbb093c9e8c78b8c7ed550390c26bb00`;
   its recorded additional-store identity `[31,14712988,1000]` now matches the
   actual directory. This is the later shared-store repair, not the historical
   device-56 profile. Reuse its separately retained qualification only after
   independently verifying that evidence; do not describe the historical
   mismatch as the current profile's state. The profile contains 33 references
   and no drop_host_proxy_for_images field. The resident router SHA256 is
   `d73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194`,
   so the proxy-capable router source `ec6f7fce...` remains an install difference.
   Preserve unrelated image entries and policies.
5. Only the main session may approve service activation. Recheck actual process,
   binary, launcher, policy and router/profile identities after activation.
   Registration alone is insufficient. Startup/history failure is a HOLD;
   never move/remove WAL/SHM or perform database recovery in this deployment.

The source-level credential chain is: private file/environment → audited
launcher → engine environment → identity-bound loader grant → private runtime
container create environment → `--env OPENGWAS_JWT` (name only) → unchanged
R dispatcher → author default environment reader. Values do not enter ordinary
node environment or request arguments. The runtime suppresses private stdout,
stderr and exit diagnostics; normal output ports still require the explicit
secret guard in the final acceptance step. This does not claim zero encoded
secret leakage under every possible author response.

## Explicit replacement bindings

`runtime-bindings.candidate.json` records seven proposed per-function bindings,
including the existing gwasinfo transport observation. Six target functions
reuse the reviewed two-factory contract. It does not modify the fixed120
selection. Request-only: one File containing exactly `operation` and named
`arguments`. Dataset: that request plus a genuine non-NULL data.frame RDS with
`rsid,pval`, operation `ld_clump_api`; clump parameters remain explicit. This
low-level helper does not group automatically by `id`. Outputs are four Files,
including complete RDS and strict typed JSON, not legacy DataFrame ports.
Legacy parameter/default translation needs explicit per-function review.
`core/source_opengwas_gwasinfo_search` remains unsupported; no author function
or invented alias is introduced.

## Evidence reuse and minimum acceptance after approved deployment

Do not rerun six real APIs. Reuse method session
`a00366403b624c888c5561aa8a447335` (six targets plus gwasinfo, full RDS and typed
projection; request and dataset fixtures) and contract review
`IEUGWASR_SIX_FUNCTION_CONTRACT_REVIEW_20261021.md` in the main repository.
Real metadata producer session `6981e61864c841f1aab46c4d878d02fe` has a successful
DAG but whole-worker exit 1; its final whole-directory secret scan did not run.
Keep that failure. Corrected offline readback session
`bd275f328d094af9955a48d0c8aa6b55` exited 0 and checked 20 typed cells without a
new API request. Neither establishes a live dataset/clumping production run.

After approval, perform the following within the managed validation lifecycle
and save necessary sanitized evidence under AUTONOMICS_VALIDATION_PERMANENT:

1. Verify installed bytes and resident implementation; confirm both address
   registrations and the exact per-image router option. Keep the credential
   value out of argv and evidence. Credential availability alone is insufficient.
2. In a bounded disposable HOME through the matching consumer, reuse this
   candidate's wrong-identity and missing-credential checks for both kinds;
   require rejection before any container creation and no normal output ports.
   These are credential tests, not dataset format/method proofs.
3. Submit exactly one request-only `gwasinfo` request for explicit ID `ieu-a-2`
   through the approved current loader/runtime. Record the actual process/source
   identity, DAG exit and all four port hashes. Gate Podman create arguments on
   name-only `--env OPENGWAS_JWT`; suppress raw secret-bearing diagnostics before
   persisting. Do not rerun the six methods or authenticated dataset clumping.
4. Read full RDS and every typed cell offline with networking disabled and no
   credential. In the same successful acceptance run, scan all new evidence,
   outputs and captured logs in memory against the private plaintext credential
   before persisting/publishing them; record only pass/fail. If a leak is found,
   refuse publication and keep the incident private. The old producer's
   unexecuted final scan must not be relabelled as executed.
5. Record actual worker/launcher exits, seal and stopped-container proof.
   Any failure stays failed. No study denominator, O/LD/IV contract, scientific
   admission or G0 changes are implied by transport acceptance.

The bundled managed test is executed from the main repository:

```
python3 -B scripts/research_validation_session.py run -- python3 -B /home/zj-normal/Work/autonomics-plugins/research-adapters/ieugwasr-official/tests/deployment_candidate_acceptance.py
```

It reads no real OpenGWAS credential and creates no containers or scientific
result. Four negative cases reject wrong identity/missing credential for both
kinds. Two synthetic positive-path cases load a randomly generated toy credential
from a mode-0600 toy file using the exact audited shared credential helper, then
exercise the compiled consumer and stop at a non-Podman create sentinel. The
sentinel verifies the synthetic value arrived in its environment and only its
name appears in argv; it deliberately writes that value to stdout/stderr before
failing. Runtime diagnostic suppression and a plaintext scan of that case's
saved evidence must pass. This checks transport to create and output suppression,
not a successful container/R/API call. The opaque dataset input never reaches R,
and is not presented as a valid RDS or author method proof.

Successful managed candidate check: session
`58d7707039e542fca306a6af1d16680c`, seal
`f2b8bf4ce2c4f8a7969647cce57a4b9ed998f0847e44dfb414584c5f8c35649b`,
member `permanent/ieugwasr-deployment-candidate/verification.json`, SHA256
`ab52aa5feb9104b83631089f8ec620bfd91c64fa5615437f30d68a3e8f859a84`.
Both worker and launcher exited 0. Its final driver, policy, bindings, manifest
and dispatcher identities are authoritative for the tested code/configuration;
this explanatory document was updated after that run and is separately hashed
at handoff. Earlier four-negative-only session
`e4a169d198524213857b1b78499405dd` also passed, but is superseded for final code.
Two intermediate test-driver failures remain failed:
`86043f03b97c46a2887bcf26b123d378` (shared sentinel marker assertion) and
`253d33eacd8d471abccea11aed90296e` (sentinel newline escaping). Both worker exits
are 1; neither is production or author-method failure evidence.

Leakage coverage is deliberately bounded: the new two synthetic cases establish
name-only argv and suppressed runtime diagnostics; the existing private runtime
Rust tests additionally cover ordinary-env collisions and non-private subprocess
scrubbing. Existing launcher credential regressions cover private-file safety,
control/duplicate/unsafe-file refusal and reports without credential values.
No real JWT was loaded here, no real-output whole-directory scan was executed,
and encoded-secret nonleakage is not claimed. The post-deployment live metadata
acceptance and final real-credential plaintext scan remain PENDING.

## Rollback prerequisites

Before the main session changes anything, retain the current complete release,
service/drop-in bytes, plugin config, owner policy absence/contents and image
router/profile identities in private permanent technical evidence. Ensure no
active worker depends on a release/config to be replaced. Rollback restores
these exact deployment artifacts, not an inferred older state; stop approved
candidate workers first and verify process/port/state bindings. Database and
WAL/SHM recovery remain separately owned. Preserve all failed activation and
acceptance records. Missing backups or concurrent state changes block rollback;
this candidate does not authorize a restart, rollback or history manipulation.
