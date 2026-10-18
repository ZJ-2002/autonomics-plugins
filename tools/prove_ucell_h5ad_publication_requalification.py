"""Requalify the complete synthetic UCell inventory after an explicit publication-only source upgrade."""

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_frozen_a_harmonisation_dag as admission
from tools import prove_h5ad_subset_official_runtime as runtime
from tools import prove_ucell_current_dag as previous
from tools import frozen_a_legacy_connected_runtime as transport
from tools.prove_frozen_a_family_runtime import stopped
from tools.prove_locked_b_source_transport import actual_ports, expected_refusal
from tools.reconcile_ab_evidence_index import verify_archive

REFERENCE = Path('/home/zj-normal/Work/autonomics/results/cachexia-v4.3.2/canonical-h5ad-ucell-v1-20261012')
REFERENCE_SEAL = '633c610ae6e69e203b63d07d13d2fdc6c68a928b2b21cf458803ab261b08cd7d'
FINAL_SEAL = '8f7efb82e743a09f0eaf9d46e1cfa4cb07dbabcffcfb5f1020e239bfb6af2d26'
BASELINE_SHA = 'a7a9dff18744e702c9caffa5d12076cd0fa008511892237b972e590d27f3b861'
SCRIPT_SHA = 'eb36132059f988864c0be04995d7b72aef04ff988e6e20faae8d9ca602c79af8'
MANIFEST_SHA = '337439a2100332e95888a7c833baffadfd53836c4d49f334a85d8b2a3a6b9f6e'
NON_PUBLICATION_AST_SHA = '40c8ecec26d37d18bf0ec19abb9d03d0216b94d3da3030beba65e040028af69f'
REGRESSION_SESSION = 'ec81ba947425422298ea94523ec8c332'
REGRESSION_SEAL = '1c8c493a50347fb09aefb6417fa6b5c33e019bc83750145dd70c8eb3468fe261'
BUILD_SESSION = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
ENGINE = '4256643c55ae6fb50e8c867069330ed6ac2b4bc0'
RUNNER_SHA = '636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b'
IMAGE = 'ghcr.io/zj-2002/ucell-h5ad-official@sha256:e18149dc957c70161029c3451584d7285ab08af2174926c593b8ae285f2dd133'
CONFIG_SHA = 'bcae27f4aa71408c3ef31ce00ad35777031a3c7d3efc0cf64e1cdc51cfee94a8'
SDK_RESOURCE_SOURCE = dict(revision=ENGINE, path='crates/container-runtime/src/podman.rs', function='podman_size',
    sha256='85d53f3a10c8a7eeba67e7210f143b51d0bdb7c5f7313137478820a7acee81a8',
    g_multiplier=1000000000, gi_multiplier=1073741824)
SCOPE = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
SOURCES = {
    'plugins/ucell-h5ad/manifest.toml': MANIFEST_SHA,
    'plugins/ucell-h5ad/scripts/score.py': SCRIPT_SHA,
    'tools/prove_ucell_current_dag.py': '49ef6839d043aa4f31f055ce710ab33b6466f6184e7c7877a8e602f95f418ff5',
    'tools/verify_ucell_current_h5ad.py': '8598a5dba88edb17c2e46baf45ea5d9844694523d2881031a6157cb2bde50658',
    'plugins/single-cell/tests/qc_compare.py': '2c4a19aad9daaac942f04b9a95b18351e53ab979a49a9df477245e958bb36ac6',
}
HELPER_PINS = {
    'tools/prove_frozen_a_harmonisation_dag.py': '8e27e01930e97bdbd84d57ca398253b705bc0ff2e5d6a88d0f5781cde66ef54e',
    'tools/prove_frozen_a_harmonisation.py': '79b36d2f5a64409f0b8b87735b7773f29dd3dedeaa3809ddb14a4c7a97685018',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_ucell_current_dag.py': '49ef6839d043aa4f31f055ce710ab33b6466f6184e7c7877a8e602f95f418ff5',
    'tools/frozen_a_legacy_connected_runtime.py': '3b4f98f6abaad13987e39ff784f6f77c5b8f0de25255c5af8d5a5560fd6bd73f',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
    'tools/prove_locked_b_source_transport.py': '191b0dccfe26e21f9fdd0c727ef1be52306927791e98e01242d82d690691dd56',
    'tools/prove_current_ldsc.py': '939159c038af706bca99530302eac5b6eed95d768536b29d80bd6baf2cba229d',
    'tools/reconcile_ab_evidence_index.py': '44878add55a5a656f15e2c936e269ba1ef9b2c4a16c81e7a5c22733da6975c72',
}
POSITIVES = ('dense', 'csr', 'csc', 'float32', 'integer32', 'boolean', 'reordered', 'negative-values',
    'close-floating-values', 'signed-int-edge', 'tied-ranks', 'flat-small-background', 'flat-large-background',
    'rank-cutoff', 'rank-boundary', 'unrelated-raw', 'old-parameters', 'one-cell', 'one-program', 'multiple-batches')
METHOD_REFUSALS = ('no-X', 'zero-cells', 'zero-genes', 'nan-X', 'inf-X', 'complex-X', 'integer-over-53',
    'unsigned-over-53', 'duplicate-int-over-53', 'bad-sparse-index', 'duplicate-cell', 'duplicate-gene',
    'empty-cell', 'empty-gene', 'tab-gene', 'malformed-json', 'empty-programs', 'duplicate-json-key',
    'empty-signature', 'numeric-member', 'empty-name', 'score-collision', 'ambiguous-sign', 'no-overlap',
    'over-maxrank', 'undefined-official-score')
DIRECT = frozenset({'h5ad-exists', 'report-exists', 'dangling-output', 'output-alias', 'input-overwrite',
    'second-link-failure', 'R-failure'})
PREFLIGHTS = ('missing-gene-sets', 'unknown-parameter', 'missing-input-edge')
require, fact, strict_json, write = runtime.require, runtime.fact, runtime.strict_json, runtime.write

