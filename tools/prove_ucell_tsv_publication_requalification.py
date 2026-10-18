"""Requalify the repaired TSV wrapper against the sealed original UCell inventory."""

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_frozen_a_harmonisation_dag as admission
from tools import prove_h5ad_subset_official_runtime as managed
from tools import prove_ucell_tsv_dag as original
from tools.prove_frozen_a_family_runtime import stopped
from tools.prove_locked_b_source_transport import actual_ports, regular
from tools.reconcile_ab_evidence_index import require, strict_json, verify_archive

BUILD_SESSION = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
RUNNER_SHA = '636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b'
ENGINE = '4256643c55ae6fb50e8c867069330ed6ac2b4bc0'
REPAIR_SESSION = '991a8e78f128469b9b69f534ca6d11c1'
REPAIR_SEAL = 'f3c63ae6477cd9c8ec092fcaa916e20b735fb237a1c9222f5aba585af1821ba0'
GOLDEN_SESSION = 'c36e3eae672b4fa39ec4222c94774d97'
GOLDEN_SEAL = 'b9852600c1b88c7f2bc51a12c19d6dacdc56a227948891c29441cc39e04ae5d7'
AUTHOR_SEAL = '633c610ae6e69e203b63d07d13d2fdc6c68a928b2b21cf458803ab261b08cd7d'
AUTHOR_FINAL = '8f7efb82e743a09f0eaf9d46e1cfa4cb07dbabcffcfb5f1020e239bfb6af2d26'
SCRIPT_SHA = '101212cac5bde9a90b7105c0e4311651d8d12c42d9e06afb3f39deb3f8aa9b5f'
MANIFEST_SHA = '697afaefb753c095dfcca39fb67ead7d39ba48bebf7d18e1b08ae3a4c6bfe857'
IMAGE = 'ghcr.io/zj-2002/cachexia-ucell-official@sha256:f5310020240016e9069783498aebbd1849c73c6ae4918058614803fe3b6bfca1'
SCOPE = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
INPUTS = ('matrix.tsv', 'signatures.tsv')
OUTPUTS = ('ucell_scores.tsv', 'ucell.RDS', 'ucell.log', 'audit.json')
NEGATIVES = ('output1-alias-input', 'output3-alias-input', 'output-alias', 'normalized-parent-alias',
    'dangling-output', 'hardlinked-output', 'missing-input-path', 'missing-output-path', 'invalid-rank',
    'invalid-weight', 'invalid-policy', 'first-result-link-failure', 'second-result-link-failure',
    'audit-link-failure', 'foreign-replacement', 'input-change')
POSITIVE = ('main', 'rank1000', 'rank2000', 'skip', 'weight0', 'weight-half', 'weight2', 'skip-weight2',
    'reordered-genes', 'reordered-cells', 'up-only', 'negative-only')
PINS = {
    'plugins/ucell/manifest.toml': MANIFEST_SHA,
    'plugins/ucell/scripts/ucell.R': SCRIPT_SHA,
    'plugins/ucell/source-lock.json': '3ef3532e2dcea96a68e16f52a442e2a9d421dd6399327db56a85eac62d627942',
    'tests/test_ucell_tsv_publication.py': '420b499230d9b2cdd6d80d3d635450ca82d959637a17dfa5c38f6eb88664a16f',
    'tools/prove_ucell_tsv_dag.py': '2934d70a2c5bb22d2d1746111c42879c18a808c4d43b438fa6dfb67d66293d83',
    'tools/prove_ucell_tsv_failures.py': '50990393d6060df282bc593df3cb471dedc285aaae9e6b7d2435d0f114f7b695',
    'tools/prove_ucell_tsv_io.py': 'e72ee41d6d3c8da2940aa2100dc5014e61867dff297c52252faee09925fe9590',
    'tools/ucell_tsv_reference.R': '34d5fd586ef93315650b17f089d11f812ad6774ec469698181c276247161bd91',
    'tools/prove_current_ldsc.py': '939159c038af706bca99530302eac5b6eed95d768536b29d80bd6baf2cba229d',
    'tools/prove_frozen_a_harmonisation.py': '79b36d2f5a64409f0b8b87735b7773f29dd3dedeaa3809ddb14a4c7a97685018',
    'tools/prove_frozen_a_harmonisation_dag.py': '8e27e01930e97bdbd84d57ca398253b705bc0ff2e5d6a88d0f5781cde66ef54e',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_locked_b_source_transport.py': '191b0dccfe26e21f9fdd0c727ef1be52306927791e98e01242d82d690691dd56',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
    'tools/reconcile_ab_evidence_index.py': '44878add55a5a656f15e2c936e269ba1ef9b2c4a16c81e7a5c22733da6975c72',
}
ENGINEERING_TESTS = {
    'tests/test_ucell_h5ad_publication.py': ('71d2ea4b44e35dc6d2d48804e5ca9566b2880623c71790d50e7ae06b7f1a935b', 23),
    'tests/test_ucell_tsv_publication.py': (PINS['tests/test_ucell_tsv_publication.py'], 19),
    'tests/test_singscore_publication_ownership.py': ('68aebb7d359e1a1ae4c7ef557a92d3373fda9e0b7ac71e7e07ee624123c0d823', 16),
}
fact, write = managed.fact, managed.write


def content(path):
    value = fact(path)
    return {name: value[name] for name in ('bytes', 'sha256')}


