# Offline explicit official-call DAG acceptance

Status: **OFFLINE_DAG_ACCEPTED_SCOPED; live API and production NOT_ADMITTED**.
This is technical fixture evidence, not scientific eligibility or G0 approval.

## Fixed identities

- Author package: ieugwasr 1.2.0, commit
  `0c5b4cc6bc5e675afe222262950c8bb488f8d2f3`.
- Actual private registry reference:
  `ghcr.io/zj-2002/ieugwasr-official@sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395`.
- Config: `38114ac009e0d023c262aa1b67eb459127810a345507b95cbc96ba515e9f5a2e`.
- Candidate manifest SHA256:
  `7611d0a7ea4efd229c75ec1f114d9871b9420509e1eb62aaa52f4063a634094e`.
- Dispatch SHA256:
  `b2d1c715a182b9d5630b42598e29649bf82f024cb568b00b1e3d01cc77a9dafe`.
- Unchanged official-wrapper suffix SHA256:
  `ea7815eef5b9d18681b87c288dc0d7097311a5fe32a2fe16bee5e82ce7e25931`.
- Reused SDK54 engine: `4256643c55ae6fb50e8c867069330ed6ac2b4bc0`.
- Frozen private technical driver SHA256:
  `aaa790c73c39201280845d02d4a56aff3804cf778670f408cf3faa0e0d2ec775`.

The image and thirteen author source/license files were not rebuilt or changed
for this DAG proof. The pre-build runtime source lock remains immutable. The
actual registry publication and its private visibility are recorded separately
in the staged runtime's `LOCAL_BUILD_STATUS.md`.

## What actually ran

The hash-bound candidate has two required-input shapes. A separate private
fixture manifest changes only the network to `isolated`, loads a static HTTP
transport fixture through `R_PROFILE_USER`, and supplies an empty test JWT.
The shipped candidate remains `egress` and does not contain a credential value.
The real cached registry name-plus-digest was inspected and matched the config
before `pull_policy=never` execution; a mutable tag was not used as execution
identity.

Before any fixture container, the fixed SDK parsed and loaded both manifests
in a zero-node schema-only job. That job is not counted as a method test.
The subsequent seven positive DAGs used real declared container input/output
ports and an additional private full-object consumer:

| Author operation | Result shape | Typed cells consumed |
|---|---:|---:|
| associations | 2 x 7 | 14 |
| phewas | 2 x 4 | 8 |
| tophits | 1 x 6 | 6 |
| variants_rsid | 1 x 5 | 5 |
| variants_chrpos | 1 x 5 | 5 |
| ld_clump_api | 1 x 3 | 3 |
| gwasinfo | 1 x 3 | 3 |

For every case, `readRDS` of the actual DAG product was `identical` to the
complete independent direct-author object already sealed in image proof
`29c0e4df69ac4e0aaf9a0e2610f7eddb`. Classes, attributes and row names were not
discarded. Every typed JSON cell, state, storage label and row/column coordinate
was checked against that RDS. All 44 cells then crossed a real
`file_to_dataframe -> dataframe_to_file` TSV terminal and were read back equal.
The consumer did not treat the nested projection schema as a one-row data table.
Author batching counts and top-hit server-preclumping semantics were checked.
No independent method oracle or official package build was repeated here.

Five negative DAGs covered request-only clumping, NULL dataset RDS, the wrong
operation on the dataset kind, the author's empty-variant error and HTTP 401.
Every method failed nonzero with no normal output ports; the verifier, reader
and sink were skipped, and no terminal table appeared.

One small fixture-preparation container, fourteen positive producer/consumer
containers and five negative producer containers were all managed and proved
stopped: **20/20**, with no detached scratch consumer.

## Evidence and retained failures

The successful managed session is `a00366403b624c888c5561aa8a447335`, worker
exit 0, lifecycle `CLEANED`, archive seal
`776ec16e1926fc73f8a9b7371b3b92edc9cfd165cf89c0d04b4be2f8f8b6be4b`.
Its permanent evidence subtree is `ieugwasr-official-explicit-dags/`, including
`verification.json`, each job/report, all actual four-port products, complete
object-consumer records, terminal tables and `owned-container-stops.json`.
Local private payloads and launcher logs are not part of this published family.

Prior attempts remain failed, not relabelled successful: absent cached registry
name, a missing private-consumer `doc`, the inherited library precedence, and
two HTTP-fixture startup-order errors. The isolated startup diagnostic session
`042799cb4647449e850788012af6a429` (seal
`4d73d1a6c76aea261540a1fb8ceb1c9f2b5d532f534864b9727199e3ab5bae87`)
proved that normal R startup selected retained ieugwasr 1.1.0 unless `R_LIBS`
was explicitly pinned. The candidate now pins both library environment values;
the original wrapper's version refusal was not weakened. The successful final
driver was frozen before admission and equals its retained executed snapshot.
Eight self-cleaning dispatch-contract tests also pass, including library pins,
required port counts and NULL/dataset refusal.

## What remains unproved or unsupported

- HTTP transport was mocked and networking disabled: no authenticated real API
  response, quota behaviour or service availability was certified.
- The registry package remains private; anonymous clean-host pull is unavailable.
- Secure live JWT transfer is pending; no JWT request parameter or public env
  template is an acceptable workaround.
- These four File outputs are not the legacy native DataFrame ports. A frozen
  study needs an explicit downstream adapter and method/default migration review.
- Projection supports only the stated atomic-column domain; other author
  objects are refused rather than silently flattened.
- `gwasinfo` is supplementary. `gwasinfo_search` has no equivalent author
  function and remains unsupported; seven fixtures do not close seven legacy
  routes by renaming one.
- No production restart, current-daemon admission, research fitting, scientific
  release, design change or G0 approval is claimed.
