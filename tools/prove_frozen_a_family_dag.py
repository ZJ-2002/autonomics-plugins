"""Prove complete frozen A families through actual isolated official-plugin DAGs."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import build_frozen_a_family_probe as builder
from tools import prove_frozen_a_family_runtime as runtime
from tools.prove_frozen_a_harmonisation_dag import (
    checked_task_receipts, file_identity, install_backend_launcher, validate_memory_report,
    verify_backend_launcher,
)
from tools.prove_locked_b_source_transport import actual_ports, dispatched_bindings, expected_refusal
from tools.reconcile_ab_evidence_index import verify_archive

SCOPE = 'LOCKED_A_COMPLETE_FAMILY_TECHNICAL_NO_MR_NOT_G0'
REPORT_SCOPE = 'LOCKED_COMPLETE_A_FAMILY_TECHNICAL_NO_MR'
DIRECT_SESSION = '1dd93528d56d4cbe8a18e63247b0c2ee'
DIRECT_SEAL = '93fdedb6434a3ab570cec95e400909ef8b12408819be1acc33732b01dfbf0ccb'
DIRECT_DRIVER_SHA = '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f'
BUILDER_SHA = '49f251098188d15d7445b103e79962cd48e607fbdaa5d8ce9cf43c5782071847'
PINS = {
    'frozen-a-family-assembly': {
        'manifest.toml': 'a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf',
        'scripts/family.py': '3370bf9a604de0c3e6acab9e1e7617f7caba579c6630e96f17e0d2f4c002d1ba',
    },
    'frozen-a-family-adjustment': {
        'manifest.toml': '55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da',
        'scripts/adjust.R': 'debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412',
    },
}
SCENARIOS = (*runtime.contract.SCENARIOS, 'REAL_FROZEN_NA_LEDGER')
STAGES = dict(zip(('assemble', 'adjust', 'publish'), runtime.KINDS, strict=True))
REPORT_FILES = (
    'job.json', 'admission.stdout', 'admission.stderr', 'admission-exit.json',
    'runner.stdout', 'runner.stderr', 'runner-exit.json', 'dag-report.json',
    'graph-verification.json', 'task-receipts-verification.json',
)
require = runtime.require
write = runtime.write
digest = runtime.digest
regular = runtime.regular


def definitions():
    return {kind: dict(value['node'], expected_image=value['image'])
        for kind, value in runtime.definitions().items()}


def validate_guard_inventory(log, execution):
    observed = re.findall(r'^test (\S+) \.\.\. ok$', log, re.MULTILINE)
    require(len(builder.GUARDS) == 37 and len(observed) == len(set(observed)) == 37 and
        set(observed) == builder.GUARDS and type(execution.get('exit')) is int and execution['exit'] == 0 and
        execution.get('required_tests') == sorted(builder.GUARDS) and execution.get('observed_passed_tests') == observed and
        'test result: ok. 37 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' in log,
        'All exact thirty-seven guards must actually execute; no skip or filtered pass')


def checked_probe(output, runner, record, seal):
    require(digest(Path(builder.__file__)) == BUILDER_SHA, 'Reviewed dedicated builder changed')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    runner, record = regular(runner), regular(record)
    archive = next((parent for parent in record.parents if parent.parent == archives and
        re.fullmatch('[0-9a-f]{32}', parent.name)), None)
    require(archive is not None and runner.parent == record.parent, 'One sealed dedicated build required')
    verified = verify_archive(archives, archive.name, seal)
    require(verified['positive_worker_exit_verified'], 'Actual build worker exit zero required')
    artifacts = Path(verified['artifact_root'])
    expected_names = ['driver.py', 'probe.rs', 'build-record.json', 'candidate.json', 'candidate.commit',
        'committed-source-files.json', 'active-git-preservation.json', 'kernel-source-pins.json',
        'frozen_a_family_dag', 'guard-tests', 'guards-execution.json', 'guards.stdout.log',
        'runner-build-exit.json', 'guards-build-exit.json',
        *['kernel-source/' + name for name in builder.KERNEL_SOURCE_PINS]]
    require(record.name == 'build-record.json' and runner.name == builder.EXAMPLE and
        all((record.parent / name).relative_to(artifacts).as_posix() in verified['member_identities']
            for name in expected_names), 'Required dedicated build artifacts must all be sealed')
    value = json.loads(record.read_text())
    require(type(value.get('actual_build_exit')) is int and value['actual_build_exit'] == 0 and
        value.get('parent_commit') == builder.PARENT and value.get('probe_sha256') == builder.PROBE_SHA and
        value.get('changed_paths') == [builder.SOURCE_PATH] and value.get('source_unchanged') is True and
        value.get('old_sdk_fallback_allowed') is False and
        re.fullmatch('[0-9a-f]{40}', value.get('engine_commit', '')) and
        all(value.get(name) is False for name in ['containers_started', 'real_study_fitted',
            'production_restarted', 'scientific_authorized', 'g0_granted']),
        'Exact fixed-engine dedicated source and actual successful compilation required')
    candidate = json.loads((record.parent / 'candidate.json').read_text())
    require(all(candidate.get(key) == value[key] for key in
        ['engine_commit', 'parent_commit', 'git_tree', 'probe_sha256', 'changed_paths']),
        'Build and immutable candidate disagree')
    raw_commit = (record.parent / 'candidate.commit').read_bytes()
    require(hashlib.sha1(b'commit ' + str(len(raw_commit)).encode() + b'\0' + raw_commit).hexdigest() ==
        value['engine_commit'] and raw_commit.startswith(('tree ' + value['git_tree'] + '\nparent ' +
        builder.PARENT + '\n').encode()), 'Exact raw candidate Git object required')
    require(digest(record.parent / 'probe.rs') == builder.PROBE_SHA and
        digest(record.parent / 'driver.py') == BUILDER_SHA, 'Compiled probe or builder source changed')
    inventory = json.loads((record.parent / 'committed-source-files.json').read_text())
    require(isinstance(inventory, dict) and len(inventory) == value['committed_source_files'] and
        inventory.get(builder.SOURCE_PATH) == builder.PROBE_SHA, 'Complete candidate source inventory required')
    preservation = json.loads((record.parent / 'active-git-preservation.json').read_text())
    require(preservation.get('active_head_and_index_unchanged') is True and
        preservation.get('before') == preservation.get('after') and
        Path(preservation.get('private_index', '')).name == 'frozen-a-family-probe.index',
        'Actual active Git HEAD/index preservation must be recorded')
    kernel = json.loads((record.parent / 'kernel-source-pins.json').read_text())
    require(candidate.get('kernel_source_pins') == builder.KERNEL_SOURCE_PINS and
        kernel.get('parent_commit') == builder.PARENT and kernel.get('files') == value['kernel_source_pins'] and
        kernel.get('exported_sources_equal_committed_parent') is True and
        kernel.get('old_sdk_fallback_allowed') is False, 'Exact repaired native source snapshots required')
    for name, checksum in builder.KERNEL_SOURCE_PINS.items():
        path = regular(record.parent / 'kernel-source' / name)
        require(digest(path) == checksum == inventory.get(name) and
            value['kernel_source_pins'][name] == dict(sha256=checksum, bytes=path.stat().st_size),
            'Native source, complete inventory and snapshot differ')
    for phase in ['runner', 'guards']:
        compiled = json.loads((record.parent / (phase + '-build-exit.json')).read_text())
        executable = regular(record.parent / value['executables'][phase]['executable'])
        require(type(compiled.get('exit')) is int and compiled['exit'] == 0 and
            digest(executable) == value['executables'][phase]['sha256'] and
            executable.name == (builder.EXAMPLE if phase == 'runner' else 'guard-tests'),
            'Actual compiler artifact or recorded exit differs')
    guard = json.loads((record.parent / 'guards-execution.json').read_text())
    log = (record.parent / 'guards.stdout.log').read_text()
    require(guard.get('stdout_sha256') == digest(record.parent / 'guards.stdout.log'), 'Actual guard log identity changed')
    validate_guard_inventory(log, guard)
    receipt = dict(session=archive.name, manifest_sha256=seal, files=verified['files'],
        bytes=verified['bytes'], engine_commit=value['engine_commit'], probe_sha256=builder.PROBE_SHA,
        runner_sha256=digest(runner), required_guards=37, all_members_rehashed=True)
    write(output / 'verified-build.json', receipt)
    return value, receipt


def make_job(work, case, source=None):
    require(case in SCENARIOS, 'Only three frozen technical family scenarios are supported')
    source = ROOT / 'research-adapters' if source is None else source
    python = source / 'frozen-a-family-assembly'
    r_family = source / 'frozen-a-family-adjustment'
    nodes = [dict(id='source' + str(index), kind='file_reference', spec=dict(
        path='vfs:///source' + str(index) + '.input', format='file', hash_content=True)) for index in range(9)]
    nodes.append(dict(id='request', kind='file_reference', spec=dict(
        path='vfs:///request.json', format='file', hash_content=True)))
    nodes.extend(dict(id=stage, kind=kind, spec={}) for stage, kind in STAGES.items())
    edges = [dict(from_node='source' + str(index), from_port=0, to='assemble', to_port=index)
        for index in range(9)]
    edges.append(dict(from_node='request', from_port=0, to='assemble', to_port=9))
    edges.extend(dict(from_node=node, from_port=port, to='adjust', to_port=target)
        for target, (node, port) in enumerate([('assemble', 1), ('assemble', 0), ('assemble', 2), ('source8', 0)]))
    edges.extend(dict(from_node=node, from_port=port, to='publish', to_port=target)
        for target, (node, port) in enumerate([('assemble', 0), ('assemble', 1), ('assemble', 2),
            ('adjust', 0), ('adjust', 1), ('adjust', 2), ('source0', 0), ('source1', 0)]))
    return dict(scope=SCOPE, family_case=case, run_root=str(work), plugin_manifest=str(python / 'manifest.toml'),
        expected_plugin_name='frozen-a-family-assembly',
        plugin_manifest_sha256=PINS['frozen-a-family-assembly']['manifest.toml'],
        script_sha256={'scripts/family.py': PINS['frozen-a-family-assembly']['scripts/family.py']},
        panel_overrides=[], panel_manifest_sha256={}, bundles=[], additional_plugins=[dict(
            plugin_manifest=str(r_family / 'manifest.toml'), expected_plugin_name='frozen-a-family-adjustment',
            plugin_manifest_sha256=PINS['frozen-a-family-adjustment']['manifest.toml'],
            script_sha256={'scripts/adjust.R': PINS['frozen-a-family-adjustment']['scripts/adjust.R']},
            panel_overrides=[])], nodes=nodes, edges=[{'from': edge.pop('from_node'), **edge} for edge in edges])


def source_facts(work, case):
    facts = []
    for index, (_, expected_size, expected_sha) in enumerate(runtime.contract.SOURCES):
        path = regular(work / ('source' + str(index) + '.input'))
        value = file_identity(path)
        stat = path.stat()
        require(value['bytes'] == expected_size and value['sha256'] == expected_sha and stat.st_uid == os.getuid(),
            'All nine bounded temporary source copies must equal the original frozen roles')
        facts.append(dict(port=index, filename=path.name, bytes=expected_size, sha256=expected_sha,
            device=stat.st_dev, inode=stat.st_ino, owner=stat.st_uid,
            mtime=stat.st_mtime_ns // 10**9, mtime_nsec=stat.st_mtime_ns % 10**9,
            ctime=stat.st_ctime_ns // 10**9, ctime_nsec=stat.st_ctime_ns % 10**9))
    request = regular(work / 'request.json')
    value = file_identity(request)
    stat = request.stat()
    scope = runtime.contract.LEDGER if case == 'REAL_FROZEN_NA_LEDGER' else runtime.contract.SYNTHETIC
    return dict(case=case, request_scope=scope, source_files=facts,
        request_sha256=value['sha256'], request_bytes=value['bytes'], request_device=stat.st_dev,
        request_inode=stat.st_ino, request_owner=stat.st_uid,
        request_mtime=stat.st_mtime_ns // 10**9, request_mtime_nsec=stat.st_mtime_ns % 10**9,
        request_ctime=stat.st_ctime_ns // 10**9, request_ctime_nsec=stat.st_ctime_ns % 10**9,
        real_overlap_classes_assigned=False, scientific_authorization_granted=False, g0_granted=False)


def check_family_report(report, work, case, *, negative=False, expected_revision=None, job=None):
    job = make_job(work, case) if job is None else job
    expected_job = make_job(work, case, Path(job['plugin_manifest']).parent.parent)
    require(job == expected_job, 'Exact dedicated thirteen-node twenty-two-edge job required')
    records = report.get('first_run', {}).get('nodes', [])
    require(isinstance(records, list) and len(records) == len({node['id'] for node in records}) == 13 and
        {node['id'] for node in records} == {node['id'] for node in job['nodes']},
        'Actual report must include exactly thirteen unique frozen nodes')
    extra = job['additional_plugins'][0]
    require(report.get('scope') == REPORT_SCOPE and report.get('family_case') == case and
        report.get('input_hashing') == 'ContentRequired' and type(report.get('max_concurrency')) is int and
        report['max_concurrency'] == 1 and report.get('incremental') is False and
        report.get('plugin_name') == 'frozen-a-family-assembly' and
        report.get('original_manifest_sha256') == PINS['frozen-a-family-assembly']['manifest.toml'] and
        report.get('additional_plugin_identities') == [dict(plugin_name='frozen-a-family-adjustment',
            original_manifest_sha256=extra['plugin_manifest_sha256'], script_sha256=extra['script_sha256'], panels=[])] and
        report.get('effective_synthetic_manifest_sha256') is None and
        all(report.get(name) is False for name in ['current_daemon_verified', 'native_statistical_factories_registered',
            'explicit_replay_scope_allows_fit', 'real_overlap_classes_assigned', 'mr_computed',
            'panel_bindings_are_explicit_synthetic_overrides', 'scientific_authorized', 'g0_granted']) and
        (expected_revision is None or report.get('engine_source_revision') == expected_revision),
        'Actual method identity, scheduler policy or false-authority scope differs')
    facts = source_facts(work, case)
    require(report.get('frozen_family_source_facts_before') == facts == report.get('frozen_family_source_facts_after'),
        'Nine frozen input roles and request must retain full before/after identities')
    nodes = {node['id']: node for node in records}
    for entry in job['nodes']:
        node = nodes[entry['id']]
        require(node.get('node_type') == entry['kind'] and node.get('reused') is False,
            'Every node kind must match and no cached execution may stand in for this proof')
        if entry['kind'] == 'file_reference':
            require(node['status'] == 'success' and set(node['port_assignments']) == {'0'},
                'Every actual frozen reference must freshly publish one file port')
            assignment = node['port_assignments']['0']
            filename = work / entry['spec']['path'].removeprefix('vfs:///')
            require(assignment['path'] == entry['spec']['path'] and assignment['format'] == 'file' and
                assignment['fingerprint']['size'] == filename.stat().st_size and
                assignment['fingerprint']['content_hash'] == 'sha256:' + digest(filename),
                'Actual file reference changed its frozen role, path, format or complete content hash')
    if negative:
        require(nodes['assemble']['status'] == 'failed' and not nodes['assemble']['port_assignments'] and
            report['first_run']['errors'], 'The actual assembly guard must fail without normal output assignments')
        for stage in ['adjust', 'publish']:
            node = nodes[stage]
            require(node['status'] == 'skipped' and node.get('execution') is None and not node['port_assignments'] and
                node.get('skipped_because') == 'assemble',
                'Failed frozen assembly must causally block adjustment and publication without executing them')
    else:
        require(not report['first_run']['errors'], 'Positive family graph contains execution errors')
        methods = definitions()
        for stage, kind in STAGES.items():
            node = nodes[stage]
            execution = node.get('execution')
            image = methods[kind]['expected_image']
            require(node['status'] == 'success' and isinstance(execution, dict) and
                type(execution.get('exit_code')) is int and execution['exit_code'] == 0 and
                execution.get('image') == image and execution.get('image_digest') == image.split('@', 1)[1],
                'Positive family proof requires actual successful official image execution at all three stages')
    return nodes


def evidence_copy(work, destination, *, ports=None, nodes=None):
    require(work.resolve() == work and destination.resolve() == destination and not destination.exists(),
        'Distinct new unaliased permanent evidence destination required')
    destination.mkdir(mode=0o700)
    copied = {}
    def transfer(original, relative):
        original = regular(original)
        identity = file_identity(original)
        target = destination / relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Safe evidence member required')
        target.parent.mkdir(parents=True, exist_ok=True)
        with original.open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        require(digest(target) == identity['sha256'] and file_identity(original) == identity,
            'Evidence copy changed an original report or product')
        copied[str(relative)] = dict(bytes=identity['bytes'], sha256=identity['sha256'])
    for name in REPORT_FILES:
        transfer(work / name, name)
    for name in ['comparison.json', 'expected-refusal.stderr', 'expected-refusal.log']:
        if (work / name).exists():
            transfer(work / name, name)
    for directory in (work / 'task-receipts').iterdir():
        require(directory.is_dir() and not directory.is_symlink() and re.fullmatch('[0-9]+-[0-9]+-[0-9]+', directory.name),
            'Only owned actual attempt directories may enter permanent task evidence')
        for name in ['task.json', 'attempt.json', 'status.json']:
            transfer(directory / name, 'task-receipts/' + directory.name + '/' + name)
    for stage, products in (ports or {}).items():
        require(stage in STAGES and [path.name for path in products] == runtime.OUTPUTS[STAGES[stage]],
            'Exactly the four declared actual outputs per successful method required')
        for path in products:
            require(path.resolve().is_relative_to(work), 'Published product must remain inside its temporary graph root')
            transfer(path, stage + '/' + path.name)
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    for stage in STAGES:
        node = (nodes or {}).get(stage, {})
        if not isinstance(node.get('execution'), dict):
            continue
        for stream in ['stdout', 'stderr']:
            reference = node['execution'].get(stream + '_log')
            if reference is None:
                continue
            require(isinstance(reference, dict) and isinstance(reference.get('path'), str),
                'A present method log must have an explicit file reference')
            original = regular(Path(reference['path']))
            receipt = Path(node['execution']['workspace'])
            require(original.is_relative_to(scratch) or
                (receipt.parent == work / 'task-receipts' and original == receipt / (stream + '.log')),
                'Actual method log must remain in its own container scratch or exact owned task receipt')
            recorded = reference.get('fingerprint')
            if recorded is not None:
                require(recorded.get('size') == original.stat().st_size and
                    recorded.get('content_hash') in [None, 'sha256:' + digest(original)],
                    'Actual recorded method log identity changed')
            transfer(original, 'execution-logs/' + stage + '.' + stream)
    require(not any('source' + str(index) + '.input' in copied for index in range(9)) and
        not any(name.startswith('archived-execution') for name in copied),
        'Rebuildable frozen-source copies and entire execution workspaces must not enter evidence')
    write(destination / 'copied-evidence.json', dict(files=copied, required_source_copies_archived=False,
        scratch_workspace_archived=False, g0_granted=False))
    return copied


def graph(runner, build, work, job, methods, *, negative=False):
    write(work / 'job.json', job)
    admission = subprocess.run([str(runner), '--validate-job', str(work / 'job.json')],
        capture_output=True, text=True, timeout=90)
    (work / 'admission.stdout').write_text(admission.stdout)
    (work / 'admission.stderr').write_text(admission.stderr)
    write(work / 'admission-exit.json', dict(actual_exit=admission.returncode))
    require(admission.returncode == 0, 'Actual guarded family preflight failed before execution')
    admitted = json.loads(admission.stdout)
    require(admitted.get('scope') == SCOPE and admitted.get('family_case') == job['family_case'] and
        admitted.get('frozen_family_source_facts') == source_facts(work, job['family_case']) and
        admitted.get('job_validated_without_execution') is True and
        all(admitted.get(name) is False for name in ['containers_started', 'scientific_results_computed', 'g0_granted']),
        'Actual no-execution family admission receipt differs')
    execution = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=600,
        env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
    (work / 'runner.stdout').write_text(execution.stdout)
    (work / 'runner.stderr').write_text(execution.stderr)
    write(work / 'runner-exit.json', dict(actual_exit=execution.returncode))
    require(execution.returncode == 0, 'Actual family runner failed before terminal graph reporting')
    report = json.loads((work / 'dag-report.json').read_text())
    nodes = check_family_report(report, work, job['family_case'], negative=negative,
        expected_revision=build['engine_commit'], job=job)
    memory = validate_memory_report(report)
    executed = {identifier: node for identifier, node in nodes.items() if node['status'] != 'skipped'}
    receipts = checked_task_receipts(work, executed)
    require(len(receipts) == (11 if negative else 13), 'Only actually executed nodes may have terminal attempt receipts')
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    require(scratch.is_dir() and scratch.resolve() == scratch, 'Actual owned family execution scratch required')
    bindings = {}
    ports = {}
    for stage, kind in STAGES.items():
        node = nodes[stage]
        if node['status'] == 'skipped':
            continue
        bindings[stage] = dispatched_bindings(work, node, nodes, job['edges'], scratch)
        if negative:
            stderr = expected_refusal(node, methods[kind]['expected_image'],
                'Analysis IDs do not equal frozen family', scratch)
            shutil.copyfile(stderr, work / 'expected-refusal.stderr')
            require(stderr.parent.name == 'logs' and stderr.parent.parent.name == '.autonomics',
                'Actual failed method stderr must locate its exact owned container workspace')
            declared_log = regular(stderr.parents[2] / 'assembly.log')
            require(declared_log.is_relative_to(scratch) and declared_log.stat().st_size > 0 and
                'Analysis IDs do not equal frozen family' in declared_log.read_text(),
                'Failed assembly must also write its nonempty declared diagnostic log')
            shutil.copyfile(declared_log, work / 'expected-refusal.log')
            require(not any(list(directory.rglob(name)) for directory in [work / 'artifacts', scratch]
                for name in ['assembly.tsv', 'vectors.tsv', 'assembly-receipt.json',
                    'adjusted.tsv', 'adjustment.RDS', 'adjustment-receipt.json', 'family.tsv', 'family-vectors.tsv', 'family-audit.json']),
                'Failed membership guard published normal family or adjustment products')
        else:
            ports[stage] = actual_ports(work, methods[kind], node, scratch)
    require(sum(map(len, bindings.values())) == (10 if negative else 22), 'Every actually dispatched family edge needs staged-byte proof')
    write(work / 'graph-verification.json', dict(case=job['family_case'], expected_membership_refusal=negative,
        nodes=13, edges=22, actual_executed_nodes=len(receipts), actual_skipped_nodes=2 if negative else 0,
        actual_bindings=bindings, actual_published_ports=sum(map(len, ports.values())),
        actual_memory_guard=memory, plugin_resources_to_native_task_budget_proven=False,
        real_overlap_classes_assigned=False, mr_computed=False, resident_execution=False, g0_granted=False))
    return ports, nodes


def checked_direct(archives, output):
    checked = verify_archive(archives, DIRECT_SESSION, DIRECT_SEAL)
    require(checked['positive_worker_exit_verified'], 'Prior full actual direct proof must record actual exit zero')
    directory = Path(checked['artifact_root']) / 'permanent/frozen-a-family-runtime'
    require(digest(directory / 'driver.py') == DIRECT_DRIVER_SHA == digest(Path(runtime.__file__)),
        'Direct proof and reused current comparator must retain the exact reviewed driver identity')
    value = json.loads((directory / 'verification.json').read_text())
    require(value.get('status') == 'SCOPED_FROZEN_FAMILY_THREE_STAGE_DIRECT_RUNTIME_PROVEN_DAG_PENDING' and
        value.get('code_identities') == runtime.sources() and value.get('full_q_equal') == 2520 and
        value.get('full_official_RDS_vectors_read_back') == 18 and value.get('actual_method_containers') == 25 and
        len(value.get('expected_method_exit2_refusals', [])) == 16 and value.get('g0_granted') is False,
        'Exact three-stage source, complete official RDS/q and refusal prerequisite required')
    receipt = dict(session=DIRECT_SESSION, manifest_sha256=DIRECT_SEAL, files=checked['files'],
        bytes=checked['bytes'], all_members_rehashed=True, actual_DAG_executed=False)
    write(output / 'verified-direct-runtime.json', receipt)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--build-seal', required=True)
    arguments = parser.parse_args()
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    output = permanent / 'frozen-a-family-dag'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    resource_output = output / 'resources'
    resource_output.mkdir()
    runtime.resource_admission(resource_output)
    build, build_receipt = checked_probe(output, arguments.runner, arguments.build_record, arguments.build_seal)
    original_runner_identity = file_identity(arguments.runner)
    runner = temporary / builder.EXAMPLE
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    require(digest(runner) == original_runner_identity['sha256'], 'Owned temporary runner copy differs')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    direct = checked_direct(archives, output)
    oracle_vectors, oracle_reference, oracle = runtime.checked_oracle(archives)
    source_before = runtime.contract.source_records(runtime.contract.STUDY)
    code_before = runtime.sources()
    source = output / 'reviewed-adapters'
    for family, identities in PINS.items():
        for name, checksum in identities.items():
            original = regular(ROOT / 'research-adapters' / family / name)
            require(digest(original) == checksum, 'Exact reviewed actual method source required')
            target = source / family / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            require(digest(target) == checksum, 'Sealed adapter source copy differs')
    for name in ['r-runtime', 'python-runtime']:
        (output / name).mkdir()
    prefix = runtime.inspected_backend(output / 'r-runtime')
    runtime_archive, prerequisites = runtime.raw.prerequisite_archives(archives)
    require(prefix == runtime.raw.backend(output / 'python-runtime', runtime_archive),
        'Both actual official runtimes must use the same owner backend')
    launcher = install_backend_launcher(prefix, temporary, output)
    methods = definitions()
    edges = runtime.contract.read_table(runtime.contract.STUDY / runtime.contract.SOURCES[0][0])
    cases = []
    rds_paths = []
    for case, negative in [(case, False) for case in SCENARIOS] + [('BOUNDARY', True)]:
        label = 'foreign-id' if negative else case
        work = temporary / ('frozen-a-family-' + label.lower())
        work.mkdir(mode=0o700)
        for index, (relative, expected_size, checksum) in enumerate(runtime.contract.SOURCES):
            original = regular(runtime.contract.STUDY / relative)
            target = work / ('source' + str(index) + '.input')
            shutil.copyfile(original, target)
            require(target.stat().st_size == expected_size and digest(target) == checksum,
                'Temporary source payload differs from its exact frozen role')
        request = runtime.request_for(edges, case)
        if negative:
            request['edges'][0]['analysis_id'] = 'SYNTHETIC_FOREIGN_ID_NOT_IN_FROZEN_FAMILY'
        write(work / 'request.json', request)
        job = make_job(work, case, source)
        ports, nodes = graph(runner, build, work, job, methods, negative=negative)
        if not negative:
            runtime.compare_case(work, case, ports['assemble'], ports['adjust'], ports['publish'],
                oracle_vectors, oracle_reference)
            comparisons = []
            for stage, products in ports.items():
                for path in products:
                    if path.suffix not in ['.tsv', '.json']:
                        continue
                    reference = regular(direct / case / stage / path.name)
                    require(path.read_bytes() == reference.read_bytes(),
                        'Actual DAG complete table or scientific receipt differs from sealed direct execution')
                    comparisons.append(dict(stage=stage, name=path.name, bytes=path.stat().st_size, sha256=digest(path)))
            comparison = json.loads((work / 'comparison.json').read_text())
            comparison['actual_DAG_executed'] = True
            comparison['complete_direct_byte_comparisons'] = comparisons
            (work / 'comparison.json').unlink()
            write(work / 'comparison.json', comparison)
        destination = output / label
        copied = evidence_copy(work, destination, ports=ports, nodes=nodes)
        if not negative:
            rds_paths.append(destination / 'adjust/adjustment.RDS')
        cases.append(dict(case=case, label=label, nodes=13, edges=22, actual_executed_nodes=11 if negative else 13,
            actual_skipped_nodes=2 if negative else 0, actual_staged_bindings=10 if negative else 22,
            actual_published_ports=sum(map(len, ports.values())), expected_membership_refusal=negative,
            copied_evidence_files=len(copied), full_q_values_compared=0 if negative else 840))
    runtime.official_rds_readback(output, archives, rds_paths)
    stopped = runtime.stopped(prefix, permanent, output, 10)
    verify_backend_launcher(launcher)
    require(file_identity(arguments.runner) == original_runner_identity and digest(runner) == original_runner_identity['sha256'] and
        runtime.contract.source_records(runtime.contract.STUDY) == source_before and runtime.sources() == code_before,
        'Frozen canonical sources, sealed runner or reviewed method source changed')
    post = runtime.original_postcheck(output)
    write(output / 'verification.json', dict(status='SCOPED_COMPLETE_FROZEN_A_FAMILY_ISOLATED_DAG_PROVEN_NOT_DEPLOYED',
        build=build_receipt, direct_session=DIRECT_SESSION, direct_seal=DIRECT_SEAL, official_oracle=oracle,
        prerequisites=prerequisites, method_sources=code_before, frozen_source_identities=source_before,
        family_counts=runtime.contract.COUNTS, cases=cases, full_q_equal=2520, full_result_rows=1692,
        full_official_RDS_vectors_read_back=18, full_official_RDS_values_exact=2520,
        actual_owned_task_receipts=50, actual_staged_bindings=76, owned_method_containers_stopped=len(stopped),
        canonical_sources_unchanged=True, rebuildable_source_payloads_archived=False,
        entire_execution_scratch_archived=False, original_post_verifier=post,
        original_fixed_candidate_denominator=120, new_scientific_candidate_slots_added=0,
        original_adjust_pvalues_and_boolean_test_reimplemented_or_certified=False,
        real_overlap_classes_assigned=False, new_MR_estimates_computed=False,
        production_restarted=False, resident_execution_proven=False, scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