def sources():
    result = {name: fact(regular(ROOT / name)) for name in PINS}
    require(all(result[name]['sha256'] == checksum for name, checksum in PINS.items()), 'Exact reviewed method and helper sources required')
    require(tuple(case['name'] for case in original.configurations()) == POSITIVE, 'All twelve original parameter branches required')
    return result


def checked_archive(archives, session, seal):
    verified = verify_archive(archives, session, seal)
    state = strict_json(regular(archives / session / 'SESSION.json').read_text())
    require(verified['positive_worker_exit_verified'] is True and type(state.get('launcher_exit_status')) is int and
        state['launcher_exit_status'] == 0, 'Only a completely sealed successful worker and launcher may supply evidence')
    return Path(verified['artifact_root']), verified


def validate_engineering(report, execution, snapshot):
    require(report.get('schema') == 'B_PUBLICATION_OWNERSHIP_REGRESSIONS_V1' and report.get('complete') is True and
        type(report.get('actual_tests_run')) is int and report['actual_tests_run'] == 58 and
        report.get('official_UCell_or_singscore_computation_executed') is False and
        report.get('scientific_authorization_granted') is False and report.get('g0_granted') is False,
        'New fifty-eight-case engineering proof without method or scientific authority required')
    required = execution.get('required_test_ids')
    actual = execution.get('actual_test_ids')
    require(isinstance(required, list) and isinstance(actual, list) and len(required) == len(set(required)) == 58 and
        len(actual) == len(set(actual)) == 58 and set(actual) == set(required) and execution.get('complete') is True and
        type(execution.get('tests_run')) is int and execution['tests_run'] == 58 and
        all(type(execution.get(name)) is int and execution[name] == 0 for name in ('failures', 'errors', 'skipped')),
        'All exact engineering cases must actually execute without failure or skips')
    expected_ids = []
    for name, (checksum, count) in ENGINEERING_TESTS.items():
        path = regular(snapshot / name)
        require(fact(path)['sha256'] == checksum and report['current_sources'][name]['sha256'] == checksum,
            'Exact three engineering test sources required')
        module = name.removesuffix('.py').replace('/', '.')
        tree = ast.parse(path.read_text())
        selected = [module + '.' + definition.name + '.' + method.name
            for definition in tree.body if isinstance(definition, ast.ClassDef)
            for method in definition.body if isinstance(method, ast.FunctionDef) and method.name.startswith('test_')]
        require(len(selected) == count, 'Complete original engineering inventory required')
        expected_ids.extend(selected)
    require(len(expected_ids) == len(set(expected_ids)) == 58 and set(required) == set(expected_ids),
        'All exact fifty-eight test IDs must match their sealed source definitions')
    for name in ('plugins/ucell/scripts/ucell.R', 'tests/test_ucell_tsv_publication.py'):
        require(report['current_sources'][name]['sha256'] == PINS[name] and fact(regular(snapshot / name))['sha256'] == PINS[name],
            'Engineering seal must cover this exact repaired TSV wrapper and tests')


def checked_engineering(archives, session, seal):
    require(session == REPAIR_SESSION and seal == REPAIR_SEAL, 'Exact new reviewed engineering seal required; no legacy fallback')
    root, verified = checked_archive(archives, session, seal)
    directory = root / 'permanent/b-publication-ownership'
    validate_engineering(strict_json((directory / 'verification.json').read_text()),
        strict_json((directory / 'tests-execution.json').read_text()), directory / 'source')
    return verified


