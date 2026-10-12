"""Check exact imported methods and full wrapper assembly without writing files.

This verifies source transport. It neither executes a scientific method nor
qualifies actual DAG producers, input resources, study gates or signatures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib
import types

from tools.catalog import ROOT, check_lock, safe_relative

FAMILIES = (
    'mr-contract', 'clump-contract', 'mr-sensitivity-contract', 'mvmr-contract',
    'mvmr-joint-contract', 'mvmr-joint-clump-contract',
    'mvmr-covariance-contract', 'mvmr-orientation-contract',
    'mrlap-contract',
)


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate source-lock field')
        result[key] = value
    return result


def regular(directory, name):
    relative = safe_relative(name)
    target = directory.joinpath(*relative.parts)
    for parent in [target, *target.parents]:
        if parent == directory:
            break
        if parent.is_symlink():
            raise ValueError('Regular unaliased source required: ' + name)
    if not target.is_file() or not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Regular contained source required: ' + name)
    return target


def identity(directory, name, record):
    if set(record) != {'source_path', 'sha256', 'bytes', 'git_blob', 'executable'}:
        raise ValueError('Complete source identity required')
    safe_relative(record['source_path'])
    if (not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256']) or
            not isinstance(record['git_blob'], str) or not re.fullmatch('[0-9a-f]{40}', record['git_blob']) or
            type(record['bytes']) is not int or record['bytes'] < 0 or
            type(record['executable']) is not bool):
        raise ValueError('Invalid source identity')
    path = regular(directory, name)
    raw = path.read_bytes()
    git_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if (len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256'] or
            git_blob != record['git_blob'] or
            bool(path.stat().st_mode & 0o111) != record['executable']):
        raise ValueError('Imported source identity differs: ' + name)
    return raw


def check_family(family):
    family = Path(family)
    lock = json.loads(regular(family, 'component-source.json').read_text(), object_pairs_hook=reject_duplicates)
    if (set(lock) != {'schema_version', 'source_repository', 'source_commit', 'source_family',
                     'transport_scope', 'scientific_authorization', 'auto_enable',
                     'imported_files', 'component_files', 'programs'} or
            lock['schema_version'] != 1 or lock['scientific_authorization'] is not False or
            lock['auto_enable'] is not False or
            lock['source_repository'] != 'https://github.com/ZJ-2002/autonomics' or
            not isinstance(lock['source_commit'], str) or
            not re.fullmatch('[0-9a-f]{40}', lock['source_commit']) or
            lock['source_family'] != 'study_plugins/' + family.name or
            family.name not in FAMILIES or
            lock['transport_scope'] != 'BYTE_EXACT_COMPLETE_METHOD_TRANSPORT_NOT_PRODUCER_OR_SCIENTIFIC_QUALIFICATION'):
        raise ValueError('Explicit unapproved imported source lock required')
    for key in ['imported_files', 'component_files', 'programs']:
        if not isinstance(lock[key], dict) or not lock[key]:
            raise ValueError('Complete method source and programs required')
    original = {}
    for name, record in lock['imported_files'].items():
        if record['source_path'] != lock['source_family'] + '/' + name:
            raise ValueError('Original source path differs')
        original[name] = identity(family, name, record)
    component_root = family/'components'
    if component_root.is_symlink() or not component_root.is_dir():
        raise ValueError('Regular component root required')
    actual = set()
    for path in component_root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Regular unaliased component required')
        if path.is_file():
            actual.add(path.relative_to(component_root).as_posix())
    if actual != set(lock['component_files']):
        raise ValueError('Complete component universe differs')
    for name, record in lock['component_files'].items():
        if record['source_path'] != name:
            raise ValueError('Component source path differs')
        identity(component_root, name, record)
    manifest = tomllib.loads(original['manifest.toml'].decode())
    programs = {node['command']['script_file'] for node in manifest['nodes']}
    if programs != set(lock['programs']):
        raise ValueError('Complete manifest program universe differs')
    # Only after ALL component/imported bytes pass may a qualified renderer run.
    # Executing via compile/exec avoids import-generated __pycache__ mutations.
    hashes = {}
    for program, descriptor in lock['programs'].items():
        rooted_mrlap = (family.name == 'mrlap-contract' and descriptor == {
            'generator': 'scripts/generate_mrlap_contract_wrapper.py',
            'function': 'wrapper', 'argument': 'study_plugins/mrlap-contract'})
        if (set(descriptor) != {'generator', 'function', 'argument'} or
                descriptor['generator'] not in lock['component_files'] or
                (not rooted_mrlap and (descriptor['function'] not in {'render', 'rendered'} or
                descriptor['argument'] not in {None, 'union', 'clump', 'harmonise'}))):
            raise ValueError('Explicit complete renderer required')
        path = regular(component_root, descriptor['generator'])
        module = types.ModuleType('qualified_frozen_method_renderer')
        module.__file__ = str(path)
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        function = getattr(module, descriptor['function'])
        if rooted_mrlap:
            expected = function(component_root/'study_plugins/mrlap-contract')
        else:
            expected = function() if descriptor['argument'] is None else function(descriptor['argument'])
        if not isinstance(expected, str) or original[program] != expected.encode():
            raise ValueError('Runnable method differs from complete original components')
        hashes[program] = hashlib.sha256(original[program]).hexdigest()
    return {'family': family.name, 'source_commit': lock['source_commit'],
            'program_sha256': hashes, 'kinds': [node['kind'] for node in manifest['nodes']],
            'image': manifest['image']['reference'], 'scientific_authorization': False,
            'auto_enable': False, 'scope': lock['transport_scope']}


def check_all(root=ROOT):
    check_lock(Path(root))
    return [check_family(Path(root)/'research-adapters'/name) for name in FAMILIES]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps({'families': check_all(args.root), 'scientific_authorization': False}, indent=2))