COMPARISON = '''import json,sys
from pathlib import Path
import h5py
sys.path.insert(0,'/proof')
from verify_ucell_current_h5ad import compare
root=Path('/proof')
names=json.loads((root/'positive-cases.json').read_text())
assert len(names)==len(set(names))==20
records=[]
for name in names:
    directory=root/name
    with h5py.File(directory/'output.h5ad') as actual,h5py.File(directory/'fresh-author.h5ad') as expected:
        actual_names=[]; expected_names=[]
        actual.visit(actual_names.append);expected.visit(expected_names.append)
        assert actual_names==expected_names
        for key in expected_names:
            assert type(actual[key]) is type(expected[key])
            if isinstance(expected[key],h5py.Dataset): assert actual[key].shape==expected[key].shape
    records.append(compare(directory))
assert all(record['complete_AnnData_and_HDF5'] is True and record['G0'] is False for record in records)
(root/'whole-object-readback.json').write_text(json.dumps(dict(cases=records,sealed_author_outputs_regenerated=False,
    explicit_HDF5_dataset_shapes_checked=True,G0=False),indent=2)+'\\n')
print('VERIFIED_COMPLETE_H5AD_CASES',len(records))
'''


def ordinary_member(name):
    require(isinstance(name, str) and name and '\\' not in name and
        not PurePosixPath(name).is_absolute() and str(PurePosixPath(name)) == name and
        all(part not in ('', '.', '..') for part in name.split('/')), 'Literal contained reference member required')
    return name


def helper_payload(path, expected):
    if not path.is_absolute() or path.resolve(strict=True) != path or any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError('Literal unaliased helper source required')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 512 * 1024:
        raise ValueError('Bounded ordinary helper source required')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if signature(os.fstat(handle.fileno())) != signature(before):
            raise ValueError('Helper source changed before read')
        payload = handle.read(512 * 1024 + 1)
        after = os.fstat(handle.fileno())
    checksum = hashlib.sha256(payload).hexdigest()
    if (signature(after) != signature(before) or signature(path.lstat()) != signature(before) or
            len(payload) != before.st_size or checksum != expected):
        raise ValueError('Pinned helper source contents or identity changed')
    return dict(bytes=len(payload), sha256=checksum, identity=list(signature(after))), payload


def helper_source_facts(base=ROOT):
    result = {}
    for name, expected in HELPER_PINS.items():
        ordinary_member(name)
        result[name] = helper_payload(base / name, expected)[0]
    if sum(item['bytes'] for item in result.values()) > 2 * 1024**2:
        raise ValueError('Small helper source-only snapshot budget exceeded')
    return result


def check_loaded_helpers():
    functions = [fact, write, strict_json, require, runtime.cgroup_observation, runtime.default_backend,
        admission.checked_build, admission.executable_copy, admission.checked_task_receipts,
        admission.validate_memory_report, admission.file_identity, admission.digest, admission.require,
        previous.settings_for, previous.expected_error, transport.workspace_mount, transport.sdk_environment,
        transport.option, transport.container_file, transport.regular_fact, transport.directory,
        stopped, actual_ports, expected_refusal, actual_ports.__globals__['digest'], verify_archive]
    result = []
    for function in functions:
        module = sys.modules.get(function.__module__)
        if module is None or not getattr(module, '__file__', None):
            raise ValueError('Actual helper callable must belong to a loaded pinned module')
        path = Path(module.__file__).absolute()
        name = path.relative_to(ROOT).as_posix()
        if (name not in HELPER_PINS or function.__globals__ is not module.__dict__ or
                Path(function.__code__.co_filename).absolute() != path or module.__dict__.get(function.__name__) is not function):
            raise ValueError('Actual loaded helper binding differs from the pinned source call path')
        result.append(dict(module=module.__name__, function=function.__name__, source=name, source_sha256=HELPER_PINS[name]))
    return result


def snapshot_helpers(destination, before, base=ROOT):
    if set(before) != set(HELPER_PINS):
        raise ValueError('Every used helper source is required before snapshot')
    destination.mkdir(mode=0o700)
    result = {}
    for name, expected in HELPER_PINS.items():
        observed, payload = helper_payload(base / name, expected)
        if observed != before[name]:
            raise ValueError('Helper source changed before its permanent snapshot')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(payload)
        result[name] = helper_payload(target, expected)[0]
        if {key: result[name][key] for key in ['bytes', 'sha256']} != {key: before[name][key] for key in ['bytes', 'sha256']}:
            raise ValueError('Permanent helper snapshot bytes differ')
    return result


def helper_postcheck(before, snapshots, loaded, destination):
    if (helper_source_facts() != before or helper_source_facts(destination) != snapshots or
            check_loaded_helpers() != loaded):
        raise ValueError('Actual helper source, loaded binding or small permanent snapshot changed')
    return dict(all_pinned_sources_unchanged=True, all_small_snapshots_unchanged=True,
        actual_loaded_bindings_unchanged=True, g0_granted=False)


def driver_source_postcheck(before, snapshot):
    if fact(Path(__file__).resolve()) != before or fact(snapshot)['sha256'] != before['sha256']:
        raise ValueError('Actual qualification driver or its small permanent source snapshot changed')
    return dict(original=before, snapshot=fact(snapshot), unchanged=True, g0_granted=False)


def nonpublication_ast(payload):
    tree = ast.parse(payload)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'publish']
    require(len(selected) == 1, 'Exactly one publication implementation required')
    tree.body = [node for node in tree.body if node is not selected[0]]
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


def validate_source_upgrade(old_payload, current_payload):
    require(hashlib.sha256(old_payload).hexdigest() == BASELINE_SHA and
        hashlib.sha256(current_payload).hexdigest() == SCRIPT_SHA and
        nonpublication_ast(old_payload) == nonpublication_ast(current_payload) == NON_PUBLICATION_AST_SHA,
        'Only the explicitly reviewed publication-only upgrade may replace the sealed old adapter')
    return dict(original_sha256=BASELINE_SHA, current_sha256=SCRIPT_SHA,
        all_nonpublication_AST_sha256=NON_PUBLICATION_AST_SHA, official_scoring_body_changed=False)


