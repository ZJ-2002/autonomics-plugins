"""Verify the already-seen O2 A chain in an isolated, source-bound execution DAG."""

import argparse
from contextlib import contextmanager
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
from tools import build_frozen_a_legacy_connected_probe as builder
from tools import prove_frozen_a_family_runtime as family
from tools import prove_frozen_a_input_qualification as raw
from tools import prove_frozen_a_input_qualification_dag as raw_dag
from tools import prove_frozen_a_legacy_family_gate as gate
from tools import prove_frozen_a_legacy_mr_runtime as mr
from tools import frozen_a_legacy_connected_runtime as oci
from tools.prove_frozen_a_harmonisation_dag import checked_task_receipts, file_identity, validate_memory_report
from tools.prove_locked_b_source_transport import actual_ports, expected_refusal
from tools.reconcile_ab_evidence_index import verify_archive

SCOPE = 'LOCKED_A_LEGACY_CONNECTED_TECHNICAL_O2_PRIMARY_NA_NOT_G0'
REPORT_SCOPE = 'REAL_LOCKED_A_LEGACY_CONNECTED_O2_PRIMARY_NA_TECHNICAL_NOT_G0'
BUILDER_SHA = '0dcf3214dba161097025c3a605100106ff3aa2747631d988c1ea7fbf5b97f8b1'
PROXY_SHA = '3b4f98f6abaad13987e39ff784f6f77c5b8f0de25255c5af8d5a5560fd6bd73f'
MR_SESSION = '5981e37694a1481f9a04ff26e1ee2876'
MR_SEAL = '000dc33851f32b768901710b07ff8ec74ec5f916e67eb1bb7168f71e1099c9f1'
GATE_SESSION = '29d87332e5d743218f798437a8eb369d'
GATE_SEAL = 'ea772e92258310c7d243391be2f1194f068e3888ef8187f3ceb34c583220b8f5'
FAMILY_SESSION = '581621a671a945eab3857b0c9a631607'
FAMILY_SEAL = '6e6dc44a5e875d4e0645073bcc3a27f2caacfd1fd422ba89c5a723ab6d827fb4'
SCENARIO = 'REAL_FROZEN_NA_LEDGER'
CASE_EXECUTION_ORDER = ('MR-output-conflict', 'positive')
CANONICAL_CASE_ORDER = ('positive', 'MR-output-conflict')
SDK_WORKSPACE_LOCK = '.autonomics-lock'
SDK_WORKSPACE_LOCK_SOURCE = dict(engine_commit='2bfbe45fa895076277e2d227f648a59be5dd67d0',
    path='crates/container-runtime/src/gc.rs', blob_sha1='e0f96819fc7307955114d8a149f8c71c58e02460',
    sha256='8fa2f948b04c75401ee3514c7fb20cbc9367146aff6d7ff34c69b120f929087c',
    definition='SCRATCH_LOCK_FILE and acquire_workdir_lock_exclusive',
    caller_path='crates/node-bundles/nodes-io/src/container_command/node.rs',
    caller_blob_sha1='106b7ba5b47c05e290e4e9990ff6340e6425291b',
    caller_sha256='19f4cddb1d985b5518ce098e6c7d62d092b495a57621b943084617e7bfd7f403')
STAGES = {
    'raw': 'frozen_a_v432_input_qualification',
    'harmonise': 'frozen_a_v432_harmonisation',
    'mr': 'twosamplemr_v432_a_exploratory',
    'gate': 'frozen_a_legacy_family_gate',
    'assemble': 'frozen_a_family_assemble',
    'adjust': 'frozen_a_family_adjust',
    'publish': 'frozen_a_family_publish',
}
PINS = {
    'frozen-a-input-qualification': ('research-adapters', 'scripts/qualify.py',
        'eb62df8d8ee4e4c18d84b66a141c6ec51e35cceff5dd42017c8723e470e4b908',
        '81421c4467c4d204e576949b9a364dd487ffb647e9e429bb922ed7938b1f5a69'),
    'frozen-a-harmonisation': ('research-adapters', 'scripts/harmonise.R',
        '07051b9e8351ae30a74ac8b25074e256bfb9d2fb0af53922864d0c16101a01fb',
        '03a7325619dd1ff927db37875c7d0c040c0d2bf9e97ef1b8af72c2f5533a91f1'),
    'twosamplemr-v432-a': ('plugins', 'scripts/mr.R',
        '661e12b231f7b38540d5cba2fca8a31ee3d5d0831305998f00fa0e898d980324',
        '33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe'),
    'frozen-a-legacy-family-gate': ('research-adapters', 'scripts/gate.py',
        'f07cd4c67cd01037dc9285670fcf3ec021990a4e2e0ebe356a601358e24bf1c1',
        '6c921c4ed2cfece1bc56031a0a40b83c1c1efbdd643d6e32f370ee851da42537'),
    'frozen-a-family-assembly': ('research-adapters', 'scripts/family.py',
        'a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf',
        '338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a'),
    'frozen-a-family-adjustment': ('research-adapters', 'scripts/adjust.R',
        '55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da',
        'debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412'),
}
require, digest, write, regular = family.require, family.digest, family.write, family.regular
strict_json = gate.strict_json


def exact_json(actual, expected):
    require(type(actual) is type(expected), 'Typed complete JSON value differs')
    if isinstance(actual, dict):
        require(actual.keys() == expected.keys(), 'Complete JSON keys differ')
        for key in actual:
            exact_json(actual[key], expected[key])
    elif isinstance(actual, list):
        require(len(actual) == len(expected), 'Complete JSON sequence differs')
        for left, right in zip(actual, expected, strict=True):
            exact_json(left, right)
    else:
        require(actual == expected, 'Complete JSON scalar differs')


def source_paths():
    helper = gate.family_helper()
    return [*raw.INPUT_PATHS, raw.STUDY / raw.AUDIT / 'R_DEPENDENCY_LOCK.tsv',
        ROOT / 'plugins/twosamplemr-v432-a/contracts/frozen-method-proof.json',
        *[raw.STUDY / relative for relative, _, _ in helper.SOURCES], ROOT / gate.HELPER]


def source_facts(paths=None):
    paths = source_paths() if paths is None else paths
    require(len(paths) == len(set(paths)) == 21, 'Twenty-one distinct canonical roles required')
    records = []
    for index, path in enumerate(paths):
        path = raw.ordinary(path)
        identity = file_identity(path)
        value = path.stat()
        require(identity == file_identity(path), 'Canonical source changed during observation')
        records.append(dict(source='source' + str(index), path=str(path), bytes=identity['bytes'],
            sha256=identity['sha256'], device=value.st_dev, inode=value.st_ino, uid=value.st_uid,
            gid=value.st_gid, mode=value.st_mode, mtime=value.st_mtime_ns // 10**9,
            mtime_nsec=value.st_mtime_ns % 10**9, ctime=value.st_ctime_ns // 10**9,
            ctime_nsec=value.st_ctime_ns % 10**9))
    return records


def edge_records():
    records = []
    def bind(source, port, target, target_port):
        records.append({'from': source, 'from_port': port, 'to': target, 'to_port': target_port})
    for port in range(9):
        bind('source' + str(port), 0, 'raw', port)
    for target, (source, port) in enumerate([('raw', 5), ('raw', 3), ('source2', 0),
        ('source3', 0), ('source9', 0), ('source19', 0)]):
        bind(source, port, 'harmonise', target)
    for target, (source, port) in enumerate([('harmonise', 1), ('source2', 0),
        ('source3', 0), ('source9', 0), ('source10', 0)]):
        bind(source, port, 'mr', target)
    for port in range(9):
        bind('mr', port, 'gate', port)
    for source, target in [(2, 9), (3, 10), (9, 11), (10, 12)]:
        bind('source' + str(source), 0, 'gate', target)
    for port in range(9):
        bind('source' + str(port + 11), 0, 'gate', port + 13)
        bind('source' + str(port + 11), 0, 'assemble', port)
    bind('source20', 0, 'gate', 22)
    bind('gate', 0, 'assemble', 9)
    for target, (source, port) in enumerate([('assemble', 1), ('assemble', 0), ('assemble', 2), ('source19', 0)]):
        bind(source, port, 'adjust', target)
    for target, (source, port) in enumerate([('assemble', 0), ('assemble', 1), ('assemble', 2),
        ('adjust', 0), ('adjust', 1), ('adjust', 2), ('source11', 0), ('source12', 0)]):
        bind(source, port, 'publish', target)
    return sorted(records, key=lambda row: (row['from'], row['from_port'], row['to'], row['to_port']))