def checked_author(root):
    root = root.absolute()
    require(fact(regular(root / 'SEALED_FILES.json'))['sha256'] == AUTHOR_SEAL and
        fact(regular(root / 'FINAL_VERIFICATION.json'))['sha256'] == AUTHOR_FINAL, 'Exact original author packet seals required')
    seal = strict_json((root / 'SEALED_FILES.json').read_text())
    rows = {row['path']: row for row in seal['files']}
    links = {row['path']: row for row in seal['internal_links']}
    negative = {row['path']: row for row in seal['declared_negative_fixture_links']}
    require(len(rows) == len(seal['files']) == 1901 and len(links) == 10 and len(negative) == 3 and
        not seal['undeclared_external_data_links'] and not (set(rows) & set(links) | set(rows) & set(negative) | set(links) & set(negative)),
        'Complete unique original author packet inventory required')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    require(actual == set(rows) | set(links) | set(negative) | {'SEALED_FILES.json', 'FINAL_VERIFICATION.json'}, 'Original author packet membership changed')
    for name in [*rows, *links, *negative]:
        require(not Path(name).is_absolute() and all(part not in ('', '.', '..') for part in name.split('/')), 'Author member escapes packet')
    for name, row in rows.items():
        require(content(regular(root / name)) == dict(bytes=row['size'], sha256=row['sha256']), 'Original author-source packet bytes changed')
    for name, row in links.items():
        path = root / name
        require(path.is_symlink() and path.resolve(strict=True).is_relative_to(root) and
            path.resolve(strict=True) == (root / row['target']).resolve(strict=True) and
            hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Original internal author-source link changed')
    for name, row in negative.items():
        path = root / name
        require(path.is_symlink() and os.readlink(path) == row['target'] and not path.exists(), 'Original intentional negative fixture link changed')
    return dict(sealed_files_sha256=AUTHOR_SEAL, final_verification_sha256=AUTHOR_FINAL, files=1901,
        internal_links=10, intentional_dangling_fixture_links=3, H5AD_adapter_qualification_inherited=False)


def checked_goldens(archives):
    root, verified = checked_archive(archives, GOLDEN_SESSION, GOLDEN_SEAL)
    directory = root / 'permanent/ucell-tsv-readback'
    report = strict_json((directory / 'verification.json').read_text())
    cases = strict_json((directory / 'positive-cases.json').read_text())
    rows = report.get('compared_cases', [])
    require(cases == original.configurations() and len(rows) == 12 and tuple(row['case'] for row in rows) == POSITIVE and
        sum(row['score_values'] for row in rows) == 208 and all(row['complete_RDS_identical_with_declared_numeric_metadata_type'] is True and
            row['official_score_object_not_modified'] is True for row in rows) and
        report.get('method_or_DAG_recomputed') is False and report.get('worker_exit_of_original_stage_rewritten') is False and
        report.get('g0_granted') is False, 'All twelve unchanged complete independent official objects and typed metadata receipts required')
    require(fact(regular(directory / 'reference.R'))['sha256'] == PINS['tools/ucell_tsv_reference.R'], 'Original whole-object comparator changed')
    for name in POSITIVE:
        for filename in (*INPUTS, *OUTPUTS, 'author-reference.RDS'):
            regular(directory / name / filename)
    return directory, verified


def job_for(work, source, parameters):
    job = original.job_for(work, source, dict(parameters))
    job['additional_plugins'] = []
    for row in job['nodes'][:2]:
        row['spec']['hash_content'] = True
    return job


def validate_report(report, build, *, positive):
    require(build['engine_commit'] == ENGINE and report.get('engine_source_revision') == ENGINE and report.get('scope') == SCOPE and
        report.get('plugin_name') == 'cachexia-ucell' and report.get('original_manifest_sha256') == MANIFEST_SHA and
        report.get('additional_plugin_identities') == [] and report.get('input_hashing') == 'ContentRequired' and
        report.get('incremental') is False and type(report.get('max_concurrency')) is int and report['max_concurrency'] == 1 and
        all(report.get(name) is False for name in ('native_statistical_factories_registered', 'current_daemon_verified',
            'scientific_authorized', 'g0_granted')), 'Exact frozen generic SDK report and no authority required')
    first = report['first_run']
    rows = first['nodes']
    require(len(rows) == 3 and {row['id'] for row in rows} == {'input0', 'input1', 'analysis'} and
        all(row.get('reused') is False for row in rows), 'Three fresh nodes required')
    nodes = {row['id']: row for row in rows}
    for port in range(2):
        node = nodes['input' + str(port)]
        require(node.get('node_type') == 'file_reference' and node.get('status') == 'success' and
            set(node.get('port_assignments', {})) == {'0'}, 'Both file sources must succeed with exactly one port')
    method = nodes['analysis']
    execution = method.get('execution', {})
    require(method.get('node_type') == 'cachexia_ucell_official' and method.get('status') == ('success' if positive else 'failed') and
        type(execution.get('exit_code')) is int and execution['exit_code'] == (0 if positive else 2) and
        execution.get('image') == IMAGE and execution.get('image_digest') == IMAGE.split('@')[1], 'Exact UCell method outcome, not infrastructure failure, required')
    expected = {} if positive else {'analysis': method.get('error')}
    require(isinstance(first.get('errors'), dict) and first['errors'] == expected and first.get('ok') is positive and
        set(method.get('port_assignments', {})) == ({'0', '1', '2', '3'} if positive else set()), 'Specific refusal must publish no normal ports')
    if positive:
        require(method.get('error') is None, 'Successful method cannot retain an error')
    else:
        error = method.get('error')
        require(isinstance(error, dict) and set(error) == {'kind', 'message'} and error['kind'] == 'node_error' and
            isinstance(error['message'], str) and error['message'], 'Attributable method error required')
    return nodes


def checked_inputs(work, nodes, scratch):
    bindings = nodes['analysis'].get('inputs', [])
    require(len(bindings) == 2, 'Both actual input bindings required')
    result = []
    for port, filename in enumerate(INPUTS):
        source = regular(work / filename)
        expected = fact(source)
        selected = [row for row in bindings if type(row.get('to_port')) is int and row['to_port'] == port]
        require(len(selected) == 1, 'Unique typed method input port required')
        binding = selected[0]
        assignment = nodes['input' + str(port)]['port_assignments']['0']
        for row in (binding, assignment):
            fingerprint = row.get('fingerprint', {})
            require(row.get('path') == 'vfs:///' + filename and type(fingerprint.get('size')) is int and
                fingerprint['size'] == expected['bytes'] and fingerprint.get('content_hash') == 'sha256:' + expected['sha256'], 'Whole bound input fingerprint differs')
        require(binding.get('from') == 'input' + str(port) and type(binding.get('from_port')) is int and
            binding['from_port'] == 0 and assignment.get('format') == 'tsv', 'Input source and role differ')
        staged = [path for path in scratch.rglob('input-' + str(port) + '.tsv') if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        require(len(staged) == 1, 'One actual staged input per port required')
        before = staged[0].lstat()
        if stat.S_ISLNK(before.st_mode):
            require(os.readlink(staged[0]) == str(source) and staged[0].resolve(strict=True) == source, 'Only a direct link to this exact toy source is allowed')
            checksum = hashlib.sha256(staged[0].read_bytes()).hexdigest()
        else:
            checksum = fact(regular(staged[0]))['sha256']
        after = staged[0].lstat()
        signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(signature(before) == signature(after) and checksum == expected['sha256'] and fact(source) == expected, 'Staged input identity or bytes changed')
        result.append(dict(port=port, name=filename, **expected))
    return result


def run_recorded(command, work, label, *, environment=None, timeout=240):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as error:
        (work / (label + '.stdout')).write_bytes(error.stdout or b'')
        (work / (label + '.stderr')).write_bytes(error.stderr or b'')
        write(work / (label + '-exit.json'), dict(actual_exit=None, timed_out=True))
        raise
    (work / (label + '.stdout')).write_bytes(result.stdout)
    (work / (label + '.stderr')).write_bytes(result.stderr)
    write(work / (label + '-exit.json'), dict(actual_exit=result.returncode, timed_out=False))
    return result


def preserve_logs(work, scratch):
    target = work / 'preserved-logs'
    target.mkdir(exist_ok=True)
    records = []
    if scratch.exists():
        roots = [path for path in scratch.glob('*/*') if path.is_dir() and not path.is_symlink() and
            re.fullmatch('[0-9a-f]{2}', path.parent.name) and re.fullmatch('[0-9a-f]{62}', path.name)]
        require(len(roots) <= 1, 'Only one owned single-method workspace may supply diagnostics')
        for root in roots:
            for name in ('.autonomics/logs/stdout.log', '.autonomics/logs/stderr.log', 'ucell.log'):
                source = root / name
                if not os.path.lexists(source):
                    continue
                before = fact(regular(source))
                require(source.stat().st_uid == os.getuid() and before['bytes'] <= 32 * 1024**2, 'Bounded owned diagnostic required')
                destination = target / name.replace('/', '__')
                with destination.open('xb') as handle:
                    handle.write(source.read_bytes())
                require(fact(source) == before and content(destination) == {key: before[key] for key in ('bytes', 'sha256')}, 'Diagnostic changed during preservation')
                records.append(dict(source=str(source), destination=str(destination), **before))
    write(work / 'preserved-log-index.json', records)
    return records


def graph(runner, build, work, source, definition, parameters, *, positive):
    write(work / 'job.json', job_for(work, source, parameters))
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    environment = dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts'))
    primary = None
    try:
        for label, flags in [('admission', ['--validate-job']), ('runner', [])]:
            result = run_recorded([str(runner), *flags, str(work / 'job.json')], work, label, environment=environment)
            require(result.returncode == 0, 'Actual SDK failed before attributable method reporting')
        report = strict_json(regular(work / 'dag-report.json').read_text())
        nodes = validate_report(report, build, positive=positive)
        bindings = checked_inputs(work, nodes, scratch)
        memory = admission.validate_memory_report(report)
        receipts = admission.checked_task_receipts(work, nodes)
        require(len(receipts) == 3 and all(row['actual_task_resources'] == {} for row in receipts.values()), 'Actual empty native resource leases required')
        method = nodes['analysis']
        if positive:
            ports = actual_ports(work, definition, method, scratch)
            require(len(ports) == 4, 'All four declared outputs required')
            for port, name in zip(ports, OUTPUTS):
                shutil.copyfile(regular(port), work / name)
        else:
            marker = 'BLOCKED: Frozen UCell parameters invalid'
            error = regular(Path(method['execution']['stderr_log']['path']))
            require(error.is_relative_to(scratch) and marker in error.read_text() and marker in method['error']['message'], 'Exact UCell parameter refusal required in actual stderr and node error')
            logs = [path for path in scratch.rglob('ucell.log') if path.parent.name != '.autonomics']
            require(any(marker in regular(path).read_text() for path in logs), 'Declared diagnostic log must retain the exact method refusal')
            require(not any(list(root.rglob(name)) for root in (scratch, work / 'artifacts') for name in (OUTPUTS[0], OUTPUTS[1], OUTPUTS[3])), 'Failed method cannot leave normal artifacts')
            ports = []
        record = dict(case=work.name, positive=positive, nodes=3, edges=2, bindings=bindings, task_receipts=3,
            normal_ports=len(ports), memory=memory, exact_method_exit=method['execution']['exit_code'],
            run_name=method['execution']['run_name'], parameters=parameters)
        write(work / 'verification.json', record)
        return record
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            preserve_logs(work, scratch)
        except Exception as error:
            write(work / 'diagnostic-preservation-error.json', dict(error_type=type(error).__name__, message=str(error), original_error_preserved=primary is not None))
            if primary is None:
                raise


def runtime_backend(kind, output):
    shim = str(regular(Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])))
    if kind == 'default':
        prefix = [shim, '--cgroup-manager=cgroupfs']
        backend = managed.default_backend(prefix, output)
        storage = Path(backend['graph_root'])
    else:
        require(fact(regular(admission.OWNER))['sha256'] == admission.OWNER_SHA, 'Original installation owner changed')
        owner = strict_json(admission.OWNER.read_text())
        for name in ('storage', 'runroot'):
            item = owner[name]
            observed = Path(item['path']).stat()
            require((observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid) == (item['device'], item['inode'], item['uid'], item['gid']), 'Owned backend identity changed')
        prefix = [shim, *owner['runtime_backend']]
        storage = Path(owner['storage']['path'])
        backend = dict(kind=kind, owner_sha256=admission.OWNER_SHA, storage=str(storage), arguments=owner['runtime_backend'])
    result = run_recorded([*prefix, 'image', 'inspect', IMAGE], output, 'image-inspect', timeout=60)
    require(result.returncode == 0, 'Exact image missing on selected backend; no pull or fallback allowed')
    rows = strict_json(result.stdout)
    require(isinstance(rows, list) and len(rows) == 1, 'One exact installed image required')
    image = rows[0]
    config = image['Id'].removeprefix('sha256:')
    requested = IMAGE.split('@sha256:')[1]
    encoded = lambda name: '=' + base64.b64encode(name.encode()).decode()
    directory = storage / 'overlay-images' / config
    manifest_raw = regular(directory / encoded('manifest-sha256:' + requested)).read_bytes()
    config_raw = regular(directory / encoded('sha256:' + config)).read_bytes()
    require(hashlib.sha256(manifest_raw).hexdigest() == requested and hashlib.sha256(config_raw).hexdigest() == config and
        strict_json(manifest_raw)['config']['digest'] == 'sha256:' + config, 'Requested OCI manifest and configuration differ')
    configuration = strict_json(config_raw)
    require(configuration['os'] == 'linux' and configuration['architecture'] == 'amd64' and configuration['rootfs']['diff_ids'] == image['RootFS']['Layers'], 'Actual ordered image layers differ')
    (output / 'image-manifest.json').write_bytes(manifest_raw)
    (output / 'image-config.json').write_bytes(config_raw)
    write(output / 'backend-identity.json', dict(backend=backend, reference=IMAGE, requested_manifest_sha256=requested,
        config_sha256=config, primary_digest=image['Digest'], no_pull=True, no_fallback=True))
    return prefix, backend


