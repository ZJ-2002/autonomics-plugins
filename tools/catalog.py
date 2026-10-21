import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Expected a nonempty relative POSIX path')
    if any(ord(character) < 32 for character in value):
        raise ValueError('Control character in path')
    if any(part in ['', '.', '..'] for part in value.split('/')):
        raise ValueError('Absolute, empty or traversal path component')
    return PurePosixPath(value)


def contained_file(directory, relative):
    candidate = directory.joinpath(*safe_relative(relative).parts)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(directory.resolve()) or not resolved.is_file():
        raise ValueError('File escapes family or is not a regular file: ' + relative)
    if candidate.is_symlink():
        raise ValueError('Release source symlinks require an explicitly reviewed policy')
    return candidate


def file_records(directory):
    records = []
    for filename in sorted(directory.rglob('*')):
        if filename.is_symlink():
            raise ValueError('Unreviewed source symlink: ' + str(filename))
        if not filename.is_file():
            continue
        if any(part in ['__pycache__', '.git'] for part in filename.relative_to(directory).parts):
            continue
        if filename.name == '.env' or filename.name.startswith('.env.'):
            raise ValueError('Credential file in release tree')
        content = filename.read_bytes()
        records.append(dict(path=filename.relative_to(directory).as_posix(),
                            sha256=hashlib.sha256(content).hexdigest(), bytes=len(content),
                            executable=bool(filename.stat().st_mode & 0o111)))
    return records


def family_record(directory, namespace):
    manifest = tomllib.loads((directory / 'manifest.toml').read_text())
    if not manifest.get('plugin_name') or not manifest.get('nodes'):
        raise ValueError('Missing family name or nodes: ' + str(directory))
    image = manifest.get('image', {}).get('reference', '')
    if not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', image):
        raise ValueError('Image is not digest pinned: ' + str(directory))
    kinds = []
    for node in manifest['nodes']:
        kind = node.get('kind')
        if not isinstance(kind, str) or not kind or kind in kinds:
            raise ValueError('Empty or duplicate kind within family')
        kinds.append(kind)
        command = node.get('command', {})
        if command.get('script_file'):
            contained_file(directory, command['script_file'])
        outputs = node.get('ports', {}).get('outputs', [])
        output_paths = []
        for output in outputs:
            relative = output['path']
            safe_relative(relative)
            if relative in output_paths:
                raise ValueError('Duplicate output path')
            output_paths.append(relative)
    return dict(directory=namespace + '/' + directory.name, plugin_name=manifest['plugin_name'],
                kinds=kinds, image_reference=image, files=file_records(directory),
                source_inventory_only=True, scientific_certified=False, auto_enable=False)