def make_job(work, paths=None):
    paths = source_paths() if paths is None else paths
    require(len(paths) == 21, 'All twenty-one frozen source roles required')
    def plugin(name):
        directory, script, manifest_sha, script_sha = PINS[name]
        return dict(plugin_manifest=str(ROOT / directory / name / 'manifest.toml'), expected_plugin_name=name,
            plugin_manifest_sha256=manifest_sha, script_sha256={script: script_sha}, panel_overrides=[])
    value = plugin('frozen-a-input-qualification')
    value.update(scope=SCOPE, run_root=str(work), panel_manifest_sha256={'/locked-panels/1000g-eur': raw_dag.PANEL_MANIFEST},
        locked_panel_source=str(raw_dag.PANEL_HOST), bundles=[dict(ident=raw_dag.PANEL_ID,
            desc='Frozen official 1000G EUR panel; read-only; not synthetic', vpath='/locked-panels/1000g-eur',
            source='/locked-panels/1000g-eur', digest=raw_dag.PANEL_DIGEST)],
        additional_plugins=[plugin(name) for name in list(PINS)[1:]],
        nodes=[*[dict(id='source' + str(index), kind='file_reference', spec=dict(
            path='vfs:///' + ('locked-inputs' if index < 9 else 'connected-inputs') + '/' + str(index) + '/' + path.name,
            format='file', hash_content=True)) for index, path in enumerate(paths)],
            *[dict(id=name, kind=kind, spec={}) for name, kind in STAGES.items()]], edges=edge_records())
    return value


def validate_job(job, paths=None):
    require(isinstance(job, dict) and isinstance(job.get('run_root'), str), 'Explicit connected job root required')
    exact_json(job, make_job(Path(job['run_root']), paths))
    require(len(job['nodes']) == 28 and len(job['edges']) == 65 and
        len({(row['to'], row['to_port']) for row in job['edges']}) == 65,
        'Twenty-eight nodes and sixty-five unique target roles required')


def validate_guard_inventory(log, execution):
    observed = re.findall(r'^test (\S+) \.\.\. ok$', log, re.MULTILINE)
    require(len(builder.GUARDS) == len(set(observed)) == len(observed) == 53 and
        set(observed) == builder.GUARDS and type(execution.get('exit')) is int and execution['exit'] == 0 and
        execution.get('required_tests') == sorted(builder.GUARDS) and
        execution.get('observed_passed_tests') == observed and
        'test result: ok. 53 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' in log,
        'All exact fifty-three guards must actually pass without skipping or fallback')


def checked_build(runner, record, seal, output):
    require(digest(Path(builder.__file__)) == BUILDER_SHA, 'Exact reviewed connected builder required')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    runner, record = regular(runner), regular(record)
    archive = next((parent for parent in record.parents if parent.parent == archives and
        re.fullmatch('[0-9a-f]{32}', parent.name)), None)
    require(archive is not None and runner.parent == record.parent and runner.name == builder.EXAMPLE and
        record.name == 'build-record.json', 'One exact dedicated sealed build required')
    verified = verify_archive(archives, archive.name, seal)
    state = strict_json((archive / 'SESSION.json').read_bytes())
    require(verified['positive_worker_exit_verified'] is True and state.get('state') == 'CLEANED' and
        type(state.get('worker_exit_status')) is int and state['worker_exit_status'] == 0 and
        type(state.get('launcher_exit_status')) is int and state['launcher_exit_status'] == 0,
        'Actual successful terminal build required; live and failed builds cannot authorize execution')
    names = ['driver.py', 'probe.rs', 'build-record.json', 'candidate.json', 'candidate.commit',
        'committed-source-files.json', 'active-git-preservation.json', 'kernel-source-pins.json',
        builder.EXAMPLE, 'guard-tests', 'guards-execution.json', 'guards.stdout.log',
        'runner-build-exit.json', 'guards-build-exit.json', *['kernel-source/' + name for name in builder.KERNEL_SOURCE_PINS]]
    artifacts = Path(verified['artifact_root'])
    require(all((record.parent / name).relative_to(artifacts).as_posix() in verified['member_identities'] for name in names),
        'Every build source, executable and compiler observation must be a sealed member')
    value = strict_json(record.read_bytes())
    require(value.get('parent_commit') == builder.PARENT and value.get('probe_sha256') == builder.PROBE_SHA and
        value.get('changed_paths') == [builder.SOURCE_PATH] and value.get('source_unchanged') is True and
        value.get('old_sdk_fallback_allowed') is False and type(value.get('actual_build_exit')) is int and
        value['actual_build_exit'] == 0 and re.fullmatch('[0-9a-f]{40}', value.get('engine_commit', '')) and
        all(value.get(key) is False for key in ['containers_started', 'real_study_fitted', 'production_restarted',
            'scientific_authorized', 'g0_granted']), 'Successful exact-engine build with no deployment or scientific authority required')
    candidate = strict_json((record.parent / 'candidate.json').read_bytes())
    for key in ['engine_commit', 'parent_commit', 'git_tree', 'probe_sha256', 'changed_paths']:
        exact_json(candidate.get(key), value.get(key))
    commit = (record.parent / 'candidate.commit').read_bytes()
    require(hashlib.sha1(b'commit ' + str(len(commit)).encode() + b'\0' + commit).hexdigest() == value['engine_commit'] and
        commit.startswith(('tree ' + value['git_tree'] + '\nparent ' + builder.PARENT + '\n').encode()),
        'Actual immutable candidate commit differs')
    require(digest(record.parent / 'driver.py') == BUILDER_SHA and digest(record.parent / 'probe.rs') == builder.PROBE_SHA,
        'Sealed builder or compiled probe source differs')
    inventory = strict_json((record.parent / 'committed-source-files.json').read_bytes())
    require(isinstance(inventory, dict) and type(value.get('committed_source_files')) is int and
        len(inventory) == value['committed_source_files'] and inventory.get(builder.SOURCE_PATH) == builder.PROBE_SHA,
        'Complete committed source inventory required')
    preservation = strict_json((record.parent / 'active-git-preservation.json').read_bytes())
    require(preservation.get('active_head_and_index_unchanged') is True and preservation.get('before') == preservation.get('after') and
        Path(preservation.get('private_index', '')).name == 'frozen-a-legacy-connected-probe.index', 'Actual Git preservation proof required')
    kernel = strict_json((record.parent / 'kernel-source-pins.json').read_bytes())
    require(candidate.get('kernel_source_pins') == builder.KERNEL_SOURCE_PINS and
        kernel.get('parent_commit') == builder.PARENT and kernel.get('files') == value.get('kernel_source_pins') and
        kernel.get('exported_sources_equal_committed_parent') is True and kernel.get('old_sdk_fallback_allowed') is False,
        'Fixed native memory implementation must be bound to the actual compiled candidate')
    for name, checksum in builder.KERNEL_SOURCE_PINS.items():
        snapshot = regular(record.parent / 'kernel-source' / name)
        require(digest(snapshot) == checksum == inventory.get(name) and
            value['kernel_source_pins'][name] == dict(sha256=checksum, bytes=snapshot.stat().st_size), 'Native source snapshot differs')
    for phase in ['runner', 'guards']:
        compiled = strict_json((record.parent / (phase + '-build-exit.json')).read_bytes())
        executable = value['executables'][phase]
        require(type(compiled.get('exit')) is int and compiled['exit'] == 0 and
            executable['executable'] == (builder.EXAMPLE if phase == 'runner' else 'guard-tests') and
            digest(regular(record.parent / executable['executable'])) == executable['sha256'], 'Compiler exit or executable differs')
    execution = strict_json((record.parent / 'guards-execution.json').read_bytes())
    require(execution.get('stdout_sha256') == digest(record.parent / 'guards.stdout.log'), 'Guard log differs')
    validate_guard_inventory((record.parent / 'guards.stdout.log').read_text(), execution)
    receipt = dict(session=archive.name, seal=seal, files=verified['files'], bytes=verified['bytes'],
        engine_commit=value['engine_commit'], runner_sha256=digest(runner), guards=53, all_members_rehashed=True)
    write(output / 'verified-build.json', receipt)
    return value, receipt


def definitions():
    methods, sources = {}, {}
    for name, (directory, script, manifest_sha, script_sha) in PINS.items():
        base = ROOT / directory / name
        for relative, expected in [('manifest.toml', manifest_sha), (script, script_sha)]:
            path = regular(base / relative)
            require(digest(path) == expected, 'Fixed connected method source differs')
            sources[path.relative_to(ROOT).as_posix()] = file_identity(path)
        manifest = tomllib.loads((base / 'manifest.toml').read_text())
        require(manifest['plugin_name'] == name, 'Exact plugin name required')
        for node in manifest['nodes']:
            require(node['kind'] in STAGES.values() and node['kind'] not in methods and not node.get('params'),
                'Only seven exact parameter-free method kinds are permitted')
            methods[node['kind']] = dict(node, expected_image=manifest['image']['reference'])
    require(set(methods) == set(STAGES.values()), 'All seven actual methods required')
    return methods, sources


