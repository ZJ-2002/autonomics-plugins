# Local runtime status — 2026-10-19

## Actual identity

- Local image config: `38114ac009e0d023c262aa1b67eb459127810a345507b95cbc96ba515e9f5a2e`.
- Local OCI manifest: `sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395`.
- Authenticated registry publication: **verified** at
  `ghcr.io/zj-2002/ieugwasr-official@sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395`.
- Package visibility: **private**, confirmed by the read-only GitHub API;
  anonymous manifest access is not available.
- Production registration, deployment and restart: **not performed**.
- Scientific release / G0: **not granted**.

The registry pin is established by the actual push receipt and remote
manifest/config readback, not inferred from the local digest. The remote
manifest is 2,509 bytes and its configuration is 15,968 bytes; both SHA256 values
match the qualified build. No fresh full-layer anonymous pull is claimed.

The image contains author ieugwasr 1.2.0 in `/opt/ieugwasr-library/ieugwasr`,
R 4.6.1, and explicit `R_ENABLE_JIT=0`. Inherited imports were read back as
dplyr 1.2.1, httr 1.4.9, jsonlite 2.0.0, magrittr 2.0.5 and stats 4.6.1.
The original immutable MRlap base config `294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c`
remains unchanged.

## Sealed technical evidence

| Evidence | Successful session | Artifact-manifest SHA256 |
|---|---|---|
| Offline derived build and explicit worker stoppage | `f01533b3fa8944fb91dc959d3884e496` | `c333eb695fd9a92aecd5a35f686ad3a195db214df71e247117a06b57929a5a74` |
| Actual local image author and port controls | `29c0e4df69ac4e0aaf9a0e2610f7eddb` | `c0fb4d7a05ae3376f580bd9e13989f59663094580945f9af963880dec045beae` |
| Actual private registry publication and remote readback | `dfd20547a7e84bffb0753d185dd94491` | `312d25957e802e9c8c6451731d2ada27f6570998a4eb26264004ec45fdcf0573` |

The build locks thirteen unmodified upstream source/license files and the
immutable base, checks all sixteen context-file identities before/after, and
retains the actual build metadata and local image inspection. Twenty-two
cgroup samples place all observed workers inside the dedicated service.
Final checks show no unknown live worker and no new external container remaining.
The earlier populated-cgroup build failure is not relabelled successful.

Registry authentication used the explicitly authorized existing GitHub account
through standard tools, password stdin and a temporary mode-0600 authfile.
Authentication stdout/stderr and credential values were not archived. The
temporary authfile was removed after the task. Package/account permissions were
not changed. An earlier attempt with no default Podman login remains failed;
GitHub login alone was not treated as evidence of package-write permission.

The actual-image evidence includes:

- Unchanged author HTTP-fixture harness: seven complete RDS result comparisons,
  identical author requests, batching/sorting/clumping checks and two error controls.
- All 41 author namespace functions remain unchanged under the locked JIT setting.
- Source checksums, installed package path/version and inherited dependencies
  are checked inside the actual image.
- Six real container-main controls: four standard output ports succeed; missing
  output 2, preexisting output 1, unsupported search, lossy projection and author
  error each fail without publishing normal output ports or altering foreign output.
- Seven fresh lifecycle container intents are matched to stopped containers with
  zero remaining entries.

Only HTTP transport is replaced by offline fixtures. No real API or GWAS request,
production service, scientific result or frozen research configuration is changed.

## Remaining boundaries

This is not full parameter-domain equivalence, live API availability, isolated
plugin DAG acceptance or production admission. Private-registry publishing
credentials have been used safely, but research-service credentials and
real authenticated deployment/log-redaction remain unqualified. A future generic
official-call node must retain the request operation as part of its explicit
method contract; its node name alone cannot identify the method.

`gwasinfo_search` has no matching author function and is refused. The seven
tested author operations include supplementary `gwasinfo`; this must not be
miscounted as seven previously unresolved native routes being closed.

The source lock is intentionally unchanged from the pre-build input. Registry
pin and current build/test state belong in subsequent evidence, not a mutable
rewrite of the source identity used by this image.