def install_launcher(prefix, temporary, output):
    directory = temporary / 'ucell-tsv-backend-bin'
    directory.mkdir(mode=0o700)
    launcher = directory / 'podman'
    program = '''#!/usr/bin/python3
import hashlib,json,os,stat,sys
from pathlib import Path
arguments=sys.argv[1:]
if not arguments or arguments[0].startswith('-'): raise SystemExit('Backend override refused')
if arguments[0]=='create':
 def option(name):
  if arguments.count(name)!=1: raise SystemExit('Missing or repeated original resource option')
  return arguments[arguments.index(name)+1]
 if option('--cpus')!='1' or option('--memory')!='2147483648': raise SystemExit('Original UCell resources differ')
 if option('--network')!='none' or option('--pull')!='missing' or arguments.count('--read-only')!=1: raise SystemExit('Original isolation differs')
 if arguments.count(__IMAGE__)!=1: raise SystemExit('Original official image differs')
 selected={}
 for position,value in enumerate(arguments[:-1]):
  if value=='--env':
   key,separator,content=arguments[position+1].partition('=')
   if key.startswith(('AUTONOMICS_','UCELL_')):
    if not separator or key in selected: raise SystemExit('Repeated or malformed SDK environment')
    selected[key]=content
 if selected.get('AUTONOMICS_SCRIPT')!='/work/.autonomics/script' or selected.get('AUTONOMICS_WORKDIR')!='/work' or selected.get('AUTONOMICS_INPUT_COUNT')!='2' or selected.get('AUTONOMICS_OUTPUT_COUNT')!='4': raise SystemExit('Original SDK script or port counts differ')
 for stem,count in [('INPUT',2),('OUTPUT',4)]:
  if {key for key in selected if key.startswith('AUTONOMICS_'+stem) and key!='AUTONOMICS_'+stem+'_COUNT'}!={'AUTONOMICS_'+stem+str(index) for index in range(count)}: raise SystemExit('SDK port roles differ')
 mounts=[]
 for position,value in enumerate(arguments[:-1]):
  if value=='--mount':
   pieces={}
   for piece in arguments[position+1].split(','):
    key,separator,content=piece.partition('=')
    if key in pieces: raise SystemExit('Repeated mount field')
    pieces[key]=content if separator else True
   if pieces.get('destination')=='/work':
    if pieces.get('type')!='bind' or pieces.get('rw')!='true' or set(pieces)!={'type','source','destination','rw'}: raise SystemExit('Original workspace mount differs')
    mounts.append(Path(pieces['source']))
 if len(mounts)!=1: raise SystemExit('One original SDK workspace required')
 workspace=mounts[0]
 allowed=Path(__ALLOWED__)
 if workspace.resolve()!=workspace or not workspace.is_relative_to(allowed) or workspace==allowed or workspace.stat().st_uid!=os.getuid(): raise SystemExit('Owned scratch required')
 script=workspace/'.autonomics/script'
 before=script.lstat()
 identity=lambda value:(value.st_dev,value.st_ino,value.st_uid,value.st_gid,value.st_mode,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
 if not stat.S_ISREG(before.st_mode) or script.resolve()!=script or hashlib.sha256(script.read_bytes()).hexdigest()!=__SCRIPT_SHA__ or identity(script.lstat())!=identity(before): raise SystemExit('Exact original staged script required')
 arguments[arguments.index('--pull')+1]='never'
 record=dict(run_name=option('--name'),cpus=1,memory_bytes=2147483648,resources_overridden=False,original_pull='missing',effective_pull='never',staged_script_sha256=__SCRIPT_SHA__,environment=selected)
 descriptor=os.open(__RECORD__,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
 with os.fdopen(descriptor,'a') as handle: handle.write(json.dumps(record)+'\\n')
os.execv(__PROGRAM__,__PREFIX__+arguments)
'''.replace('__RECORD__', repr(str(output / 'actual-container-create.jsonl'))).replace('__PROGRAM__', repr(prefix[0])).replace(
        '__PREFIX__', repr(prefix)).replace('__IMAGE__', repr(IMAGE)).replace('__SCRIPT_SHA__', repr(SCRIPT_SHA)).replace(
        '__ALLOWED__', repr(str(temporary / 'official-plugin-container-workspaces')))
    launcher.write_text(program)
    launcher.chmod(0o700)
    os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
    return launcher, fact(launcher)