def checked_references(output):
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    records, directories = {}, {}
    for name, session, seal, relative in [('MR', MR_SESSION, MR_SEAL, 'frozen-a-legacy-mr-runtime'),
        ('gate', GATE_SESSION, GATE_SEAL, 'frozen-a-legacy-family-gate'),
        ('family', FAMILY_SESSION, FAMILY_SEAL, 'family-helper-source-repair')]:
        checked = verify_archive(archives, session, seal)
        state = strict_json((archives / session / 'SESSION.json').read_bytes())
        require(checked['positive_worker_exit_verified'] is True and state.get('state') == 'CLEANED' and
            all(type(state.get(key)) is int and state[key] == 0 for key in ['worker_exit_status', 'launcher_exit_status']),
            'All three current direct prerequisites must be truly terminal and successful')
        directories[name] = Path(checked['artifact_root']) / 'permanent' / relative
        records[name] = dict(session=session, seal=seal, files=checked['files'], bytes=checked['bytes'], all_members_rehashed=True)
    mr_ports, _ = gate.checked_mr_archive(archives, MR_SESSION, MR_SEAL)
    barrier = strict_json((directories['gate'] / 'verification.json').read_bytes())
    repair = strict_json((directories['family'] / 'verification.json').read_bytes())
    require(barrier.get('mr_replay', {}).get('session') == MR_SESSION and
        barrier['mr_replay'].get('seal') == MR_SEAL and barrier.get('actual_container_entries') == 8 and
        barrier.get('stopped_container_intents') == 8 and barrier.get('runtime_backend') == 'owner-canonical' and
        barrier.get('actual_connected_DAG_executed') is False and barrier.get('g0_granted') is False,
        'Actual gate direct proof and explicit backend limitation must remain bound')
    require(repair.get('actual_method_containers') == 25 and repair.get('full_adjustments_compared') == 2520 and
        repair.get('RDS_vectors_compared') == 18 and repair.get('complete_connected_DAG_executed') is False and
        repair.get('g0_granted') is False, 'Repaired helper must retain its complete prior official numerical proof')
    for name, fact in repair['family_sources'].items():
        path = regular(ROOT / name)
        require(digest(path) == fact['sha256'] and path.stat().st_size == fact['bytes'], 'Repaired family source differs from reference')
    directories['family'] = directories['family'].parent / 'frozen-a-family-runtime'
    directories['MR_ports'] = mr_ports
    write(output / 'verified-direct-references.json', records)
    return directories, records


def validate_report(report, job, build, facts, methods, *, negative=False):
    validate_job(job, [Path(row['path']) for row in facts])
    require(report.get('scope') == REPORT_SCOPE and report.get('engine_source_revision') == build['engine_commit'] and
        report.get('input_hashing') == 'ContentRequired' and type(report.get('max_concurrency')) is int and
        report['max_concurrency'] == 1 and report.get('incremental') is False and report.get('scope_permits_mr') is True and
        report.get('explicit_replay_scope_allows_fit') is True and report.get('is_connected_scope') is True and
        report.get('plugin_name') == job['expected_plugin_name'] and report.get('original_manifest_sha256') == job['plugin_manifest_sha256'] and
        report.get('effective_synthetic_manifest_sha256') is None and
        all(report.get(key) is False for key in ['current_daemon_verified', 'native_statistical_factories_registered',
            'real_overlap_classes_assigned', 'panel_bindings_are_explicit_synthetic_overrides', 'scientific_authorized', 'g0_granted']),
        'Exact connected legacy identity, scheduler and non-scientific scope required')
    exact_json(report.get('connected_source_facts_before'), facts)
    exact_json(report.get('connected_source_facts_after'), facts)
    expected_plugins = [dict(plugin_name=row['expected_plugin_name'], original_manifest_sha256=row['plugin_manifest_sha256'],
        script_sha256=row['script_sha256'], panels=[]) for row in job['additional_plugins']]
    exact_json(report.get('additional_plugin_identities'), expected_plugins)
    panel = report.get('locked_actual_panel_source_before')
    require(isinstance(panel, dict) and panel == report.get('locked_actual_panel_source_after') and
        panel.get('host_source') == str(raw_dag.PANEL_HOST) and panel.get('manifest_sha256') == raw_dag.PANEL_MANIFEST and
        panel.get('digest') == raw_dag.PANEL_DIGEST and panel.get('catalog_bundle') == raw_dag.PANEL_ID and
        len(panel.get('payload_files', [])) == 66 and {row['path'] for row in panel['payload_files']} ==
        {f'1000G.EUR.QC.{chromosome}.{suffix}' for chromosome in range(1, 23) for suffix in ['bed', 'bim', 'fam']} and
        report.get('panel_transport') == 'TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT',
        'All sixty-six canonical panel payloads and metadata must remain unchanged; no copy fallback')
    first = report.get('first_run', {})
    require(isinstance(first.get('errors'), dict), 'Actual SDK errors-map schema required')
    records = first.get('nodes')
    require(isinstance(records, list) and len(records) == len({row['id'] for row in records}) == 28 and
        {row['id'] for row in records} == {row['id'] for row in job['nodes']}, 'All twenty-eight unique actual nodes required')
    nodes = {row['id']: row for row in records}
    for entry in job['nodes']:
        node = nodes[entry['id']]
        require(node.get('node_type') == entry['kind'] and node.get('reused') is False, 'Actual node kind or cache reuse differs')
        if entry['kind'] == 'file_reference':
            role = int(entry['id'].removeprefix('source'))
            assignment = node.get('port_assignments', {}).get('0', {})
            require(node.get('status') == 'success' and set(node.get('port_assignments', {})) == {'0'} and
                assignment.get('path') == entry['spec']['path'] and assignment.get('format') == 'file' and
                assignment.get('fingerprint', {}).get('size') == facts[role]['bytes'] and
                assignment['fingerprint'].get('content_hash') == 'sha256:' + facts[role]['sha256'], 'Actual canonical source port differs')
        elif negative and entry['id'] in ['gate', 'assemble', 'adjust', 'publish']:
            require(node.get('status') == 'skipped' and node.get('execution') is None and
                not node.get('port_assignments') and node.get('skipped_because') == 'mr',
                'MR refusal must causally skip all four downstream stages without executing them')
        elif negative and entry['id'] == 'mr':
            require(node.get('status') == 'failed' and not node.get('port_assignments'), 'Real MR must fail without publishing ports')
        else:
            execution = node.get('execution', {})
            image = methods[entry['kind']]['expected_image']
            require(node.get('status') == 'success' and type(execution.get('exit_code')) is int and execution['exit_code'] == 0 and
                execution.get('image') == image and execution.get('image_digest') == image.split('@', 1)[1],
                'Every positive method must actually finish in its exact official image')
    require((set(first['errors']) == {'mr'}) if negative else not first['errors'], 'Only the intended MR error may occur')
    return nodes