def checked_reference(root):
    require(root == REFERENCE and root.resolve(strict=True) == root,
        'The canonical sealed technical reference is fixed, not a new fixture source')
    require(fact(root / 'SEALED_FILES.json')['sha256'] == REFERENCE_SEAL and
        fact(root / 'FINAL_VERIFICATION.json')['sha256'] == FINAL_SEAL, 'Both original reference seals must remain exact')
    seal = strict_json((root / 'SEALED_FILES.json').read_bytes())
    groups = [seal['files'], seal['internal_links'], seal['declared_negative_fixture_links']]
    require([len(group) for group in groups] == [1901, 10, 3] and seal['undeclared_external_data_links'] == [],
        'All 1901 ordinary files, ten internal links and three declared negative fixtures are mandatory')
    indexes = [{ordinary_member(row['path']): row for row in group} for group in groups]
    require(all(len(index) == len(group) for index, group in zip(indexes, groups, strict=True)) and
        len(set().union(*indexes)) == sum(map(len, indexes)), 'Duplicate or overlapping reference declarations forbidden')
    expected = set().union(*indexes) | {'SEALED_FILES.json', 'FINAL_VERIFICATION.json'}
    actual = set()
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        for name in [*subdirectories, *filenames]:
            path = Path(directory) / name
            if path.is_symlink() or path.is_file():
                actual.add(path.relative_to(root).as_posix())
    require(actual == expected, 'Original complete reference membership differs')
    total = 0
    for name, identity in indexes[0].items():
        observed = fact(root / name)
        require(type(identity['size']) is int and observed['bytes'] == identity['size'] and
            observed['sha256'] == identity['sha256'], 'Original sealed ordinary file changed: ' + name)
        total += observed['bytes']
    for name, identity in indexes[1].items():
        source = root / name
        target = root / ordinary_member(identity['target'])
        require(identity['target'] in indexes[0] and source.is_symlink() and source.resolve(strict=True) == target and
            fact(target)['sha256'] == identity['sha256'], 'Original internal reference identity changed')
    for name, identity in indexes[2].items():
        source = root / name
        require(source.is_symlink() and os.readlink(source) == identity['target'] == 'absent.h5ad' and not source.exists(),
            'Original intentional negative dangling fixture changed')
    require(total == 108033663, 'Complete sealed reference byte denominator differs')
    old_source = (root / 'plugin-source/plugins/ucell-h5ad/scripts/score.py').read_bytes()
    upgrade = validate_source_upgrade(old_source, (ROOT / 'plugins/ucell-h5ad/scripts/score.py').read_bytes())
    positive = strict_json((root / 'repaired-official-v1/SUMMARY.json').read_bytes())['records']
    negative = strict_json((root / 'repaired-boundaries-v1/SUMMARY.json').read_bytes())['records']
    require([row['case'] for row in positive] == list(POSITIVES) and len(negative) == 34 and
        {row['case'] for row in negative} == set(METHOD_REFUSALS) | DIRECT | {'missing-gene-sets'},
        'The original complete 54-case inventory cannot shrink or change')
    return dict(files=1901, bytes=total, internal_links=10, negative_links=3,
        reference_seal=REFERENCE_SEAL, final_verification_sha256=FINAL_SEAL, source_upgrade=upgrade,
        sealed_author_outputs_regenerated=False)


def checked_regression(archives):
    verified = verify_archive(archives, REGRESSION_SESSION, REGRESSION_SEAL)
    root = Path(verified['artifact_root']) / 'permanent/b-publication-ownership'
    state = strict_json((archives / REGRESSION_SESSION / 'SESSION.json').read_bytes())
    require(verified['positive_worker_exit_verified'] is True and type(state.get('launcher_exit_status')) is int and
        state['launcher_exit_status'] == 0, 'Publication regressions must have truly completed successfully')
    execution = strict_json((root / 'tests-execution.json').read_bytes())
    ids = execution['actual_test_ids']
    selected = [name for name in ids if name.startswith('tests.test_ucell_h5ad_publication.')]
    require(type(execution.get('tests_run')) is int and execution['tests_run'] == len(ids) == len(set(ids)) == 52 and
        len(selected) == len(set(selected)) == 23 and set(ids) == set(execution['required_test_ids']) and
        execution['complete'] is True and all(type(execution.get(name)) is int and execution[name] == 0
        for name in ['failures', 'errors', 'skipped']), 'All exact 23 source-bound publication controls must actually pass')
    report = strict_json((root / 'verification.json').read_bytes())
    require(report['current_sources']['plugins/ucell-h5ad/scripts/score.py'] ==
        dict(bytes=19054, sha256=SCRIPT_SHA) and report['official_UCell_or_singscore_computation_executed'] is False and
        report['g0_granted'] is False, 'Mechanical publication evidence is not official numerical requalification')
    return dict(session=REGRESSION_SESSION, seal=REGRESSION_SEAL, files=verified['files'],
        bytes=verified['bytes'], actual_h5ad_tests=selected, official_numerics_inherited=False)


def job_for(work, source, settings):
    return dict(scope=SCOPE, run_root=str(work), expected_plugin_name='ucell-h5ad',
        plugin_manifest=str(source / 'manifest.toml'), plugin_manifest_sha256=MANIFEST_SHA,
        script_sha256={'scripts/score.py': SCRIPT_SHA}, additional_plugins=[], bundles=[],
        panel_overrides=[], panel_manifest_sha256={},
        nodes=[dict(id='input', kind='file_reference', spec=dict(path='vfs:///input.h5ad', format='h5ad', hash_content=True)),
            dict(id='analysis', kind='h5ad_ucell_score', spec=settings)],
        edges=[{'from': 'input', 'from_port': 0, 'to': 'analysis', 'to_port': 0}])


def captured(command, destination, label, **keywords):
    def persist(content, stream):
        payload = b'' if content is None else content.encode() if isinstance(content, str) else content
        with (destination / (label + '.' + stream)).open('xb') as handle:
            handle.write(payload)
    try:
        result = subprocess.run(command, **keywords)
    except subprocess.TimeoutExpired as error:
        persist(error.stdout, 'stdout')
        persist(error.stderr, 'stderr')
        write(destination / (label + '-execution.json'), dict(actual_exit=None, timed_out=True))
        raise
    persist(result.stdout, 'stdout')
    persist(result.stderr, 'stderr')
    write(destination / (label + '-execution.json'), dict(actual_exit=result.returncode, timed_out=False))
    return result


