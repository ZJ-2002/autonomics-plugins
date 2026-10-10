import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
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


def verify_import(root):
    index = json.loads((root / 'provenance/source-index.json').read_text())
    checked = 0
    sources = index['plugins'] + index['research_adapters']
    shared = root / 'provenance/shared-image-sources.json'
    if shared.is_file():
        sources += [json.loads(shared.read_text())]
    for source in sources:
        directory = root.joinpath(*safe_relative(source['directory']).parts)
        for record in source['files']:
            filename = contained_file(directory, record['path'])
            content = filename.read_bytes()
            if len(content) != record['bytes'] or hashlib.sha256(content).hexdigest() != record['sha256']:
                raise ValueError('Imported bytes differ: ' + str(filename))
            checked += 1
    if not checked:
        raise ValueError('No imported files verified')
    return checked


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
        print(json.dumps(dict(imported_files_verified=verify_import(arguments.root), G0=False)))
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
