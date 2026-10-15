"""Prove the fixed seven-node official A qualification graph, without fitting MR."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_frozen_a_harmonisation import (
    AUDIT, BLOCK_SHA, FAMILY, IMAGE, INPUTS, OWNER, OWNER_SHA, PRODUCTS, SOURCE_SHA, STUDY,
    digest, inspected_backend, original_postcheck, require, resource_admission, source_records, write,
)
from tools.prove_locked_b_source_transport import actual_ports, dispatched_bindings, expected_refusal, regular
from tools.reconcile_ab_evidence_index import verify_archive

REVISION = 'e78dae40195d86b1c52e5c2934b54f2161b867db'
PARENT = '11f061589473cb8e4fa57d364ad7107108245de1'
KERNEL_SOURCE_PINS = {
    'crates/dag-core/src/resource.rs': '21c32eb20d1a4b22573b1032048329ee7c5f29217066123b718cbbb2b8d75e06',
    'crates/dag-core/src/resource_tests.rs': '9a80098c52b5242b8d3f34734052d0ee26a5ddac021d4ac3e90578c63697a1d7',
    'crates/dag-core/src/dag/execution/local.rs': 'da748075d402c0c1cefebe3a8a1a364f17f3eef6a085599628bc6302979765eb',
}
PROBE_SHA = '2a23a4189c0a3df9d8c39071e0d5b33a386f342338d2076e1c29b8f97aa1c4c7'
EXPECTED_GUARD_COUNT = 23
SCOPE = 'LOCKED_LEGACY_A_HARMONISATION_NO_FIT_NOT_G0'
METHOD = 'frozen_a_v432_harmonisation'
DIRECT_SESSION = 'a685dfe45f9448b78083b7c510844912'
DIRECT_SEAL = '90b5a6eabc39f3d24caba443a1c3494a0c3bcc30168b59f0c4c4561fcb8d7e29'
IDENTITY_SESSION = '4f717274ece54f4396b8097b4db0ad8a'
IDENTITY_SEAL = 'bf9ce79a277c51193bb7a8af3be6ca7c9231f14567d9e7f1d0fbcc7016364f48'
PINS = {
    'manifest.toml': '07051b9e8351ae30a74ac8b25074e256bfb9d2fb0af53922864d0c16101a01fb',
    'README.md': '22662eecc0e1c67cf01faf3ee1b928932245d65e57a4e6c43c4cbe402b55e832',
    'contracts/source-lock.json': '99349e339055059d8639217ca49cba29cf82116959306bdebdb00f774d3c5ce2',
    'scripts/harmonise.R': '03a7325619dd1ff927db37875c7d0c040c0d2bf9e97ef1b8af72c2f5533a91f1',
}
GUARDS = {
    'transport_tests::original_synthetic_scope_remains_available',
    'transport_tests::synthetic_scope_cannot_relabel_fixed_real_frozen_b_plugin',
    'transport_tests::exact_transport_job_is_accepted_without_executing_it',
    'transport_tests::fit_sql_conversion_and_unknown_kinds_are_rejected',
    'transport_tests::plugin_identity_panels_and_additional_plugins_cannot_be_substituted',
    'transport_tests::unsafe_paths_specs_and_unknown_scope_are_rejected',
    'transport_tests::source_report_requires_actual_readonly_success_without_scientific_authority',
    'transport_tests::source_capsule_checks_seal_membership_and_each_file_hash',
    'transport_tests::source_capsule_rejects_extra_members_symlinks_and_missing_evidence',
    'transport_tests::full_replay_requires_exact_typed_29_node_64_edge_topology',
    'transport_tests::full_replay_cannot_change_source_images_methods_or_authorization_identity',
    'transport_tests::full_replay_does_not_relax_no_fit_mode',
    'transport_tests::a_harmonisation_requires_exact_six_sources_and_one_method',
    'transport_tests::a_harmonisation_rejects_fit_sql_other_plugins_and_source_substitution',
    'transport_tests::a_harmonisation_requires_all_six_unique_input_bindings',
    'transport_tests::a_harmonisation_cannot_be_relabelled_synthetic',
    'transport_tests::a_raw_requires_exact_nine_sources_and_one_no_mr_method',
    'transport_tests::a_raw_rejects_changed_panel_source_digest_manifest_and_plugins',
    'transport_tests::a_raw_requires_all_nine_unique_input_bindings',
    'transport_tests::a_raw_cannot_be_relabelled_synthetic_or_other_no_fit_scope',
    'transport_tests::synthetic_scope_rejects_renamed_families_with_locked_kinds',
    'transport_tests::synthetic_manifest_kinds_cannot_hide_locked_nodes_by_renaming',
    'transport_tests::a_raw_sources_require_exact_canonical_readonly_mount_and_port_roles',
}


def validate_guard_inventory(text, execution):
    observed = re.findall(r'^test (\S+) \.\.\. ok$', text, re.MULTILINE)
    require(len(GUARDS) == EXPECTED_GUARD_COUNT and type(execution.get('exit')) is int and execution['exit'] == 0 and
        len(observed) == EXPECTED_GUARD_COUNT and len(set(observed)) == EXPECTED_GUARD_COUNT and set(observed) == GUARDS and
        execution.get('required_tests') == sorted(GUARDS) and execution.get('observed_passed_tests') == observed and
        f'test result: ok. {EXPECTED_GUARD_COUNT} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' in text,
        'All exact frozen guards must have actually executed without skipped or failed cases')


def checked_build(archives, runner, record, seal):
    require(isinstance(PROBE_SHA, str) and re.fullmatch('[0-9a-f]{64}', PROBE_SHA) and
        len(GUARDS) == EXPECTED_GUARD_COUNT, 'Merged guard source is not yet frozen; execution unavailable')
    runner, record = regular(runner), regular(record)
    archive = next((parent for parent in record.parents if re.fullmatch('[0-9a-f]{32}', parent.name) and
        parent.parent == archives), None)
    require(archive is not None, 'Literal sealed build archive required')
    checked = verify_archive(archives, archive.name, seal)
    require(checked['positive_worker_exit_verified'], 'Build worker must have recorded integer exit zero')
    artifacts = archive / 'artifacts'
    require(runner.parent == record.parent and runner.is_relative_to(artifacts) and record.is_relative_to(artifacts),
        'Runner and build record must belong to the same sealed build directory')
    for member in [runner, record]:
        require(member.relative_to(artifacts).as_posix() in checked['member_identities'], 'Unsealed build member')
    build = json.loads(record.read_text())
    require(type(build.get('actual_build_exit')) is int and build['actual_build_exit'] == 0 and
        build.get('parent_commit') == PARENT and build.get('probe_sha256') == PROBE_SHA and
        build.get('changed_paths') == ['crates/container-plugin/examples/official_plugin_dag.rs'] and
        build.get('source_unchanged') is True and re.fullmatch('[0-9a-f]{40}', build.get('engine_commit', '')) and
        build.get('containers_started') is False and build.get('real_study_fitted') is False and
        build.get('production_restarted') is False and build.get('g0_granted') is False,
        'Exact reviewed parent and no-fit frozen-guard build required')
    expected = build['executables']['runner']
    require(expected['executable'] == runner.name == 'official_plugin_dag' and digest(runner) == expected['sha256'],
        'Actual runner bytes differ from build')
    for name in ['probe.rs', 'candidate.json', 'guards-execution.json', 'guards.stdout.log', 'guard-tests',
                 'runner-build-exit.json', 'guards-build-exit.json', 'kernel-source-pins.json',
                 *['kernel-source/' + name for name in KERNEL_SOURCE_PINS]]:
        require((record.parent / name).relative_to(artifacts).as_posix() in checked['member_identities'],
            'Required build/guard artifact is absent from the sealed archive: ' + name)
    require(digest(record.parent / 'probe.rs') == PROBE_SHA, 'Actual compiled probe source differs')
    candidate = json.loads((record.parent / 'candidate.json').read_text())
    require(all(candidate.get(key) == build[key] for key in ['engine_commit', 'parent_commit', 'probe_sha256',
        'git_tree', 'changed_paths']), 'Candidate and actual build identities differ')
    kernel = build.get('kernel_source_pins')
    receipt = json.loads((record.parent / 'kernel-source-pins.json').read_text())
    require(candidate.get('kernel_source_pins') == KERNEL_SOURCE_PINS and isinstance(kernel, dict) and
        set(kernel) == set(KERNEL_SOURCE_PINS) and receipt.get('parent_commit') == PARENT and
        receipt.get('files') == kernel and receipt.get('exported_sources_equal_committed_parent') is True and
        receipt.get('old_sdk_fallback_allowed') is False and build.get('old_sdk_fallback_allowed') is False,
        'Exact fixed native memory source evidence required; no old SDK fallback')
    for name, checksum in KERNEL_SOURCE_PINS.items():
        snapshot = regular(record.parent / 'kernel-source' / name)
        require(kernel[name] == dict(sha256=checksum, bytes=snapshot.stat().st_size) and digest(snapshot) == checksum,
            'Sealed native memory source snapshot differs from the reviewed engine')
    guard_executable = build['executables']['guards']
    require(guard_executable['executable'] == 'guard-tests' and
        digest(record.parent / 'guard-tests') == guard_executable['sha256'], 'Actual guard executable differs')
    for name in ['runner-build-exit.json', 'guards-build-exit.json']:
        value = json.loads((record.parent / name).read_text())
        require(type(value.get('exit')) is int and value['exit'] == 0, 'Actual compilation failed')
    execution = json.loads((record.parent / 'guards-execution.json').read_text())
    require(execution['stdout_sha256'] == digest(record.parent / 'guards.stdout.log'), 'Actual guard log changed')
    validate_guard_inventory((record.parent / 'guards.stdout.log').read_text(), execution)
    return build, dict(session=archive.name, manifest_sha256=seal, members=checked['files'],
        bytes=checked['bytes'], runner_sha256=digest(runner), guard_count=EXPECTED_GUARD_COUNT, original_parent=PARENT,
        kernel_source_pins=kernel)


def executable_copy(original, temporary):
    original = regular(original)
    before = file_identity(original)
    target = temporary / 'official_plugin_dag'
    with original.open('rb') as incoming, target.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    target.chmod(0o700)
    require(digest(target) == before['sha256'] and file_identity(original) == before,
        'Owned executable copy must preserve the sealed original bytes and identity')
    return target, before


def file_identity(path):
    path = regular(path)
    before = path.stat()
    checksum = digest(path)
    after = path.stat()
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(signature(before) == signature(after), 'Regular evidence file changed during hashing')
    return dict(bytes=after.st_size, sha256=checksum, identity=list(signature(after)))


def install_backend_launcher(prefix, temporary, output):
    original = regular(Path(os.environ['AUTONOMICS_PODMAN_PROGRAM']))
    owner = regular(OWNER)
    owner_identity = file_identity(owner)
    require(owner_identity['sha256'] == OWNER_SHA and prefix ==
        [str(original), *json.loads(owner.read_text())['runtime_backend']] and len(prefix) > 1 and
        all(isinstance(value, str) and value and '\0' not in value for value in prefix),
        'Launcher must forward exactly the inspected owner backend through the original managed shim')
    directory = temporary / 'frozen-a-owner-backend-bin'
    directory.mkdir(mode=0o700)
    launcher = directory / 'podman'
    script = '''#!/usr/bin/python3
import os
import sys

PREFIX = __PREFIX__
if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
    print('explicit Podman operation required; backend override refused', file=sys.stderr)
    raise SystemExit(125)
os.execv(PREFIX[0], [*PREFIX, *sys.argv[1:]])
'''.replace('__PREFIX__', repr(prefix))
    with launcher.open('x') as handle:
        handle.write(script)
    launcher.chmod(0o700)
    previous_path = os.environ.get('PATH', '/usr/bin:/bin')
    os.environ['PATH'] = str(directory) + os.pathsep + previous_path
    receipt = dict(launcher_path=str(launcher), launcher=file_identity(launcher), original_shim_path=str(original),
        original_shim=file_identity(original), owner=owner_identity, backend=prefix[1:],
        prior_path_sha256=hashlib.sha256(previous_path.encode()).hexdigest(),
        current_worker_path_sha256=hashlib.sha256(os.environ['PATH'].encode()).hexdigest(),
        original_managed_program_unchanged=os.environ['AUTONOMICS_PODMAN_PROGRAM'] == str(original),
        shared_or_parent_environment_modified=False, containers_started=False)
    verify_backend_launcher(receipt)
    write(output / 'backend-launcher.json', receipt)
    return receipt


def verify_backend_launcher(receipt):
    launcher = regular(Path(receipt['launcher_path']))
    original = regular(Path(receipt['original_shim_path']))
    require(file_identity(launcher) == receipt['launcher'] and file_identity(original) == receipt['original_shim'] and
        file_identity(OWNER) == receipt['owner'] and receipt['owner']['sha256'] == OWNER_SHA and
        os.environ.get('AUTONOMICS_PODMAN_PROGRAM') == str(original) and
        os.environ.get('PATH', '').split(os.pathsep)[0] == str(launcher.parent),
        'Owned backend launcher, owner, original managed shim or worker PATH changed')


def checked_task_receipts(work, nodes):
    root = work / 'task-receipts'
    require(root.is_dir() and root.resolve() == root and not root.is_symlink(), 'Owned task receipt root required')
    directories = list(root.iterdir())
    require(len(directories) == len(nodes) and all(path.is_dir() and not path.is_symlink() and
        re.fullmatch(r'[0-9]+-[0-9]+-[0-9]+', path.name) for path in directories),
        'Exactly one owned attempt directory per actual graph node required')
    observed = {}
    for directory in directories:
        task_path, attempt_path, status_path = [regular(directory / name) for name in ['task.json', 'attempt.json', 'status.json']]
        task = json.loads(task_path.read_text())
        attempt = json.loads(attempt_path.read_text())
        status = json.loads(status_path.read_text())
        identifier = task.get('spec', {}).get('id')
        require(identifier in nodes and identifier not in observed, 'Owned task receipt ID is missing or duplicated')
        node = nodes[identifier]
        execution = node.get('execution')
        require(isinstance(execution, dict) and isinstance(task.get('resources'), dict) and
            task['spec'].get('kind') == node['node_type'] and
            attempt.get('task_id') == identifier and attempt.get('executor') == 'local' and
            attempt.get('status') == status.get('status') == node['status'] and
            type(attempt.get('exit_code')) is int and attempt['exit_code'] == execution.get('exit_code') and
            type(execution.get('exit_code')) is int and attempt.get('workspace') == execution.get('workspace') == str(directory) and
            attempt.get('task_manifest', {}).get('path') == execution.get('task_manifest', {}).get('path') == str(task_path) and
            attempt['task_manifest'].get('fingerprint', {}).get('size') == task_path.stat().st_size,
            'Actual node, owned task manifest and terminal attempt receipt differ')
        observed[identifier] = dict(status=node['status'], exit_code=attempt['exit_code'],
            actual_task_resources=task.get('resources'),
            files={path.name: file_identity(path) for path in [task_path, attempt_path, status_path]})
    require(set(observed) == set(nodes), 'Every actual node needs its own terminal attempt receipt')
    write(work / 'task-receipts-verification.json', observed)
    return observed


def validate_memory_report(report):
    memory = report.get('first_run', {}).get('resource', {}).get('memory', {})
    peak = memory.get('peak')
    require(memory.get('enabled') is True and memory.get('source') == 'cgroup_v2' and memory.get('error') is None and
        memory.get('trigger') is None and type(memory.get('sample_count')) is int and memory['sample_count'] > 0 and
        memory.get('threshold_ratio') == 0.9 and memory.get('sample_interval_ms') == 250 and
        isinstance(peak, dict) and peak.get('source') == 'cgroup_v2' and
        type(peak.get('limit_bytes')) is int and peak['limit_bytes'] > 0 and
        all(type(peak.get(name)) is int and peak[name] >= 0 for name in ['charged_bytes', 'usage_bytes']) and
        peak['usage_bytes'] <= peak['charged_bytes'], 'Actual repaired cgroup memory guard observation required')
    return memory


def stopped_owned_containers(prefix, output, permanent):
    session = permanent.parent.name
    require(re.fullmatch('[0-9a-f]{32}', session), 'Literal current managed session required')
    path = regular(permanent / 'container-intents.json')
    before = file_identity(path)
    value = json.loads(path.read_text())
    require(value.get('session') == session and len(value.get('intents', [])) == 2 and
        len({row['token'] for row in value['intents']}) == 2, 'Exactly two owned method intents required')
    owner = json.loads(regular(OWNER).read_text())
    observations = []
    for row in value['intents']:
        require(re.fullmatch('[0-9a-f]{32}', row['token']) and row['backend'] in
            [owner['runtime_backend'], [*owner['runtime_backend'], '--cgroup-manager=cgroupfs']],
            'Exact recorded backend and managed intent token required')
        command = [prefix[0], *row['backend'], 'ps', '-a', '--filter', 'label=autonomics.validation.session=' + session,
            '--filter', 'label=autonomics.validation.intent=' + row['token'], '--format=json']
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0 and json.loads(result.stdout) == [], 'Owned method container is not proven stopped')
        observations.append(dict(token=row['token'], backend=row['backend'], actual_exit=result.returncode,
            command=command, containers_remaining=0))
    require(file_identity(path) == before, 'Managed intent inventory changed during stoppage observation')
    write(output / 'owned-container-stop-observations.json', dict(session=session, intents=observations,
        whole_managed_worker_stoppage_not_yet_certified=True, global_container_idle_claimed=False))
    return observations


def job_for(work, source):
    nodes = [dict(id='input' + str(index), kind='file_reference', spec=dict(
        path='vfs:///input' + str(index) + '.input', format='file', hash_content=True)) for index in range(6)]
    nodes.append(dict(id='harmonisation', kind=METHOD, spec={}))
    return dict(scope=SCOPE, run_root=str(work), plugin_manifest=str(source / 'manifest.toml'),
        expected_plugin_name='frozen-a-harmonisation', plugin_manifest_sha256=PINS['manifest.toml'],
        script_sha256={'scripts/harmonise.R': PINS['scripts/harmonise.R']}, panel_overrides=[],
        panel_manifest_sha256={}, bundles=[], additional_plugins=[], nodes=nodes,
        edges=[{'from': 'input' + str(index), 'from_port': 0, 'to': 'harmonisation', 'to_port': index}
               for index in range(6)])


def validate_job(job):
    require(job.get('scope') == SCOPE and job.get('expected_plugin_name') == 'frozen-a-harmonisation' and
        job.get('plugin_manifest_sha256') == PINS['manifest.toml'] and
        job.get('script_sha256') == {'scripts/harmonise.R': PINS['scripts/harmonise.R']} and
        job.get('panel_overrides') == [] and job.get('panel_manifest_sha256') == {} and
        job.get('bundles') == [] and job.get('additional_plugins') == [], 'Exact no-fit official A source scope required')
    expected = job_for(Path(job['run_root']), Path(job['plugin_manifest']).parent)
    require(job.get('nodes') == expected['nodes'] and job.get('edges') == expected['edges'],
        'Exactly six fixed source references, one harmonisation node and six distinct port bindings required')


def validate_report(report, job, build, *, negative):
    validate_job(job)
    records = report.get('first_run', {}).get('nodes', [])
    require(isinstance(records, list) and len(records) == 7 and len({node['id'] for node in records}) == 7 and
        {node['id'] for node in records} == {node['id'] for node in job['nodes']}, 'Exact actual seven-node report required')
    require(report.get('scope') == 'REAL_LOCKED_LEGACY_A_HARMONISATION_NO_FIT' and
        report.get('engine_source_revision') == build['engine_commit'] and report.get('input_hashing') == 'ContentRequired' and
        type(report.get('max_concurrency')) is int and report['max_concurrency'] == 1 and
        report.get('incremental') is False and report.get('native_statistical_factories_registered') is False and
        report.get('original_manifest_sha256') == PINS['manifest.toml'] and
        report.get('plugin_name') == 'frozen-a-harmonisation' and report.get('additional_plugin_identities') == [] and
        report.get('current_daemon_verified') is False and report.get('explicit_replay_scope_allows_fit') is False and
        report.get('scientific_authorized') is False and report.get('g0_granted') is False,
        'Actual graph source, method, concurrency or authority differs')
    nodes = {node['id']: node for node in records}
    require(all(nodes[record['id']].get('node_type') == record['kind'] for record in job['nodes']),
        'Actual registered node kinds differ from the reviewed job')
    require(all(nodes['input' + str(index)]['status'] == 'success' and
        nodes['input' + str(index)].get('reused') is False for index in range(6)),
        'Every actual file reference must freshly succeed')
    method = nodes['harmonisation']
    require(method.get('reused') is False, 'The method must execute; cache reuse is not fresh proof')
    if not negative:
        execution = method.get('execution')
        require(method['status'] == 'success' and isinstance(execution, dict) and
            type(execution.get('exit_code')) is int and execution['exit_code'] == 0 and execution.get('image') == IMAGE and
            execution.get('image_digest') == IMAGE.split('@', 1)[1] and not report['first_run']['errors'],
            'Positive proof requires actual successful official method execution')
    else:
        require(method['status'] == 'failed' and report['first_run']['errors'] and not method['port_assignments'],
            'Negative source guard must fail without publishing normal output assignments')
    return nodes


def validate_provenance(value, before):
    require(value.get('scope') == 'FROZEN_39_IV_LEGACY_HARMONISATION_ONLY_NOT_RAW_QC_PLINK_MR_OR_G0' and
        value.get('input_sha256') == [before[name]['sha256'] for name in INPUTS] and
        value.get('input_bytes') == [before[name]['bytes'] for name in INPUTS] and
        value.get('adapter_sha256') == PINS['scripts/harmonise.R'] and value.get('original_scientific_code_sha256') == SOURCE_SHA and
        value.get('qualify_A_block_sha256') == BLOCK_SHA and value.get('original_qualify_A_branch_evaluated') is True and
        value.get('R') == '4.6.1' and value.get('TwoSampleMR') == '0.7.11' and 'TwoSampleMR_RemoteSha' in value and
        value['TwoSampleMR_RemoteSha'] is None and
        value.get('package_description_sha256') == '911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531' and
        type(value.get('package_namespace_function_count')) is int and value['package_namespace_function_count'] == 171 and
        value.get('package_namespace_aggregate_sha256') == '127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73' and
        value.get('source_commit_supported_by_frozen_host_identity') == 'd4df21929fdabeb2f89686ffaad0db5f56973d64' and
        value.get('package_identity_proof_session') == IDENTITY_SESSION and
        value.get('package_identity_proof_manifest_sha256') == IDENTITY_SEAL and
        type(value.get('n_clumped')) is int and value['n_clumped'] == 39 and
        type(value.get('n_qualified')) is int and value['n_qualified'] == 39 and value.get('seed') == 432202610 and
        value.get('additional_config_envelope_checked_without_reselection') is True and
        all(value.get(name) is False for name in ['raw_GWAS_QC_reexecuted', 'PLINK_or_LD_reexecuted',
            'MR_estimates_computed', 'original_full_project_verifier_executed', 'scientific_authorization_granted',
            'formal_scientific_pass_granted', 'G0']), 'Complete runtime/source/null-metadata and false-authority provenance required')


def graph(runner, build, work, job, definition, *, negative):
    validate_job(job)
    write(work / 'job.json', job)
    admission = subprocess.run([str(runner), '--validate-job', str(work / 'job.json')],
        capture_output=True, text=True, timeout=60)
    (work / 'admission.stdout').write_text(admission.stdout)
    (work / 'admission.stderr').write_text(admission.stderr)
    require(admission.returncode == 0, 'Guarded no-execution job validation failed')
    admitted = json.loads(admission.stdout)
    require(admitted.get('scope') == SCOPE and admitted.get('job_validated_without_execution') is True and
        admitted.get('containers_started') is False and admitted.get('scientific_results_computed') is False and
        admitted.get('g0_granted') is False, 'Actual no-execution admission receipt differs')
    run = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=600,
        env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
    (work / 'runner.stdout').write_text(run.stdout)
    (work / 'runner.stderr').write_text(run.stderr)
    write(work / 'runner-exit.json', dict(actual_exit=run.returncode))
    require(run.returncode == 0, 'Guarded graph runner failed before valid reporting')
    report = json.loads((work / 'dag-report.json').read_text())
    nodes = validate_report(report, job, build, negative=negative)
    memory = validate_memory_report(report)
    receipts = checked_task_receipts(work, nodes)
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    method = nodes['harmonisation']
    for index in range(6):
        assignments = nodes['input' + str(index)]['port_assignments']
        require(set(assignments) == {'0'}, 'Each file reference must publish exactly one source port')
        assigned = assignments['0']
        original = regular(work / ('input' + str(index) + '.input'))
        require(assigned['path'] == 'vfs:///' + original.name and assigned['format'] == 'file' and
            assigned['fingerprint']['size'] == original.stat().st_size and
            assigned['fingerprint']['content_hash'] == 'sha256:' + digest(original),
            'Actual source reference does not retain its exact role/path/content identity')
    bindings = dispatched_bindings(work, method, nodes, job['edges'], scratch)
    require(len(bindings) == 6 and {row['to_port'] for row in bindings} == set(range(6)), 'All six dispatched bindings required')
    for index in range(6):
        bound = next(item for item in method['inputs'] if item['to_port'] == index)
        reference = nodes['input' + str(index)]['port_assignments']['0']
        require(bound.get('kind') == 'File' and bound.get('path') == reference['path'] and
            bound['fingerprint']['content_hash'] == reference['fingerprint']['content_hash'],
            'Dispatched binding must retain its exact source role and content hash')
    ports = []
    if negative:
        stderr = expected_refusal(method, IMAGE, 'Only the exact six frozen harmonisation inputs are supported', scratch)
        shutil.copyfile(stderr, work / 'expected-refusal.stderr')
        normal = [port['path'] for port in definition['ports']['outputs'][:-1]]
        require(not any(list(root.rglob(name)) for root in [work / 'artifacts', scratch] for name in normal),
            'Failed source guard published normal results')
    else:
        ports = actual_ports(work, definition, method, scratch)
    require(scratch.is_dir() and not scratch.is_symlink(), 'Actual owned execution workspace required')
    require(not any(path.is_symlink() for path in scratch.rglob('*')), 'Execution archive cannot follow source aliases')
    shutil.copytree(scratch, work / 'archived-execution-workspaces', symlinks=False)
    write(work / 'graph-verification.json', dict(nodes=7, edges=6, actual_input_bindings=bindings,
        actual_output_ports=[dict(port=index, name=path.name, bytes=path.stat().st_size, sha256=digest(path))
            for index, path in enumerate(ports)], expected_source_refusal=negative,
        actual_owned_task_receipts=len(receipts), actual_native_memory_guard=memory,
        plugin_resource_to_native_budget_mapping_verified=False,
        current_daemon_verified=False, raw_QC_or_PLINK_proven=False, MR_estimates_computed=False, g0_granted=False))
    return ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--build-seal', required=True)
    arguments = parser.parse_args()
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-harmonisation-dag'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    build, build_receipt = checked_build(archives, arguments.runner, arguments.build_record, arguments.build_seal)
    write(output / 'verified-build.json', build_receipt)
    runner, runner_identity = executable_copy(arguments.runner, Path(os.environ['TMPDIR']))
    direct = verify_archive(archives, DIRECT_SESSION, DIRECT_SEAL)
    identity = verify_archive(archives, IDENTITY_SESSION, IDENTITY_SEAL)
    require(direct['positive_worker_exit_verified'] and identity['positive_worker_exit_verified'], 'Prior direct/identity proof must have actual zero exits')
    before = source_records()
    source = output / 'source'
    source.mkdir()
    for name, expected in PINS.items():
        original = regular(FAMILY / name)
        data = subprocess.check_output(['git', '-C', str(ROOT), 'show', REVISION + ':research-adapters/frozen-a-harmonisation/' + name])
        require(hashlib.sha256(data).hexdigest() == expected == digest(original), 'Current source differs from fixed published Git blob')
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    require(manifest['plugin_name'] == 'frozen-a-harmonisation' and manifest['image']['reference'] == IMAGE and
        len(manifest['nodes']) == 1 and manifest['nodes'][0]['kind'] == METHOD, 'Exact official single-kind manifest required')
    definition = manifest['nodes'][0]
    require(len(definition['ports']['inputs']) == 6 and len(definition['ports']['outputs']) == 5 and
        not definition.get('params'), 'Exact six-input/five-output zero-parameter node required')
    resource_admission(output)
    prefix = inspected_backend(output)
    launcher = install_backend_launcher(prefix, Path(os.environ['TMPDIR']), output)
    results = []
    for label, negative in [('positive', False), ('wrong-config', True)]:
        work = output / label
        work.mkdir()
        for index, name in enumerate(INPUTS):
            target = work / ('input' + str(index) + '.input')
            shutil.copyfile(STUDY / name, target)
            require(digest(target) == before[name]['sha256'], 'Copied frozen input differs')
        if negative:
            config = work / 'input2.input'
            config.write_bytes(config.read_bytes() + b'\n')
        ports = graph(runner, build, work, job_for(work, source), definition, negative=negative)
        if not negative:
            value = json.loads(ports[3].read_text())
            validate_provenance(value, before)
            comparisons = []
            for index, name in enumerate(PRODUCTS):
                expected = Path(direct['artifact_root']) / 'permanent/frozen-a-harmonisation/positive' / name
                require(expected.relative_to(Path(direct['artifact_root'])).as_posix() in direct['member_identities'] and
                    ports[index].read_bytes() == expected.read_bytes() == (STUDY / AUDIT / name).read_bytes(),
                    'Complete actual DAG product differs from sealed direct/canonical bytes')
                comparisons.append(dict(name=name, bytes=ports[index].stat().st_size, sha256=digest(ports[index])))
            require(value['output_sha256'] == [item['sha256'] for item in comparisons] and
                'no MR estimates computed' in ports[4].read_text(), 'Actual output/provenance/log identity differs')
            write(work / 'product-comparison.json', dict(complete_products=comparisons, full_byte_equal=True))
        results.append(dict(case=label, nodes=7, edges=6, positive=not negative, expected_method_exit=2 if negative else 0,
            input_bindings=6, published_ports=len(ports)))
    stopped = stopped_owned_containers(prefix, output, Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']))
    verify_backend_launcher(launcher)
    require(file_identity(arguments.runner) == runner_identity and digest(runner) == runner_identity['sha256'] and
        before == source_records() and digest(OWNER) == OWNER_SHA and
        all(digest(FAMILY / name) == expected == digest(source / name) for name, expected in PINS.items()),
        'Original source, candidate or software owner changed during graph proof')
    post = original_postcheck(output)
    write(output / 'verification.json', dict(status='SCOPED_SEVEN_NODE_SIX_EDGE_OFFICIAL_HARMONISATION_DAG_PROVEN_NOT_DEPLOYED',
        source_revision=REVISION, source_sha256=PINS, build=build_receipt, official_reference_session=DIRECT_SESSION,
        official_reference_seal=DIRECT_SEAL, package_identity_session=IDENTITY_SESSION, package_identity_seal=IDENTITY_SEAL,
        cases=results, actual_positive_nodes=7, actual_positive_edges=6, actual_positive_outputs=5,
        actual_owned_task_receipts=14, owned_stopped_containers=len(stopped), sealed_runner_unchanged=True,
        plugin_resource_to_native_budget_mapping_verified=False,
        all_three_complete_products_byte_equal=True, canonical_inputs_unchanged=True, original_post_verifier=post,
        raw_GWAS_QC_or_PLINK_proven=False, MR_estimates_computed=False, production_restarted=False,
        current_daemon_verified=False, scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
