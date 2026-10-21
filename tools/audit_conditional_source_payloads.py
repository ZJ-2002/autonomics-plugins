import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
LOCK_PREFIX = ARCHIVES / '587358e53cf14c258b10f1d3418e79fb/artifacts/permanent/conditional-source-lock-recovery'
IMAGE = 'localhost/cachexia-lcmm@sha256:602bbf79fa81124edc1d78f366a71e2f8e55f1c768377810104eb81bb03ac97a'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def checksum(filename):
    with filename.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    original = verify_archive(ARCHIVES, '587358e53cf14c258b10f1d3418e79fb',
        '4f8009bf10229b5d77f57c92254ae76ae4ded05f1ecf38598400376ce5b34728')
    require(original['worker_exit_status'] == 1, 'Preserve actual failed parent status')
    require(verify_archive(ARCHIVES, '40a1d61213a54a9cb4cd708c9833b05f',
        '0283543dbc6ee6ff31bc47e116476bea943a14fb4c6b726eccd79c1c338bdba3')['positive_worker_exit_verified'],
        'Original image identity audit required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'conditional-source-payloads'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    locks = {}
    for name, expected in {
        'mice-source-plan.json': 'bba54da13dc82bab7e0f2402419596cdc75ff51b3ae6703383fb7232ff1ad011',
        'survey-source-provenance.json': '44057ba7ec4cda587de819c1e0b88fc81aefd0f9c3d8916e9e0bdf66fe9b5db7',
        'mice-runtime-debs.SHA256SUMS': 'b81998f806069e011dd589b3d02e3675f67abdc3157c54541df3959b7d9be05f',
    }.items():
        raw = (LOCK_PREFIX / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Recovered lock identity differs')
        (output / name).write_bytes(raw)
        locks[name] = raw
    lcmm = ROOT / 'research-adapters/cachexia-lcmm/source-plan.json'
    require(checksum(lcmm) == '5963bc270fe7ea42e1ee1f24a980889e63847241b92a23bcdca0dd9cd2c14b37', 'LCMM lock differs')
    expected_members = {}
    for family, plan in [('mice', json.loads(locks['mice-source-plan.json'])),
                         ('survey', json.loads(locks['survey-source-provenance.json'])),
                         ('lcmm', json.loads(lcmm.read_bytes()))]:
        for record in plan['archives']:
            filename = record.get('filename', record['url'].rsplit('/', 1)[1])
            expected_members[f'opt/cachexia-{family}/sources/{filename}'] = record['sha256']
    for line in locks['mice-runtime-debs.SHA256SUMS'].decode().splitlines():
        digest, filename = line.split(maxsplit=1)
        require(re.fullmatch(r'[0-9a-f]{64}', digest) is not None, 'Invalid Debian lock')
        expected_members['opt/cachexia-mice/runtime-debs/' + PurePosixPath(filename.lstrip('*')).name] = digest
    require(len(expected_members) == 32, 'Exactly 24 R archives and eight Debian archives required')
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    require(IMAGE in profile['images'], 'No implicit image enrollment')
    primary = profile['primary']
    backend = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--storage-opt',
        'additionalimagestore=' + profile['additional']['path'], '--root', primary['graphroot'],
        '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
        '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
    directory = Path(os.environ['TMPDIR']) / 'source-payload-oci'
    saved = subprocess.run([*backend, 'save', '--format', 'oci-dir', '--output', str(directory), IMAGE],
                           capture_output=True, timeout=600)
    require(saved.returncode == 0, 'Exact cached image export failed')

    def blob(descriptor):
        digest = descriptor['digest']
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None, 'Invalid blob digest')
        filename = directory / 'blobs/sha256' / digest.split(':')[1]
        require(filename.is_file() and not filename.is_symlink() and filename.stat().st_size == descriptor['size']
                and checksum(filename) == digest.split(':')[1], 'OCI blob differs')
        return filename

    index = json.loads((directory / 'index.json').read_bytes())
    require(len(index['manifests']) == 1, 'Exactly one manifest required')
    manifest = json.loads(blob(index['manifests'][0]).read_bytes())
    require(manifest['config']['digest'] == 'sha256:ef26c21806ef2bddd36601c47a24a8f0ed2423ffe56174779ae7ad3aa450a822',
            'Exact previously audited LCMM image config required')
    config = json.loads(blob(manifest['config']).read_bytes())
    previous_path = ARCHIVES / '40a1d61213a54a9cb4cd708c9833b05f/artifacts/permanent/conditional-image-layer-audit/verification.json'
    require(checksum(previous_path) == '6c424a8196f6f386545220f0ac14c9b05fa577d27c9a84bc1dcd9f1f915d2471', 'Layer audit report differs')
    previous = next(item for item in json.loads(previous_path.read_bytes())['images'] if item['family'] == 'cachexia-lcmm')
    require(len(manifest['layers']) == len(previous['layers']) == 20, 'Full layer axis required')
    require(config['rootfs']['diff_ids'] == [item['diff_id'] for item in previous['layers']], 'Layer content axis differs')
    observed = {}
    additional = []
    for descriptor, prior in zip(manifest['layers'], previous['layers'], strict=True):
        require(descriptor['digest'] == prior['blob_digest'], 'Layer digest differs from original audit')
        filename = blob(descriptor)
        with filename.open('rb') as raw:
            compressed = raw.read(2) == b'\x1f\x8b'
            raw.seek(0)
            stream = gzip.GzipFile(fileobj=raw) if compressed else raw
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                for member in archive:
                    name = member.name.removeprefix('./')
                    relative = PurePosixPath(name)
                    require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe member path')
                    if not name.startswith(('opt/cachexia-mice/', 'opt/cachexia-survey/', 'opt/cachexia-lcmm/')):
                        continue
                    require(not relative.name.startswith('.wh.'), 'Payload whiteout needs explicit review')
                    if member.isdir():
                        continue
                    require(member.isfile() and member.size <= 64 * 1024**2, 'Unexpected payload kind or size')
                    require(name not in observed, 'Duplicate payload overwrite needs explicit review')
                    payload = archive.extractfile(member)
                    digest = hashlib.file_digest(payload, 'sha256').hexdigest()
                    observed[name] = dict(sha256=digest, bytes=member.size)
                    if name not in expected_members:
                        additional.append(dict(path=name, **observed[name]))
    missing = sorted(set(expected_members) - observed.keys())
    mismatches = sorted(name for name in expected_members.keys() & observed.keys()
                        if expected_members[name] != observed[name]['sha256'])
    report = dict(schema='CONDITIONAL_SOURCE_PAYLOAD_IDENTITY_V1',
        image=IMAGE, parent_recovery_worker_exit_status=1, parent_failure_not_reclassified=True,
        locked_payloads=len(expected_members), source_archives=24, debian_archives=8,
        observed_payloads=observed, missing=missing, mismatches=mismatches,
        additional_payloads_pending_content_review=additional,
        source_payloads_match=not missing and not mismatches,
        source_bytes_extracted_to_host=False, new_method_executions=0, new_images_pushed=False,
        complete_secret_absence_certified=False, publication_authorized=False,
        scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    require(not missing and not mismatches, 'Locked source payload mismatch; preserve report')
    print(json.dumps(dict(locked_payloads=len(expected_members), source_payloads_match=True,
        additional_payloads_pending_review=len(additional), new_method_executions=0)), flush=True)


if __name__ == '__main__':
    main()