def capture_method_logs(scratch, destination):
    destination.mkdir(exist_ok=True)
    copied = {}
    if scratch.exists():
        for path in scratch.glob('*/*/.autonomics/logs/*'):
            require(path.name in {'stdout.log', 'stderr.log'} and path.resolve(strict=True) == path and
                path.stat().st_uid == os.getuid() and path.stat().st_size <= 4 * 1024**2,
                'Only this bounded owned method log may be retained')
            name = path.parents[3].name + path.parents[2].name + '-' + path.name
            observed = fact(path)
            target = destination / name
            require(not target.exists(), 'Method diagnostics must not overwrite earlier evidence')
            shutil.copyfile(path, target)
            require(fact(target)['sha256'] == observed['sha256'] and fact(path) == observed, 'Method log changed during retention')
            copied[name] = observed
    write(destination / 'captured.json', dict(files=copied, complete_workspace_copied=False,
        inputs_copied=False, g0_granted=False))
    return copied


def inspect_image(prefix, output, label):
    result = captured([*prefix, 'image', 'inspect', IMAGE], output, label, capture_output=True, timeout=60)
    require(type(result.returncode) is int and result.returncode == 0, 'The exact installed official image must already be available')
    rows = strict_json(result.stdout)
    require(len(rows) == 1 and rows[0]['Id'].removeprefix('sha256:') == CONFIG_SHA, 'Installed official configuration differs')
    store = Path.home() / '.local/share/containers/storage/overlay-images' / CONFIG_SHA
    encoded = lambda value: '=' + base64.b64encode(value.encode()).decode()
    manifest_path = store / encoded('manifest-sha256:' + IMAGE.split('@sha256:', 1)[1])
    config_path = store / encoded('sha256:' + CONFIG_SHA)
    manifest, configuration = manifest_path.read_bytes(), config_path.read_bytes()
    require(hashlib.sha256(manifest).hexdigest() == IMAGE.split('@sha256:', 1)[1] and
        hashlib.sha256(configuration).hexdigest() == CONFIG_SHA, 'The actual parsed immutable image buffers differ')
    parsed, config = strict_json(manifest), strict_json(configuration)
    require(parsed['config']['digest'] == 'sha256:' + CONFIG_SHA and config['architecture'] == 'amd64' and
        config['os'] == 'linux' and rows[0]['RootFS']['Layers'] == config['rootfs']['diff_ids'],
        'Official manifest/configuration/ordered layer chain differs')
    (output / (label + '-manifest.json')).write_bytes(manifest)
    (output / (label + '-configuration.json')).write_bytes(configuration)
    return dict(manifest_sha256=IMAGE.split('@sha256:', 1)[1], configuration_sha256=CONFIG_SHA,
        ordered_diff_ids=config['rootfs']['diff_ids'], default_backend=True, installed_only_no_pull=True)


def prepare_create(arguments, allowed):
    original = list(arguments)
    require(arguments and arguments[0] == 'create', 'Exact SDK create argv required')
    pairs = {'--name', '--network', '--security-opt', '--tmpfs', '--pull', '--user', '--userns', '--shm-size',
        '--cpus', '--memory', '--memory-swap', '--pids-limit', '--env', '--mount', '--workdir'}
    seen = set()
    position = 1
    while position < len(arguments) and arguments[position] != '--entrypoint':
        option = arguments[position]
        if option == '--read-only':
            require(option not in seen, 'Repeated read-only flag rejected')
            seen.add(option)
            position += 1
            continue
        require(option in pairs and position + 1 < len(arguments) and isinstance(arguments[position + 1], str),
            'Only exact compiled SDK option/value slots are allowed')
        require(option in {'--env', '--mount'} or option not in seen, 'Duplicate SDK option rejected')
        seen.add(option)
        position += 2
    workspace = transport.workspace_mount(arguments, allowed)
    relative = workspace.relative_to(allowed)
    require(len(relative.parts) == 3 and relative.parts[0] in set(POSITIVES) | set(METHOD_REFUSALS) and
        re.fullmatch('[0-9a-f]{2}', relative.parts[1]) and re.fullmatch('[0-9a-f]{62}', relative.parts[2]),
        'Only a named original synthetic method-case workspace is allowed')
    selected = transport.sdk_environment(arguments)
    require(transport.option(arguments, '--workdir') == '/work' and
        selected.get('AUTONOMICS_WORKDIR') == '/work' and selected.get('AUTONOMICS_SCRIPT') == '/work/.autonomics/script' and
        selected.get('AUTONOMICS_INPUT_COUNT') == '1' and selected.get('AUTONOMICS_OUTPUT_COUNT') == '2',
        'Exact UCell script/workdir and one-input/two-output ABI required')
    inputs = {name: value for name, value in selected.items() if re.fullmatch('AUTONOMICS_INPUT[0-9]+', name)}
    outputs = {name: value for name, value in selected.items() if re.fullmatch('AUTONOMICS_OUTPUT[0-9]+', name)}
    require(set(inputs) == {'AUTONOMICS_INPUT0'} and set(outputs) == {'AUTONOMICS_OUTPUT0', 'AUTONOMICS_OUTPUT1'},
        'Unexpected input/output port environment rejected')
    script = transport.container_file(workspace, selected['AUTONOMICS_SCRIPT'])
    require(fact(script)['sha256'] == SCRIPT_SHA, 'Only the exact requalified scoring script may execute')
    expected_input = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-h5ad-publication-requalification' / relative.parts[0] / 'input.h5ad'
    staged = transport.container_file(workspace, inputs['AUTONOMICS_INPUT0'])
    require(staged == workspace / '.autonomics/inputs/input-0.h5ad' and staged.is_symlink() and
        os.readlink(staged) == str(expected_input) and staged.resolve(strict=True) == expected_input and
        fact(expected_input)['bytes'] > 0, 'The default SDK link must point only to this owned original synthetic input')
    mounts = [arguments[index + 1] for index, value in enumerate(arguments[:-1]) if value == '--mount']
    require(len(mounts) == 2 and set(mounts) == {
        'type=bind,source=' + str(workspace) + ',destination=/work,rw=true',
        'type=bind,source=' + str(expected_input.parent) + ',destination=' + str(expected_input.parent) + ',readonly'},
        'Only this owned workspace and its exact read-only synthetic input parent may be mounted')
    require([outputs['AUTONOMICS_OUTPUT' + str(index)] for index in range(2)] == ['/work/output.h5ad', '/work/report.json'] and
        all(not os.path.lexists(workspace / name) for name in ['output.h5ad', 'report.json']), 'Exact fresh declared output paths required')
    entrypoint = arguments.index('--entrypoint')
    require(arguments.count('--entrypoint') == 1 and arguments[entrypoint + 1:] == ['python', IMAGE, '/work/.autonomics/script'] and
        transport.option(arguments, '--cpus') == '2' and transport.option(arguments, '--memory') == '8589934592' and
        arguments.count('--read-only') == 1 and transport.option(arguments, '--network') == 'none' and
        transport.option(arguments, '--pull') == 'missing', 'Actual immutable SDK image, resource and default read-only policy differ')
    require(transport.option(arguments, '--security-opt') == 'no-new-privileges' and
        transport.option(arguments, '--tmpfs') == '/tmp:rw,nosuid,nodev' and
        transport.option(arguments, '--user') == str(os.getuid()) + ':' + str(os.getgid()) and
        transport.option(arguments, '--userns') == 'keep-id' and
        transport.option(arguments, '--shm-size') == '1073741824' and transport.option(arguments, '--pids-limit') == '512' and
        ('--memory-swap' not in seen or transport.option(arguments, '--memory-swap') == '8589934592'),
        'The original SDK security/user and resource options must remain unchanged')
    require(re.fullmatch('autonomics-container-command-[0-9]+-[0-9]+', transport.option(arguments, '--name')),
        'A literal SDK run name is required for the owned create receipt')
    changed = list(arguments)
    changed[changed.index('--pull') + 1] = 'never'
    require(changed[:changed.index('--pull')] == original[:original.index('--pull')] and original == arguments,
        'The narrow technical proxy must not mutate caller argv')
    return changed, dict(workspace=str(workspace), name=transport.option(arguments, '--name'),
        script_sha256=SCRIPT_SHA, image=IMAGE, cpus='2', memory='8589934592',
        original_pull='missing', effective_pull='never', network='none', read_only_rootfs=True,
        original_manifest_resources_certified=False, parameters_changed=False, g0_granted=False)