def preflight(runner, source, golden, output):
    records = []
    for name in ('unknown-parameter', 'missing-signature-edge'):
        work = output / name
        work.mkdir()
        for filename in INPUTS:
            shutil.copyfile(regular(golden / 'main' / filename), work / filename)
        job = job_for(work, source, original.configurations()[0]['parameters'])
        if name == 'unknown-parameter':
            job['nodes'][-1]['spec']['unexpected_free_parameter'] = 1
            marker = 'node `cachexia_ucell_official`: unknown param `unexpected_free_parameter`'
        else:
            job['edges'] = job['edges'][:1]
            marker = 'PortDisconnected { node: "analysis", port: 1 }'
        write(work / 'job.json', job)
        environment = dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts'))
        result = run_recorded([str(runner), str(work / 'job.json')], work, 'construction', environment=environment)
        require(result.returncode == 1 and marker in result.stderr.decode() and not (work / 'dag-report.json').exists() and
            not (work / 'task-receipts').exists(), 'Exact graph preflight refusal without any task execution required')
        records.append(dict(case=name, exit=1, exact_diagnostic=marker, actual_method_execution=False))
    return records


def direct_boundaries(output):
    source = ROOT / 'tools/prove_ucell_tsv_failures.py'
    launcher = output / 'original-boundary-selection.py'
    launcher.write_text('''import ast,hashlib,json,sys
from pathlib import Path
source=Path(sys.argv[1])
case=sys.argv[2]
output=Path(sys.argv[3])
payload=source.read_bytes()
assert hashlib.sha256(payload).hexdigest()==__SHA__
tree=ast.parse(payload)
method=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="main")
assignments=[node for node in method.body if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=="output"]
assert len(assignments)==1 and ast.unparse(assignments[0].value)=="Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-failures'"
assertions_before=[ast.dump(node) for node in ast.walk(tree) if isinstance(node,(ast.Assert,ast.If,ast.Raise))]
assignments[0].value=ast.Name(id="__case_output",ctx=ast.Load())
assert [ast.dump(node) for node in ast.walk(tree) if isinstance(node,(ast.Assert,ast.If,ast.Raise))]==assertions_before
namespace={"__name__":"original_boundary_module","__file__":str(source),"__case_output":output}
exec(compile(ast.fix_missing_locations(tree),str(source),"exec"),namespace)
assert case in namespace["CASES"] and len(namespace["CASES"])==16
namespace["CASES"]=[case]
with (output.parent/"selection-receipt.json").open("x") as handle:
 json.dump(dict(source_sha256=hashlib.sha256(payload).hexdigest(),selected_cases=[case],selected_case_count=1,
  assertion_ast_sha256=hashlib.sha256(json.dumps(assertions_before).encode()).hexdigest(),
  only_changes=["main.output_assignment","CASES_singleton_selection"],original_predicates_and_assertions_preserved=True,
  session_permanent_environment_unchanged=True,original_stdout_hardcoded_inventory_not_used_as_count=True),handle)
sys.argv=[str(source)]
namespace["main"]()
'''.replace('__SHA__', repr(PINS['tools/prove_ucell_tsv_failures.py'])))
    records = []
    for name in NEGATIVES:
        work = output / 'direct-boundaries' / name
        work.mkdir(parents=True)
        result = run_recorded([sys.executable, '-B', str(launcher), str(source), name, str(work / 'ucell-tsv-failures')],
            work, 'original-boundary', environment=dict(os.environ), timeout=180)
        case = work / 'ucell-tsv-failures' / name
        stage_records = []
        for directory in sorted(case.glob('.ucell-stage-*')):
            information = directory.lstat()
            row = dict(path=directory.relative_to(work).as_posix(), mode=information.st_mode,
                device=information.st_dev, inode=information.st_ino, uid=information.st_uid, gid=information.st_gid,
                contents_read=False, deleted_by_requalification_driver=False)
            if stat.S_ISDIR(information.st_mode) and not directory.is_symlink():
                row['members'] = [dict(name=child.name, mode=child.lstat().st_mode, bytes=child.lstat().st_size)
                    for child in sorted(directory.iterdir())]
            stage_records.append(row)
        failure = result.stderr.decode(errors='replace')
        cleanup_failure = result.returncode != 0 and 'RuntimeError: Owned staging directories not cleaned' in failure
        complete = result.returncode == 0
        if complete:
            report = strict_json(regular(work / 'ucell-tsv-failures/verification.json').read_text())
            require(report.get('method_source_sha256') == SCRIPT_SHA and report.get('image') == IMAGE and report.get('g0_granted') is False and
                len(report['cases']) == 1 and report['cases'][0]['case'] == name and
                type(report['cases'][0]['exit_code']) is int and report['cases'][0]['exit_code'] == 2 and not stage_records,
                'Complete unchanged original case assertions required')
        row = dict(case=name, selected_original_cases=1, original_assertions_passed=complete, original_harness_exit=result.returncode,
            exact_refusal_and_input_and_normal_output_checks_completed=complete or cleanup_failure,
            original_strict_staging_cleanup_passed=complete, retained_stage_metadata=stage_records,
            original_assertions_changed=False, underlying_method_exit_recorded=(case / 'process.stderr').exists())
        records.append(row)
        write(work / 'boundary-outcome.json', row)
        require(complete or cleanup_failure, 'Original boundary failed before an attributable cleanup assertion; runtime or dependency failure cannot be treated as a case refusal')
    require(tuple(row['case'] for row in records) == NEGATIVES, 'All original sixteen controls must actually be attempted')
    write(output / 'direct-boundary-outcomes.json', records)
    return records