def checked_bindings(work, node, nodes, job, methods, scratch, facts):
    expected = [row for row in job['edges'] if row['to'] == node['id']]
    bindings = node.get('inputs')
    require(isinstance(bindings, list) and len(bindings) == len(expected) and
        len({row['to_port'] for row in bindings}) == len(bindings), 'Every actual input role needs one unique binding')
    if node['port_assignments']:
        workspace = Path(next(iter(node['port_assignments'].values()))['path']).parent
    else:
        workspace = Path(node['execution']['stderr_log']['path']).parents[2]
    require(workspace.resolve(strict=True) == workspace and workspace.is_relative_to(scratch), 'Owned actual container workspace required')
    staged_root = workspace / '.autonomics/inputs'
    require(staged_root.is_dir() and staged_root.resolve() == staged_root, 'Actual staging root must be owned and unaliased')
    observed = []
    for edge in expected:
        binding = next(row for row in bindings if row['to_port'] == edge['to_port'])
        source = nodes[edge['from']]['port_assignments'][str(edge['from_port'])]
        if edge['from'].startswith('source'):
            original = Path(facts[int(edge['from'].removeprefix('source'))]['path'])
        else:
            original = regular(Path(source['path']))
        original_fact = file_identity(original)
        staged = staged_root / raw_dag.staged_basename(edge['to_port'], original)
        require(binding.get('kind') == 'File' and binding.get('from') == edge['from'] and
            binding.get('from_port') == edge['from_port'] and binding.get('path') == source['path'] and
            binding.get('fingerprint', {}).get('size') == original_fact['bytes'] and
            binding['fingerprint'].get('content_hash') in [None, 'sha256:' + original_fact['sha256']], 'Actual dispatched file identity differs')
        if methods[node['node_type']]['stage_in_mode'] == 'symlink':
            require(staged.is_symlink() and os.readlink(staged) == str(original) and staged.resolve(strict=True) == original,
                'Actual raw staging must directly link the exact read-only canonical source, without copying')
            link_before = staged.lstat()
            staged_hash = digest(original)
            require(staged.lstat() == link_before and os.readlink(staged) == str(original) and
                staged.resolve(strict=True) == original, 'Owned raw staging link changed during content verification')
        else:
            require(not staged.is_symlink() and regular(staged).is_relative_to(scratch), 'Copy-mode staging may not use a symlink')
            staged_hash = digest(staged)
        require(staged.stat().st_size == original_fact['bytes'] and staged_hash == original_fact['sha256'] and
            file_identity(original) == original_fact,
            'Complete staged bytes differ from the actual upstream artifact')
        observed.append(dict(**edge, bytes=original_fact['bytes'], sha256=original_fact['sha256'],
            staged_path=str(staged), staged_is_symlink=staged.is_symlink()))
    return observed


def compare_positive(work, ports, references):
    helper = gate.family_helper()
    inputs = [*ports['mr'], *gate.frozen_inputs(helper)]
    barrier = gate.validate_positive(ports['gate'][0].parent, helper, inputs)
    for index in [*range(6), 7]:
        require(ports['mr'][index].read_bytes() == references['MR_ports'][index].read_bytes(),
            'Complete MR TSV or diagnostic log differs from the sealed current independent direct replay')
    exact_json(strict_json(ports['mr'][8].read_bytes()), strict_json(references['MR_ports'][8].read_bytes()))
    provenance = strict_json(ports['mr'][8].read_bytes())
    require(provenance.get('primary_p_source') == 'NA' and provenance.get('overlap_class') == 'O2' and
        provenance.get('seed') == 432202610 and type(provenance.get('seed')) is int and
        provenance.get('bootstrap_n') == 1000 and provenance.get('n_independent_IV') == 39 and
        provenance.get('scientific_authorization_granted') is False and provenance.get('formal_scientific_pass_granted') is False,
        'Exploratory MR cannot become a primary estimate or scientific authorization')
    for index, name in enumerate(gate.OUTPUTS):
        reference = regular(references['gate'] / 'positive' / name)
        if name.endswith('.json'):
            exact_json(strict_json(ports['gate'][index].read_bytes()), strict_json(reference.read_bytes()))
        else:
            require(ports['gate'][index].read_bytes() == reference.read_bytes(), 'Complete gate ledger or log differs from the direct barrier')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    vectors, adjusted, oracle = family.checked_oracle(archives)
    family_comparison = work / 'family-only-comparison'
    family_comparison.mkdir(mode=0o700)
    family.compare_case(family_comparison, SCENARIO, ports['assemble'], ports['adjust'], ports['publish'], vectors, adjusted)
    comparisons = []
    for stage in ['assemble', 'adjust', 'publish']:
        for path in ports[stage]:
            reference = regular(references['family'] / SCENARIO / stage / path.name)
            if path.suffix == '.RDS':
                continue
            if path.suffix == '.json':
                exact_json(strict_json(path.read_bytes()), strict_json(reference.read_bytes()))
            else:
                require(path.read_bytes() == reference.read_bytes(), 'Whole frozen family table or log differs from repaired direct execution')
            comparisons.append(dict(stage=stage, name=path.name, bytes=path.stat().st_size, sha256=digest(path)))
    result = dict(gate=barrier, full_MR_TSVs_byte_equal=6, complete_MR_log_byte_equal=True,
        complete_typed_MR_provenance_equal=True, full_family_rows=564, full_vectors=840,
        all_q_values_equal=840, family_comparisons=comparisons, official_oracle=oracle,
        actual_connected_DAG_executed=True, family_only_reference_comparison=strict_json((family_comparison / 'comparison.json').read_bytes()),
        MR_RDS_deserialized_in_Python=False, adjustment_RDS_deserialized_in_Python=False, g0_granted=False)
    write(work / 'comparison.json', result)
    return result


RDS_COMPARE = mr.FUNCTION_IDENTITY_R + '''args <- commandArgs(trailingOnly=TRUE)
stopifnot(identical(as.character(getRversion()), "4.6.1"), identical(as.character(packageVersion("stats")), "4.6.1"))
identity <- namespace_function_identity()
stopifnot(identical(as.character(packageVersion("TwoSampleMR")), "0.7.11"), identity$function_count==171L,
  identical(identity$aggregate_sha256,"127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73"),
  identical(digest::digest(file=system.file("DESCRIPTION",package="TwoSampleMR"),algo="sha256",serialize=FALSE),
    "911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531"), is.null(packageDescription("TwoSampleMR")$RemoteSha))
complete <- function(actual, expected) {
  stopifnot(identical(typeof(actual), typeof(expected)), identical(attributes(actual), attributes(expected)))
  if (is.list(actual)) {
    stopifnot(length(actual)==length(expected))
    for (position in seq_along(actual)) complete(actual[[position]], expected[[position]])
  } else stopifnot(identical(actual, expected))
  invisible(TRUE)
}
for (label in c("MR", "ADJUSTMENT")) {
  complete(readRDS(file.path(args[1], paste0(label,"-actual.RDS"))), readRDS(file.path(args[1], paste0(label,"-reference.RDS"))))
  cat(label, "COMPLETE_OFFICIAL_RDS_OBJECT_IDENTICAL\\n")
}
'''


def official_rds_compare(prefix, output, ports, references):
    directory = output / 'official-rds-comparison'
    directory.mkdir(mode=0o700)
    (directory / 'compare.R').write_text(RDS_COMPARE)
    facts = {}
    for label, actual, reference in [('MR', ports['mr'][6], references['MR_ports'][6]),
        ('ADJUSTMENT', ports['adjust'][1], references['family'] / SCENARIO / 'adjust/adjustment.RDS')]:
        for role, source in [('actual', actual), ('reference', reference)]:
            source = regular(source)
            before = file_identity(source)
            target = directory / (label + '-' + role + '.RDS')
            shutil.copyfile(source, target)
            require(digest(target) == before['sha256'] and file_identity(source) == before, 'RDS transport changed bytes')
            facts[label + '-' + role] = before
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
        '--pids-limit=64', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-v', str(directory) + ':/proof:ro', '--entrypoint=Rscript', mr.IMAGE,
        '--vanilla', '/proof/compare.R', '/proof']
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (directory / 'stdout.log').write_text(run.stdout)
    (directory / 'stderr.log').write_text(run.stderr)
    write(directory / 'execution.json', dict(command=command, actual_exit=run.returncode, sources=facts,
        all_171_namespace_functions_checked=True, RemoteSha_observed_null=True,
        scientific_authorization_granted=False, g0_granted=False))
    require(type(run.returncode) is int and run.returncode == 0 and run.stdout.splitlines() ==
        ['MR COMPLETE_OFFICIAL_RDS_OBJECT_IDENTICAL', 'ADJUSTMENT COMPLETE_OFFICIAL_RDS_OBJECT_IDENTICAL'],
        'Both complete RDS objects must be truly read and compared by the fixed official R image')
    return dict(complete_objects=2, official_image=mr.IMAGE, tolerance=0, actual_exit=0,
        compared_to_current_direct_official_references=True, Python_RDS_parsing=False,
        all_171_namespace_functions_checked=True, RemoteSha_observed_null=True)


