"""Replay sealed tiny AnnData cases on a pinned SDK, not the resident daemon."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_h5ad_subset_official_runtime import (
    ARCHIVES, IMAGE, POSITIVES, SOURCES, cgroup_observation, default_backend,
    fact, inspect, require, strict_json, write,
)
from tools.reconcile_ab_evidence_index import verify_archive

REVISION = 'abeea973fdb9ac9bfe8d9f00ec21a3f365613953'
BUILD_SESSION = 'f7e02ba49c024ceca6b934b4a123f751'
BUILD_SEAL = '431dd1cdf0ea5c2ea66ce98621354b65ebdac356d03d081ee71045b0c81d4caf'
RUNNER_SHA = 'bbc1a387b508ba05c50e79eb95b3dc15f87cf274a6e2c3983bcd320246339481'
ENGINE = '4ceefbd821baab8deebb070645a2fb8b1fa8e1ba'
PROBE_SHA = 'e9c8fdcaa8d11a2460ebd8c142721c91bfd96116b2701d215fa4fd583034ea60'
REFERENCE_SESSION = '28def8d5e9514b05984323ba05c65346'
REFERENCE_SEAL = 'b59aa8111ce1164cb13a56e53b18fffc0ff7e9eda0aba3eabe90c655742ba88c'
FAILED_SESSION = '2251feccb2634ce2b342613a43222aea'
FAILED_SEAL = 'dd4da589d8d704caa9ec85c0d3c06d238a1b6ce223b5003181e0dfdea2e292d5'
PANEL = Path.home() / '.autonomics/panels/wjixiang/catalog-celltypist-models-pan-immune@sha256:a5260755be97513698812a5739763ecaddb75a68b261c95209fdd874e4bfc35c'
PANEL_SHA = '0f76b752e9ab9e08726d42a85b95e313b0df1584faeaa6f5a2b6377baa6474e5'
PANEL_DIGEST = 'sha256:a5260755be97513698812a5739763ecaddb75a68b261c95209fdd874e4bfc35c'
ALIAS = 'autonomics-technical/canonical-celltypist-byte-transport'
PANEL_PATH = '/synthetic-panels/celltypist-model'
DIRECT_ONLY = {'existing-h5ad', 'existing-report', 'aliased-outputs', 'input-overwrite', 'ordinary-second-link-failure'}
NEGATIVES = {
    'unknown': 'unknown identifiers', 'unknown-partial': 'unknown identifiers', 'unknown-group': 'unknown identifiers',
    'duplicate-request': 'unique identifiers', 'duplicate-group': 'unique identifiers',
    'empty-request': 'at least one', 'null-request': 'lexical strings', 'integer-request': 'lexical strings',
    'empty-string': 'lexical strings', 'tab-request': 'lexical strings', 'numeric-group': 'lexical strings',
    'absent-column': 'obs has no', 'duplicate-obs': 'unique identifiers', 'duplicate-var': 'unique identifiers',
    'missing-group': 'lexical strings', 'zero-cells': 'nonempty', 'zero-genes': 'nonempty',
    'missing-selection-column': 'selection Parquet has no', 'corrupt-selection': 'Parquet',
}
DEPENDENCIES = [
    'tools/prove_h5ad_subset_official_runtime.py', 'tools/reconcile_ab_evidence_index.py',
]
COMPARE = '''import json,sys
from pathlib import Path
sys.path.insert(0,'/source/tests')
from test_subset_by_obs import compare
root=Path('/proof')
records=[]
for name in json.loads((root/'positive-inventory.json').read_text()):
    records.append(dict(case=name,**compare(root/name)))
(root/'whole-object-comparison.json').write_text(json.dumps(dict(records=records,G0=False),indent=2)+'\\n')
'''


def digest(path):
    return fact(path)['sha256']


def export_source(output):
    manifest_bytes = subprocess.check_output(['git', '-C', str(ROOT), 'show', REVISION + ':plugins/single-cell/manifest.toml'])
    require(hashlib.sha256(manifest_bytes).hexdigest() == SOURCES['manifest.toml'], 'Pinned original manifest differs')
    manifest = tomllib.loads(manifest_bytes.decode())
    names = {'manifest.toml', 'tests/test_subset_by_obs.py', 'tests/qc_compare.py'}
    names.update(item['command']['script_file'] for item in manifest['nodes'])
    require(len(manifest['nodes']) == 10 and len(names) == 13, 'Exact ten original family scripts required')
    source = output / 'source'
    source.mkdir()
    identities = {}
    for name in sorted(names):
        payload = subprocess.check_output(['git', '-C', str(ROOT), 'show', REVISION + ':plugins/single-cell/' + name])
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        identities[name] = fact(destination)
        if name in SOURCES:
            require(identities[name]['sha256'] == SOURCES[name], 'Current published source differs from direct proof')
    require(manifest['image']['reference'] == IMAGE and len(manifest['panels']) == 1, 'Exact original runtime and panel required')
    definition = next(item for item in manifest['nodes'] if item['kind'] == 'h5ad_subset_by_obs')
    require(definition['resources'] == dict(cpus=2.0, memory='8Gi', pids_limit=512, shm_size='1Gi') and
        len(definition['ports']['inputs']) == 2 and len(definition['ports']['outputs']) == 2,
        'Original method ports and resource declaration must not be weakened')
    return source, manifest, definition, identities


def panel_facts():
    require(digest(PANEL / 'manifest.json') == PANEL_SHA, 'Original canonical panel manifest differs')
    manifest = strict_json((PANEL / 'manifest.json').read_text())
    require(manifest.get('digest') == PANEL_DIGEST and len(manifest['files']) == 4, 'Exact real model bundle required')
    result = {'manifest.json': fact(PANEL / 'manifest.json')}
    for item in manifest['files']:
        name = item['path']
        require(isinstance(name, str) and Path(name).name == name and name not in result, 'Unique direct panel member required')
        observed = fact(PANEL / name)
        require(observed['bytes'] == item['size'] and 'sha256:' + observed['sha256'] == item['sha256'], 'Real panel payload differs')
        result[name] = observed
    return result


def retire_transport_copy(directory, identity, owned):
    current = directory.lstat()
    require((current.st_dev, current.st_ino, current.st_mode) == identity and
        {item.name for item in directory.iterdir()} == set(owned), 'Transport directory identity or complete membership changed')
    require(all(fact(directory / name) == expected for name, expected in owned.items()), 'Transport member identity changed')
    for name, expected in owned.items():
        require(fact(directory / name) == expected, 'Transport file changed before retirement')
        (directory / name).unlink()
    directory.rmdir()


def job_for(work, source, manifest, identities, join_column):
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', run_root=str(work), expected_plugin_name='single-cell',
        plugin_manifest=str(source / 'manifest.toml'), plugin_manifest_sha256=SOURCES['manifest.toml'],
        script_sha256={item['command']['script_file']: identities[item['command']['script_file']]['sha256']
            for item in manifest['nodes']},
        additional_plugins=[], panel_overrides=[dict(binding='model',
            declared_bundle='wjixiang/catalog-celltypist-models-pan-immune', mount='/panels/celltypist_model', synthetic_bundle=ALIAS)],
        bundles=[dict(ident=ALIAS, desc='TECHNICAL TRANSPORT ALIAS; unchanged real canonical model bytes; models not loaded',
            vpath=PANEL_PATH, source=PANEL_PATH, digest=PANEL_DIGEST)], panel_manifest_sha256={PANEL_PATH: PANEL_SHA},
        nodes=[dict(id='input0', kind='file_reference', spec=dict(path='vfs:///input.h5ad', format='h5ad', hash_content=True)),
            dict(id='input1', kind='file_reference', spec=dict(path='vfs:///selection.parquet', format='parquet', hash_content=True)),
            dict(id='analysis', kind='h5ad_subset_by_obs', spec=dict(join_column=join_column))],
        edges=[{'from': 'input' + str(index), 'from_port': 0, 'to': 'analysis', 'to_port': index} for index in range(2)])


def validate_report(report, job, *, positive):
    require(report.get('scope') == 'TECHNICAL_PLUGIN_DAG_NOT_G0' and report.get('engine_source_revision') == ENGINE and
        report.get('plugin_name') == 'single-cell' and report.get('original_manifest_sha256') == SOURCES['manifest.toml'] and
        report.get('max_concurrency') == 1 and type(report.get('max_concurrency')) is int and
        report.get('incremental') is False and report.get('input_hashing') == 'ContentRequired' and
        report.get('additional_plugin_identities') == [] and report.get('native_statistical_factories_registered') is False and
        report.get('panel_bindings_are_explicit_synthetic_overrides') is True and report.get('actual_research_panels_qualified') is False and
        all(report.get(name) is False for name in ['current_daemon_verified', 'scientific_authorized', 'g0_granted']),
        'Actual SDK identity, transport scope or authority differs')
    first = report.get('first_run')
    require(isinstance(first, dict) and len(first.get('nodes', [])) == 3, 'Complete three-node actual report required')
    nodes = {node['id']: node for node in first['nodes']}
    require(set(nodes) == {'input0', 'input1', 'analysis'} and
        all(nodes[item['id']].get('node_type') == item['kind'] for item in job['nodes']) and
        all(nodes[name].get('status') == 'success' for name in ['input0', 'input1']), 'Both actual input references must succeed')
    method = nodes['analysis']
    execution = method.get('execution')
    require(isinstance(execution, dict) and execution.get('image') == IMAGE and execution.get('image_digest') == IMAGE.split('@')[1]
        and type(execution.get('exit_code')) is int and method.get('reused') is False, 'Fresh real method execution required')
    require(method.get('status') == ('success' if positive else 'failed') and
        (not first.get('errors') if positive else bool(first.get('errors'))), 'Graph outcome does not match frozen method case')
    if positive:
        require(execution['exit_code'] == 0, 'Positive method must actually exit zero')
    else:
        require(not method.get('port_assignments'), 'Failed method must not publish normal output ports')
    return method


def check_inputs(work, originals, method, scratch):
    bindings = method.get('inputs', [])
    require(len(bindings) == 2 and {item['to_port'] for item in bindings} == {0, 1}, 'Two complete actual input bindings required')
    records = []
    for index, original in enumerate(originals):
        source = work / original.name
        matches = [path for path in scratch.rglob('input-' + str(index) + original.suffix)
            if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        bound = next(item for item in bindings if item['to_port'] == index)
        identity = fact(source)
        require(len(matches) == 1 and matches[0].parent.resolve(strict=True) == matches[0].parent and
            bound.get('from') == 'input' + str(index) and type(bound.get('from_port')) is int and bound['from_port'] == 0 and
            type(bound.get('to_port')) is int and bound.get('path') == 'vfs:///' + original.name and
            type(bound['fingerprint']['size']) is int and bound['fingerprint']['size'] == identity['bytes'] and
            bound['fingerprint']['content_hash'].removeprefix('sha256:') == identity['sha256'] and
            identity['sha256'] == digest(original), 'Actual staged input identity or binding differs')
        staged = matches[0]
        before = staged.lstat()
        linked = stat.S_ISLNK(before.st_mode)
        if linked:
            require(os.readlink(staged) == str(source) and staged.resolve(strict=True) == source,
                'Only a direct link to this exact owned input is allowed')
            with staged.open('rb') as handle:
                observed = hashlib.file_digest(handle, 'sha256').hexdigest()
            require(os.readlink(staged) == str(source), 'Staged link changed during hashing')
        else:
            observed = fact(staged)['sha256']
        after = staged.lstat()
        signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(signature(before) == signature(after) and observed == identity['sha256'] and fact(source) == identity,
            'Staged input or its exact owned source changed')
        records.append(dict(port=index, sha256=identity['sha256'], bytes=identity['bytes'],
            staging_mode='exact_owned_input_symlink' if linked else 'regular_byte_copy'))
    return records


def check_ports(work, definition, method, scratch):
    assignments = method.get('port_assignments')
    require(isinstance(assignments, dict) and set(assignments) == {'0', '1'}, 'Both actual output port assignments required')
    run_name = method['execution']['run_name']
    require(isinstance(run_name, str) and Path(run_name).name == run_name and run_name not in {'', '.', '..'}, 'Exact actual run name required')
    result = []
    for index, port in enumerate(definition['ports']['outputs']):
        value = assignments[str(index)]
        live = Path(value['path'])
        published = work / definition['artifact_prefix'].lstrip('/') / run_name / port['path']
        require(live.resolve().is_relative_to(scratch) and live.name == port['path'] and
            fact(live)['sha256'] == digest(published) and value['format'] == port['format'] and
            value['fingerprint']['size'] == live.stat().st_size, 'Exact run output, published file or format differs')
        content_hash = value['fingerprint'].get('content_hash')
        require(content_hash is None or content_hash.removeprefix('sha256:') == digest(live), 'Output fingerprint differs')
        result.append(published)
    return result


def sample_service(service, stop, observations, failures):
    while not stop.is_set():
        try:
            require((service / 'memory.max').read_text().strip() == '2147483648', 'Recorded parent limit changed')
            for path in service.rglob('memory.max'):
                if 'libpod' not in str(path.relative_to(service)):
                    continue
                try:
                    limit = path.read_text().strip()
                    current = int(path.with_name('memory.current').read_text())
                    peak = int(path.with_name('memory.peak').read_text())
                except FileNotFoundError:
                    continue
                relative = str(path.parent.relative_to(service))
                require(path.parent.resolve().is_relative_to(service), 'Observed container escaped recorded service')
                entry = observations.setdefault(relative, dict(relative_cgroup=relative, limits=[], samples=0,
                    maximum_sampled_current_bytes=0, maximum_observed_kernel_peak_bytes=0))
                entry['samples'] += 1
                if limit not in entry['limits']:
                    entry['limits'].append(limit)
                entry['maximum_sampled_current_bytes'] = max(entry['maximum_sampled_current_bytes'], current)
                entry['maximum_observed_kernel_peak_bytes'] = max(entry['maximum_observed_kernel_peak_bytes'], peak)
        except Exception as error:
            failures.append(dict(type=type(error).__name__, error=str(error)))
            return
        stop.wait(0.05)


def execute(runner, work, service):
    observations, failures = {}, []
    stop = threading.Event()
    monitor = threading.Thread(target=sample_service, args=(service, stop, observations, failures))
    monitor.start()
    try:
        with (work / 'runner.stdout').open('xb') as stdout, (work / 'runner.stderr').open('xb') as stderr:
            result = subprocess.run([str(runner), str(work / 'job.json')], stdout=stdout, stderr=stderr, timeout=240,
                env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
    finally:
        stop.set()
        monitor.join(timeout=10)
    require(not monitor.is_alive() and not failures, 'Independent cgroup monitor failed')
    write(work / 'cgroup-observations.json', dict(records=list(observations.values()), failures=failures,
        interval_seconds=0.05, peak_semantics='kernel hierarchical high-water mark, not RSS', native_sampler_certified=False))
    write(work / 'runner-exit.json', dict(exit=result.returncode))
    return result, list(observations.values())


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed light session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'h5ad-subset-isolated-dag'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    initial = cgroup_observation()
    service = Path(initial['path'])
    available = int(next(row.split()[1] for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3, 'Bounded graph plus reserve unavailable')
    write(output / 'resource-admission.json', dict(parent=initial, available_memory_bytes=available,
        other_builds_continue_to_have_priority=True, heavy_build_started=False))
    checked = {}
    for session, seal in [(BUILD_SESSION, BUILD_SEAL), (REFERENCE_SESSION, REFERENCE_SEAL)]:
        checked[session] = verify_archive(ARCHIVES, session, seal)
        require(checked[session]['positive_worker_exit_verified'], 'Successful sealed dependency required')
    failed = verify_archive(ARCHIVES, FAILED_SESSION, FAILED_SEAL)
    require(type(failed['worker_exit_status']) is int and failed['worker_exit_status'] == 1,
        'Original driver refusal must remain a failed terminal archive, not a pass')
    build_root = ARCHIVES / BUILD_SESSION / 'artifacts/permanent/current-ldsc-build'
    original_runner = build_root / 'official_plugin_dag'
    before_runner = fact(original_runner)
    build = strict_json((build_root / 'build-record.json').read_text())
    require(before_runner['sha256'] == build['executable_sha256'] == RUNNER_SHA and build['engine_commit'] == ENGINE and
        build['probe_sha256'] == PROBE_SHA and type(build['actual_build_exit']) is int and build['actual_build_exit'] == 0,
        'Exact successful existing SDK runner required; no rebuild fallback')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    with original_runner.open('rb') as incoming, runner.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    runner.chmod(0o700)
    require(digest(runner) == RUNNER_SHA, 'Owned executable copy differs from sealed SDK')
    shutil.copyfile(build_root / 'build-record.json', output / 'build-record.json')
    reference = ARCHIVES / REFERENCE_SESSION / 'artifacts/permanent/h5ad-subset-official-runtime'
    source, manifest, definition, identities = export_source(output)
    dependencies = {}
    (output / 'driver-dependencies').mkdir()
    for name in DEPENDENCIES:
        dependencies[name] = fact(ROOT / name)
        shutil.copyfile(ROOT / name, output / 'driver-dependencies' / Path(name).name)
    original_panel = panel_facts()
    panel_snapshot = output / 'canonical-panel-source'
    panel_snapshot.mkdir()
    for filename in original_panel:
        shutil.copyfile(PANEL / filename, panel_snapshot / filename)
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    prefix = [str(shim), '--cgroup-manager=cgroupfs']
    backend = default_backend(prefix, output)
    image_before = inspect(prefix, output, 'before')
    records = []
    for name in [*sorted(POSITIVES), *sorted(NEGATIVES), 'missing-input0-edge', 'missing-input1-edge']:
        positive = name in POSITIVES
        preflight = name.startswith('missing-input')
        original = reference / ('positive' if positive or preflight else 'boundary') / ('dense' if preflight else name)
        work = output / name
        work.mkdir()
        input_before = {filename: fact(original / filename) for filename in ['input.h5ad', 'selection.parquet', 'request.json']}
        for filename in input_before:
            shutil.copyfile(original / filename, work / filename)
        settings = strict_json((work / 'request.json').read_text())
        target_panel = work / PANEL_PATH.lstrip('/')
        target_panel.mkdir(parents=True)
        for filename, expected in original_panel.items():
            shutil.copyfile(PANEL / filename, target_panel / filename)
            require(digest(target_panel / filename) == expected['sha256'], 'Owned real panel transport copy differs')
        transport_files = {filename: fact(target_panel / filename) for filename in original_panel}
        directory_stat = target_panel.lstat()
        transport_identity = (directory_stat.st_dev, directory_stat.st_ino, directory_stat.st_mode)
        job = job_for(work, source, manifest, identities, settings['join_column'])
        if preflight:
            missing = int(name[len('missing-input')])
            job['edges'] = [edge for edge in job['edges'] if edge['to_port'] != missing]
        write(work / 'job.json', job)
        result, observed_cgroups = execute(runner, work, service)
        scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / name
        if preflight:
            stderr = (work / 'runner.stderr').read_text()
            exact_display = 'input port `' + str(missing) + '` on node `analysis` is not connected'
            exact_debug = 'PortDisconnected { node: "analysis", port: ' + str(missing) + ' }'
            require(result.returncode != 0 and (exact_debug in stderr or exact_display in stderr) and not (work / 'dag-report.json').exists() and
                not scratch.exists() and not observed_cgroups, 'Missing edge must fail graph validation before container dispatch')
            record = dict(case=name, route='ENGINE_INPUT_COMPLETENESS', missing_port=missing,
                nodes=3, edges=1, actual_exit=result.returncode, actual_method_executed=False)
        else:
            require(result.returncode == 0, 'Actual SDK runner failed: ' + name)
            report = strict_json((work / 'dag-report.json').read_text())
            method = validate_report(report, job, positive=positive)
            bound = check_inputs(work, [original / 'input.h5ad', original / 'selection.parquet'], method, scratch)
            require(observed_cgroups and any('8589934592' in item['limits'] for item in observed_cgroups),
                'Actual declared eight-GiB child cgroup must be observed under recorded two-GiB service')
            record = dict(case=name, route='DAG', nodes=3, edges=2, positive=positive, input_bindings=bound,
                method_exit=method['execution']['exit_code'], observed_container_cgroups=len(observed_cgroups))
            if positive:
                ports = check_ports(work, definition, method, scratch)
                for index, filename in enumerate(['output.h5ad', 'report.json']):
                    shutil.copyfile(ports[index], work / filename)
                shutil.copyfile(original / 'fresh-author.h5ad', work / 'fresh-author.h5ad')
                require(digest(work / 'output.h5ad') == digest(original / 'fresh-author.h5ad') == digest(original / 'output.h5ad'),
                    'Complete graph output must match already sealed independent official output byte-for-byte')
                record['complete_h5ad_byte_equal_to_sealed_independent_author'] = True
                record['published_ports'] = 2
            else:
                method_log = Path(method['execution']['stderr_log']['path'])
                require(method_log.resolve().is_relative_to(scratch), 'Actual method error log must belong to its owned workspace')
                fact(method_log)
                diagnostic = method_log.read_text()
                expected_exit = 3 if name == 'corrupt-selection' else 2
                require(method['execution']['exit_code'] == expected_exit and NEGATIVES[name] in diagnostic and
                    NEGATIVES[name] in method['error']['message'] and
                    all(not list(scratch.rglob(filename)) and not list((work / 'artifacts').rglob(filename))
                        for filename in ['output.h5ad', 'report.json']), 'Specific method refusal/no-publication failed: ' + name)
                (work / 'preserved-method.stderr').write_text(diagnostic)
                record.update(specific_refusal=NEGATIVES[name], published_ports=0, normal_results_absent=True)
        require(input_before == {filename: fact(original / filename) for filename in input_before} and
            all(digest(work / filename) == expected['sha256'] for filename, expected in input_before.items()),
            'Source fixtures or copied graph inputs changed')
        require(all(digest(target_panel / filename) == expected['sha256'] for filename, expected in original_panel.items()),
            'Owned technical panel transport bytes changed')
        write(work / 'panel-transport-receipt.json', dict(files=original_panel, alias=ALIAS,
            canonical_source_unchanged=True, retained_snapshot='../canonical-panel-source', duplicate_transport_copy_disposable=True))
        retire_transport_copy(target_panel, transport_identity, transport_files)
        records.append(record)
        write(work / 'checked-case.json', record)
        print(name + ' checked', flush=True)
    write(output / 'completed-cases.json', records)
    write(output / 'positive-inventory.json', sorted(POSITIVES))
    (source / 'compare-sealed.py').write_text(COMPARE)
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
        '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=128m', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(source) + ':/source:ro',
        '-v', str(output) + ':/proof:rw', '--entrypoint=python', IMAGE, '/source/compare-sealed.py']
    write(output / 'comparison-command.json', command)
    with (output / 'comparison.stdout').open('xb') as stdout, (output / 'comparison.stderr').open('xb') as stderr:
        compared = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=180)
    write(output / 'comparison-exit.json', dict(exit=compared.returncode))
    require(compared.returncode == 0, 'Actual complete official object/report comparison failed')
    comparison = strict_json((output / 'whole-object-comparison.json').read_text())
    require(len(comparison['records']) == 11 and {item['case'] for item in comparison['records']} == POSITIVES and
        all(item['whole_container_checks'] > 0 and item['hdf5_datasets_checked'] > 0 and
            item['complete_cell_ledger_rows_checked'] == 6 and item['full_report_checked'] is True and item['G0'] is False
            for item in comparison['records']), 'Every graph result needs complete object and report verification')
    require(before_runner == fact(original_runner) and digest(runner) == RUNNER_SHA and original_panel == panel_facts() and
        all(digest(panel_snapshot / name) == expected['sha256'] for name, expected in original_panel.items()) and
        identities == {name: fact(source / name) for name in identities} and
        dependencies == {name: fact(ROOT / name) for name in dependencies} and image_before == inspect(prefix, output, 'after'),
        'Pinned runner, source, helper, canonical panel or runtime changed')
    final = cgroup_observation()
    events = lambda value: dict(row.split() for row in value['memory_events'].splitlines())
    require(all(events(final).get(name) == events(initial).get(name) for name in ['oom', 'oom_kill', 'max']),
        'Recorded service encountered memory pressure/OOM')
    write(output / 'verification.json', dict(scope='BOUNDED_OLD_PINNED_SDK_DAG_NO_SCIENTIFIC_AUTHORITY',
        source_git_revision=REVISION, source_identities=identities, driver_dependencies=dependencies,
        sealed_dependencies=checked, build=build, runner_sha256=RUNNER_SHA, official_runtime=image_before,
        preserved_previous_driver_failure=failed, original_failure_not_a_method_failure=True,
        runtime_backend=backend, canonical_panel=original_panel, technical_transport_alias=ALIAS,
        original_model_registry_qualified=False, models_unpickled=False,
        positives=11, method_refusals=19, engine_missing_input_preflights=2,
        direct_only_controls_not_claimed_as_DAG=sorted(DIRECT_ONLY),
        inherited_official_package_census_session=REFERENCE_SESSION, fresh_package_census_executed=False,
        full_comparison=comparison, initial_parent_cgroup=initial, final_parent_cgroup=final,
        effective_parent_memory_max_bytes=2147483648, original_manifest_resources_unchanged=True,
        original_eight_GiB_full_scale_resource_certified=False, native_memory_sampler_certified=False,
        owned_container_intents_expected=31, stoppage='PENDING_OUTER_MANAGED_SESSION_FINALIZATION',
        latest_merged_guard_runner_verified=False, current_daemon_verified=False, production_restarted=False,
        real_study_inputs_read=False, scientific_model_fitted=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
