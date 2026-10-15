"""Owned SDK launcher and explicit output-conflict fault for the frozen A proof."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


PYTHON_IMAGE = 'docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d'
R_IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
SCRIPTS = {
    'raw': ('81421c4467c4d204e576949b9a364dd487ffb647e9e429bb922ed7938b1f5a69', 9, 12, PYTHON_IMAGE, 'python3', '1', '2147483648'),
    'harmonise': ('03a7325619dd1ff927db37875c7d0c040c0d2bf9e97ef1b8af72c2f5533a91f1', 6, 5, R_IMAGE, 'Rscript', '1', '1073741824'),
    'mr': ('33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe', 5, 9, R_IMAGE, 'Rscript', '2', '2147483648'),
    'gate': ('6c921c4ed2cfece1bc56031a0a40b83c1c1efbdd643d6e32f370ee851da42537', 23, 4, PYTHON_IMAGE, 'python3', '1', '1073741824'),
    'assemble': ('338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a', 10, 4, PYTHON_IMAGE, 'python3', '1', '1073741824'),
    'adjust': ('debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412', 4, 4, R_IMAGE, 'Rscript', '1', '1073741824'),
    'publish': ('338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a', 8, 4, PYTHON_IMAGE, 'python3', '1', '1073741824'),
}
FOREIGN = b'CONTROLLED_FOREIGN_OUTPUT_NOT_RESULT\n'
MR_OUTPUTS = ['ALL_METHODS_EXPLORATORY.tsv', 'HETEROGENEITY.tsv', 'EGGER_INTERCEPT.tsv',
    'ALL_LEAVE_ONE_OUT.tsv', 'ALL_REGION_SENSITIVITIES.tsv', 'QUALIFIED_INPUT.tsv',
    'twosamplemr_v432_a.RDS', 'twosamplemr_v432_a.log', 'INPUT_METHOD_PROVENANCE.json']
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')
RAW_INPUT_PATHS = [STUDY / name for name in (
    '04_DATA/G0_MINIMUM_A/GCST90652391.h.tsv.gz',
    '04_DATA/G0_MINIMUM_A/GCST90002393.h.tsv.gz',
    '03_AUDIT/G0_v4.3.2_2026-10-11/A_ANALYSIS_CONFIG.json',
    '03_AUDIT/G0_v4.3.2_2026-10-11/G0_V432_CERTIFICATE.json',
    '02_EXECUTION/prepare_minimum_g0.py', '02_EXECUTION/verify_minimum_ld.py',
    '04_SOFTWARE/bin/plink', '04_DATA/LD_REF_1000G_EUR_489/manifest.json',
    '02_EXECUTION/SOFTWARE_LOCK.tsv')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular_fact(path):
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in (path, *path.parents)), 'Unaliased ordinary owned file required')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'Ordinary owned file required')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    with path.open('rb') as handle:
        require(signature(os.fstat(handle.fileno())) == signature(before), 'Owned file changed before reading')
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
        require(signature(os.fstat(handle.fileno())) == signature(before), 'Owned file changed during reading')
    require(signature(path.lstat()) == signature(before), 'Owned file changed while inspecting')
    return dict(bytes=before.st_size, sha256=checksum, device=before.st_dev, inode=before.st_ino,
        mode=before.st_mode, mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)


def directory(path):
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in (path, *path.parents)), 'Unaliased existing owned directory required')
    value = path.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid(), 'Operator-owned directory required')
    return path


def option(arguments, name):
    require(arguments.count(name) == 1, 'Exactly one SDK option required: ' + name)
    position = arguments.index(name)
    require(position + 1 < len(arguments), 'Missing SDK option value: ' + name)
    return arguments[position + 1]


def sdk_environment(arguments):
    selected = {}
    for position, argument in enumerate(arguments):
        if argument == '--env':
            require(position + 1 < len(arguments), 'Missing SDK environment assignment')
            key, separator, value = arguments[position + 1].partition('=')
            if re.fullmatch(r'AUTONOMICS_(?:INPUT\d+|OUTPUT\d+|INPUT_COUNT|OUTPUT_COUNT|SCRIPT|WORKDIR)', key) or key == 'FROZEN_A_FAMILY_MODE':
                require(separator and key not in selected, 'Malformed or duplicate selected SDK environment assignment')
                selected[key] = value
    return selected


def workspace_mount(arguments, allowed):
    matches = []
    for position, argument in enumerate(arguments):
        if argument != '--mount':
            continue
        require(position + 1 < len(arguments), 'Missing SDK mount')
        value = arguments[position + 1]
        require('\\' not in value, 'Escaped paths are outside this exact technical proof')
        parts = value.split(',')
        fields = {}
        for part in parts:
            name, separator, field = part.partition('=')
            require(name not in fields, 'Duplicate SDK mount field')
            fields[name] = field if separator else True
        if fields.get('destination') == '/work':
            require(fields.get('type') == 'bind' and fields.get('rw') == 'true' and set(fields) == {'type', 'source', 'destination', 'rw'},
                'Exact writable owned /work mount required')
            candidate = directory(Path(fields['source']))
            require(candidate != allowed and candidate.is_relative_to(directory(allowed)), 'Workspace is outside its recorded technical scratch')
            matches.append(candidate)
    require(len(matches) == 1, 'Exactly one owned SDK workspace mount required')
    return matches[0]


def container_file(workspace, value):
    require(isinstance(value, str) and value.startswith('/work/'), 'Only an owned /work file may be inspected or injected')
    relative = value.removeprefix('/work/')
    parsed = PurePosixPath(relative)
    require(relative and not parsed.is_absolute() and str(parsed) == relative and
        all(part not in ('', '.', '..') for part in relative.split('/')), 'Literal unaliased SDK workspace-relative file required')
    candidate = workspace / relative
    directory(candidate.parent)
    return candidate


def staged_input_facts(arguments, workspace, inputs, role):
    records, paths = [], []
    for index in range(len(inputs)):
        path = container_file(workspace, inputs['AUTONOMICS_INPUT' + str(index)])
        require(path.parent == workspace / '.autonomics/inputs' and
            (path.name == 'input-' + str(index) or path.name.startswith('input-' + str(index) + '.')),
            'Exact owned per-port SDK staging path required')
        if role == 'raw':
            require(path.is_symlink(), 'The frozen raw-input scope requires direct canonical symlink staging')
            target = RAW_INPUT_PATHS[index]
            require(os.readlink(path) == str(target) and path.resolve(strict=True) == target,
                'Raw input link must name its exact frozen canonical source role')
            mount = 'type=bind,source=' + str(target.parent) + ',destination=' + str(target.parent) + ',readonly'
            require(any(argument == '--mount' and position + 1 < len(arguments) and arguments[position + 1] == mount
                for position, argument in enumerate(arguments)), 'Raw input source parent must be mounted read-only')
            identity = regular_fact(target)
            require(path.is_symlink() and os.readlink(path) == str(target), 'Raw input link changed during inspection')
            record = dict(port=index, staged_path=str(path), mode='EXACT_CANONICAL_READONLY_SYMLINK',
                canonical_source=str(target), identity=identity)
        else:
            identity = regular_fact(path)
            record = dict(port=index, staged_path=str(path), mode='OWNED_REGULAR_BYTE_COPY', identity=identity)
        paths.append(path)
        records.append(record)
    require(len({(record['identity']['device'], record['identity']['inode']) for record in records}) == len(records),
        'Each distinct input role requires its own source or copied inode')
    return paths, records


def prepare_create(arguments, allowed, fault):
    require(type(fault) is bool and arguments and arguments[0] == 'create', 'Explicit create and boolean technical fault mode required')
    original = list(arguments)
    selected = sdk_environment(arguments)
    workspace = workspace_mount(arguments, allowed)
    require(selected.get('AUTONOMICS_WORKDIR') == '/work' and
        selected.get('AUTONOMICS_SCRIPT') == '/work/.autonomics/script' and
        option(arguments, '--workdir') == '/work', 'Exact SDK script/workdir declaration required')
    script = container_file(workspace, selected['AUTONOMICS_SCRIPT'])
    script_fact = regular_fact(script)
    inputs = {key: value for key, value in selected.items() if re.fullmatch('AUTONOMICS_INPUT[0-9]+', key)}
    outputs = {key: value for key, value in selected.items() if re.fullmatch('AUTONOMICS_OUTPUT[0-9]+', key)}
    require(set(inputs) == {'AUTONOMICS_INPUT' + str(index) for index in range(len(inputs))} and
        set(outputs) == {'AUTONOMICS_OUTPUT' + str(index) for index in range(len(outputs))} and
        selected.get('AUTONOMICS_INPUT_COUNT') == str(len(inputs)) and
        selected.get('AUTONOMICS_OUTPUT_COUNT') == str(len(outputs)), 'Complete consecutive SDK input/output port declarations required')
    roles = [role for role, values in SCRIPTS.items() if
        (script_fact['sha256'], len(inputs), len(outputs)) == values[:3]]
    require(len(roles) == 1, 'Exact approved script bytes and method ABI required')
    role = roles[0]
    expected = SCRIPTS[role]
    entrypoint = arguments.index('--entrypoint')
    require(arguments.count('--entrypoint') == 1 and len(arguments) == entrypoint + 4 and
        arguments[entrypoint + 1:] == [expected[4], expected[3], selected['AUTONOMICS_SCRIPT']],
        'Exact fixed image and original script-only interpreter command required')
    require(option(arguments, '--name') and re.fullmatch('[A-Za-z0-9_.-]{1,200}', option(arguments, '--name')) and
        option(arguments, '--network') == 'none' and
        option(arguments, '--cpus') == expected[5] and option(arguments, '--memory') == expected[6],
        'Exact declared image resources, name and network required')
    if role in {'assemble', 'publish'}:
        require(selected.get('FROZEN_A_FAMILY_MODE') == role, 'Exact family mode required')
    changed = list(arguments)
    original_pull = option(arguments, '--pull')
    original_ro = '--read-only' in arguments
    require(arguments.count('--read-only') == 1 and original_pull == ('missing' if role == 'mr' else 'never') and
        original_ro is True, 'Unchanged exact manifest pull/rootfs declaration required')
    if role == 'mr':
        require([PurePosixPath(outputs['AUTONOMICS_OUTPUT' + str(index)]).name for index in range(9)] == MR_OUTPUTS,
            'Exact nine MR output names required')
        changed[changed.index('--cpus') + 1] = '1'
        changed[changed.index('--pull') + 1] = 'never'
    input_paths, input_records = staged_input_facts(arguments, workspace, inputs, role)
    paths = [container_file(workspace, outputs['AUTONOMICS_OUTPUT' + str(index)]) for index in range(len(outputs))]
    require(len(set(paths)) == len(paths) and all(path.parent == workspace and path not in input_paths and path != script for path in paths),
        'Distinct fresh flat SDK outputs must not alias staged inputs or scripts')
    require(all(not os.path.lexists(path) for path in paths), 'The controlled proof must not replace any preexisting output')
    foreign = None
    if fault and role == 'mr':
        target = paths[0]
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(FOREIGN)
            handle.flush()
            os.fsync(handle.fileno())
        foreign = dict(path=str(target), identity=regular_fact(target))
    require(original == arguments and regular_fact(script) == script_fact, 'Proxy cannot modify the caller argv or script')
    record = dict(schema='FROZEN_A_CONNECTED_OCI_CREATE_V1', role=role,
        run_name=option(arguments, '--name'), workspace=str(workspace), image=expected[3],
        script_sha256=script_fact['sha256'], input_count=len(inputs), input_identities=input_records,
        output_paths=[str(path) for path in paths],
        original_resources=dict(cpus=expected[5], memory=expected[6], pull=original_pull, read_only_rootfs=original_ro),
        actual_resources=dict(cpus='1', memory=expected[6], pull='never', read_only_rootfs=True),
        resource_override_is_technical_not_manifest_certification=True,
        fault_requested=fault, fault_injected=foreign is not None, foreign_before=foreign,
        scientific_inputs_or_method_parameters_changed=False, g0_granted=False)
    return changed, record


def save_record(directory_path, record):
    require(isinstance(record.get('run_name'), str) and re.fullmatch('[A-Za-z0-9_.-]{1,200}', record['run_name']),
        'Literal safe OCI run name required for observation publication')
    path = directory(directory_path) / (record['run_name'] + '.json')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(record, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def proxy_main(prefix, allowed, records, fault):
    arguments = sys.argv[1:]
    require(arguments and arguments[0] in {'create', 'start', 'rm', 'inspect', 'ps', 'kill', 'stop', 'container'},
        'Only the required local managed container operations are supported')
    if arguments[0] == 'create':
        arguments, record = prepare_create(arguments, Path(allowed), fault)
        save_record(Path(records), record)
    os.execv(prefix[0], [*prefix, *arguments])


def install_launcher(prefix, temporary, output, *, workspace_root, fault=False):
    require(type(fault) is bool and prefix and prefix[0] == os.environ.get('AUTONOMICS_PODMAN_PROGRAM'),
        'The original managed shim and an explicit boolean fault selection are required')
    original = Path(prefix[0])
    original_fact = regular_fact(original)
    canonical = Path.home() / '.autonomics/containers-overlay'
    require(prefix[1:] == ['--root', str(canonical / 'storage'), '--runroot', str(canonical / 'run'),
        '--tmpdir', str(canonical / 'run/libpod-tmp'), '--storage-driver', 'overlay'],
        'Only the explicitly qualified owner-canonical local backend is supported')
    allowed = directory(workspace_root)
    directory(temporary)
    directory(output)
    source = output / 'connected-runtime-source.py'
    payload = Path(__file__).read_bytes()
    with source.open('xb') as handle:
        handle.write(payload)
    source_sha = hashlib.sha256(payload).hexdigest()
    records = output / 'actual-container-create'
    records.mkdir(mode=0o700)
    location = temporary / 'connected-backend-bin'
    location.mkdir(mode=0o700)
    launcher = location / 'podman'
    text = '''#!/usr/bin/python3
import hashlib
from pathlib import Path
payload = Path(__SOURCE__).read_bytes()
if hashlib.sha256(payload).hexdigest() != __SHA__:
    raise SystemExit('Frozen connected runtime launcher source changed')
scope = {'__name__':'frozen_connected_runtime', '__file__':__SOURCE__}
exec(compile(payload,__SOURCE__,'exec'),scope)
scope['proxy_main'](__PREFIX__,__ALLOWED__,__RECORDS__,__FAULT__)
'''.replace('__SOURCE__', repr(str(source))).replace('__SHA__', repr(source_sha)).replace(
        '__PREFIX__', repr(list(prefix))).replace('__ALLOWED__', repr(str(allowed))).replace(
        '__RECORDS__', repr(str(records))).replace('__FAULT__', repr(fault))
    with launcher.open('x') as handle:
        handle.write(text)
    launcher.chmod(0o700)
    return dict(original=original, original_fact=original_fact, launcher=launcher, launcher_fact=regular_fact(launcher),
        source=source, source_fact=regular_fact(source), records=records, workspace_root=allowed, fault=fault,
        path_prefix=str(location))


def child_environment(configuration):
    return dict(os.environ, PATH=configuration['path_prefix'] + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin'))


def observations(configuration, *, expected_roles):
    paths = sorted(configuration['records'].iterdir())
    require(all(path.suffix == '.json' for path in paths), 'Unexpected entry in OCI observation inventory')
    records = []
    for path in paths:
        regular_fact(path)
        records.append(json.loads(path.read_text()))
    require(len(records) == len(expected_roles) and sorted(record['role'] for record in records) == sorted(expected_roles) and
        len({record['run_name'] for record in records}) == len(records), 'Every exact expected actual OCI create must be recorded once')
    for record in records:
        require(record['schema'] == 'FROZEN_A_CONNECTED_OCI_CREATE_V1' and record['g0_granted'] is False and
            record['fault_requested'] is configuration['fault'] and
            record['fault_injected'] is (configuration['fault'] and record['role'] == 'mr'), 'Exact controlled-fault provenance required')
        if record['fault_injected']:
            foreign = record['foreign_before']
            path = Path(foreign['path'])
            require(path == Path(record['output_paths'][0]) and path.is_relative_to(configuration['workspace_root']) and
                regular_fact(path) == foreign['identity'] and path.read_bytes() == FOREIGN,
                'The actual MR refusal must preserve the complete original foreign-file identity and bytes')
            record['foreign_after'] = regular_fact(path)
    require(regular_fact(configuration['original']) == configuration['original_fact'] and
        regular_fact(configuration['launcher']) == configuration['launcher_fact'] and
        regular_fact(configuration['source']) == configuration['source_fact'], 'Managed program or reviewed proxy source changed')
    return records