def evidence_copy(work, destination, ports, nodes):
    require(not destination.exists() and destination.resolve() == destination, 'New owned evidence destination required')
    destination.mkdir(mode=0o700)
    copied = {}
    def transfer(source, relative):
        source = regular(source)
        require(source.is_relative_to(work) or source.is_relative_to(Path(os.environ['TMPDIR']) /
            'official-plugin-container-workspaces' / work.name), 'Only this owned graph may supply evidence')
        before = file_identity(source)
        target = destination / relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Contained evidence member required')
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        require(digest(target) == before['sha256'] and file_identity(source) == before, 'Evidence transport changed bytes')
        copied[relative] = dict(bytes=before['bytes'], sha256=before['sha256'])
    for name in ['job.json', 'admission.stdout', 'admission.stderr', 'admission-exit.json', 'runner.stdout', 'runner.stderr',
        'runner-exit.json', 'dag-report.json', 'task-receipts-verification.json', 'graph-verification.json']:
        transfer(work / name, name)
    for stage, files in ports.items():
        for path in files:
            transfer(path, stage + '/' + path.name)
    for node in nodes.values():
        if node['status'] == 'skipped':
            continue
        receipt = Path(node['execution']['workspace'])
        require(receipt.parent == work / 'task-receipts' and receipt.resolve() == receipt and
            re.fullmatch('[0-9]+-[0-9]+-[0-9]+', receipt.name), 'Exact owned attempt directory required')
        for name in ['task.json', 'attempt.json', 'status.json']:
            transfer(receipt / name, 'task-receipts/' + receipt.name + '/' + name)
        for stream in ['stdout', 'stderr']:
            reference = node['execution'].get(stream + '_log')
            if reference is None:
                continue
            path = regular(Path(reference['path']))
            require(path.is_relative_to(Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name) or
                path == receipt / (stream + '.log'), 'Only exact owned method or receipt logs may be preserved')
            fingerprint = reference.get('fingerprint')
            require(fingerprint is None or (fingerprint.get('size') == path.stat().st_size and
                fingerprint.get('content_hash') in [None, 'sha256:' + digest(path)]), 'Declared log fingerprint differs')
            transfer(path, 'execution-logs/' + node['id'] + '.' + stream)
    for name in ['comparison.json', 'expected-MR-refusal.stderr']:
        if (work / name).exists():
            transfer(work / name, name)
    write(destination / 'copied-evidence.json', dict(files=copied, source_payloads_archived=False,
        canonical_raw_inputs_copied=False, whole_execution_scratch_archived=False))
    return copied


def preserve_failure_diagnostics(work, destination, failure):
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    scratch = temporary / 'official-plugin-container-workspaces' / work.name
    require(work.resolve(strict=True) == work and work.is_relative_to(temporary) and
        destination.resolve() == destination and destination.is_relative_to(permanent) and not destination.exists(),
        'Failure evidence needs a new owned permanent destination and the exact temporary graph root')
    destination.mkdir(mode=0o700)
    files, omitted = {}, []
    def transfer(path, relative):
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Contained failure diagnostic member required')
        path = regular(path)
        require(path.stat().st_uid == os.getuid() and path.stat().st_size <= 32 * 1024**2,
            'Only bounded operator-owned diagnostic files may be preserved')
        before = file_identity(path)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        require(file_identity(path) == before and digest(target) == before['sha256'], 'Failure diagnostic changed during transport')
        files[relative] = dict(bytes=before['bytes'], sha256=before['sha256'], original_path=str(path))
    def attempt(path, relative):
        try:
            transfer(path, relative)
        except Exception as error:
            omitted.append(dict(member=relative, error_type=type(error).__name__, reason=str(error)[:512]))
    for name in ['job.json', 'admission.stdout', 'admission.stderr', 'admission-exit.json',
        'runner.stdout', 'runner.stderr', 'runner-exit.json', 'dag-report.json']:
        path = work / name
        if os.path.lexists(path):
            attempt(path, name)
    report_path = work / 'dag-report.json'
    records = []
    if 'dag-report.json' in files:
        try:
            report = strict_json(regular(report_path).read_bytes())
            records = report.get('first_run', {}).get('nodes', [])
            require(isinstance(records, list), 'Failed SDK node inventory must remain a list')
        except Exception as error:
            omitted.append(dict(member='node-inventory', error_type=type(error).__name__, reason=str(error)[:512]))
            records = []
    admitted = {**{'source' + str(index): 'file_reference' for index in range(21)}, **STAGES}
    seen = set()
    for node in records:
        if not isinstance(node, dict) or node.get('id') not in admitted or node.get('node_type') != admitted[node['id']] or node['id'] in seen:
            omitted.append(dict(member='node-inventory', error_type='UnrecognizedNode', reason='Unknown or duplicate failed-report node not traversed'))
            continue
        seen.add(node['id'])
        execution = node.get('execution')
        if not isinstance(execution, dict):
            continue
        receipt = Path(execution.get('workspace', ''))
        receipt_owned = (receipt.is_absolute() and receipt.parent == work / 'task-receipts' and
            re.fullmatch('[0-9]+-[0-9]+-[0-9]+', receipt.name) and not receipt.is_symlink() and
            receipt.is_dir() and receipt.resolve(strict=True) == receipt and receipt.stat().st_uid == os.getuid())
        if receipt_owned:
            try:
                task_path = regular(receipt / 'task.json')
                require(task_path.stat().st_size <= 1024**2, 'Bounded actual task manifest required')
                task = strict_json(task_path.read_bytes())
                require(task.get('spec', {}).get('id') == node['id'] and task['spec'].get('kind') == node['node_type'],
                    'Failed node does not own this task receipt')
            except Exception as error:
                receipt_owned = False
                omitted.append(dict(member='task-receipts/' + receipt.name, error_type=type(error).__name__, reason=str(error)[:512]))
            if receipt_owned:
                for name in ['task.json', 'attempt.json', 'status.json']:
                    if os.path.lexists(receipt / name):
                        attempt(receipt / name, 'task-receipts/' + receipt.name + '/' + name)
        for stream in ['stdout', 'stderr']:
            reference = execution.get(stream + '_log')
            if reference is None:
                continue
            try:
                require(isinstance(reference, dict) and isinstance(reference.get('path'), str), 'Explicit actual log reference required')
                path = regular(Path(reference['path']))
                native_log = receipt_owned and path == receipt / (stream + '.log')
                method_log = (node['id'] in STAGES and path.is_relative_to(scratch) and
                    path.name == stream + '.log' and path.parent.name == 'logs' and
                    path.parent.parent.name == '.autonomics')
                require(native_log or method_log, 'Log is outside the exact owned task receipt or method diagnostic directory')
                fingerprint = reference.get('fingerprint')
                require(fingerprint is None or (fingerprint.get('size') == path.stat().st_size and
                    fingerprint.get('content_hash') in [None, 'sha256:' + digest(path)]), 'Failed log fingerprint differs')
                transfer(path, 'execution-logs/' + node['id'] + '.' + stream)
            except Exception as error:
                omitted.append(dict(member='execution-logs/' + node['id'] + '.' + stream,
                    error_type=type(error).__name__, reason=str(error)[:512]))
    def owned_directory(path):
        require(path.resolve(strict=True) == path and not path.is_symlink() and path.is_dir() and
            path.stat().st_uid == os.getuid(), 'Unaliased operator-owned diagnostic directory required')
        return path
    def bounded_entries(path, limit):
        if not path.exists():
            return []
        owned_directory(path)
        with os.scandir(path) as entries:
            result = []
            for item in entries:
                require(len(result) < limit, 'Diagnostic directory census exceeds its exact bounded inventory')
                result.append(Path(item.path))
        return result
    def transfer_once(path, relative):
        if not any(value['original_path'] == str(path) for value in files.values()):
            attempt(path, relative)
    try:
        workspaces = []
        for prefix in bounded_entries(scratch, 7):
            if not re.fullmatch('[0-9a-f]{2}', prefix.name):
                continue
            for child in bounded_entries(owned_directory(prefix), 7):
                if not re.fullmatch('[0-9a-f]{62}', child.name):
                    continue
                require(len(workspaces) < 7, 'At most seven exact method workspaces belong to this graph')
                workspaces.append(owned_directory(child))
        for workspace in workspaces:
            logs = workspace / '.autonomics/logs'
            if logs.exists():
                owned_directory(logs)
                for stream in ['stdout', 'stderr']:
                    path = logs / (stream + '.log')
                    if os.path.lexists(path):
                        transfer_once(path, 'workspace-diagnostics/' + workspace.parent.name + workspace.name + '.' + stream)
    except Exception as error:
        omitted.append(dict(member='bounded-workspace-log-census', error_type=type(error).__name__, reason=str(error)[:512]))
    try:
        task_ids = set()
        for receipt in bounded_entries(work / 'task-receipts', 28):
            require(re.fullmatch('[0-9]+-[0-9]+-[0-9]+', receipt.name), 'Only exact owned attempt-directory names may enter the census')
            owned_directory(receipt)
            task_path = regular(receipt / 'task.json')
            require(task_path.stat().st_size <= 1024**2, 'Bounded owned task manifest required')
            task = strict_json(task_path.read_bytes())
            name, kind = task.get('spec', {}).get('id'), task.get('spec', {}).get('kind')
            require(name in admitted and kind == admitted[name] and name not in task_ids,
                'Each census receipt must belong to a unique admitted graph node')
            task_ids.add(name)
            for filename in ['task.json', 'attempt.json', 'status.json', 'stdout.log', 'stderr.log']:
                path = receipt / filename
                if os.path.lexists(path):
                    transfer_once(path, 'task-receipts/' + receipt.name + '/' + filename)
    except Exception as error:
        omitted.append(dict(member='bounded-task-receipt-census', error_type=type(error).__name__, reason=str(error)[:512]))
    result = dict(status='FAILED_GRAPH_DIAGNOSTICS_RETAINED_NOT_PASS', failure_type=type(failure).__name__,
        failure_message=str(failure)[:2048], copied_files=files, omitted=omitted,
        source_inputs_or_panels_archived=False, whole_execution_scratch_archived=False,
        successful_graph_claimed=False, scientific_authorization_granted=False, g0_granted=False)
    write(destination / 'failure-diagnostics.json', result)
    return result


