"""Bounded direct official AnnData regression, not manifest-resource or DAG certification."""

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/single-cell'
PROC_CGROUP = Path('/proc/self/cgroup')
CGROUP_ROOT = Path('/sys/fs/cgroup')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
HISTORICAL = Path('/home/zj-normal/Work/autonomics/results/cachexia-v4.3.2/canonical-h5ad-subset-agent-v1-20261012')
HISTORICAL_SEAL = '9e17a8b25ffe4ac0952206fe5ce2747b480109953a38d98c9dae8ebdb9f0abd4'
PAYLOAD_LOCK_SHA = 'c751f28b2aa87f03ce6de0d1094cd59a08bbbe2cf145065b1d489049e2a53abe'
IMAGE = 'ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20'
IMAGE_SHA = IMAGE.split('@sha256:', 1)[1]
ALTERNATE_MANIFEST_SHA = 'ffc10f7a1412663224da5a50504687c1f36730c45d344fa3140f4150f393addd'
CONFIG_SHA = '3144c037c6da31b27ea8d240e4bf013c45258099f44242193946d209ab24dc7b'
SOURCES = {
    'manifest.toml': '5288e9c7ac552f318b93c67f107fd45dcddf12d9396c38e00e6950e3bede9c42',
    'scripts/subset_by_obs.py': '4d1afc22f291ab80b92033308319306db30b1a779ef873466920e6040fa87b5b',
    'tests/test_subset_by_obs.py': 'fca602d463d59b30f8a84acd2a2260a881009fc1caafd03b5ac211d83e26e0c7',
    'tests/qc_compare.py': '2c4a19aad9daaac942f04b9a95b18351e53ab979a49a9df477245e958bb36ac6',
    'test_subset_assurance.sh': '43281195f4fbdd87b2b2d163943fcc6b8089abd9ab38d736205be0e8711a6f86',
}
VERSIONS = dict(anndata='0.11.4', numpy='2.1.3', scipy='1.14.1', pandas='2.2.3', h5py='3.16.0', pyarrow='25.0.1')
PAYLOAD_COUNTS = dict(anndata=46, numpy=941, scipy=1384, pandas=1504, h5py=93, pyarrow=748)
BASELINE_REVISION = '7c9a8b4529a57d03e7b02840d05d055e3b2896ff'
BASELINE_SOURCES = {
    'qc_compare.py': 'd2d30324793dc33b5e438be8269a8fe7f9021d54d637a88d3aa3dd8f78d1b109',
    'test_subset_by_obs.py': 'c88766868a9c747ac1dd8b3308956603923dde877023af20e48a1a0e24cdcf81',
}
POSITIVES = {'dense', 'csr', 'csc', 'group-many-to-one', 'all-cells', 'lexical-numeric', 'single-cell',
    'prior-params', 'no-raw', 'no-X', 'nonfinite-X'}
BOUNDARIES = {'unknown', 'unknown-partial', 'unknown-group', 'duplicate-request', 'duplicate-group', 'empty-request',
    'null-request', 'integer-request', 'empty-string', 'tab-request', 'numeric-group', 'absent-column', 'duplicate-obs',
    'duplicate-var', 'missing-group', 'zero-cells', 'zero-genes', 'missing-selection-column', 'corrupt-selection',
    'existing-h5ad', 'existing-report', 'aliased-outputs', 'input-overwrite', 'ordinary-second-link-failure'}
