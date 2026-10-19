# Hashutil publication repair

This repairs the explicit `cachexia-hashutil` adapter's filesystem publication,
not its SHA256/BLAKE3 computation. The original `file_hashes` node's different
FileSet contract is not silently certified or replaced.

## Reproduced defect and repair

The former script removed an existing result or fixed `.partial`, truncated an
existing log, and could overwrite a result created after hashing began. Sixteen
self-cleaning real-script toy controls reproduce eleven failures on the frozen
original source. After repair all sixteen pass.

The entry point now rejects pre-existing result, log and fixed partial paths,
including regular files, symlinks and dangling symlinks. Alias checks still
protect the input. Log and partial creation are exclusive. Final publication
uses a no-clobber hard link, and failure cleanup checks the recorded device/inode
before unlinking its own result or partial. Diagnostics retain their original
open file descriptor rather than reopening a possibly replaced foreign path.
Preflight refusal does not create a diagnostic at an already occupied path;
the error remains on stderr. Valid fresh-workspace failures still retain their
owned `BLOCKED` diagnostic and no successful result table.

`positive_integer`, `parameters`, `identity` and `file_digests` have unchanged
function ASTs. The manifest, image, input/output declarations, algorithm order,
streaming bounds and expected output table are unchanged. The original
source-bound vector and positive numerical evidence need not be recomputed for
this publication-only change; this repair does not claim those historical runs
were newly executed.

## Scope and limits

Controls cover pre-existing result/partial/log, symlinks and dangling paths,
input aliases, invalid parameters, competing publication, foreign replacement
of a partial or diagnostic, and serialization failure. Valid nonempty and empty
SHA256 inputs verify the exact table contract. These are engineering controls,
not new scientific analyses or a new full official BLAKE3 domain certificate.

The `lstat` identity check and later unlink/link are not an atomic conditional
namespace operation. This is not a guarantee against malicious concurrent
parent-directory/path replacement, an atomic two-output transaction, crash
durability, all filesystem backends, or a current resident-daemon deployment.
The intended scope is an isolated, controlled, fresh worker workspace.

Tests: `python3 -B -m unittest tests.test_hashutil_publication -q`.
The test-only `AUTONOMICS_HASHUTIL_TEST_SOURCE` selects a frozen baseline source
for independent before/after engineering controls; it is not a production-node
option or a way to alter the hash method.

No production restart, image change, frozen research-input change, scientific
release or G0 approval is implied by this repair.