def inventory(root):
    records = []
    owners = {}
    for namespace in ['plugins', 'research-adapters']:
        for directory in sorted((root / namespace).iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('Unexpected file in family root: ' + str(directory))
            record = family_record(directory, namespace)
            if namespace == 'plugins':
                for kind in record['kinds']:
                    if kind in owners:
                        raise ValueError('Duplicate canonical kind: ' + kind)
                    owners[kind] = record['directory']
            records.append(record)
    if not owners:
        raise ValueError('Empty canonical catalog is not a PASS')
    return dict(schema_version='1.0', scope='SOURCE_AND_INTERFACE_INVENTORY_NOT_METHOD_CERTIFICATION',
                canonical_families=sum(entry['directory'].startswith('plugins/') for entry in records),
                canonical_kinds=len(owners), families=records,
                shared_image_source_files=file_records(root / 'shared-image-sources')
                if (root / 'shared-image-sources').is_dir() else [], G0=False)


def check_lock(root):
    locked = json.loads((root / 'catalog/release-lock.json').read_text())
    current = inventory(root)
    if locked != current:
        raise ValueError('Current sources differ from reviewed release-lock; explicitly refresh and review the diff')
    return current


EVOLUTION_REPOSITORY = 'https://github.com/ZJ-2002/autonomics-plugins.git'
EVOLUTION_SCOPE = 'RECORDED_GIT_SOURCE_EVOLUTION_NOT_METHOD_CERTIFICATION'


def _git(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Independent Git object verification unavailable or failed')
    return result.stdout


def _identity(content):
    return {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
            'git_blob': hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()}


P0_IMPORT_COMMIT = '073fa0b888828a661a73fa87ee562adbbe571c32'
P0_IMPORT_REPOSITORY = 'https://github.com/ZJ-2002/autonomics'
P0_IMPORT_FAMILIES = frozenset(('b-bulk-inputs-contract', 'b-donor-contract', 'b-donor-method',
    'b-state-contract', 'b-state-method', 'pseudobulk-contract', 'singscore-contract',
    'c-network-contract', 'c-network-source-contract', 'c-safety-contract', 'b-bulk-limma-contract'))


def _additional_original_sources(root):
    path = root / 'provenance/p0-load-source-imports-20261012.json'
    if not path.exists():
        return []
    index = json.loads(contained_file(root, 'provenance/p0-load-source-imports-20261012.json').read_bytes())
    if (type(index.get('schema_version')) is not int or index['schema_version'] != 1
            or index.get('source_commit') != P0_IMPORT_COMMIT
            or index.get('source_repository') != P0_IMPORT_REPOSITORY
            or index.get('scope') != 'ADDITIONAL_EXPLICIT_OPT_IN_SOURCE_TRANSPORT_NOT_DEFAULT_PROFILE_OR_METHOD_CERTIFICATION'
            or any(index.get(k) is not False for k in
                   ('auto_enable', 'scientific_certified', 'original_source_index_rewritten'))):
        raise ValueError('Exact preserved additional import index required')
    rows = index.get('research_adapters')
    if (type(rows) is not list or len(rows) != len(P0_IMPORT_FAMILIES)
            or {row.get('directory') for row in rows} !=
               {'research-adapters/' + name for name in P0_IMPORT_FAMILIES}):
        raise ValueError('Exact eleven original additional import families required')
    sources = []
    for row in rows:
        directory = str(safe_relative(row['directory']))
        lock = json.loads(contained_file(root, directory + '/component-source.json').read_bytes())
        if (row.get('source_commit') != P0_IMPORT_COMMIT or lock.get('source_commit') != P0_IMPORT_COMMIT
                or lock.get('source_repository') != P0_IMPORT_REPOSITORY
                or lock.get('source_family') != 'study_plugins/' + directory.split('/')[1]
                or type(row.get('files')) is not dict or not row['files']
                or row['files'] != lock.get('imported_files')
                or row.get('source_inventory_only') is not True
                or any(row.get(k) is not False for k in ('auto_enable', 'scientific_certified'))
                or lock.get('status') != 'ENGINEERING_CANDIDATE'
                or any(lock.get(k) is not False for k in ('auto_enable', 'scientific_authorization',
                    'method_acceptance_verified', 'loaded_worker_registration_verified'))):
            raise ValueError('Preserved additional index/component-source identity differs')
        sources.append({'directory': directory, 'repository': P0_IMPORT_REPOSITORY,
            'revision': P0_IMPORT_COMMIT,
            'files': [{'path': str(safe_relative(name)), **record} for name, record in row['files'].items()]})
    return sources


def _original_sources(root):
    index = json.loads((root / 'provenance/source-index.json').read_text())
    sources = index['plugins'] + index['research_adapters']
    shared = root / 'provenance/shared-image-sources.json'
    if shared.is_file():
        sources += [json.loads(shared.read_text())]
    return sources + _additional_original_sources(root)


def _verified_import_data(root):
    """Preserve import history and independently verify explicitly evolved Git bytes.

    An evolved source requires the original identity and actual immutable Git
    commit/blob objects from this checkout. A source-only checkout without Git
    fails closed for evolution; the ledger alone never proves new provenance.
    """
    root = Path(root)
    originals = {}
    for source in _original_sources(root):
        for record in source['files']:
            path = str(safe_relative(source['directory'])) + '/' + str(safe_relative(record['path']))
            if path in originals:
                raise ValueError('Duplicate original import path')
            originals[path] = (source, record)
    evolution_path = root/'provenance/source-evolution.json'
    evolutions = {}
    if evolution_path.is_file():
        if evolution_path.is_symlink():
            raise ValueError('Regular source evolution ledger required')
        ledger = json.loads(evolution_path.read_text())
        if (set(ledger) != {'schema_version', 'scope', 'scientific_certified', 'auto_enable', 'changes'} or
                ledger['schema_version'] != 1 or ledger['scope'] != EVOLUTION_SCOPE or
                ledger['scientific_certified'] is not False or ledger['auto_enable'] is not False or
                not isinstance(ledger['changes'], list)):
            raise ValueError('Explicit unapproved source evolution ledger required')
        if ledger['changes']:
            top = _git(root, 'rev-parse', '--show-toplevel').decode().strip()
            if Path(top).resolve() != root.resolve():
                raise ValueError('Exact repository Git object store required for source evolution')
        for change in ledger['changes']:
            if set(change) != {'path', 'original', 'current'}:
                raise ValueError('Exact original/current source evolution fields required')
            path = str(safe_relative(change['path']))
            if path in evolutions:
                raise ValueError('Duplicate source evolution path')
            if path not in originals:
                raise ValueError('Source evolution does not name an original import path')
            source, record = originals[path]
            expected = {'repository': source['repository'], 'revision': source['revision'],
                        **{key: record[key] for key in ['sha256', 'bytes', 'git_blob']}}
            if change['original'] != expected:
                raise ValueError('Source evolution original identity differs from preserved import record')
            current = change['current']
            if (not isinstance(current, dict) or set(current) !=
                    {'repository', 'revision', 'path', 'sha256', 'bytes', 'git_blob'} or
                    current['repository'] != EVOLUTION_REPOSITORY or current['path'] != path or
                    not isinstance(current['revision'], str) or
                    not re.fullmatch('[0-9a-f]{40}', current['revision']) or
                    not isinstance(current['git_blob'], str) or
                    not re.fullmatch('[0-9a-f]{40}', current['git_blob']) or
                    not isinstance(current['sha256'], str) or
                    not re.fullmatch('[0-9a-f]{64}', current['sha256']) or
                    type(current['bytes']) is not int or current['bytes'] < 0):
                raise ValueError('Complete current Git source identity required')
            revision = current['revision']
            if _git(root, 'cat-file', '-t', revision).strip() != b'commit':
                raise ValueError('Actual Git commit object required')
            _git(root, 'merge-base', '--is-ancestor', revision, 'HEAD')
            tree = _git(root, 'ls-tree', revision, '--', path).decode().strip().split('\t')
            if (len(tree) != 2 or tree[1] != path or
                    tree[0].split() not in [['100644', 'blob', current['git_blob']],
                                           ['100755', 'blob', current['git_blob']]]):
                raise ValueError('Current path/blob differs from actual Git commit tree')
            raw = _git(root, 'cat-file', 'blob', current['git_blob'])
            if _identity(raw) != {key: current[key] for key in ['sha256', 'bytes', 'git_blob']}:
                raise ValueError('Current identity differs from independently read Git blob')
            old = _git(root, 'cat-file', 'blob', expected['git_blob'])
            if _identity(old) != {key: expected[key] for key in ['sha256', 'bytes', 'git_blob']}:
                raise ValueError('Preserved original identity differs from independent Git blob')
            evolutions[path] = current
    unchanged, evolved = 0, 0
    for path, (source, record) in originals.items():
        content = contained_file(root, path).read_bytes()
        current = evolutions.get(path)
        if current:
            if _identity(content) != {key: current[key] for key in ['sha256', 'bytes', 'git_blob']}:
                raise ValueError('Current source differs from independently verified evolution: ' + path)
            evolved += 1
        else:
            if (len(content) != record['bytes'] or hashlib.sha256(content).hexdigest() != record['sha256'] or
                    ('git_blob' in record and _identity(content)['git_blob'] != record['git_blob'])):
                raise ValueError('Imported bytes differ without recorded Git source evolution: ' + path)
            unchanged += 1
    checked = unchanged + evolved
    if not checked:
        raise ValueError('No imported files verified')
    report = {'imported_files_verified': checked, 'original_import_files_verified': unchanged,
            'recorded_source_evolution_files_verified': evolved,
            'git_object_verification_required_for_evolution': True,
            'scientific_method_certified': False, 'auto_enable': False, 'G0': False}
    return originals, evolutions, report


def read_verified_import(root, relative):
    """Read only an actual original import, after the shared full Git replay.

    No caller-provided verified flag, identity map or callback is accepted.
    """
    root = Path(root)
    path = str(safe_relative(relative))
    originals, evolutions, _ = _verified_import_data(root)
    if path not in originals:
        raise ValueError('Not a preserved original import path')
    expected = evolutions.get(path, originals[path][1])
    raw = contained_file(root, path).read_bytes()
    if any(_identity(raw)[k] != expected[k] for k in ('sha256', 'bytes')) or (
            'git_blob' in expected and _identity(raw)['git_blob'] != expected['git_blob']):
        raise ValueError('Verified import changed before consumption')
    return raw


def verify_import_detailed(root):
    root = Path(root)
    _, _, report = _verified_import_data(root)
    # Also measure the complete current inventory (including new peer-added
    # source files), while keeping original-import/evolution counts distinct.
    if (root/'catalog/release-lock.json').is_file():
        current = check_lock(root)
        report['current_source_inventory_files_verified'] = sum(
            len(row['files']) for row in current['families']) + len(current['shared_image_source_files'])
        report['current_source_inventory_matches_release_lock'] = True
    return report


def verify_import(root):
    return verify_import_detailed(root)['imported_files_verified']


def render_profile(catalog, revision, selected):
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Profile requires a full lower-case 40-hex commit SHA')
    canonical = {entry['directory'].split('/')[1]: entry for entry in catalog['families']
                 if entry['directory'].startswith('plugins/')}
    if not selected or len(set(selected)) != len(selected) or set(selected) - canonical.keys():
        raise ValueError('Select known, distinct canonical families explicitly')
    entries = []
    for name in selected:
        family = canonical[name]
        entries.append('[[plugin]]\nname = ' + json.dumps(name) + '\n'
                       'git = "https://github.com/ZJ-2002/autonomics-plugins.git"\n'
                       'rev = ' + json.dumps(revision) + '\nsubdir = ' + json.dumps(family['directory']) + '\n')
    return '# PROPOSED PROFILE — no automatic deployment or scientific admission\n\n' + '\n'.join(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['refresh', 'check', 'verify-import', 'profile'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--rev')
    parser.add_argument('--families', nargs='+')
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    if arguments.action == 'refresh':
        target = arguments.root / 'catalog/release-lock.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(inventory(arguments.root), indent=2) + '\n')
        print('Refreshed source inventory; inspect the diff. No scientific certificate issued.')
    elif arguments.action == 'verify-import':
        print(json.dumps(verify_import_detailed(arguments.root)))
    elif arguments.action == 'check':
        current = check_lock(arguments.root)
        print(json.dumps(dict(canonical_families=current['canonical_families'], canonical_kinds=current['canonical_kinds'],
                              source_lock_matches=True, G0=False)))
    else:
        if arguments.output is None:
            parser.error('profile requires --output; existing files are never overwritten')
        text = render_profile(check_lock(arguments.root), arguments.rev or '', arguments.families or [])
        with arguments.output.open('x') as handle:
            handle.write(text)
        print('Proposed profile written; production is unchanged.')
