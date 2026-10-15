"""Audit sealed official direct partitions from a complete multi-archive file index."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.acquire_opentargets_direct_reference import BASE, SELECTED, TOTAL, FILE_LIMIT, SOURCE_SESSION, SOURCE_SEAL
from tools.audit_opentargets_bulk_metadata import READER_IMAGE


INDEX_SCHEMA = 'OPENTARGETS_DIRECT_MULTI_ARCHIVE_INDEX_V1'
INDEX_STATUS = 'ALL_18_SEALED_FILE_FACTS_INDEXED_NOT_SOURCE_QUALIFIED'
ARCHIVE_LIMIT = TOTAL + 32 * 1024**2


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def no_alias(path):
    path = path.absolute()
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise RuntimeError('Source path aliases forbidden')
    return path


def read_json(path, limit=2 * 1024**2):
    no_alias(path)
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > limit:
        raise RuntimeError('Bounded ordinary JSON evidence required')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError('Duplicate JSON evidence key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError('Nonfinite JSON evidence')))


def member_path(name):
    if not isinstance(name, str):
        raise RuntimeError('Archive member name must be literal text')
    path = Path(name)
    if (path.is_absolute() or name != path.as_posix() or len(path.parts) < 2
            or '..' in path.parts or path.parts[0] not in {'permanent', 'retained'}):
        raise RuntimeError('Archive member classification differs')
    return path


def sealed_archive(archive, expected, successful=False):
    archive = no_alias(archive)
    if not re.fullmatch('[0-9a-f]{32}', archive.name) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise RuntimeError('Literal managed archive and independent SHA256 required')
    artifacts = no_alias(archive / 'artifacts')
    manifest_path = no_alias(artifacts / 'MANIFEST.json')
    manifest = read_json(manifest_path)
    session = read_json(archive / 'SESSION.json')
    if (digest(manifest_path) != expected or session.get('state') != 'CLEANED'
            or session.get('session') != archive.name or manifest.get('session') != archive.name
            or session.get('manifest_sha256') != expected
            or successful and (type(session.get('worker_exit_status')) is not int or session['worker_exit_status'] != 0)):
        raise RuntimeError('Sealed archive lifecycle or content identity differs')
    entries = manifest.get('files')
    if not isinstance(entries, dict) or not entries or len(entries) > 200:
        raise RuntimeError('Bounded complete archive membership required')
    for name in entries:
        member_path(name)
    paths = list(artifacts.rglob('*'))
    if any(path.is_symlink() or not (stat.S_ISREG(path.lstat().st_mode) or path.is_dir()) for path in paths):
        raise RuntimeError('Archive aliases or special files forbidden')
    actual = {path.relative_to(artifacts).as_posix() for path in paths if path.is_file() and path != manifest_path}
    if actual != set(entries):
        raise RuntimeError('Complete source archive membership differs')
    total = 0
    for name, identity in entries.items():
        path = artifacts / member_path(name)
        if (not isinstance(identity, dict) or set(identity) != {'bytes', 'sha256'}
                or type(identity['bytes']) is not int or identity['bytes'] < 0
                or not isinstance(identity['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', identity['sha256'])):
            raise RuntimeError('Exact bounded archive member identity required')
        total += identity['bytes']
        if total > ARCHIVE_LIMIT or path.stat().st_size != identity['bytes'] or digest(path) != identity['sha256']:
            raise RuntimeError('Archive member bytes or hash differ')
    return dict(archive=archive, manifest=manifest, session=session)


def inventory(verification):
    if (verification.get('schema') != INDEX_SCHEMA or verification.get('status') != INDEX_STATUS
            or verification.get('release') != '26.09' or verification.get('total_bytes') != TOTAL
            or verification.get('g0_granted') is not False):
        raise RuntimeError('Exact complete multi-archive file-facts index required')
    records = verification['files']
    if (not isinstance(records, list) or len(records) != sum(SELECTED.values())
            or Counter(row['dataset'] for row in records) != SELECTED
            or sum(row['bytes'] for row in records) != TOTAL):
        raise RuntimeError('All eighteen fixed dataset partitions required')
    urls = set()
    for row in records:
        name = member_path(row['relative_path'])
        if (len(name.parts) < 5 or name.parts[0] != 'permanent'
                or name.parts[-3:-1] != ('files', row['dataset'])
                or not re.fullmatch(r'[A-Za-z0-9_.-]+[.]parquet', name.name) or '..' in name.name
                or row['url'] in urls or row['url'] != BASE + row['dataset'] + '/' + name.name
                or type(row['bytes']) is not int or not 12 <= row['bytes'] <= FILE_LIMIT
                or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or not re.fullmatch('[0-9a-f]{32}', row['source_session'])
                or not re.fullmatch('[0-9a-f]{64}', row['source_manifest_sha256'])):
            raise RuntimeError('Exact unique official partition and archive identity required')
        urls.add(row['url'])
    return records


def source_index(archives, index_archive, expected, index_member):
    index_seal = sealed_archive(index_archive, expected, successful=True)
    member = member_path(index_member)
    if member.parts[0] != 'permanent' or index_member not in index_seal['manifest']['files']:
        raise RuntimeError('Permanent sealed complete index member required')
    records = inventory(read_json(index_archive / 'artifacts' / member))
    metadata = sealed_archive(archives / SOURCE_SESSION, SOURCE_SEAL, successful=True)
    preaudited = {}
    for dataset in SELECTED:
        resource_name = 'permanent/opentargets-bulk-metadata/' + dataset + '.resource.json'
        if resource_name not in metadata['manifest']['files']:
            raise RuntimeError('Preaudited official metadata member absent')
        resource = read_json(metadata['archive'] / 'artifacts' / resource_name)
        if resource['dataset'] != dataset or len(resource['files']) != SELECTED[dataset]:
            raise RuntimeError('Fixed release metadata partition membership differs')
        for row in resource['files']:
            if row['url'] in preaudited:
                raise RuntimeError('Duplicate preaudited partition URL')
            preaudited[row['url']] = row
    sealed = {index_archive.name: index_seal}
    receipts = {}
    for row in records:
        identity = preaudited.get(row['url'])
        if identity is None or any(row.get(key) != identity[key] for key in ['bytes', 'etag', 'last_modified']):
            raise RuntimeError('File facts differ from independently sealed official release metadata')
        session = row['source_session']
        if session not in sealed:
            sealed[session] = sealed_archive(archives / session, row['source_manifest_sha256'])
        archive = sealed[session]
        if (archive['session']['manifest_sha256'] != row['source_manifest_sha256']
                or archive['manifest']['files'].get(row['relative_path']) != dict(bytes=row['bytes'], sha256=row['sha256'])):
            raise RuntimeError('Indexed raw file differs from its exact sealed archive member')
        prefix = Path(row['relative_path']).parents[2].as_posix() + '/'
        receipt_name = prefix + 'completed-files.json'
        receipt_key = session, receipt_name
        if receipt_key not in receipts:
            if receipt_name not in archive['manifest']['files']:
                raise RuntimeError('Sealed original per-file acquisition receipts required')
            values = read_json(archive['archive'] / 'artifacts' / receipt_name)
            if not isinstance(values, list) or not values or len(values) > 18:
                raise RuntimeError('Bounded original acquisition receipt list required')
            by_url = {value['url']: value for value in values}
            if len(by_url) != len(values):
                raise RuntimeError('Duplicate original acquisition receipt')
            receipts[receipt_key] = by_url
        receipt = receipts[receipt_key].get(row['url'])
        if (receipt is None or receipt.get('sha256_is_measured_not_author_published') is not True
                or any(receipt.get(key) != row[key] for key in ['dataset', 'url', 'bytes', 'sha256', 'etag', 'last_modified'])
                or prefix + receipt.get('relative_path', '') != row['relative_path']):
            raise RuntimeError('Index differs from sealed original full-file response receipt')
    if set(preaudited) != {row['url'] for row in records}:
        raise RuntimeError('Complete preaudited release membership differs')
    return records, sealed


def reader_command(output, sources):
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
               '--userns=keep-id', f'--user={os.getuid()}:{os.getgid()}']
    for session, archive in sorted(sources.items()):
        command.extend(['-v', str(archive['archive'] / 'artifacts') + ':/sources/' + session + ':ro'])
    command.extend(['-v', str(output) + ':/work:rw', '--entrypoint=python', READER_IMAGE, '/work/reader.py'])
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--index-archive', type=Path, required=True)
    parser.add_argument('--index-manifest-sha256', required=True)
    parser.add_argument('--index-member', required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed technical validation required')
    records, sources = source_index(arguments.archives, arguments.index_archive,
        arguments.index_manifest_sha256, arguments.index_member)
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'opentargets-direct-membership'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    reader = Path(__file__).with_name('opentargets_direct_reader.py')
    (output / 'reader.py').write_bytes(reader.read_bytes())
    (output / 'reader-input.json').write_text(json.dumps(records, indent=2) + '\n')
    command = reader_command(output, sources)
    (output / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (output / 'reader.stdout').open('x') as stdout, (output / 'reader.stderr').open('x') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1200)
    (output / 'reader-exit.json').write_text(json.dumps(dict(exit=result.returncode)) + '\n')
    source_index(arguments.archives, arguments.index_archive, arguments.index_manifest_sha256, arguments.index_member)
    if result.returncode:
        (output / 'failure.json').write_text(json.dumps(dict(
            status='OFFLINE_READER_FAILED_NO_SOURCE_EQUIVALENCE_GRANTED',
            full_raw_source_hashes_rechecked_before_and_after=True,
            current_daemon_verified=False, scientific_authorization_granted=False, g0_granted=False), indent=2) + '\n')
        raise RuntimeError('Complete offline official-PyArrow read failed')
    result = read_json(output / 'reader-verification.json')
    if (len(result['partitions']) != 18 or result['pyarrow_version'] != '25.0.1'
            or result.get('g0_granted') is not False):
        raise RuntimeError('Full fixed-reader partition execution not proven')
    result.update(index_session=arguments.index_archive.name, index_manifest_sha256=arguments.index_manifest_sha256,
        source_sessions=[dict(session=name, manifest_sha256=value['session']['manifest_sha256'],
            worker_exit_status=value['session'].get('worker_exit_status'),
            worker_success_inferred=False) for name, value in sorted(sources.items())],
        full_raw_source_hashes_rechecked_before_and_after=True, current_daemon_verified=False)
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('ALL_18_PARTITIONS_READ; CONTROL_MEMBERS=' + str(result['control_members']) + '; API_EQUIVALENCE_NOT_GRANTED; G0=false')


if __name__ == '__main__':
    main()