def check_staged_input(work, workspace, bindings):
    original = work / 'input.h5ad'
    expected = fact(original)
    require(len(bindings) == 1 and bindings[0]['from'] == 'input' and bindings[0]['from_port'] == 0 and
        bindings[0]['to_port'] == 0 and bindings[0]['path'] == 'vfs:///input.h5ad' and bindings[0].get('kind') == 'File' and
        bindings[0]['fingerprint']['size'] == expected['bytes'] and
        bindings[0]['fingerprint'].get('content_hash') in [None, 'sha256:' + expected['sha256']], 'Exact complete original input role required')
    staged = workspace / '.autonomics/inputs/input-0.h5ad'
    require(staged.is_symlink() and os.readlink(staged) == str(original) and staged.resolve(strict=True) == original,
        'The unchanged manifest default must stage only this exact owned input link')
    require(fact(staged.resolve(strict=True)) == expected and fact(original) == expected,
        'Full staged input bytes and original identity must remain unchanged')
    return dict(mode='EXACT_OWNED_SYNTHETIC_INPUT_SYMLINK', bytes=expected['bytes'], sha256=expected['sha256'])


def proxy_main(prefix, allowed, records):
    helper_source_facts()
    check_loaded_helpers()
    arguments = sys.argv[1:]
    if arguments and arguments[0] == 'create':
        arguments, record = prepare_create(arguments, Path(allowed))
        with (Path(records) / (record['name'] + '.json')).open('x') as handle:
            json.dump(record, handle, indent=2)
    os.execv(prefix[0], [*prefix, *arguments])


