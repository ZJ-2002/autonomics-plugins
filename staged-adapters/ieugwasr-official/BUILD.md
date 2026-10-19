# Unbuilt, offline derived image plan

No derived image has been built, published or assigned a digest. There is no
deployment manifest. The existing MRlap image and its certified pin are not
modified or replaced by this proposal.

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

## Future controlled build, not yet executed

From the engine repository, after the build slot is available and lifecycle
admission permits it:

```sh
python3 -B scripts/research_validation_session.py --profile build run -- \
  podman build --pull=never --network=none \
  -f /home/zj-normal/Work/autonomics-plugins/staged-adapters/ieugwasr-official/Dockerfile \
  /home/zj-normal/Work/autonomics-plugins/staged-adapters/ieugwasr-official
```

This is only a command plan, not an acceptance driver: the actual build must
also retain its image ID, source hashes, inherited dependency records and logs,
then verify owned build workers have stopped. It must not start detached
scratch consumers or infer success from an image tag. There is no automatic
production restart or old-cache removal.

After a successful build, independently inspect the actual local config ID;
run the untouched author/mock-HTTP harness in that image, retain the full RDS
comparisons and error controls, then test the declared plugin ports in an
isolated DAG. Only after publishing and inspecting a real immutable registry
digest should a manifest reference it. No digest is fabricated in advance.

Those checks would qualify an explicit official replacement in its tested
scope, not native REST equivalence, real-service availability, scientific
eligibility or G0. `gwasinfo_search` still has no official equivalent and remains
outside this adapter.
