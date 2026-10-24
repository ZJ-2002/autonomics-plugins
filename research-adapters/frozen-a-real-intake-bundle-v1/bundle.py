"""Stable archive transport for unchanged, hash-locked A real-intake code."""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile


SCHEMA = 'A_REAL_INTAKE_BUNDLE_V1'
REQUEST_SCHEMA = 'A_REAL_INPUT_REQUEST_V1'
REQUEST_SCOPE = 'A_REAL_INPUT_CANDIDATE_V1_QUALIFICATION_PENDING'
MAX_DEPENDENCIES = 3 * 276
MAX_ENTRIES = 16 + MAX_DEPENDENCIES
MAX_FILE_BYTES = 32 * 1024**2
MAX_REQUEST_BYTES = 4 * 1024**2
MAX_TOTAL_BYTES = 128 * 1024**2
MAX_BUNDLE_BYTES = MAX_TOTAL_BYTES + MAX_REQUEST_BYTES + 1024**2
IMPLEMENTATIONS = (
    'frozen-a-family-assembly/scripts/family.py',
    'frozen-a-family-assembly/replay/seen_real_v1.py',
    'frozen-a-family-assembly/real-intake-v1/intake.py',
    'frozen-a-family-adjustment/real-intake-v1/adjust_real.R',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def decode(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON number')
    return json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid)


def read(path, limit=MAX_FILE_BYTES):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in (path, *path.parents)), 'Canonical ordinary File required')
    before = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'File type or byte budget differs')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'File changed before read')
        payload = stream.read(limit + 1)
        require(identity(os.fstat(stream.fileno())) == identity(before), 'File changed during read')
    require(identity(path.stat()) == identity(before) and len(payload) == before.st_size, 'File identity changed')
    return payload


def digest(value):
    return isinstance(value, str) and len(value) == 64 and all(character in '0123456789abcdef' for character in value)


def records(request, study, adapters, request_path, request_sha, lock):
    require(isinstance(request, dict) and set(request) == {'schema', 'scope', 'sources', 'seen_history', 'edges'} and
        request['schema'] == REQUEST_SCHEMA and request['scope'] == REQUEST_SCOPE, 'Exact unchanged V1 request required')
    require(len(lock['frozen_sources']) == 9 and len(lock['decision_files']) == 2 and
        set(lock['implementation_files']) == set(IMPLEMENTATIONS), 'Exact frozen code/source roles required')
    result = []
    for index, binding in enumerate(lock['frozen_sources']):
        result.append(dict(role='frozen:' + str(index), original_path=str(Path(study) / binding['path']),
            target='study/' + binding['path'], **{key: binding[key] for key in ['sha256', 'bytes']}))
    result.append(dict(role='request', original_path=request_path, target='request.original.json', sha256=request_sha))
    for index, binding in enumerate(lock['decision_files']):
        result.append(dict(role='decision:' + str(index), original_path=str(Path(study) / binding['path']),
            target='study/' + binding['path'], **{key: binding[key] for key in ['sha256', 'bytes']}))
    for name in IMPLEMENTATIONS:
        result.append(dict(role='implementation:' + name, original_path=str(Path(adapters) / name),
            target='adapters/' + name, **lock['implementation_files'][name]))
    dependencies = {}
    def add(binding):
        require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}, 'Exact request File binding required')
        name = binding['path']
        require(isinstance(name, str) and Path(name).is_absolute() and str(Path(name)) == name and
            '\x00' not in name and digest(binding['sha256']), 'Absolute File identity and SHA256 required')
        require(name not in dependencies or dependencies[name] == binding['sha256'], 'Conflicting shared File SHA256')
        dependencies[name] = binding['sha256']
    require(isinstance(request['sources'], list) and 1 <= len(request['sources']) <= 276 and
        isinstance(request['edges'], list) and 1 <= len(request['edges']) <= 276 and
        isinstance(request['seen_history'], list) and len(request['seen_history']) <= 276, 'Frozen request cardinality exceeded')
    for source in request['sources']:
        require(isinstance(source, dict) and set(source) == {'source_id', 'path', 'sha256'}, 'Exact source File required')
        add({key: source[key] for key in ['path', 'sha256']})
    for history in request['seen_history']:
        if 'history_file' in history:
            add(history['history_file'])
    for edge in request['edges']:
        if edge['rds'] is not None:
            add(edge['rds'])
    require(1 <= len(dependencies) <= MAX_DEPENDENCIES, 'Maximum unique V1 dependencies exceeded')
    for index, (name, checksum) in enumerate(sorted(dependencies.items())):
        result.append(dict(role='request-dependency:' + str(index), original_path=name,
            target='dependencies/' + str(index) + '.input', sha256=checksum))
    require(len({entry['original_path'] for entry in result}) == len(result), 'Cross-role File aliases forbidden')
    targets = [entry['target'] for entry in result]
    require(len(set(targets)) == len(targets) and all(not PurePosixPath(name).is_absolute() and
        '..' not in PurePosixPath(name).parts and str(PurePosixPath(name)) == name for name in targets), 'Unsafe or duplicate materialization target')
    return result


