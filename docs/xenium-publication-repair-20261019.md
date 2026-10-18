# Xenium ingestion publication repair

Status: **publication-layer repair; full image/DAG requalification pending**.

The frozen Xenium adapter previously checked output absence and then used
replacement renames. A file arriving between those operations could be
overwritten. Its failure handler could also overwrite a foreign diagnostic.
Both defects were reproduced against owner main `b455a53118f1e702b4a70f8611db1f2740b8ee47`.

The repaired entry stages products privately and publishes each file with an
exclusive hard link. Existing files and dangling symlinks are not replaced.
Rollback checks device/inode ownership before removing a published file;
foreign replacements observed by that check are retained. Failure diagnostics
use the same exclusive publication and never intentionally replace a file.
This is not a transaction across all ports or a security guarantee against a
hostile same-UID process racing every ownership check.

Seven self-cleaning unit tests cover successful publication, late foreign
analytical output, late foreign diagnostic, all nine dangling output paths,
partial rollback, replacement preservation, and malformed-request diagnostics.
The numerical calculator is mocked in these tests: they do not certify CSC
decoding, official format coverage, image execution, or DAG integration.
The old non-entry function ASTs, including validation and count conversion,
are compared unchanged in the managed proof.

No frozen scientific parameters, donor assumptions or spatial null model were
changed. B-S remains CONDITIONAL_NOT_READY; GS01 remains OPEN. No production,
research admission, segmentation, or G0 approval is granted by this repair.
