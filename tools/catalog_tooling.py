import json
from pathlib import PurePosixPath


def non_plugin_directories(root, file_records):
    index = root / 'catalog/non-plugin-directories.json'
    if not index.exists():
        return {}
    if index.is_symlink() or not index.is_file():
        raise ValueError('Regular non-plugin directory index required')
    document = json.loads(index.read_bytes())
    if (type(document) is not dict or set(document) != {'schema_version', 'directories'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or type(document['directories']) is not list):
        raise ValueError('Invalid non-plugin directory index')
    records = {}
    for relative in document['directories']:
        if (type(relative) is not str or '\\' in relative or ':' in relative
                or any(ord(character) < 32 for character in relative)
                or relative.split('/')[:1] != ['research-adapters']
                or len(relative.split('/')) != 2
                or relative.split('/')[1] in {'', '.', '..'}
                or relative in records):
            raise ValueError('Unique direct research-adapter directory required')
        directory = root.joinpath(*PurePosixPath(relative).parts)
        if (directory.is_symlink() or not directory.is_dir()
                or not directory.resolve().is_relative_to(root.resolve())
                or (directory / 'manifest.toml').exists()
                or (directory / 'manifest.toml').is_symlink()):
            raise ValueError('Non-plugin declaration cannot hide a manifest or escape its root')
        files = file_records(directory)
        if not files:
            raise ValueError('Empty non-plugin source directory')
        records[relative] = dict(directory=relative, files=files,
            scope='TECHNICAL_TOOLING_NOT_LOADABLE_PLUGIN', source_inventory_only=True,
            scientific_certified=False, auto_enable=False)
    return records