MUTANTS = {
    name: dict(comparison_scope='WHOLE_CURRENT_FIXTURE_AND_REPORT', old_accepted=False)
    for name in ['wrong-X', 'missing-raw', 'reordered-cells', 'missing-obsp', 'raw-varm']
}
MUTANTS.update({
    name: dict(comparison_scope='WHOLE_CURRENT_FIXTURE_AND_REPORT', old_accepted=True)
    for name in ['missing-unselected-ledger', 'wrong-output-bytes', 'extra-output-port',
        'false-donor-eligibility', 'nonfinite-report']
})
MUTANTS.update({
    name: dict(comparison_scope='SHARED_COMPARE_VALUE_ONLY', old_accepted=True)
    for name in ['shared-scalar-broadcast', 'shared-sparse-shape']
})
CENSUS = '''import hashlib,importlib,importlib.metadata,json,stat,sys
from pathlib import Path,PurePosixPath
lock=json.loads(Path('/source/installed-payload-lock.json').read_text())
root=Path('/usr/local/lib/python3.11/site-packages')
observed=[]
assert sys.implementation.name=='cpython' and sys.version_info[:3]==(3,11,11)
for package in lock['records']:
    assert importlib.metadata.version(package['package'])==package['version']
    imported=importlib.import_module(package['package'])
    package_root=(root/package['package']).resolve()
    module_file=Path(imported.__file__).resolve()
    assert package_root.is_relative_to(root.resolve()) and module_file.is_relative_to(package_root)
    assert module_file.relative_to(root).as_posix() in {item['path'] for item in package['files']}
    files=[]
    for item in package['files']:
        relative=PurePosixPath(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        path=root.joinpath(*relative.parts)
        before=path.lstat()
        assert stat.S_ISREG(before.st_mode) and path.resolve().is_relative_to(root.resolve()) and before.st_size==item['bytes']
        with path.open('rb') as handle: actual=hashlib.file_digest(handle,'sha256').hexdigest()
        after=path.lstat()
        assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        assert actual==item['sha256'],item['path']
        files.append(dict(path=item['path'],bytes=after.st_size,sha256=actual))
    observed.append(dict(package=package['package'],version=package['version'],files=files,
        imported_module_file=str(module_file),rehash_package_root=str(package_root),import_resolves_to_rehashed_payload=True))
Path('/proof/package-census.json').write_text(json.dumps(dict(records=observed,files=sum(len(item['files']) for item in observed),
    Python=sys.version,Python_version=list(sys.version_info[:3]),implementation=sys.implementation.name,
    inherited_primary_origin_not_new_installation=True,whole_environment_certified=False,full_ABI_certified=False,g0_granted=False),indent=2)+'\\n')
'''
BOUNDARIES_AND_MUTANTS = '''import subprocess,sys
subprocess.run([sys.executable,'/source/tests/test_subset_by_obs.py','/proof/boundary','boundary'],check=True)
subprocess.run([sys.executable,'/source/tests/test_subset_by_obs.py','/proof/mutants','mutants'],check=True)
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON constant: ' + value)))


def validate_summaries(positives, boundaries, mutants):
    for summary, mode, cases in [(positives, 'positive', POSITIVES), (boundaries, 'boundary', BOUNDARIES),
            (mutants, 'mutants', set(MUTANTS))]:
        require(isinstance(summary, dict) and summary.get('mode') == mode and
            type(summary.get('cases')) is int and summary['cases'] == len(cases) and
            isinstance(summary.get('records'), list) and len(summary['records']) == len(cases) and
            all(isinstance(item, dict) and isinstance(item.get('case'), str) for item in summary['records']) and
            {item['case'] for item in summary['records']} == cases,
            'Complete unique frozen ' + mode + ' inventory required')
        require(summary.get('whole_current_engine') is False and summary.get('resident_daemon') is False and
            summary.get('G0') is False, 'Summary must not grant whole-engine, deployment or scientific authority')
    for record in positives['records']:
        require(type(record.get('whole_container_checks')) is int and record['whole_container_checks'] > 0 and
            type(record.get('hdf5_datasets_checked')) is int and record['hdf5_datasets_checked'] > 0 and
            type(record.get('complete_cell_ledger_rows_checked')) is int and record['complete_cell_ledger_rows_checked'] == 6 and
            record.get('full_report_checked') is True and record.get('G0') is False,
            'Every positive must compare its complete container, HDF5 objects and full report')
    for record in boundaries['records']:
        if record['case'] == 'ordinary-second-link-failure':
            require(record.get('ordinary_rollback') is True and record.get('crash_atomicity_claimed') is False,
                'Controlled rollback must not become a crash-atomic claim')
        else:
            require(type(record.get('exit')) is int and record['exit'] == (3 if record['case'] == 'corrupt-selection' else 2) and
                isinstance(record.get('specific_refusal'), str) and bool(record['specific_refusal']),
                'Boundary failure must match its original error contract, not OOM or launch failure')
    for record in mutants['records']:
        expected = MUTANTS[record['case']]
        previous = record.get('old_comparison')
        current = record.get('current_comparison')
        require(isinstance(previous, dict) and isinstance(current, dict) and
            record.get('comparison_scope') == expected['comparison_scope'] and
            previous.get('accepted') is expected['old_accepted'] and current.get('accepted') is False and
            current.get('refusal_type') in {'AssertionError', 'ValueError'} and
            isinstance(current.get('diagnostic'), str) and record.get('G0') is False,
            'Actual old/new comparison result differs from the frozen typed negative control')
        require((previous.get('refusal_type') is None and previous.get('diagnostic') is None) if expected['old_accepted']
            else (previous.get('refusal_type') in {'AssertionError', 'ValueError'} and isinstance(previous.get('diagnostic'), str)),
            'Old comparison observation must record its actual acceptance or refusal')
        if expected['comparison_scope'] == 'SHARED_COMPARE_VALUE_ONLY':
            require(record.get('old_whole_object_comparison_executed') is False,
                'Shared-helper shape control is not an old whole-HDF5 acceptance claim')
        else:
            require(record.get('baseline_source_sha256') == BASELINE_SOURCES, 'Actual old whole-object comparator identity differs')
    return dict(positive_cases=len(POSITIVES), boundary_cases=len(BOUNDARIES), comparator_controls=len(MUTANTS))


def fact(path):
    require(path.resolve(strict=True) == path and not any(parent.is_symlink() for parent in [path, *path.parents]),
        'Unaliased regular file required')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'Ordinary file required')
    with path.open('rb') as handle:
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_mtime_ns, before.st_ctime_ns) ==
        (after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_mtime_ns, after.st_ctime_ns), 'Source changed while reading')
    return dict(bytes=before.st_size, sha256=checksum, device=before.st_dev, inode=before.st_ino,
        mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def payload_lock():
    seal = HISTORICAL / 'ROOT_REVIEW_SEALED_FILES.json'
    require(fact(seal)['sha256'] == HISTORICAL_SEAL, 'Exact historical source-evidence seal required')
    entries = strict_json(seal.read_text())['files']
    matches = [entry for entry in entries if entry['path'] == 'INHERITED_AUTHOR_PAYLOADS.json']
    require(len(matches) == 1, 'One sealed author payload record required')
    source = HISTORICAL / matches[0]['path']
    identity = fact(source)
    require(identity['sha256'] == matches[0]['sha256'] == PAYLOAD_LOCK_SHA and
        identity['bytes'] == matches[0]['size'] == 910879, 'Sealed author payload record differs')
    value = strict_json(source.read_text())
    require(len(value['records']) == 6 and {item['package']: item['version'] for item in value['records']} == VERSIONS,
        'Exact six official inherited package versions required')
    names = set()
    for package in value['records']:
        require(len(package['files']) == package['files_exact'] == PAYLOAD_COUNTS[package['package']], 'Full package payload count differs')
        for item in package['files']:
            name = item['path']
            require(isinstance(name, str) and name and not PurePosixPath(name).is_absolute() and '\\' not in name and
                all(part not in {'', '.', '..'} for part in name.split('/')) and name not in names and
                type(item['bytes']) is int and item['bytes'] >= 0 and re.fullmatch('[0-9a-f]{64}', item['sha256']),
                'Unique bounded lexical official payload identity required')
            names.add(name)
    require(len(names) == 4716, 'Complete 4716-file primary package payload inventory required')
    return value, dict(seal_sha256=HISTORICAL_SEAL, entry_sha256=PAYLOAD_LOCK_SHA, files=4716,
        versions=VERSIONS, source_record_identity=identity, fresh_download_or_installation=False)


def cgroup_observation():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session = permanent.parent.name
    require(permanent.is_absolute() and permanent.name == 'permanent' and re.fullmatch('[0-9a-f]{32}', session),
        'Exact managed permanent/session path required')
    record_path = ARCHIVES / session / 'SESSION.json'
    fact(record_path)
    record = strict_json(record_path.read_text())
    unit = 'autonomics-validation-' + session + '.service'
    require(record.get('schema') == 'TECHNICAL_VALIDATION_SESSION_V1' and record.get('session') == session and
        record.get('unit') == unit and record.get('workspace') == str(permanent.parent) and record.get('profile') == 'light',
        'Exact recorded light service ownership required')
    cgroup = PROC_CGROUP.read_text()
    paths = [line.split(':', 2)[2] for line in cgroup.splitlines() if line.startswith('0::')]
    suffix = '/' + unit + '/worker-native'
    require(len(paths) == 1 and paths[0].startswith('/') and paths[0].endswith(suffix) and
        not any(part in {'.', '..'} for part in paths[0].split('/')),
        'Current process must belong to its exact recorded delegated worker subgroup')
    leaf = CGROUP_ROOT / paths[0].lstrip('/')
    service = CGROUP_ROOT / paths[0].removesuffix('/worker-native').lstrip('/')
    require(leaf.is_dir() and service.is_dir() and (service / 'memory.max').read_text().strip() == '2147483648',
        'Exact recorded service cgroup must enforce two GiB')
    observation = dict(path=str(service), worker_leaf_path=str(leaf), recorded_unit=unit, session=session,
        session_record_sha256=fact(record_path)['sha256'], memory_max_bytes=2147483648,
        memory_current_bytes=int((service / 'memory.current').read_text()), memory_peak_bytes=int((service / 'memory.peak').read_text()),
        memory_events=(service / 'memory.events').read_text(), worker_leaf_controller_observations={
            name: (leaf / name).read_text() if (leaf / name).is_file() else None
            for name in ['memory.max', 'memory.current', 'memory.peak', 'memory.events']})
    require(PROC_CGROUP.read_text() == cgroup, 'Worker cgroup changed during resource observation')
    return observation


def inspect(prefix, output, label):
    run = subprocess.run([*prefix, 'image', 'inspect', IMAGE], capture_output=True, text=True, timeout=60)
    (output / (label + '-inspect.stdout.json')).write_text(run.stdout)
    (output / (label + '-inspect.stderr')).write_text(run.stderr)
    require(run.returncode == 0, 'Already installed default-backend image unavailable; no pull fallback')
    records = strict_json(run.stdout)
    require(len(records) == 1, 'One actual installed image required')
    actual = records[0]
    store = Path.home() / '.local/share/containers/storage/overlay-images' / CONFIG_SHA
    encoded = lambda name: '=' + base64.b64encode(name.encode()).decode()
    manifest_path = store / encoded('manifest-sha256:' + IMAGE_SHA)
    config_path = store / encoded('sha256:' + CONFIG_SHA)
    manifest = manifest_path.read_bytes()
    configuration = config_path.read_bytes()
    require(hashlib.sha256(manifest).hexdigest() == IMAGE_SHA and hashlib.sha256(configuration).hexdigest() == CONFIG_SHA and
        fact(manifest_path)['sha256'] == IMAGE_SHA and fact(config_path)['sha256'] == CONFIG_SHA,
        'Actual cached original manifest and image configuration bytes differ')
    parsed = strict_json(manifest)
    config = strict_json(configuration)
    require(parsed['config']['digest'] == 'sha256:' + CONFIG_SHA and config['architecture'] == 'amd64' and
        actual['Id'].removeprefix('sha256:') == CONFIG_SHA and actual['RootFS']['Layers'] == config['rootfs']['diff_ids'] and
        actual['Digest'] in {'sha256:' + IMAGE_SHA, 'sha256:' + ALTERNATE_MANIFEST_SHA}, 'Actual image/configuration/layers differ')
    if actual['Digest'] == 'sha256:' + ALTERNATE_MANIFEST_SHA:
        alternate = store / encoded('manifest-sha256:' + ALTERNATE_MANIFEST_SHA)
        alternate_manifest = alternate.read_bytes()
        require(hashlib.sha256(alternate_manifest).hexdigest() == ALTERNATE_MANIFEST_SHA and
            fact(alternate)['sha256'] == ALTERNATE_MANIFEST_SHA and
            strict_json(alternate_manifest)['config']['digest'] == 'sha256:' + CONFIG_SHA,
            'Alternate stored manifest must actually bind the identical configuration')
        (output / (label + '-alternate-manifest.json')).write_bytes(alternate_manifest)
    (output / (label + '-requested-manifest.json')).write_bytes(manifest)
    (output / (label + '-image-configuration.json')).write_bytes(configuration)
    return dict(requested_reference=IMAGE, requested_manifest_sha256=IMAGE_SHA, config_sha256=CONFIG_SHA,
        installed_primary_manifest_digest=actual['Digest'], ordered_diff_ids=config['rootfs']['diff_ids'],
        default_backend=True, private_AB_backend_used=False, image_name_alone_not_identity=True)


def default_backend(prefix, output):
    run = subprocess.run([*prefix, 'info', '--format', 'json'], capture_output=True, text=True, timeout=60)
    (output / 'default-backend.stdout.json').write_text(run.stdout)
    (output / 'default-backend.stderr').write_text(run.stderr)
    require(run.returncode == 0, 'Actual default runtime backend unavailable')
    value = strict_json(run.stdout)
    graph = Path(value['store']['graphRoot'])
    runtime = Path(value['store']['runRoot'])
    expected = Path.home() / '.local/share/containers/storage'
    expected_runtime = Path('/run/user') / str(os.getuid()) / 'containers'
    require(graph == expected and graph.resolve() == graph and value['store']['graphDriverName'] == 'overlay' and
        value['host']['cgroupManager'] == 'cgroupfs' and stat.S_ISDIR(graph.lstat().st_mode) and
        graph.stat().st_uid == os.getuid() and runtime == expected_runtime and runtime.resolve() == runtime and
        stat.S_ISDIR(runtime.lstat().st_mode) and runtime.stat().st_uid == os.getuid(),
        'Actual rootless default overlay backend must not be the private A/B store')
    return dict(graph_root=str(graph), graph_root_device=graph.stat().st_dev, graph_root_inode=graph.stat().st_ino,
        graph_root_uid=graph.stat().st_uid, run_root=str(runtime), run_root_device=runtime.stat().st_dev,
        run_root_inode=runtime.stat().st_ino, run_root_uid=runtime.stat().st_uid, cgroup_manager='cgroupfs',
        private_AB_backend_used=False)


def container(prefix, source, output, label, arguments):
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
        '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=128m', '-e', 'PYTHONDONTWRITEBYTECODE=1',
        '-v', str(source) + ':/source:ro', '-v', str(output) + ':/proof:rw', '--entrypoint=python', IMAGE, *arguments]
    write(output / (label + '-command.json'), command)
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    (output / (label + '.stdout')).write_text(result.stdout)
    (output / (label + '.stderr')).write_text(result.stderr)
    write(output / (label + '-execution.json'), dict(actual_exit=result.returncode, image=IMAGE,
        container_cpus=1, container_memory_bytes=1024**3, parent_memory_max_bytes=2 * 1024**3,
        no_build=True, no_pull=True, no_network=True, scientific_release=False))
    require(type(result.returncode) is int and result.returncode == 0, 'Actual bounded direct container failed: ' + label)


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed light session required')
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) for value in SOURCES.values()),
        'Final complete official comparison source has not been frozen')
    require(isinstance(MUTANTS, dict) and len(MUTANTS) == 12, 'Final typed mutant inventory has not been frozen')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'h5ad-subset-official-runtime'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    initial_cgroup = cgroup_observation()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3, 'Tiny bounded task plus system reserve unavailable')
    write(output / 'resource-admission.json', dict(parent=initial_cgroup, available_memory_bytes=available,
        container_limit_bytes=1024**3, parent_limit_bytes=2 * 1024**3, competing_builds_not_stopped=True))
    before = {name: fact(FAMILY / name) for name in SOURCES}
    require(all(before[name]['sha256'] == expected for name, expected in SOURCES.items()), 'Actual reviewed source differs')
    source = output / 'source'
    source.mkdir()
    for name in SOURCES:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FAMILY / name, destination)
        require(fact(destination)['sha256'] == SOURCES[name], 'Small source snapshot differs')
    baseline = source / 'baseline-tests'
    baseline.mkdir()
    for name, expected in BASELINE_SOURCES.items():
        payload = subprocess.check_output(['git', '-C', str(ROOT), 'show',
            BASELINE_REVISION + ':plugins/single-cell/tests/' + name])
        require(hashlib.sha256(payload).hexdigest() == expected, 'Fixed published old comparator differs')
        (baseline / name).write_bytes(payload)
    lock, origin = payload_lock()
    write(source / 'installed-payload-lock.json', lock)
    (source / 'package-census.py').write_text(CENSUS)
    (source / 'boundaries-and-mutants.py').write_text(BOUNDARIES_AND_MUTANTS)
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    fact(shim)
    prefix = [str(shim), '--cgroup-manager=cgroupfs']
    backend = default_backend(prefix, output)
    image_before = inspect(prefix, output, 'before')
    container(prefix, source, output, 'package-census', ['/source/package-census.py'])
    census = strict_json((output / 'package-census.json').read_text())
    expected = {item['package']: (item['version'], item['files']) for item in lock['records']}
    actual = {item['package']: (item['version'], item['files']) for item in census['records']}
    require(census['files'] == 4716 and actual == expected and census['Python_version'] == [3, 11, 11] and
        census['implementation'] == 'cpython' and all(item['import_resolves_to_rehashed_payload'] is True for item in census['records']),
        'Current installed full official payload and actual imported runtime comparison failed')
    container(prefix, source, output, 'positive', ['/source/tests/test_subset_by_obs.py', '/proof/positive', 'positive'])
    container(prefix, source, output, 'boundary-and-mutants', ['/source/boundaries-and-mutants.py'])
    positives = strict_json((output / 'positive/SUMMARY.json').read_text())
    boundaries = strict_json((output / 'boundary/SUMMARY.json').read_text())
    mutants = strict_json((output / 'mutants/SUMMARY.json').read_text())
    validate_summaries(positives, boundaries, mutants)
    ports = []
    for record in positives['records']:
        case = output / 'positive' / record['case']
        execution = strict_json((case / 'execution.json').read_text())
        require(type(execution['exit']) is int and execution['exit'] == 0 and execution['script'] == '/source/scripts/subset_by_obs.py',
            'Actual fixed wrapper must execute, not a substitute baked runner')
        for filename in ['output.h5ad', 'report.json', 'fresh-author.h5ad', 'input.h5ad', 'selection.parquet']:
            ports.append(dict(case=record['case'], path=filename, **fact(case / filename)))
    require(before == {name: fact(FAMILY / name) for name in SOURCES} and
        all(fact(source / name)['sha256'] == expected for name, expected in SOURCES.items()) and
        all(fact(baseline / name)['sha256'] == expected for name, expected in BASELINE_SOURCES.items()), 'Current/source-snapshot changed')
    require(image_before == inspect(prefix, output, 'after'), 'Runtime image identity changed')
    final_cgroup = cgroup_observation()
    write(output / 'verification.json', dict(scope='BOUNDED_DIRECT_OFFICIAL_ANNDATA_TINY_FIXTURES_NOT_DAG_OR_DEPLOYMENT',
        sources=before, runtime_backend=backend, image=image_before, official_payload_origin=origin, installed_payload_files=4716,
        old_comparator_source_revision=BASELINE_REVISION, old_comparator_source_sha256=BASELINE_SOURCES,
        positive_cases=len(POSITIVES), boundary_cases=len(BOUNDARIES), complete_positive_artifacts=ports,
        comparator_controls=mutants,
        original_full_case_inventory_preserved=True, inherited_primary_origin_not_new_installation=True,
        owned_container_intents_expected=3, stoppage='PENDING_OUTER_MANAGED_SESSION_FINALIZATION',
        initial_parent_cgroup=initial_cgroup, final_parent_cgroup=final_cgroup,
        manifest_eight_GiB_resource_certified=False, full_size_or_all_H5AD_encodings_certified=False,
        actual_DAG_executed=False, current_daemon_verified=False, production_restarted=False,
        scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
