"""Managed cached Python OCI acceptance using self-cleaning engineering inputs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'docker.io/library/python@sha256:a66d3a463d0be3cc537c269b0d3418746dda512417a975559a0eaa8a6406baaf'


def main():
    if not os.environ.get('AUTONOMICS_PODMAN_PROGRAM'):
        raise RuntimeError('latest managed python-script driver required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    def execute(command, name):
        result = subprocess.run(command, capture_output=True, text=True)
        (permanent / (name + '.stdout.txt')).write_text(result.stdout)
        (permanent / (name + '.stderr.txt')).write_text(result.stderr)
        result.check_returncode()
        return result.stdout
    info = json.loads(execute(['podman', 'image', 'inspect', IMAGE], 'python-image-inspection'))[0]
    raw = execute(['/usr/bin/skopeo', 'inspect', '--raw', 'containers-storage:' + IMAGE], 'python-exact-platform-manifest')
    if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != IMAGE.split('@')[1]:
        raise ValueError('actual Python platform manifest differs')
    manifest = json.loads(raw)
    if manifest['config']['digest'] != 'sha256:' + info['Id'].removeprefix('sha256:'):
        raise ValueError('actual Python platform config differs')
    run = ['podman', 'run', '--rm', '--pull=never', '--network=none',
           '--security-opt=no-new-privileges', '--cpus=1', '--memory=1g',
           '-e', 'PYTHONDONTWRITEBYTECODE=1', '--entrypoint=python3']
    runtime = json.loads(execute([*run, IMAGE, '-B', '-c',
        'import json,sys;assert sys.version_info>=(3,11);print(json.dumps(dict(version=sys.version,executable=sys.executable)))'],
        'python-actual-runtime'))
    execute([*run, '-v', str(ROOT) + ':' + str(ROOT) + ':ro',
             '--workdir', str(ROOT), IMAGE, '-B', '-m', 'unittest',
             'tests.test_frozen_b_project', 'tests.test_normalized_bulk_interface', '-v'], 'python-synthetic-method-tests')
    sources = [Path(__file__), ROOT / 'tests/test_frozen_b_project.py',
               ROOT / 'tests/test_normalized_bulk_interface.py',
               *sorted((ROOT / 'plugins/frozen-b-project/scripts').glob('*.py')),
               ROOT / 'plugins/frozen-b-project/project-lock.json']
    record = dict(scope='ENGINEERING_SYN_PYTHON_INTAKE_FAMILY_AND_INTERFACE_NOT_REAL_STUDY',
        actual_backend='HOST_DEFAULT_CACHED_OVERLAY_NOT_PRIVATE_DEPLOYMENT_STORE',
        image_reference=IMAGE, image_config_id=info['Id'], ordered_diff_ids=info['RootFS']['Layers'],
        actual_current_store_identity_verified=True, actual_python_runtime=runtime,
        actual_synthetic_tests_verified=True, tests_run=11, study_assay_read_or_fitted=False,
        actual_frozen_intake_executed=False, scientific_authorization=False, G0=False,
        source_files={str(p.relative_to(ROOT)): dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
                      for p in sources})
    (permanent / 'PYTHON_ENVIRONMENT_RESULT.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