def readback(prefix, output, author):
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
        '--userns=keep-id', '--tmpfs=/tmp:rw,size=64m', '-v', str(output) + ':/work:rw',
        '-v', str(author / 'fresh-author-R') + ':/author:ro', '--entrypoint=Rscript', IMAGE,
        '--vanilla', '/work/reference.R', 'compare', '/work', '/author']
    write(output / 'readback-command.json', command)
    result = run_recorded(command, output, 'official-readback')
    require(result.returncode == 0 and b'COMPARE CASES 12' in result.stdout and
        sum(line.endswith(b'EXACT_COMPLETE_RDS_TSV_AUDIT_AND_IDENTITIES_PASS') for line in result.stdout.splitlines()) == 12,
        'Every complete official object, score TSV, audit and identity comparison must execute')
    rows = strict_json(regular(output / 'readback-verification.json').read_text())
    require(tuple(row['case'] for row in rows) == POSITIVE and sum(row['score_values'] for row in rows) == 208 and
        all(row['complete_RDS_identical_with_declared_numeric_metadata_type'] is True and row['official_score_object_not_modified'] is True
            for row in rows), 'Full twelve-object and 208-value official readback required')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--author-packet', required=True, type=Path)
    parser.add_argument('--engineering-session', required=True)
    parser.add_argument('--engineering-seal', required=True)
    parser.add_argument('--runtime-backend', required=True, choices=('default', 'owner-canonical'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require(args.execute and os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Explicit --execute in a managed session required')
    permanent, temporary = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']), Path(os.environ['TMPDIR'])
    output = permanent / 'ucell-tsv-publication-requalification'
    output.mkdir(mode=0o700)
    before, own_before = sources(), fact(regular(Path(__file__)))
    shutil.copyfile(Path(__file__), output / 'driver.py')
    snapshots = {}
    for name, identity in before.items():
        target = output / 'proof-sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regular(ROOT / name), target)
        require(content(target) == {key: identity[key] for key in ('bytes', 'sha256')}, 'Exact imported proof helper snapshot changed during transport')
        snapshots[name] = fact(target)
    require(managed.cgroup_observation()['memory_max_bytes'] == 2 * 1024**3 and shutil.disk_usage(output).free >= 2 * 1024**3,
        'A visible 2Gi managed parent and scratch reserve are required')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    require(args.build_record.is_relative_to(archives / BUILD_SESSION), 'Only the exact already-sealed generic SDK may run')
    build, built = admission.checked_build(archives, args.runner, args.build_record, BUILD_SEAL)
    require(build['engine_commit'] == ENGINE and fact(regular(args.runner))['sha256'] == RUNNER_SHA, 'No alternate SDK or latest-daemon claim allowed')
    runner, runner_before = admission.executable_copy(args.runner, temporary)
    engineering = checked_engineering(archives, args.engineering_session, args.engineering_seal)
    author = checked_author(args.author_packet)
    golden, golden_verified = checked_goldens(archives)
    write(output / 'prerequisites.json', dict(build=built, engineering=engineering, author=author, golden=golden_verified))
    source = output / 'source'
    (source / 'scripts').mkdir(parents=True)
    for name in ('manifest.toml', 'scripts/ucell.R'):
        shutil.copyfile(regular(ROOT / 'plugins/ucell' / name), source / name)
    shutil.copyfile(regular(ROOT / 'tools/ucell_tsv_reference.R'), output / 'reference.R')
    shutil.copyfile(regular(ROOT / 'tools/prove_ucell_tsv_failures.py'), output / 'original-boundary-driver.py')
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    require(manifest['image']['reference'] == IMAGE and len(manifest['nodes']) == 1 and
        manifest['nodes'][0]['kind'] == 'cachexia_ucell_official' and
        tuple(port['path'] for port in manifest['nodes'][0]['ports']['outputs']) == OUTPUTS, 'Unchanged complete interface required')
    prefix, backend = runtime_backend(args.runtime_backend, output)
    launcher, launcher_before = install_launcher(prefix, temporary, output)
    cases = original.configurations()
    write(output / 'positive-cases.json', cases)
    records, controls, boundaries, official, stops = [], [], None, None, []
    primary = None
    try:
        controls = preflight(runner, source, golden, output)
        for case in cases:
            work = output / case['name']
            work.mkdir()
            for filename in (*INPUTS, 'author-reference.RDS'):
                shutil.copyfile(regular(golden / case['name'] / filename), work / filename)
            records.append(graph(runner, build, work, source, manifest['nodes'][0], case['parameters'], positive=True))
            require((work / 'ucell_scores.tsv').read_bytes() == (golden / case['name'] / 'ucell_scores.tsv').read_bytes(), 'Complete original score TSV bytes changed')
            require((work / 'audit.json').read_bytes() == (golden / case['name'] / 'audit.json').read_bytes(), 'Complete original UCell provenance bytes changed')
        work = output / 'invalid-policy'
        work.mkdir()
        for filename in INPUTS:
            shutil.copyfile(regular(golden / 'main' / filename), work / filename)
        parameters = dict(cases[0]['parameters'], missing_genes='invalid')
        records.append(graph(runner, build, work, source, manifest['nodes'][0], parameters, positive=False))
        write(output / 'completed-cases.json', records)
        boundaries = direct_boundaries(output)
        official = readback(prefix, output, args.author_packet)
        creates = [strict_json(line) for line in regular(output / 'actual-container-create.jsonl').read_text().splitlines()]
        require(len(creates) == len({row['run_name'] for row in creates}) == 13 and
            all(type(row['cpus']) is int and row['cpus'] == 1 and type(row['memory_bytes']) is int and
                row['memory_bytes'] == 2147483648 and row['resources_overridden'] is False and
                row['original_pull'] == 'missing' and row['effective_pull'] == 'never' and
                row['staged_script_sha256'] == SCRIPT_SHA for row in creates),
            'All thirteen actual method creates must bind the unchanged manifest resources and staged source')
        for record in records:
            matching = [row for row in creates if row['run_name'] == record['run_name']]
            expected = {'UCELL_MAX_RANK': str(record['parameters']['max_rank']),
                'UCELL_NEGATIVE_WEIGHT': str(record['parameters']['negative_weight']),
                'UCELL_MISSING_GENES': record['parameters']['missing_genes']}
            require(len(matching) == 1 and {key: value for key, value in matching[0]['environment'].items() if key.startswith('UCELL_')} == expected,
                'Each actual SDK method environment must equal the exact original parameter branch')
    except BaseException as error:
        primary = error
        raise
    finally:
        secondary = []
        try:
            inventory = permanent / 'container-intents.json'
            if inventory.exists():
                count = len(strict_json(inventory.read_text())['intents'])
                stops = stopped(prefix, permanent, output, count)
            else:
                write(output / 'no-container-intents.json', dict(actual_intents=0, successful_proof=False))
        except Exception as error:
            secondary.append(dict(stage='stoppage', error_type=type(error).__name__, message=str(error)))
        try:
            require(sources() == before and fact(regular(Path(__file__))) == own_before and admission.file_identity(args.runner) == runner_before and
                fact(launcher) == launcher_before and checked_author(args.author_packet) == author and
                all(fact(regular(output / 'proof-sources' / name)) == identity for name, identity in snapshots.items()) and
                content(source / 'manifest.toml') == content(ROOT / 'plugins/ucell/manifest.toml') and
                content(source / 'scripts/ucell.R') == content(ROOT / 'plugins/ucell/scripts/ucell.R') and
                content(output / 'reference.R') == content(ROOT / 'tools/ucell_tsv_reference.R'),
                'Original method, imported helpers, driver, executable, backend launcher or author evidence changed')
            checked_goldens(archives)
        except Exception as error:
            secondary.append(dict(stage='source-and-reference-postcheck', error_type=type(error).__name__, message=str(error)))
        write(output / 'finalization.json', dict(primary_error_type=None if primary is None else type(primary).__name__, secondary_errors=secondary,
            successful_proof_not_inferred_from_cleanup=True, g0_granted=False))
        if primary is None:
            require(not secondary, 'Final source/reference/stoppage verification failed')
    write(output / 'inventory-outcomes.json', dict(numerical_DAGs_completed=sum(row['positive'] for row in records),
        complete_official_readbacks=len(official or []), direct_boundaries=boundaries,
        all_original_assertions_passed=all(row['original_assertions_passed'] for row in boundaries or []),
        cleanup_does_not_imply_method_success=True, scientific_authorization_granted=False, g0_granted=False))
    require(len(records) == 13 and len(controls) == 2 and len(boundaries) == 16 and len(official) == 12 and len(stops) == 30,
        'All twelve numerical DAGs, one method refusal, two preflights, sixteen direct controls and one readback must execute')
    require(all(row['original_assertions_passed'] for row in boundaries), 'Every unchanged original boundary assertion, including strict staging cleanup, remains required')
    write(output / 'verification.json', dict(schema='UCELL_TSV_PUBLICATION_REQUALIFICATION_V1', sources=before, build=built,
        engine_commit=ENGINE, backend=backend, exact_DAGs=13, positive_DAGs=12, method_refusal_DAGs=1, preflight_refusals=controls,
        direct_boundary_cases=16, full_official_RDS_objects=12, official_score_values=208, actual_task_receipts=39, actual_input_bindings=26,
        actual_normal_ports=48, actual_container_intents=30, stopped_intents=len(stops), independent_new_oracle_generated=False,
        author_packet=author, engineering_session=args.engineering_session, engineering_seal=args.engineering_seal,
        original_reference_metadata_numeric_weight_conversion_only=True, H5AD_adapter_qualification_inherited=False,
        technical_cached_image_pull_override=dict(original='missing', effective='never', cpu_memory_readonly_network_changed=False),
        manifest_resource_budget_certified=False, arbitrary_hostile_TOCTOU_or_multiport_atomicity_certified=False,
        latest_daemon_or_resident_execution_proven=False, real_research_inputs_read=False, production_changed=False,
        scientific_authorization_granted=False, g0_granted=False))
    print('UCELL_TSV_DAGS=13 OFFICIAL_OBJECTS=12 DIRECT_REFUSALS=16 PREFLIGHT=2 STOPPED=30 G0=false')


if __name__ == '__main__':
    main()
