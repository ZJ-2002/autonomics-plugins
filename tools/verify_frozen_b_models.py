"""Managed 25-gene SYN parity for all three frozen B models in the existing image."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'localhost/autonomics/frozen-b-normalized@sha256:723904dd46c9148d75716555e2f641604d98c22909bc333d5fac832f33ebffed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-code', type=Path, required=True)
    parser.add_argument('--runtime-owner', type=Path, required=True)
    args = parser.parse_args()
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    if "'--tmpdir'" not in shim.read_text():
        raise ValueError('qualified managed tmpdir source capsule required')
    owner_path = args.runtime_owner.resolve(strict=True)
    owner = json.loads(owner_path.read_bytes())
    storage = owner_path.parent
    backend = ['--root', str(storage / 'storage'), '--runroot', str(storage / 'run'),
               '--tmpdir', str(storage / 'run/libpod-tmp'), '--storage-driver', 'overlay']
    if owner['runtime_backend'] != backend or not owner['all_three_software_images_exactly_installed']:
        raise ValueError('existing exact installed private-overlay backend required')
    item = next(row for row in owner['installed'] if row['label'] == 'B')
    if item['reference'] != REFERENCE:
        raise ValueError('the reviewed normalized limma image must be reused')
    source_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True):
        raise ValueError('committed immutable plugin source required')
    evidence = permanent / 'frozen-b-three-models'
    evidence.mkdir()
    inspected = subprocess.run(['podman', *backend, 'image', 'inspect', REFERENCE], capture_output=True, text=True, check=True)
    (evidence / 'image-inspect.json').write_text(inspected.stdout)
    image = json.loads(inspected.stdout)[0]
    if (image['Digest'] != item['installed_manifest_sha256'] or
            'sha256:' + image['Id'].removeprefix('sha256:') != item['image_config_digest'] or
            image['RootFS']['Layers'] != item['ordered_diff_ids']):
        raise ValueError('actual runtime image/config/layer identity differs')
    toy_path = ROOT / 'plugins/bulk-limma-normalized/tests/run_method_toy.py'
    spec = importlib.util.spec_from_file_location('three_model_toy', toy_path)
    toy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(toy)
    original_run = subprocess.run
    calls = []
    with tempfile.TemporaryDirectory(prefix='frozen-b-three-models-', dir=os.environ['TMPDIR']) as scratch:
        case = Path(scratch) / 'case'
        def translated(value):
            value = str(value)
            for host, mounted in [(case, '/case'), (ROOT, '/source')]:
                if value == str(host) or value.startswith(str(host) + '/'):
                    return mounted + value[len(str(host)):]
            return value
        def execute_r(arguments, **options):
            if arguments[:1] != ['Rscript']:
                raise ValueError('toy subprocess must be the exact R component')
            argv = arguments[1:]
            if argv[:1] == ['--vanilla']:
                argv = argv[1:]  # The verified launcher itself enforces --vanilla.
            ports = options.get('env', {})
            command = ['podman', *backend, 'run', '--rm', '--pull=never', '--network=none', '--read-only',
                       '--security-opt=no-new-privileges', '--cpus=1', '--memory=1g', '--pids-limit=64',
                       '--volume=' + str(case) + ':/case:rw', '--volume=' + str(ROOT) + ':/source:ro']
            for key, value in sorted(ports.items()):
                if re.fullmatch(r'AUTONOMICS_(INPUT|OUTPUT)[0-9]+', key):
                    command.append('--env=' + key + '=' + translated(value))
            command.extend(['--entrypoint=/opt/b-bulk/bin/Rscript-vanilla', REFERENCE, *map(translated, argv)])
            options = {key: value for key, value in options.items() if key != 'env'}
            number = len(calls)
            (evidence / f'call-{number:02d}.command.json').write_text(json.dumps(command, indent=2) + '\n')
            checked = options.pop('check', False)
            options.setdefault('timeout', 180)
            result = original_run(command, **options)
            (evidence / f'call-{number:02d}.stdout.txt').write_text(result.stdout or '')
            (evidence / f'call-{number:02d}.stderr.txt').write_text(result.stderr or '')
            calls.append(dict(number=number, returncode=result.returncode))
            if checked:
                result.check_returncode()
            return result
        subprocess.run = execute_r
        try:
            toy.run(Path('/opt/b-bulk-library'), case, args.frozen_code.resolve(strict=True), execution_scope='OCI')
        finally:
            subprocess.run = original_run
        shutil.copytree(case, evidence / 'method')
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True) or subprocess.check_output(
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip() != source_commit:
        raise ValueError('plugin source changed during the bounded toy')
    (evidence / 'EXECUTION.json').write_text(json.dumps(dict(source_commit=source_commit,
        scope='ONLY_25_SYN_GENES_8_SYN_UNITS_THREE_FROZEN_MODELS', backend=backend, image_reference=REFERENCE,
        image_config_digest=item['image_config_digest'], calls=calls,
        helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        managed_shim_sha256=hashlib.sha256(shim.read_bytes()).hexdigest(),
        container_stoppage_verification_pending_session_reconcile=True,
        real_gse_data_read_or_fitted=False, scientific_authorization=False, G0=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
