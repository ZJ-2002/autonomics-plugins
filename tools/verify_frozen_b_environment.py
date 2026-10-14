"""Verify the sealed two-package OCI original; no image build or export allowed."""
import argparse
import json
import os
from pathlib import Path
import sys

import build_frozen_b_environment as builder

SESSION = '8342bfe298384e80a9e98b6db09481cc'
RELATIVE = 'permanent/frozen-b-thin-environment/frozen-b-normalized.oci.tar'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--frozen-code', type=Path, required=True)
    parser.add_argument('--reuse-archive', type=Path, required=True)
    args = parser.parse_args()
    archive = args.reuse_archive.resolve(strict=True)
    root = archive.parents[3]
    if root.name != SESSION or archive != root / 'artifacts' / RELATIVE:
        parser.error('only the original sealed8342 software OCI archive is admitted')
    manifest = json.loads((root / 'artifacts/MANIFEST.json').read_bytes())
    expected = manifest['files'][RELATIVE]
    actual = dict(sha256=builder.sha(archive), bytes=archive.stat().st_size)
    if actual != expected or actual['bytes'] > 650 * 1024 ** 2:
        parser.error('sealed source SHA/size differs or exceeds650MiB')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    admission = dict(scope='ENGINEERING_VERIFY_ONLY_EXISTING_SOFTWARE_OCI_NOT_IMAGE_BUILD',
        original_build_session=SESSION, original_archive=actual, original_archive_path=str(archive),
        resource_classification='ROOT_REVIEW_WORK_CHANGED_TO_IMPORT_ABI_25_GENE_TOY',
        managed_profile='light', cpu_limit=2, memory_max_bytes=2 * 1024 ** 3,
        toy_gene_count=25, build_allowed=False, save_allowed=False,
        active_publication_exempted=False, scientific_budget_changed=False,
        scientific_authorization=False, G0=False)
    (permanent / 'VERIFY_ONLY_ENGINEERING_ADMISSION.json').write_text(json.dumps(admission, indent=2) + '\n')
    original = builder.execute
    def verify_execute(command, output, **kwargs):
        if command[:3] == ['skopeo', 'copy', '--preserve-digests']:
            if command[3:] != ['oci-archive:' + str(archive),
                               'containers-storage:localhost/autonomics/frozen-b-normalized:v432-export-verified']:
                raise RuntimeError('verify-only copy must use the sealed original and explicit local destination')
            return original(command, output, **kwargs)
        if command[0] != 'podman' or command[1] not in {'image', 'run', 'load'}:
            raise RuntimeError('verify-only task forbids build/save and unrelated lifecycle commands')
        if command[1] == 'image' and command[2] != 'inspect':
            raise RuntimeError('verify-only image command must be inspect')
        return original(command, output, **kwargs)
    builder.execute = verify_execute
    sys.argv = [str(Path(builder.__file__)), '--library', str(args.library), '--frozen-code', str(args.frozen_code),
                '--reuse-archive', str(archive)]
    builder.main()


if __name__ == '__main__':
    main()
