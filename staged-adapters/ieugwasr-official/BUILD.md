# Offline derived image: local build complete

The derived image has been built and tested locally. Its actual config ID and
local OCI manifest digest are recorded in [LOCAL_BUILD_STATUS.md](LOCAL_BUILD_STATUS.md).
Authenticated registry publication is also verified, but the package is private,
anonymous access is unavailable, and there is no deployment manifest.
The existing MRlap image and its certified pin are not modified or replaced.

## Fixed sources

- Base: `ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d`.
- Previously observed base config identity: `294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c`.
- Official ieugwasr `v1.2.0`, commit `0c5b4cc6bc5e675afe222262950c8bb488f8d2f3`.
- Exactly 13 upstream files: complete ten-file `R/` implementation,
  `DESCRIPTION`, `NAMESPACE`, `LICENSE`. No author method or license bytes are
  rewritten. Upstream docs/tests/vignettes are not included in this minimal
  runtime installation; this is not a copy of the full source repository.
- Each file is bound by SHA256 and original Git blob SHA1. The archived official
  tag and complete Git tree establish that the entire `R/` directory is present
  and no `src/`, `data/` or `inst/` runtime payload is omitted.

The package needs R >=4.1 and imports only `dplyr`, `httr`, `jsonlite`, `magrittr`
and `stats`. Those dependencies are inherited from the immutable base. The
Dockerfile does not run apt, CRAN, Git or any network download. Build-time version
records are emitted for the inherited dependencies; the base digest, not guessed
version strings, locks their bytes.

## Isolation

Install only the small author package into `/opt/ieugwasr-library`. The base's
ieugwasr 1.1.0 remains unchanged in its original library. `R_LIBS_USER` makes the
new 1.2.0 package the default **only inside this derived image**. Do not use this
derived image as an unreviewed replacement for MRlap's frozen environment.

`R_ENABLE_JIT=0` is explicit: the unchanged host integrity harness passed with
this setting, whereas default JIT=3 altered runtime function serialization
without changing author formals, source bodies or namespace identity. This
setting does not waive source checks. Future image checks must still compare
the complete author results and retained method namespace.

The checksum list itself is SHA256-bound in the Dockerfile. All 13 source files
and the source inventory are checked before installation. The image build
refuses absent base dependencies rather than fetching mutable replacements.

## Controlled build and worker ownership

The completed build used a dedicated lifecycle-managed build service with its
8 GiB parent memory limit and a verified, initially empty OCI subgroup inside
that service. Buildah's `--cgroup-parent` uses the supplied group directly: it
must not point to the populated subgroup containing the driver. A first failed
attempt established that restriction and remains recorded as failed.

The successful driver fixes `cgroupfs`, the exact empty OCI subgroup,
`--cgroupns=host`, `--network=none`, `--pull=never`, one job and forced removal of
intermediate build containers. It supplies a newly created empty registry auth
file and no inherited credential variables. Only the sixteen locked build
context files are copied; no dependency environment is cloned.

Finally, two stable service-process snapshots contain only the original driver
ancestors, the external-container census has no new remaining entries, all
sampled workers belong to the service, and source hashes remain unchanged.
Permission failures or unknown consumers are not ignored. The exact empty
subgroup is retired only after its inode identity and emptiness are checked.

Future builds must retain this explicit worker-ownership and stoppage contract;
merely putting a bare `podman build` inside a session is not equivalent. The
generic lifecycle shim currently tracks `run/create` intents, not build workers.
There is no production restart or shared-image/cache pruning.

The actual local config ID was independently inspected. The untouched
author/mock-HTTP harness and actual container-main output-port controls pass
in that image, with seven owned containers stopped. Isolated plugin DAG
integration remains outstanding. The actual immutable registry manifest and
configuration have now been independently read back and hash-verified; this
is separate from local digest inspection. The package remains private: neither
public availability nor clean-host deployment is claimed. A future manifest
must account for its actual credential/cache requirements rather than assuming
anonymous pulls will work.

`runtime-source-lock.json` remains the immutable pre-build input. Its
`derived_image_digest: null` means no registry deployment pin was specified;
the historical `build_executed: false` describes the input snapshot, not the
current build status. Actual build/test facts are recorded separately rather
than changing an already-used image source lock.

Those checks would qualify an explicit official replacement in its tested
scope, not native REST equivalence, real-service availability, scientific
eligibility or G0. `gwasinfo_search` still has no official equivalent and remains
outside this adapter.