def captured_run(command, work, label, **keywords):
    require(label in ['admission', 'runner'], 'Only this proof SDK command may supply captured diagnostics')
    def save(value, suffix):
        content = b'' if value is None else value.encode() if isinstance(value, str) else value
        require(isinstance(content, bytes), 'Captured SDK stream must retain actual text or bytes')
        with (work / (label + '.' + suffix)).open('xb') as handle:
            handle.write(content)
    try:
        result = subprocess.run(command, **keywords)
    except subprocess.TimeoutExpired as error:
        save(error.stdout, 'stdout')
        save(error.stderr, 'stderr')
        write(work / (label + '-exit.json'), dict(actual_exit=None, timed_out=True, timeout_seconds=error.timeout))
        raise
    save(result.stdout, 'stdout')
    save(result.stderr, 'stderr')
    write(work / (label + '-exit.json'), dict(actual_exit=result.returncode))
    return result


def run_graph(runner, build, work, methods, facts, environment, *, negative=False, failure_output=None):
    try:
        return _run_graph(runner, build, work, methods, facts, environment, negative=negative)
    except Exception as failure:
        if failure_output is not None:
            try:
                preserve_failure_diagnostics(work, failure_output, failure)
            except Exception as retention_failure:
                print('Narrow failure diagnostic retention failed: ' + type(retention_failure).__name__, file=sys.stderr)
        raise


@contextmanager
def retain_case_failure(work, destination):
    try:
        yield
    except Exception as failure:
        if not destination.exists():
            try:
                preserve_failure_diagnostics(work, destination, failure)
            except Exception as retention_failure:
                print('Narrow case diagnostic retention failed: ' + type(retention_failure).__name__, file=sys.stderr)
        raise