def launcher(prefix, temporary, output, allowed):
    require(prefix == [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--cgroup-manager=cgroupfs'], 'Only the explicit default managed shim is allowed')
    source = output / 'proxy-source.py'
    source.write_bytes(Path(__file__).read_bytes())
    checksum = fact(source)['sha256']
    records = output / 'actual-creates'
    records.mkdir()
    directory = temporary / 'ucell-requalification-bin'
    directory.mkdir()
    executable = directory / 'podman'
    program = '''#!/usr/bin/python3
import hashlib
from pathlib import Path
payload=Path(__SOURCE__).read_bytes()
if hashlib.sha256(payload).hexdigest()!=__HASH__: raise SystemExit('Proxy source changed')
scope={'__name__':'ucell_requalification_proxy','__file__':__ORIGINAL__}
exec(compile(payload,__SOURCE__,'exec'),scope)
scope['proxy_main'](__PREFIX__,__ALLOWED__,__RECORDS__)
'''.replace('__SOURCE__', repr(str(source))).replace('__HASH__', repr(checksum)).replace(
        '__ORIGINAL__', repr(str(Path(__file__)))).replace('__PREFIX__', repr(prefix)).replace(
        '__ALLOWED__', repr(str(allowed))).replace('__RECORDS__', repr(str(records)))
    executable.write_text(program)
    executable.chmod(0o700)
    return dict(os.environ, PATH=str(directory) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin'))


def validate_inventory(records, direct, preflight, comparison):
    require(len(records) == 46 and len({row['case'] for row in records}) == 46 and
        {row['case'] for row in records if row.get('positive') is True} == set(POSITIVES) and
        {row['case'] for row in records if row.get('positive') is False} == set(METHOD_REFUSALS), 'All 46 complete actual method DAG cases are mandatory')
    for row in records:
        for name, expected in [('actual_exit', 0 if row['positive'] else 2), ('nodes', 2), ('edges', 1),
                ('actual_task_receipts', 2), ('actual_input_bindings', 1), ('output_ports', 2 if row['positive'] else 0)]:
            require(type(row.get(name)) is int and row[name] == expected, 'Complete typed actual DAG execution counts required')
    require(len(direct) == 7 and {row['case'] for row in direct} == DIRECT and all(row.get('exact_refusal') is True for row in direct),
        'All seven direct controls must actually complete')
    require(all(type(row.get('actual_exit')) is int and row['actual_exit'] == (3 if row['case'] == 'second-link-failure' else 2)
        and row.get('actual_DAG_entered') is False for row in direct), 'Direct controls must retain exact original method-specific exits')
    require(len(preflight) == 3 and {row['case'] for row in preflight} == set(PREFLIGHTS) and
        all(row.get('actual_DAG_entered') is False and row.get('exact_refusal') is True for row in preflight),
        'The original required-param control and both additional graph controls are mandatory')
    require(all(type(row.get('actual_exit')) is int and row['actual_exit'] == 1 for row in preflight), 'Exact preflight exits required')
    rows = comparison.get('cases')
    require(isinstance(rows, list) and len(rows) == 20 and {row['case'] for row in rows} == set(POSITIVES) and
        comparison.get('sealed_author_outputs_regenerated') is False and comparison.get('explicit_HDF5_dataset_shapes_checked') is True,
        'All twenty complete unchanged author objects must actually be read and compared')
    for row in rows:
        require(type(row.get('finite_values_checked')) is int and row['finite_values_checked'] > 0 and
            row.get('complete_AnnData_and_HDF5') is True and
            row.get('complete_report_except_externally_revalidated_output_identity') is True and
            row.get('numeric_atol') == 1e-12 and type(row.get('numeric_rtol')) is int and row['numeric_rtol'] == 0 and row.get('G0') is False,
            'Complete H5AD, exact integer identities and unchanged declared numeric tolerance required')
    require(sum(row['finite_values_checked'] for row in rows) == 148165, 'The complete original numeric comparison denominator differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    arguments = parser.parse_args()
    require(arguments.execute is True and os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),
        'Explicit managed technical execution is required')
    permanent, temporary = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']), Path(os.environ['TMPDIR'])
    output = permanent / 'ucell-h5ad-publication-requalification'
    output.mkdir()
    driver_before = fact(Path(__file__).resolve())
    shutil.copyfile(__file__, output / 'driver.py')
    require(fact(output / 'driver.py')['sha256'] == driver_before['sha256'], 'Driver snapshot differs from the executing source')
    helper_before = helper_source_facts()
    loaded_helpers = check_loaded_helpers()
    helper_snapshots = snapshot_helpers(output / 'helper-source', helper_before)
    write(output / 'helper-source-identity.json', dict(originals=helper_before, snapshots=helper_snapshots,
        loaded_function_bindings=loaded_helpers, scope='USED_PROOF_CALL_PATHS_NOT_WHOLE_ENVIRONMENT_OR_HOSTILE_MEMORY_ATTESTATION',
        no_dependency_environment_copied=True, g0_granted=False))
    before = {name: fact(ROOT / name) for name in SOURCES}
    require(all(before[name]['sha256'] == expected for name, expected in SOURCES.items()), 'Reviewed current or comparison source changed')
    write(output / 'verified-reference.json', checked_reference(REFERENCE))
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    write(output / 'verified-regression.json', checked_regression(archives))
    build_root = archives / BUILD_SESSION / 'artifacts/permanent/locked-b-probe-build'
    build, build_receipt = admission.checked_build(archives, build_root / 'official_plugin_dag', build_root / 'build-record.json', BUILD_SEAL)
    require(build['engine_commit'] == ENGINE and build_receipt['runner_sha256'] == RUNNER_SHA, 'Only the explicitly older sealed 23-guard SDK may be reused')
    runner, runner_before = admission.executable_copy(build_root / 'official_plugin_dag', temporary)
    runner_copy_before = fact(runner)
    write(output / 'verified-build.json', build_receipt)
    source = output / 'source/ucell-h5ad'
    (source / 'scripts').mkdir(parents=True)
    for name in ['manifest.toml', 'scripts/score.py']:
        shutil.copyfile(ROOT / 'plugins/ucell-h5ad' / name, source / name)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    definition = manifest['nodes'][0]
    require(len(manifest['nodes']) == 1 and manifest['image']['reference'] == IMAGE and
        definition['resources'] == dict(cpus=2.0, memory='8Gi', pids_limit=512, shm_size='1Gi'), 'Original manifest resource declarations must not change')
    comparison_source = output / 'source/single-cell/tests'
    comparison_source.mkdir(parents=True)
    shutil.copyfile(ROOT / 'plugins/single-cell/tests/qc_compare.py', comparison_source / 'qc_compare.py')
    shutil.copyfile(ROOT / 'tools/verify_ucell_current_h5ad.py', output / 'verify_ucell_current_h5ad.py')
    (output / 'compare.py').write_text(COMPARISON)
    resource = runtime.cgroup_observation()
    require(resource['memory_max_bytes'] == 2 * 1024**3, 'This bounded technical parent must retain its exact 2GiB limit')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3, 'At least four GiB system memory reserve required before this tiny synthetic replay')
    write(output / 'resource-admission.json', dict(parent=resource, available_memory_bytes=available,
        manifest_memory_bytes=8 * 1024**3, manifest_cpus=2, effective_parent_limit_bytes=2 * 1024**3,
        resource_quantity_source=SDK_RESOURCE_SOURCE,
        original_8GiB_resource_qualification_granted=False, full_scale_certified=False, g0_granted=False))
    require(shutil.disk_usage(temporary).free >= 2 * 1024**3, 'At least two GiB disposable capacity required')
    prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--cgroup-manager=cgroupfs']
    runtime.default_backend(prefix, output)
    image_before = inspect_image(prefix, output, 'image-before')
    allowed = temporary / 'official-plugin-container-workspaces'
    allowed.mkdir(exist_ok=True)
    environment = launcher(prefix, temporary, output, allowed)
    thread_variables = ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']
    environment.update({name: '1' for name in thread_variables})
    records, direct, preflight, dangling_fixtures = [], [], [], []
    failure = None
    try:
        for name in [*PREFLIGHTS, *METHOD_REFUSALS, *POSITIVES]:
            work = output / name
            work.mkdir()
            positive = name in POSITIVES
            original = REFERENCE / ('repaired-official-v1' if positive else 'repaired-boundaries-v1') / (name if name not in PREFLIGHTS[1:] else 'no-X')
            if name in PREFLIGHTS[1:]:
                original = REFERENCE / 'repaired-official-v1/dense'
            shutil.copyfile(original / 'input.h5ad', work / 'input.h5ad')
            settings = previous.settings_for('dense' if name in PREFLIGHTS[1:] else name, original)
            job = job_for(work, source, settings)
            if name == 'unknown-parameter':
                job['nodes'][1]['spec']['unexpected_free_parameter'] = 1
            elif name == 'missing-input-edge':
                job['edges'] = []
            write(work / 'job.json', job)
            scratch = allowed / name
            try:
                completed = captured([str(runner), str(work / 'job.json')], work, 'runner', capture_output=True,
                    text=True, timeout=600, env=dict(environment, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
                if name in PREFLIGHTS:
                    marker = ('node `h5ad_ucell_score`: missing required param `gene_sets`' if name == 'missing-gene-sets'
                        else 'node `h5ad_ucell_score`: unknown param `unexpected_free_parameter`' if name == 'unknown-parameter'
                        else 'PortDisconnected { node: "analysis", port: 0 }')
                    require(type(completed.returncode) is int and completed.returncode == 1 and marker in completed.stderr and
                        not (work / 'dag-report.json').exists(), 'Exact pre-execution graph diagnostic required')
                    preflight.append(dict(case=name, exact_refusal=True, actual_DAG_entered=False, actual_exit=1))
                    continue
                require(type(completed.returncode) is int and completed.returncode == 0, 'Runner infrastructure failed')
                report = strict_json((work / 'dag-report.json').read_bytes())
                require(report['scope'] == SCOPE and report['engine_source_revision'] == ENGINE and
                    report['plugin_name'] == 'ucell-h5ad' and report['original_manifest_sha256'] == MANIFEST_SHA and
                    report['additional_plugin_identities'] == [] and report['max_concurrency'] == 1 and
                    report['incremental'] is False and report['input_hashing'] == 'ContentRequired' and
                    all(report[key] is False for key in ['native_statistical_factories_registered', 'current_daemon_verified', 'scientific_authorized', 'g0_granted']),
                    'Exact SDK identity and bounded non-scientific scope required')
                nodes = {row['id']: row for row in report['first_run']['nodes']}
                require(set(nodes) == {'input', 'analysis'} and all(row.get('reused') is False for row in nodes.values()) and
                    nodes['input']['status'] == 'success', 'Both actual fresh nodes are required')
                assigned = nodes['input']['port_assignments']['0']
                require(assigned['path'] == 'vfs:///input.h5ad' and assigned['format'] == 'h5ad' and
                    assigned['fingerprint']['content_hash'] == 'sha256:' + fact(work / 'input.h5ad')['sha256'],
                    'Actual source output must retain its complete content fingerprint')
                method = nodes['analysis']
                require(method['execution']['image'] == IMAGE and method['execution']['image_digest'] == IMAGE.split('@', 1)[1], 'Exact actual official image required')
                execution = method['execution']
                workspace = Path(execution['output_artifacts'][0]['path']).parent if positive else Path(execution['stderr_log']['path']).parents[2]
                staged = check_staged_input(work, workspace, method['inputs'])
                admission.validate_memory_report(report)
                receipts = admission.checked_task_receipts(work, nodes)
                require(len(receipts) == 2, 'Both actual owned terminal task receipts required')
                if positive:
                    require(execution['exit_code'] == 0 and method['status'] == 'success' and report['first_run']['errors'] == {}, 'Valid official method failed')
                    ports = actual_ports(work, definition, method, scratch)
                    for index, filename in enumerate(['output.h5ad', 'report.json']):
                        shutil.copyfile(ports[index], work / filename)
                    for filename in ['fresh-author.h5ad', 'author-scores.tsv']:
                        shutil.copyfile(original / filename, work / filename)
                    shutil.copyfile(original / 'report.json', work / 'sealed-report.json')
                else:
                    expected = strict_json((original / 'declared-node-script.execution.json').read_bytes())['exit']
                    require(type(execution['exit_code']) is int and execution['exit_code'] == expected and expected in [2, 3] and
                        method['status'] == 'failed' and set(report['first_run']['errors']) == {'analysis'} and not method['port_assignments'],
                        'Only the exact original method refusal is acceptable, not OOM or startup failure')
                    expected_refusal(method, IMAGE, previous.expected_error(original), scratch)
                    require(not any(os.path.lexists(workspace / filename) for filename in ['output.h5ad', 'report.json']), 'Refused method published a normal output')
                records.append(dict(case=name, positive=positive, actual_exit=execution['exit_code'], nodes=2, edges=1,
                    actual_task_receipts=2, actual_input_bindings=1, staged_input=staged, output_ports=2 if positive else 0,
                    run_name=execution['run_name']))
            finally:
                primary_failure = sys.exception()
                try:
                    capture_method_logs(scratch, work / 'diagnostics')
                except Exception as error:
                    write(work / 'diagnostic-retention-error.json', dict(type=type(error).__name__, message=str(error), g0_granted=False))
                    if primary_failure is None:
                        raise
        write(output / 'positive-cases.json', list(POSITIVES))
        command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
            '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs=/tmp:rw,size=64m',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(output) + ':/proof:rw', '--entrypoint=python', IMAGE, '/proof/compare.py']
        for name in thread_variables:
            command[command.index('--entrypoint=python'):command.index('--entrypoint=python')] = ['-e', name + '=1']
        comparison_run = captured(command, output, 'comparison', capture_output=True, timeout=300)
        require(comparison_run.returncode == 0 and b'VERIFIED_COMPLETE_H5AD_CASES 20' in comparison_run.stdout, 'Full unchanged official-author H5AD comparison failed')
        comparison = strict_json((output / 'whole-object-readback.json').read_bytes())
        for name in sorted(DIRECT):
            original = REFERENCE / 'repaired-boundaries-v1' / name
            work = output / name
            work.mkdir()
            shutil.copyfile(original / 'input.h5ad', work / 'input.h5ad')
            before_input = fact(work / 'input.h5ad')
            variables = dict(AUTONOMICS_INPUT0='/work/input.h5ad', AUTONOMICS_OUTPUT0='/work/output.h5ad',
                AUTONOMICS_OUTPUT1='/work/report.json', SC_P_JSON_GENE_SETS=previous.settings_for(name, original)['gene_sets'])
            sentinel = work / ('report.json' if name == 'report-exists' else 'output.h5ad')
            if name in ['h5ad-exists', 'report-exists']:
                sentinel.write_bytes((original / sentinel.name).read_bytes())
            elif name == 'dangling-output':
                sentinel.symlink_to('absent.h5ad')
                observed = sentinel.lstat()
                dangling_fixtures.append((sentinel, observed.st_dev, observed.st_ino))
            if name == 'output-alias':
                variables['AUTONOMICS_OUTPUT1'] = '/work/output.h5ad'
            elif name == 'input-overwrite':
                variables['AUTONOMICS_OUTPUT0'] = '/work/input.h5ad'
            old = strict_json((original / 'declared-node-script.execution.json').read_bytes())
            invocation = ['/program.py']
            if name in ['second-link-failure', 'R-failure']:
                code = old['command'][2].replace('/source/ucell-h5ad/scripts/score.py', '/program.py')
                (work / 'fault-injection.py').write_text(code)
                invocation = ['/work/fault-injection.py']
            command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
                '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs=/tmp:rw,size=64m',
                '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(work) + ':/work:rw', '-v', str(source / 'scripts/score.py') + ':/program.py:ro']
            for key, value in variables.items():
                command.extend(['-e', key + '=' + value])
            for key in thread_variables:
                command.extend(['-e', key + '=1'])
            command.extend(['--entrypoint=python', IMAGE, *invocation])
            completed = captured(command, work, 'direct', capture_output=True, timeout=240)
            require(type(old['exit']) is int and type(completed.returncode) is int and completed.returncode == old['exit'] and
                previous.expected_error(original) in completed.stderr.decode() and fact(work / 'input.h5ad') == before_input,
                'The complete original direct refusal and input preservation must remain exact')
            for filename in ['output.h5ad', 'report.json']:
                path = work / filename
                if path == sentinel and name in ['h5ad-exists', 'report-exists']:
                    require(path.read_bytes() == (original / filename).read_bytes(), 'Existing output sentinel changed')
                elif path == sentinel and name == 'dangling-output':
                    require(path.is_symlink() and os.readlink(path) == 'absent.h5ad' and not path.exists(), 'Dangling sentinel changed')
                else:
                    require(not os.path.lexists(path), 'Direct refusal left an undeclared normal output')
            require(not list(work.glob('.ucell-*')), 'Ordinary direct refusal left unexpected owned staging debris')
            direct.append(dict(case=name, exact_refusal=True, actual_exit=completed.returncode, actual_DAG_entered=False))
        validate_inventory(records, direct, preflight, comparison)
        creates = [strict_json(path.read_bytes()) for path in (output / 'actual-creates').glob('*.json')]
        require(len(creates) == 46 and {row['name'] for row in creates} == {row['run_name'] for row in records} and
            all(row['image'] == IMAGE and row['script_sha256'] == SCRIPT_SHA and row['cpus'] == '2' and
                row['memory'] == '8589934592' and row['effective_pull'] == 'never' and row['network'] == 'none' and
                row['read_only_rootfs'] is True for row in creates), 'Every actual method needs the exact bounded technical create record')
        require(image_before == inspect_image(prefix, output, 'image-after') and
            all(fact(ROOT / name) == observed for name, observed in before.items()), 'Source or installed official image changed')
        require(admission.file_identity(build_root / 'official_plugin_dag') == runner_before and
            fact(runner) == runner_copy_before, 'Original sealed executable or owned copy changed under its own identity schema')
    except BaseException as error:
        failure = error
        write(output / 'failure.json', dict(type=type(error).__name__, message=str(error), successful_qualification_claimed=False,
            completed_DAGs=records, completed_direct=direct, completed_preflight=preflight, g0_granted=False))
        raise
    finally:
        finalization_errors = []
        intents_path = permanent / 'container-intents.json'
        try:
            intents = strict_json(intents_path.read_bytes())['intents'] if intents_path.exists() else []
            stop_records = stopped(prefix, permanent, output, len(intents)) if intents else []
            for path, device, inode in dangling_fixtures:
                observed = path.lstat()
                require(stat.S_ISLNK(observed.st_mode) and (observed.st_dev, observed.st_ino) == (device, inode) and
                    os.readlink(path) == 'absent.h5ad' and not path.exists(), 'Only the exact stopped own dangling toy may be retired')
                write(path.parent / 'dangling-retirement.json', dict(target='absent.h5ad', unchanged=True,
                    device=device, inode=inode, all_owned_containers_proven_stopped=True,
                    removal_scope='THIS_EXITED_SYNTHETIC_CASE_ONLY', g0_granted=False))
                path.unlink()
        except Exception as error:
            write(output / 'stop-failure.json', dict(type=type(error).__name__, message=str(error), g0_granted=False))
            finalization_errors.append(dict(check='owned-container-stops', type=type(error).__name__, message=str(error)))
        for label, operation in [('reference-postcheck', lambda: checked_reference(REFERENCE)),
                ('resource-postcheck', runtime.cgroup_observation),
                ('helper-source-postcheck', lambda: helper_postcheck(helper_before, helper_snapshots, loaded_helpers, output / 'helper-source')),
                ('driver-source-postcheck', lambda: driver_source_postcheck(driver_before, output / 'driver.py'))]:
            try:
                write(output / (label + '.json'), operation())
            except Exception as error:
                finalization_errors.append(dict(check=label, type=type(error).__name__, message=str(error)))
        if finalization_errors:
            write(output / 'postcheck-failure.json', dict(errors=finalization_errors,
                primary_failure_preserved=failure is not None, successful_qualification_claimed=False, g0_granted=False))
            if failure is None:
                raise ValueError('Independent UCell runtime finalization failed; retained postcheck diagnostics are mandatory')
    require(len(stop_records) == 54 and len(records) == 46, 'All 54 actual method/readback containers must have stopped')
    write(output / 'verification.json', dict(status='SCOPED_PUBLICATION_ONLY_UPGRADE_OFFICIAL_UCELL_REQUALIFIED_NOT_DEPLOYED',
        source_upgrade=validate_source_upgrade((REFERENCE / 'plugin-source/plugins/ucell-h5ad/scripts/score.py').read_bytes(),
            (source / 'scripts/score.py').read_bytes()), build=build_receipt, engine=ENGINE, original_cases=54,
        helper_source_identity=helper_before, helper_snapshots=helper_snapshots, loaded_function_bindings=loaded_helpers,
        driver_source_identity=driver_before,
        actual_DAG_cases=records, direct_cases=direct, preflight_cases=preflight, actual_input_bindings=46,
        actual_task_receipts=92, published_ports=40, whole_author_comparisons=20, owned_containers_stopped=54,
        original_manifest_cpus=2, original_manifest_memory_bytes=8 * 1024**3, actual_parent_memory_bytes=2 * 1024**3,
        resource_claim='BOUNDED_SYNTHETIC_PARENT_LIMIT_NOT_MANIFEST_8GIB_OR_FULL_SCALE_CERTIFICATION',
        latest_engine_or_daemon_verified=False, production_changed=False, official_reference_regenerated=False,
        scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
