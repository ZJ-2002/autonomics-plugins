import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tomllib


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
FAMILIES = ['cachexia-lcmm', 'cachexia-survey', 'cachexia-mice']
LIMIT = 8 * 1024**3


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_sha(filename):
    with filename.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class HashedStream:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size=-1):
        require(size >= 0, 'Bounded streaming reads required')
        payload = self.stream.read(size)
        self.size += len(payload)
        require(self.size <= 20 * 1024**3, 'Uncompressed layer exceeds reviewed bound')
        self.digest.update(payload)
        return payload


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'conditional-image-layer-audit'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    primary = profile['primary']
    prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--storage-opt',
        'additionalimagestore=' + profile['additional']['path'], '--root', primary['graphroot'],
        '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
        '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
    reviewed_layers = {}
    images = []
    for family in FAMILIES:
        manifest_path = ROOT / 'research-adapters' / family / 'manifest.toml'
        source = manifest_path.read_bytes()
        manifest = tomllib.loads(source.decode())
        image = manifest['image']['reference']
        require(image in profile['images'], 'Exact prequalified image required; no implicit image enrollment')
        inspect = subprocess.run([*prefix, 'image', 'inspect', image], capture_output=True, timeout=60)
        require(inspect.returncode == 0, 'Exact local image unavailable')
        inspected = json.loads(inspect.stdout)
        require(len(inspected) == 1 and inspected[0]['Size'] <= LIMIT, 'Image count or size exceeds audit budget')
        config_id = inspected[0]['Id'].removeprefix('sha256:')
        require(re.fullmatch(r'[0-9a-f]{64}', config_id) is not None, 'Exact local config identity required')
        directory = Path(os.environ['TMPDIR']) / family
        saved = subprocess.run([*prefix, 'save', '--format', 'oci-dir', '--output', str(directory), image],
                               capture_output=True, timeout=600)
        require(saved.returncode == 0, 'OCI export failed; no layer contents qualified')
        index = json.loads((directory / 'index.json').read_text())
        require(len(index['manifests']) == 1, 'Exactly one exported manifest required')

        def blob(descriptor):
            digest = descriptor['digest']
            require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None, 'Unsupported blob digest')
            filename = directory / 'blobs/sha256' / digest.split(':')[1]
            require(filename.is_file() and not filename.is_symlink() and filename.stat().st_size == descriptor['size']
                    and file_sha(filename) == digest.split(':')[1], 'Exported OCI blob identity differs')
            return filename

        manifest = json.loads(blob(index['manifests'][0]).read_text())
        require(manifest['config']['digest'] == 'sha256:' + config_id, 'Export changed actual image config')
        configuration = json.loads(blob(manifest['config']).read_text())
        diffs = configuration['rootfs']['diff_ids']
        require(len(diffs) == len(manifest['layers']), 'Complete layer/diff-ID axis required')
        environment = configuration.get('config', {}).get('Env', [])
        names = [assignment.split('=', 1)[0] for assignment in environment]
        credential_names = [name for name in names if re.search(r'(TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY)', name, re.I)]
        history = configuration.get('history', [])
        suspicious_history = sum(bool(re.search(r'(gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|--password[=\s])',
                                    entry.get('created_by', ''), re.I)) for entry in history)
        layers = []
        for descriptor, expected_diff in zip(manifest['layers'], diffs, strict=True):
            filename = blob(descriptor)
            identity = descriptor['digest']
            if identity in reviewed_layers:
                require(reviewed_layers[identity]['diff_id'] == expected_diff, 'Shared layer identity differs')
                layers.append(dict(reviewed_layers[identity], shared_review_reused=True))
                continue
            entries = 0
            sensitive = []
            candidates = []
            with filename.open('rb') as raw:
                magic = raw.read(2)
                raw.seek(0)
                require(magic == b'\x1f\x8b' or not descriptor['mediaType'].endswith(('+zstd', '+gzip')),
                        'Unsupported declared compression')
                decoded = gzip.GzipFile(fileobj=raw) if magic == b'\x1f\x8b' else raw
                stream = HashedStream(decoded)
                with tarfile.open(fileobj=stream, mode='r|') as archive:
                    for entry in archive:
                        entries += 1
                        require(entries <= 2000000, 'Layer entry count exceeds audit budget')
                        name = entry.name.removeprefix('./')
                        relative = PurePosixPath(name)
                        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe image-layer member path')
                        if entry.isfile():
                            if relative.name in {'.env', '.netrc', 'auth.json', 'id_rsa', 'id_ed25519'} or '.aws/credentials' in name:
                                require(len(sensitive) < 100, 'Too many sensitive-path candidates')
                                sensitive.append(name)
                            if relative.suffix.lower() in {'.tsv', '.csv', '.h5ad', '.rds', '.parquet'} and not name.startswith(('usr/', 'lib/', 'opt/')):
                                require(len(candidates) < 1000, 'Too many potential non-package payload paths')
                                candidates.append(name)
                while stream.read(1024**2):
                    pass
                require('sha256:' + stream.digest.hexdigest() == expected_diff, 'Complete uncompressed layer identity differs')
            record = dict(blob_digest=identity, diff_id=expected_diff, entries=entries,
                uncompressed_bytes=stream.size, sensitive_path_candidates=sensitive,
                non_package_payload_path_candidates=candidates)
            reviewed_layers[identity] = record
            layers.append(dict(record, shared_review_reused=False))
        dockerfile = ROOT / 'research-adapters' / family / 'Dockerfile'
        images.append(dict(family=family, image=image, config_id=config_id,
            source_manifest_sha256=hashlib.sha256(source).hexdigest(), layers=layers,
            environment_variable_names=names, credential_named_environment_variables=credential_names,
            suspicious_history_entries=suspicious_history, history_entries=len(history),
            canonical_Dockerfile_present=dockerfile.is_file(),
            canonical_Dockerfile_sha256=file_sha(dockerfile) if dockerfile.is_file() else None,
            source_manifest_unchanged=manifest_path.read_bytes() == source))
        require(manifest_path.read_bytes() == source, 'Method manifest changed during image inspection')
        (output / 'image-audit-progress.json').write_text(json.dumps(images, indent=2) + '\n')
        shutil.rmtree(directory)
    report = dict(schema='CONDITIONAL_OFFICIAL_IMAGE_LAYER_AUDIT_V1', images=images,
        exact_images_streamed=3, unique_layers_verified=len(reviewed_layers),
        layer_metadata_entries=sum(item['entries'] for item in reviewed_layers.values()),
        full_uncompressed_diff_ids_verified=True, raw_layers_retained=False,
        nested_package_archives_content_certified=False, complete_secret_absence_certified=False,
        publication_authorized=False, registry_push_performed=False, new_method_executions=0,
        new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(images=3, unique_layers_verified=len(reviewed_layers),
        publication_authorized=False, new_method_executions=0, g0_granted=False)), flush=True)


if __name__ == '__main__':
    main()
