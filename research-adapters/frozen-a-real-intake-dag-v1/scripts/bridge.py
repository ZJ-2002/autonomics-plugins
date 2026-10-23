"""Explicit File closure materialization; unchanged intake is loaded only from pins."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


SCHEMA = 'A_REAL_INTAKE_FILE_CLOSURE_V1'
MAX_DEPENDENCIES = 239  # 17 fixed inputs + 239 = 256, last u8 port is 255.
MAX_TOTAL_BYTES = 128 * 1024**2
IMPLEMENTATIONS = ['frozen-a-family-assembly/scripts/family.py',
    'frozen-a-family-assembly/replay/seen_real_v1.py',
    'frozen-a-family-assembly/real-intake-v1/intake.py',
    'frozen-a-family-adjustment/real-intake-v1/adjust_real.R']


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
    def constant(value):
        raise ValueError('Nonfinite JSON value')
    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def read(path, limit=32 * 1024**2):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(p.is_symlink() for p in [path, *path.parents]) and
        stat.S_ISREG(path.lstat().st_mode), 'Canonical ordinary File required')
    signature = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    before = path.stat()
    require(before.st_size <= limit, 'File byte budget exceeded')
    with path.open('rb') as stream:
        require(signature(os.fstat(stream.fileno())) == signature(before), 'File changed before reading')
        payload = stream.read(limit + 1)
        require(signature(os.fstat(stream.fileno())) == signature(before), 'File changed during reading')
    require(signature(path.stat()) == signature(before) and len(payload) == before.st_size, 'File identity changed')
    return payload


def records(request, study, adapters, request_path, request_sha, lock):
    """Derive the exact closure from request bytes, never from an ambient directory."""
    result = []
    for index, binding in enumerate(lock['frozen_sources']):
        result.append(dict(role='frozen:' + str(index), original_path=str(Path(study) / binding['path']),
            target='study/' + binding['path'], **{k: binding[k] for k in ['sha256', 'bytes']}))
    result.append(dict(role='request', original_path=request_path, target='request.original.json', sha256=request_sha))
    for index, binding in enumerate(lock['decision_files']):
        result.append(dict(role='decision:' + str(index), original_path=str(Path(study) / binding['path']),
            target='study/' + binding['path'], **{k: binding[k] for k in ['sha256', 'bytes']}))
    for name in IMPLEMENTATIONS:
        binding = lock['implementation_files'][name]
        result.append(dict(role='implementation:' + name, original_path=str(Path(adapters) / name),
            target='adapters/' + name, **binding))
    dependencies = {}
    def add(binding):
        require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}, 'Exact request File binding required')
        path, digest = binding['path'], binding['sha256']
        require(isinstance(path, str) and Path(path).is_absolute() and str(Path(path)) == path,
            'Absolute lexical original identity required')
        require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
            'Exact SHA256 required')
        require(path not in dependencies or dependencies[path] == digest, 'Conflicting shared dependency SHA')
        dependencies[path] = digest
    require(request['schema'] == 'A_REAL_INPUT_REQUEST_V1' and
        request['scope'] == 'A_REAL_INPUT_CANDIDATE_V1_QUALIFICATION_PENDING', 'Separate V1 request required')
    for source in request['sources']:
        add({k: source[k] for k in ['path', 'sha256']})
    for history in request['seen_history']:
        if 'history_file' in history:
            add(history['history_file'])
    for edge in request['edges']:
        if edge['rds'] is not None:
            add(edge['rds'])
    require(1 <= len(dependencies) <= MAX_DEPENDENCIES,
        'SDK u8 port limit: at most 239 unique request dependencies; use a reviewed typed FileSet/bundle extension')
    for index, (path, digest) in enumerate(sorted(dependencies.items())):
        result.append(dict(role='request-dependency:' + str(index), original_path=path,
            target='dependencies/' + str(index) + '.input', sha256=digest))
    require(len({r['original_path'] for r in result}) == len(result), 'Cross-role aliases are forbidden')
    return result


def plan(request_path, study, adapters, lock):
    payload = read(request_path, 4 * 1024**2)
    entries = records(decode(payload), str(study), str(adapters), str(request_path), sha(payload), lock)
    for entry in entries:
        data = read(entry['original_path'])
        require(sha(data) == entry['sha256'] and entry.get('bytes', len(data)) == len(data),
            'Declared dependency SHA/bytes differ: ' + entry['role'])
        entry['bytes'] = len(data)
    require(sum(entry['bytes'] for entry in entries) <= MAX_TOTAL_BYTES, 'Aggregate File byte budget exceeded')
    return dict(schema=SCHEMA, study_root=str(study), adapters_root=str(adapters),
        original_request_path=str(request_path), original_request_sha256=sha(payload), entries=entries)


def materialize(inputs, workspace, lock):
    contract_bytes = read(inputs[0], 4 * 1024**2)
    contract = decode(contract_bytes)
    require(set(contract) == {'schema', 'study_root', 'adapters_root', 'original_request_path',
        'original_request_sha256', 'entries'} and contract['schema'] == SCHEMA, 'Exact File closure contract required')
    entries = contract['entries']
    require(isinstance(entries, list) and 17 <= len(entries) <= 255 and len(inputs) == len(entries) + 1,
        'Missing or extra declared File dependency')
    require(all(type(e.get('bytes')) is int and 0 <= e['bytes'] <= 32 * 1024**2 for e in entries) and
        sum(e['bytes'] for e in entries) <= MAX_TOTAL_BYTES, 'Aggregate File byte budget exceeded')
    original = read(inputs[10], 4 * 1024**2)
    require(sha(original) == contract['original_request_sha256'], 'Original request identity differs')
    request = decode(original)
    expected = records(request, contract['study_root'], contract['adapters_root'],
        contract['original_request_path'], sha(original), lock)
    require(len(expected) == len(entries), 'Request closure declaration differs')
    payloads = []
    for actual, wanted, path in zip(entries, expected, inputs[1:], strict=True):
        require(set(actual) == {'role', 'original_path', 'target', 'sha256', 'bytes'} and
            all(actual[k] == v for k, v in wanted.items()), 'File role/order/identity differs')
        data = read(path)
        require(type(actual['bytes']) is int and len(data) == actual['bytes'] and sha(data) == actual['sha256'],
            'Staged dependency SHA/bytes differ: ' + actual['role'])
        payloads.append(data)
    require(workspace.is_absolute() and workspace.parent.resolve(strict=True) == workspace.parent and
        not workspace.exists() and not workspace.is_symlink(), 'New canonical materialization required')
    workspace.mkdir(mode=0o700)
    mapping = {}
    for entry, data in zip(entries, payloads, strict=True):
        target = workspace / entry['target']
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
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
    relocated_path = workspace / 'request.materialized.json'
    relocated_path.write_bytes(encode(relocated))
    relocated_path.chmod(0o444)
    transport = dict(schema='A_REAL_INTAKE_FILE_TRANSPORT_V1', closure_sha256=sha(contract_bytes),
        original_request_sha256=sha(original), materialized_request_sha256=sha(read(relocated_path)),
        dependencies=[dict(port=i + 1, **entry, materialized_path=mapping[entry['original_path']])
            for i, entry in enumerate(entries)],
        primary_results_published=False, scientific_authorization_granted=False, g0_granted=False)
    return relocated_path, transport


def run_assembly(inputs, outputs, workspace, lock):
    require(len(outputs) == 4 and len(set(outputs)) == 4 and
        not any(p.exists() or p.is_symlink() for p in outputs), 'Four new output Files required')
    request, transport = materialize(inputs, workspace, lock)
    module_path = workspace / 'adapters' / IMPLEMENTATIONS[2]
    spec = importlib.util.spec_from_file_location('explicit_file_real_intake', module_path)
    intake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(intake)
    frozen = [workspace / 'study' / row['path'] for row in lock['frozen_sources']]
    products = intake.assemble(frozen, request)
    transport['assembly_output_sha256'] = {name: sha(payload) for name, payload in products.items()}
    for path, name in zip(outputs[:3], ['real-family.tsv', 'real-vectors.tsv', 'real-assembly.json'], strict=True):
        with path.open('xb') as stream:
            stream.write(products[name])
    with outputs[3].open('xb') as stream:
        stream.write(encode(transport))
    return transport


def main():
    # The generator embeds source-lock.json in command.files. It is not read from
    # an ambient host path. Manifest SHA binds this file along with the script.
    lock = decode(read(Path(os.environ['AUTONOMICS_FILES_DIR']) / 'source-lock.json'))
    count = int(os.environ['AUTONOMICS_INPUT_COUNT'])
    inputs = [Path(os.environ['AUTONOMICS_INPUT' + str(i)]) for i in range(count)]
    outputs = [Path(os.environ['AUTONOMICS_OUTPUT' + str(i)]) for i in range(4)]
    require(os.environ['AUTONOMICS_OUTPUT_COUNT'] == '4', 'Exact output count required')
    run_assembly(inputs, outputs, outputs[0].parent / '.real-intake-materialized', lock)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