def pack(request_path, study, adapters, output, lock):
    request_bytes = read(request_path, MAX_REQUEST_BYTES)
    entries = records(decode(request_bytes), study, adapters, str(request_path), sha(request_bytes), lock)
    payloads = []
    total = 0
    for entry in entries:
        payload = read(entry['original_path'])
        require(sha(payload) == entry['sha256'] and entry.get('bytes', len(payload)) == len(payload), 'Source SHA256 or bytes differ')
        entry['bytes'] = len(payload)
        total += len(payload)
        require(total <= MAX_TOTAL_BYTES, 'Aggregate source byte budget exceeded')
        payloads.append(payload)
    closure = dict(schema=SCHEMA, study_root=str(study), adapters_root=str(adapters),
        original_request_path=str(request_path), original_request_sha256=sha(request_bytes), entries=entries)
    closure_bytes = encode(closure)
    require(len(closure_bytes) <= MAX_REQUEST_BYTES, 'Closure metadata byte budget exceeded')
    output = Path(output)
    require(output.is_absolute() and output.parent.resolve(strict=True) == output.parent and
        not output.exists() and not output.is_symlink(), 'New canonical bundle output required')
    with output.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, payload in [('closure.json', closure_bytes), *[(f'files/{index:04d}.bin', payload) for index, payload in enumerate(payloads)]]:
                information = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                information.create_system = 3
                information.external_attr = (stat.S_IFREG | 0o444) << 16
                archive.writestr(information, payload)
    require(output.stat().st_size <= MAX_BUNDLE_BYTES, 'Bundle byte budget exceeded')
    return closure