def _run_graph(runner, build, work, methods, facts, environment, *, negative=False):
    job = make_job(work, [Path(row['path']) for row in facts])
    validate_job(job, [Path(row['path']) for row in facts])
    write(work / 'job.json', job)
    admitted = captured_run([str(runner), '--validate-job', str(work / 'job.json')], work, 'admission',
        env=environment, capture_output=True, text=True, timeout=600)
    require(admitted.returncode == 0, 'Actual source-bound connected preflight failed before execution')
    admission = strict_json(admitted.stdout)
    exact_json(admission.get('connected_source_facts'), facts)
    require(admission.get('scope') == SCOPE and admission.get('job_validated_without_execution') is True and
        all(admission.get(key) is False for key in ['containers_started', 'scientific_results_computed', 'g0_granted']),
        'Actual no-execution preflight scope differs')
    run = captured_run([str(runner), str(work / 'job.json')], work, 'runner', capture_output=True, text=True, timeout=2700,
        env=dict(environment, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
    require(type(run.returncode) is int and run.returncode == 0, 'Runner failed before producing its terminal graph report')
    report = strict_json((work / 'dag-report.json').read_bytes())
    nodes = validate_report(report, job, build, facts, methods, negative=negative)
    memory = validate_memory_report(report)
    receipts = checked_task_receipts(work, {name: node for name, node in nodes.items() if node['status'] != 'skipped'})
    require(len(receipts) == (24 if negative else 28), 'Every executed source/method needs an owned terminal task receipt')
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    bindings, ports = {}, {}
    for stage, kind in STAGES.items():
        if nodes[stage]['status'] == 'skipped':
            continue
        bindings[stage] = checked_bindings(work, nodes[stage], nodes, job, methods, scratch, facts)
        if negative and stage == 'mr':
            stderr = expected_refusal(nodes[stage], methods[kind]['expected_image'],
                'Refusing to overwrite existing or linked outputs', scratch)
            shutil.copyfile(stderr, work / 'expected-MR-refusal.stderr')
        else:
            ports[stage] = actual_ports(work, methods[kind], nodes[stage], scratch)
    require(sum(map(len, bindings.values())) == (20 if negative else 65), 'All actual dispatched bindings must have complete staged-byte proof')
    write(work / 'graph-verification.json', dict(nodes=28, edges=65, actual_task_receipts=len(receipts),
        actual_staged_bindings=bindings, actual_output_ports=sum(map(len, ports.values())), native_memory=memory,
        expected_MR_existing_output_refusal=negative, downstream_stages_skipped=4 if negative else 0,
        plugin_resources_to_native_TaskResources_proven=False, g0_granted=False))
    return ports, nodes


def validate_upstream(ports, methods, contract, raw_before, panel_before):
    raw_proof = raw.validate_positive(ports['raw'][0].parent, methods[STAGES['raw']], contract, raw_before, panel_before)
    provenance = strict_json(ports['harmonise'][3].read_bytes())
    qualification = gate.qualification
    require(provenance.get('input_sha256') == [digest(path) for path in [ports['raw'][5], ports['raw'][3],
        raw.INPUT_PATHS[2], raw.INPUT_PATHS[3], raw.STUDY / raw.AUDIT / 'R_DEPENDENCY_LOCK.tsv',
        raw.STUDY / family.contract.SOURCES[8][0]]] and provenance.get('adapter_sha256') == PINS['frozen-a-harmonisation'][3] and
        provenance.get('original_scientific_code_sha256') == qualification.SOURCE_SHA and
        provenance.get('qualify_A_block_sha256') == qualification.BLOCK_SHA and provenance.get('original_qualify_A_branch_evaluated') is True and
        provenance.get('R') == '4.6.1' and provenance.get('TwoSampleMR') == '0.7.11' and
        'TwoSampleMR_RemoteSha' in provenance and provenance['TwoSampleMR_RemoteSha'] is None and
        provenance.get('package_description_sha256') == qualification.PACKAGE_DESCRIPTION_SHA and
        provenance.get('package_namespace_function_count') == 171 and
        provenance.get('package_namespace_aggregate_sha256') == qualification.PACKAGE_FUNCTIONS_SHA and
        provenance.get('n_clumped') == provenance.get('n_qualified') == 39 and
        provenance.get('additional_config_envelope_checked_without_reselection') is True and
        all(provenance.get(key) is False for key in ['raw_GWAS_QC_reexecuted', 'PLINK_or_LD_reexecuted',
            'MR_estimates_computed', 'original_full_project_verifier_executed', 'scientific_authorization_granted',
            'formal_scientific_pass_granted', 'G0']), 'Actual upstream harmonisation provenance differs from its frozen official envelope')
    for name in qualification.PRODUCTS:
        actual = next(path for path in ports['harmonise'] if path.name == name)
        require(actual.read_bytes() == (raw.STUDY / raw.AUDIT / name).read_bytes(), 'Complete canonical harmonisation product differs')
    require('no MR estimates computed' in ports['harmonise'][4].read_text(), 'Actual harmonisation diagnostic log required')
    return dict(raw=raw_proof, harmonised_variants=39, complete_harmonisation_products=3,
        individual_harmonisation_node_does_not_compute_MR=True)


def verify_refusal_workspace(configuration, record):
    workspace = oci.directory(Path(record['workspace']))
    workspace_root = oci.directory(configuration['workspace_root'])
    relative = workspace.relative_to(workspace_root)
    require(len(relative.parts) == 2 and re.fullmatch('[0-9a-f]{2}', relative.parts[0]) and
        re.fullmatch('[0-9a-f]{62}', relative.parts[1]), 'Exact owned SDK method workspace required for the refusal census')
    destination = oci.directory(configuration['records'].parent)
    permanent = oci.directory(Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']))
    require(destination.is_relative_to(permanent), 'Refusal diagnostic metadata must survive in this managed permanent namespace')
    marker = Path(record['foreign_before']['path'])
    require(marker == workspace / mr.OUTPUTS[0], 'Only the controlled foreign marker may be content-hashed in this census')
    original_marker = record['foreign_before']['identity']
    marker_errors = []
    def marker_fact(label):
        try:
            return oci.regular_fact(marker)
        except (OSError, ValueError) as error:
            marker_errors.append(dict(checkpoint=label, error_type=type(error).__name__, message=str(error)[:512]))
            return None
    def flat_metadata():
        rows, truncated = [], False
        with os.scandir(workspace) as entries:
            for entry in entries:
                if len(rows) == 64:
                    truncated = True
                    break
                observed = entry.stat(follow_symlinks=False)
                kind = ('regular' if stat.S_ISREG(observed.st_mode) else 'directory' if stat.S_ISDIR(observed.st_mode)
                    else 'symlink' if stat.S_ISLNK(observed.st_mode) else 'other')
                rows.append(dict(name=entry.name, kind=kind, device=observed.st_dev, inode=observed.st_ino,
                    uid=observed.st_uid, gid=observed.st_gid, mode=observed.st_mode, bytes=observed.st_size,
                    links=observed.st_nlink, mtime_ns=observed.st_mtime_ns, ctime_ns=observed.st_ctime_ns))
        return sorted(rows, key=lambda row: row['name']), truncated
    observed_marker = marker_fact('before-census')
    rows, truncated = flat_metadata()
    current_marker = marker_fact('after-census')
    census = dict(schema='MR_REFUSAL_WORKSPACE_FLAT_CENSUS_V1', scope=SCOPE,
        workspace=str(workspace), entries=rows, sdk_workspace_lock_source=SDK_WORKSPACE_LOCK_SOURCE,
        entry_limit=64, truncated=truncated, original_marker_identity=original_marker,
        observed_marker_before=observed_marker, observed_marker_after=current_marker,
        marker_read_errors=list(marker_errors), lock_file_presence_does_not_prove_lock_held=True,
        unknown_file_bodies_read=False, recursive_workspace_copy=False,
        successful_graph_claimed=False, scientific_authorization_granted=False, g0_granted=False)
    with (destination / 'MR-refusal-workspace-census.json').open('x') as handle:
        json.dump(census, handle, indent=2, allow_nan=False)
        handle.write('\n')
    final_rows, final_truncated = flat_metadata()
    final_marker = marker_fact('after-permanent-census')
    postcheck = dict(schema='MR_REFUSAL_WORKSPACE_CENSUS_POSTCHECK_V1', workspace=str(workspace),
        entries=final_rows, truncated=final_truncated, marker_identity=final_marker,
        marker_read_errors=marker_errors, metadata_unchanged=final_rows == rows and final_truncated == truncated,
        unknown_file_bodies_read=False, successful_graph_claimed=False, scientific_authorization_granted=False, g0_granted=False)
    with (destination / 'MR-refusal-workspace-census-postcheck.json').open('x') as handle:
        json.dump(postcheck, handle, indent=2, allow_nan=False)
        handle.write('\n')
    require(not truncated, 'Refusal workspace exceeds the bounded diagnostic flat-entry census')
    require(postcheck['metadata_unchanged'] and not final_truncated, 'Refusal workspace metadata changed after the permanent diagnostic census')
    require(not marker_errors and observed_marker == current_marker == final_marker == original_marker == record['foreign_after'],
        'Foreign MR output identity changed during the diagnostic census')
    indexed = {row['name']: row for row in rows}
    require(set(indexed) == {mr.OUTPUTS[0], SDK_WORKSPACE_LOCK, '.autonomics'},
        'The failed MR workspace may contain only the controlled foreign output and verified SDK bookkeeping, not normal MR products')
    lock = indexed[SDK_WORKSPACE_LOCK]
    permissions = stat.S_IMODE(lock['mode'])
    require(lock['kind'] == 'regular' and lock['bytes'] == 0 and lock['links'] == 1 and
        lock['uid'] == os.getuid() and lock['gid'] == os.getgid() and
        permissions & 0o600 == 0o600 and permissions & ~0o644 == 0,
        'SDK workspace lock must be an empty single-link owned regular file with safe owner read-write permissions')
    metadata_directory = indexed['.autonomics']
    require(metadata_directory['kind'] == 'directory' and metadata_directory['uid'] == os.getuid() and
        metadata_directory['gid'] == os.getgid(), 'Only the original regular owned SDK metadata directory is allowed')
    for name in mr.OUTPUTS[1:]:
        require(not os.path.lexists(workspace / name), 'The conflict refusal must not emit any normal MR result or log')
    return census


def verify_creates(configuration, nodes, *, negative=False):
    roles = ['raw', 'harmonise', 'mr'] if negative else list(STAGES)
    records = oci.observations(configuration, expected_roles=roles)
    for record in records:
        node = nodes[record['role']]
        assignments = node['port_assignments']
        actual_workspace = (Path(next(iter(assignments.values()))['path']).parent if assignments else
            Path(node['execution']['stderr_log']['path']).parents[2])
        require(record['run_name'] == node['execution']['run_name'] and
            record['workspace'] == str(actual_workspace) and
            record['image'] == node['execution']['image'] and
            record['script_sha256'] == oci.SCRIPTS[record['role']][0] and
            record['actual_resources'] == dict(cpus='1', memory=oci.SCRIPTS[record['role']][6], pull='never', read_only_rootfs=True) and
            record['scientific_inputs_or_method_parameters_changed'] is False and
            record['resource_override_is_technical_not_manifest_certification'] is True,
            'Actual SDK container creation must bind the recorded method attempt and exact technical resource narrowing')
        if assignments:
            require(record['output_paths'] == [assignments[str(index)]['path'] for index in range(len(assignments))],
                'Recorded SDK output environment must exactly match its actual reported output roles')
        inputs = record.get('input_identities')
        require(isinstance(inputs, list) and len(inputs) == len(node['inputs']) and
            [row['port'] for row in inputs] == list(range(len(inputs))), 'Every actual container input needs its pre-launch complete identity')
        for item in inputs:
            staged = Path(item['staged_path'])
            binding = next(row for row in node['inputs'] if row['to_port'] == item['port'])
            require(staged.parent == actual_workspace / '.autonomics/inputs' and
                item['identity']['bytes'] == binding['fingerprint']['size'] and
                binding['fingerprint'].get('content_hash') in [None, 'sha256:' + item['identity']['sha256']],
                'Pre-launch input identity must bind the actual dispatched port')
            if record['role'] == 'raw':
                target = oci.RAW_INPUT_PATHS[item['port']]
                require(item['mode'] == 'EXACT_CANONICAL_READONLY_SYMLINK' and item['canonical_source'] == str(target) and
                    staged.is_symlink() and os.readlink(staged) == str(target), 'Pre-launch raw role changed its canonical read-only link')
            else:
                target = staged
                require(item['mode'] == 'OWNED_REGULAR_BYTE_COPY', 'Pre-launch copied input mode differs')
            require(oci.regular_fact(target) == item['identity'], 'Complete input file identity changed after actual container execution')
    if negative:
        record = next(row for row in records if row['role'] == 'mr')
        require(record['foreign_before']['identity'] == record['foreign_after'], 'Foreign MR output identity changed')
        verify_refusal_workspace(configuration, record)
    return records


def observed_stops(prefix, permanent, output):
    path = permanent / 'container-intents.json'
    if not path.exists():
        write(output / 'owned-container-stops.json', [])
        return []
    value = strict_json(path.read_bytes())
    require(isinstance(value.get('intents'), list) and len(value['intents']) <= 11,
        'Only the seven-positive, three-negative and one-readback container intents belong to this proof')
    return family.stopped(prefix, permanent, output, len(value['intents']))


def execution_cases():
    return [True, False]


def complete_case_inventory(cases):
    require(isinstance(cases, list) and len(cases) == 2 and
        all(isinstance(case, dict) for case in cases), 'Both actual complete connected graph cases are mandatory')
    actual_order = [case.get('case') for case in cases]
    require(actual_order == list(CASE_EXECUTION_ORDER), 'Actual cases must complete the fail-fast refusal before the positive graph')
    indexed = {case['case']: case for case in cases}
    require(len(indexed) == len(CANONICAL_CASE_ORDER) and set(indexed) == set(CANONICAL_CASE_ORDER),
        'Missing or duplicated graph cases cannot become a complete proof')
    return [indexed[name] for name in CANONICAL_CASE_ORDER], actual_order


@contextmanager
def finalize_execution(prefix, permanent, output):
    result = {}
    primary_failure = None
    try:
        yield result
    except BaseException as failure:
        primary_failure = failure
        raise
    finally:
        errors = {}
        try:
            result['stops'] = observed_stops(prefix, permanent, output)
        except Exception as failure:
            errors['owned_container_stops'] = dict(error_type=type(failure).__name__, message=str(failure)[:2048])
        try:
            result['post'] = raw.original_postcheck(output / 'post-verifier')
        except Exception as failure:
            errors['original_whole_root_post_verifier'] = dict(error_type=type(failure).__name__, message=str(failure)[:2048])
        record = dict(primary_failure_type=None if primary_failure is None else type(primary_failure).__name__,
            original_post_verifier=result.get('post'), owned_container_stops=result.get('stops'), errors=errors,
            finalization_succeeded=not errors, successful_graph_claimed=False,
            scientific_authorization_granted=False, g0_granted=False)
        try:
            write(output / 'execution-finalization.json', record)
        except Exception as failure:
            errors['finalization_record'] = dict(error_type=type(failure).__name__)
            print('Independent finalization record could not be written: ' + type(failure).__name__, file=sys.stderr)
        if primary_failure is None and errors:
            raise RuntimeError('Independent container stoppage or original post-verification failed; see retained finalization evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--build-seal', required=True)
    parser.add_argument('--runtime-backend', choices=['owner-canonical'], required=True)
    parser.add_argument('--execute', action='store_true')
    arguments = parser.parse_args()
    require(arguments.execute is True and os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),
        'Explicit already-seen technical replay in a managed worker required')
    require(re.fullmatch('[0-9a-f]{64}', PROXY_SHA) and digest(Path(oci.__file__)) == PROXY_SHA,
        'Connected runtime proxy identity is pending final review; no graph may execute')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    output = permanent / 'frozen-a-legacy-connected-dag'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    build, build_receipt = checked_build(arguments.runner, arguments.build_record, arguments.build_seal, output)
    runner_before = file_identity(arguments.runner)
    runner = temporary / builder.EXAMPLE
    with regular(arguments.runner).open('rb') as incoming, runner.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    runner.chmod(0o700)
    require(digest(runner) == runner_before['sha256'], 'One owned executable copy must equal the sealed build')
    references, reference_receipts = checked_references(output)
    methods, method_before = definitions()
    helper_before = {str(Path(module.__file__).resolve()): file_identity(Path(module.__file__).resolve())
        for module in [sys.modules[__name__], builder, family, raw, raw_dag, gate, mr, oci]}
    facts = source_facts()
    for name, observed in method_before.items():
        target = output / 'method-sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        require(digest(target) == observed['sha256'], 'Pinned method-source snapshot changed')
    contract_file = regular(raw.FAMILY / 'contracts/source-lock.json')
    require(digest(contract_file) == raw.SOURCE_PINS['contracts/source-lock.json'], 'Exact raw contract required')
    contract = strict_json(contract_file.read_bytes())
    raw_before = raw.source_facts(raw.INPUT_PATHS, contract)
    panel_manifest = strict_json(raw.INPUT_PATHS[7].read_bytes())
    panel_before = raw.panel_facts(raw_dag.PANEL_HOST, panel_manifest)
    for name in ['resources', 'pre-verifier', 'post-verifier', 'python-runtime', 'r-runtime']:
        (output / name).mkdir(mode=0o700)
    raw.resource_admission(output / 'resources')
    cgroup = gate.runtime.cgroup_observation()
    write(output / 'resource-envelope.json', dict(actual_parent=cgroup, max_concurrent_our_method_containers=1,
        technical_container_cpus=1, largest_declared_and_actual_child_memory_bytes=2147483648,
        original_MR_resource_contract_certified=False, technical_MR_resource_changes=['cpus 2 to 1', 'pull missing to never'],
        original_MR_default_read_only_rootfs_retained=True,
        plugin_resource_to_native_TaskResources_mapping_proven=False, g0_granted=False))
    pre = raw.original_postcheck(output / 'pre-verifier')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    python_runtime, runtime_prerequisites = raw.prerequisite_archives(archives)
    prefix = raw.backend(output / 'python-runtime', python_runtime)
    require(prefix == family.inspected_backend(output / 'r-runtime'), 'Both official runtimes must use the explicit same owner-canonical backend')
    cases = []
    original_environment = dict(os.environ)
    with finalize_execution(prefix, permanent, output) as finalization:
        for negative in execution_cases():
            label = 'MR-output-conflict' if negative else 'positive'
            work = temporary / ('connected-a-' + label)
            work.mkdir(mode=0o700)
            launcher_temporary = temporary / ('connected-a-launcher-' + label)
            launcher_temporary.mkdir(mode=0o700)
            proxy_output = output / ('proxy-' + label)
            proxy_output.mkdir(mode=0o700)
            workspace_root = temporary / 'official-plugin-container-workspaces' / work.name
            workspace_root.mkdir(parents=True, mode=0o700)
            configuration = oci.install_launcher(prefix, launcher_temporary, proxy_output, workspace_root=workspace_root, fault=negative)
            with retain_case_failure(work, output / ('failed-' + label)):
                ports, nodes = run_graph(runner, build, work, methods, facts, oci.child_environment(configuration), negative=negative,
                    failure_output=output / ('failed-' + label))
                creates = verify_creates(configuration, nodes, negative=negative)
                write(proxy_output / 'checked-creates.json', creates)
                upstream = validate_upstream(ports, methods, contract, raw_before, panel_before)
                comparison = None if negative else compare_positive(work, ports, references)
                destination = output / label
                copied = evidence_copy(work, destination, ports, nodes)
                if negative:
                    foreign = Path(next(row for row in creates if row['role'] == 'mr')['foreign_before']['path'])
                    foreign_before = file_identity(foreign)
                    shutil.copyfile(foreign, destination / 'controlled-foreign-output.bin')
                    require(file_identity(foreign) == foreign_before and digest(destination / 'controlled-foreign-output.bin') == foreign_before['sha256'],
                        'Controlled foreign output evidence changed during transport')
                else:
                    positive_ports = {stage: [destination / stage / path.name for path in paths] for stage, paths in ports.items()}
                cases.append(dict(case=label, nodes=28, edges=65, actual_executed_nodes=24 if negative else 28,
                    actual_skipped_nodes=4 if negative else 0, actual_staged_bindings=20 if negative else 65,
                    actual_method_containers=3 if negative else 7, actual_output_ports=sum(map(len, ports.values())),
                    upstream=upstream, comparison=comparison, copied_evidence_files=len(copied),
                    expected_real_MR_exit2_refusal=negative, scientific_authorization_granted=False, g0_granted=False))
        canonical_cases, actual_order = complete_case_inventory(cases)
        rds = official_rds_compare(prefix, output, positive_ports, references)
    stops, post = finalization['stops'], finalization['post']
    require(len(stops) == 11 and dict(os.environ) == original_environment, 'All eleven owned container intents must stop; parent environment must remain unchanged')
    require(source_facts() == facts and definitions()[1] == method_before and
        raw.source_facts(raw.INPUT_PATHS, contract) == raw_before and raw.panel_facts(raw_dag.PANEL_HOST, panel_manifest) == panel_before and
        file_identity(arguments.runner) == runner_before and digest(runner) == runner_before['sha256'] and
        all(file_identity(Path(name)) == observed for name, observed in helper_before.items()),
        'Canonical inputs, panel, sealed executable, method source or proof source changed')
    write(output / 'verification.json', dict(status='SCOPED_ALREADY_SEEN_O2_CONNECTED_A_DAG_PROVEN_NOT_SCIENTIFIC_RELEASE',
        scope=SCOPE, build=build_receipt, independent_direct_references=reference_receipts,
        runtime_backend='EXPLICIT_OWNER_BOUND_CANONICAL_ALTERNATE_NOT_DEFAULT', runtime_prerequisites=runtime_prerequisites,
        method_sources=method_before, frozen_sources=facts, proof_sources=helper_before,
        cases=canonical_cases, actual_case_execution_order=actual_order,
        whole_official_RDS_comparison=rds, all_owned_container_intents_stopped=11,
        total_actual_task_receipts=52, total_staged_bindings=85, frozen_family_counts=family.contract.COUNTS,
        primary_p_remains_missing=True, original_unresolved_overlap_entries_preserved=275,
        previous_results_are_already_seen=True, scientific_new_independent_evidence=False,
        original_whole_root_verifier_pre=pre, original_whole_root_verifier_post=post,
        whole_root_verifier_hashes_raw_file_bytes=True, method_parses_raw_only_in_frozen_input_qualification=True,
        raw_inputs_archived=False, original_method_resources_certified=False, production_changed=False,
        resident_DAG_execution_proven=False, full_plan_completed=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