def unpack(bundle, workspace, lock):
    payload = read(bundle, MAX_BUNDLE_BYTES)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        information = archive.infolist()
        require(not archive.comment and 18 <= len(information) <= MAX_ENTRIES + 1, 'Unexpected bundle member count or comment')
        require(all(not item.is_dir() and not item.flag_bits & 1 and item.compress_type == zipfile.ZIP_STORED and
            not item.extra and not item.comment and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
            for item in information), 'Only ordinary uncompressed bundle members supported')
        require(information[0].filename == 'closure.json' and information[0].file_size <= MAX_REQUEST_BYTES,
            'Bounded closure must be the first bundle member')
        closure_bytes = archive.read('closure.json')
        closure = decode(closure_bytes)
        require(isinstance(closure, dict) and set(closure) == {'schema', 'study_root', 'adapters_root',
            'original_request_path', 'original_request_sha256', 'entries'} and closure['schema'] == SCHEMA,
            'Exact archive closure required')
        entries = closure['entries']
        require(isinstance(entries, list) and 17 <= len(entries) <= MAX_ENTRIES, 'Closure cardinality exceeded')
        names = ['closure.json', *[f'files/{index:04d}.bin' for index in range(len(entries))]]
        require([item.filename for item in information] == names, 'Extra, missing, duplicate or reordered members')
        require(all(type(entry.get('bytes')) is int and 0 <= entry['bytes'] <= MAX_FILE_BYTES for entry in entries) and
            sum(entry['bytes'] for entry in entries) <= MAX_TOTAL_BYTES, 'Source byte budget exceeded')
        require(all(item.file_size == entry['bytes'] for item, entry in zip(information[1:], entries, strict=True)), 'Archive member size differs')
        original = archive.read('files/0009.bin')
        require(len(original) <= MAX_REQUEST_BYTES and sha(original) == closure['original_request_sha256'], 'Original request identity differs')
        request = decode(original)
        expected = records(request, closure['study_root'], closure['adapters_root'],
            closure['original_request_path'], sha(original), lock)
        require(len(expected) == len(entries), 'Request and closure members differ')
        payloads = []
        for entry, wanted, name in zip(entries, expected, names[1:], strict=True):
            require(set(entry) == {'role', 'original_path', 'target', 'sha256', 'bytes'} and
                all(entry[key] == value for key, value in wanted.items()), 'Closure role, order or identity differs')
            content = archive.read(name)
            require(sha(content) == entry['sha256'], 'Member SHA256 differs')
            payloads.append(content)
    workspace = Path(workspace)
    require(workspace.is_absolute() and workspace.parent.resolve(strict=True) == workspace.parent and
        not workspace.exists() and not workspace.is_symlink(), 'New canonical workspace required')
    workspace.mkdir(mode=0o700)
    mapping = {}
    for entry, content in zip(entries, payloads, strict=True):
        target = workspace / entry['target']
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o444)
        mapping[entry['original_path']] = str(target)
    relocated = copy.deepcopy(request)
    for source in relocated['sources']:
        source['path'] = mapping[source['path']]
    for history in relocated['seen_history']:
        if 'history_file' in history:
            history['history_file']['path'] = mapping[history['history_file']['path']]
    for edge in relocated['edges']:
        if edge['rds'] is not None:
            edge['rds']['path'] = mapping[edge['rds']['path']]
    request_path = workspace / 'request.materialized.json'
    request_path.write_bytes(encode(relocated))
    request_path.chmod(0o444)
    receipt = dict(schema='A_REAL_INTAKE_BUNDLE_TRANSPORT_V1', bundle_sha256=sha(payload),
        closure_sha256=sha(closure_bytes), original_request_sha256=sha(original),
        materialized_request_sha256=sha(read(request_path)), dependencies=entries,
        relocated_original_paths=mapping, archive_timestamps_are_not_viewing_history=True,
        scientific_authorization_granted=False, g0_granted=False)
    return request_path, receipt


def assemble(bundle, outputs, workspace, lock):
    require(len(outputs) == len(set(outputs)) == 6 and not any(path.exists() or path.is_symlink() for path in outputs),
        'Six distinct new output Files required')
    request, transport = unpack(bundle, workspace, lock)
    source = workspace / 'adapters' / IMPLEMENTATIONS[2]
    specification = importlib.util.spec_from_file_location('bundle_unchanged_real_intake', source)
    intake = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(intake)
    products = intake.assemble([workspace / 'study' / entry['path'] for entry in lock['frozen_sources']], request)
    transport['assembly_output_sha256'] = {name: sha(value) for name, value in products.items()}
    content = [products[name] for name in ['real-family.tsv', 'real-vectors.tsv', 'real-assembly.json']]
    content.append(encode(transport))
    content.append(read(workspace / 'study' / lock['frozen_sources'][8]['path']))
    content.append(read(workspace / 'adapters' / IMPLEMENTATIONS[3]))
    for path, value in zip(outputs, content, strict=True):
        with path.open('xb') as stream:
            stream.write(value)
    return transport


def fixed_lock():
    folder = Path(os.environ['AUTONOMICS_FILES_DIR']) if 'AUTONOMICS_FILES_DIR' in os.environ else Path(__file__).resolve().parent
    return decode(read(folder / 'source-lock.json', 64 * 1024))


def main():
    if 'AUTONOMICS_INPUT_COUNT' in os.environ:
        require(os.environ['AUTONOMICS_INPUT_COUNT'] == '1' and os.environ.get('AUTONOMICS_OUTPUT_COUNT') == '6',
            'Exactly one bundle input and six outputs required')
        outputs = [Path(os.environ['AUTONOMICS_OUTPUT' + str(index)]) for index in range(6)]
        assemble(Path(os.environ['AUTONOMICS_INPUT0']), outputs, outputs[0].parent / '.bundle-materialized', fixed_lock())
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--study-root', type=Path, required=True)
    parser.add_argument('--adapters-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    pack(arguments.request, arguments.study_root, arguments.adapters_root, arguments.output, fixed_lock())


if __name__ == '__main__':
    main()
