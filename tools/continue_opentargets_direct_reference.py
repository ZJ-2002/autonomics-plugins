"""Explicit bounded continuation of sealed per-file facts, never a successful-exit recovery."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.request import HTTPRedirectHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import acquire_opentargets_direct_reference as original


OLD_SESSION = '3a35db8dda8e44018860e7e1895e9c7d'
OLD_SEAL = 'c60029a5a4a7c20c2375b0b37ba32f629d17603d984f8bf1474cd9afe56f685a'
OLD_PREFIX = 'permanent/opentargets-direct-reference-files/'
PREFIX = 'permanent/opentargets-direct-continuation/'
BATCH_SIZE = 2


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_archive(archives, session_id, seal, require_success):
    if not re.fullmatch('[0-9a-f]{32}', session_id) or not re.fullmatch('[0-9a-f]{64}', seal):
        raise RuntimeError('Literal session and independently supplied seal required')
    archive = archives / session_id
    artifacts = archive / 'artifacts'
    manifest_path = artifacts / 'MANIFEST.json'
    if archive.is_symlink() or artifacts.is_symlink() or manifest_path.is_symlink():
        raise RuntimeError('Literal archive paths required')
    if manifest_path.stat().st_size > 2 * 1024**2 or digest_file(manifest_path) != seal:
        raise RuntimeError('Archive seal differs')
    manifest = json.loads(manifest_path.read_bytes())
    session = json.loads((archive / 'SESSION.json').read_bytes())
    if (manifest['session'] != session_id or session['session'] != session_id
            or session['state'] != 'CLEANED' or session['manifest_sha256'] != seal
            or (require_success and (type(session['worker_exit_status']) is not int
                or session['worker_exit_status'] != 0))):
        raise RuntimeError('Archive lifecycle or successful new batch exit not established')
    paths = list(artifacts.rglob('*'))
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in paths):
        raise RuntimeError('Unsupported archive object')
    actual = {path.relative_to(artifacts).as_posix() for path in paths if path.is_file() and path != manifest_path}
    if actual != set(manifest['files']) or len(actual) > 1000:
        raise RuntimeError('Complete archive membership differs')
    total = 0
    for name, identity in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in {'permanent', 'retained'}:
            raise RuntimeError('Unsafe archive member')
        path = artifacts / name
        total += identity['bytes']
        if (not 0 <= identity['bytes'] <= original.FILE_LIMIT or total > 2 * 1024**3
                or path.stat().st_size != identity['bytes'] or digest_file(path) != identity['sha256']):
            raise RuntimeError('Archive content identity differs')
    return artifacts, manifest, session


def check_receipts(artifacts, manifest, session_id, seal, prefix, receipts, planned):
    expected = {(dataset, record['url']): record for dataset, _, record in planned}
    result = []
    seen = set()
    for receipt in receipts:
        key = receipt['dataset'], receipt['url']
        if key not in expected or key in seen:
            raise RuntimeError('Unexpected or duplicate completed resource')
        seen.add(key)
        record = expected[key]
        name = original.validate_resource(receipt['dataset'], record)
        relative = prefix + 'files/' + receipt['dataset'] + '/' + name
        if (receipt['relative_path'] != 'files/' + receipt['dataset'] + '/' + name
                or relative not in manifest['files']
                or any(receipt[field] != record[field] for field in ['url', 'bytes', 'etag', 'last_modified'])
                or receipt.get('sha256_is_measured_not_author_published') is not True
                or manifest['files'][relative] != {'bytes': receipt['bytes'], 'sha256': receipt['sha256']}):
            raise RuntimeError('Per-file receipt does not bind metadata and sealed bytes')
        path = artifacts / relative
        with path.open('rb') as source:
            header = source.read(4)
            source.seek(-4, 2)
            if header != b'PAR1' or source.read(4) != b'PAR1':
                raise RuntimeError('Per-file ordinary Parquet framing differs')
        result.append(dict(dataset=receipt['dataset'], url=receipt['url'], bytes=receipt['bytes'],
            sha256=receipt['sha256'], etag=receipt['etag'], last_modified=receipt['last_modified'],
            source_session=session_id, source_manifest_sha256=seal, relative_path=relative))
    return result


def planned_resources(archives, output):
    resources = original.archived_metadata(archives / original.SOURCE_SESSION, original.SOURCE_SEAL, output)
    selected = {record['dataset']: record for record in resources if record['dataset'] in original.SELECTED}
    if set(selected) != set(original.SELECTED):
        raise RuntimeError('Declared dataset membership differs')
    planned = []
    for dataset, count in original.SELECTED.items():
        if len(selected[dataset]['files']) != count:
            raise RuntimeError('Declared partition membership differs')
        for record in selected[dataset]['files']:
            planned.append((dataset, original.validate_resource(dataset, record), record))
    if len(planned) != 18 or sum(record['bytes'] for _, _, record in planned) != original.TOTAL:
        raise RuntimeError('Complete declared bytes differ')
    return planned


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RuntimeError('Redirect forbidden; no fallback request sent')


def acquire(record, temporary, destination):
    opener = build_opener(NoRedirect())
    previous = original.urlopen
    try:
        original.urlopen = opener.open
        return original.acquire(record, temporary, destination)
    finally:
        original.urlopen = previous


def old_facts(archives, planned):
    artifacts, manifest, session = verify_archive(archives, OLD_SESSION, OLD_SEAL, False)
    receipts = json.loads((artifacts / (OLD_PREFIX + 'completed-files.json')).read_bytes())
    facts = check_receipts(artifacts, manifest, OLD_SESSION, OLD_SEAL, OLD_PREFIX, receipts, planned)
    if (len(facts) != 10 or sum(item['bytes'] for item in facts) != 597416410
            or [item['url'] for item in facts] != [record['url'] for _, _, record in planned[:10]]
            or session['worker_exit_status'] is not None):
        raise RuntimeError('Fixed interrupted source facts differ')
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--batch', type=int, choices=range(4))
    parser.add_argument('--assemble', action='store_true')
    parser.add_argument('--batch-source', action='append', default=[])
    arguments = parser.parse_args()
    if arguments.assemble == (arguments.batch is not None):
        parser.error('Exactly one of --batch or --assemble required')
    if not arguments.assemble and arguments.batch_source:
        parser.error('Batch sources are only used for final assembly')
    if not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT'):
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'opentargets-direct-continuation'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(Path(original.__file__), output / 'original-acquisition-driver.py')
    planned = planned_resources(arguments.archives, output)
    facts = old_facts(arguments.archives, planned)
    write(output / 'old-per-file-facts.json', facts)
    write(output / 'predeclared.json', dict(release='26.09', assemble=arguments.assemble,
        batch=arguments.batch, batch_size=BATCH_SIZE, complete_inventory_files=18,
        old_task_exit_is_unknown=True, old_task_success_not_inferred=True,
        partial_bytes_never_reused=True, repeated_verified_downloads=0, network_retries=0,
        metadata_session=original.SOURCE_SESSION, metadata_manifest_sha256=original.SOURCE_SEAL,
        source_qualification_or_study_release_granted=False, g0_granted=False))
    if not arguments.assemble:
        subset = planned[10 + arguments.batch * BATCH_SIZE:10 + (arguments.batch + 1) * BATCH_SIZE]
        if len(subset) != BATCH_SIZE or shutil.disk_usage(output).free < 20 * 1024**3:
            raise RuntimeError('Batch scope or conservative free-space admission differs')
        write(output / 'batch-plan.json', [dict(dataset=dataset, **record) for dataset, _, record in subset])
        completed = []
        for dataset, name, record in subset:
            destination = output / 'files' / dataset / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(os.environ['TMPDIR']) / ('opentargets-continuation-' + name + '.partial')
            time.sleep(2)
            receipt = acquire(record, temporary, destination)
            receipt.update(dataset=dataset, relative_path=destination.relative_to(output).as_posix())
            completed.append(receipt)
            write(output / f'file-{len(completed)}-receipt.json', receipt)
            print(f'BATCH={arguments.batch} FILES={len(completed)}/2 VERIFIED', flush=True)
        write(output / 'completed-files.json', completed)
        write(output / 'verification.json', dict(status='DECLARED_TWO_FILE_BATCH_ACQUIRED',
            batch=arguments.batch, files=completed, old_task_success_not_inferred=True,
            complete_source_or_scientific_release_granted=False, g0_granted=False))
        return
    if len(arguments.batch_source) != 4:
        raise RuntimeError('Exactly four independently sealed successful two-file batches required')
    batches = set()
    for reference in arguments.batch_source:
        if reference.count(':') != 1:
            raise RuntimeError('Use explicit session:seal references')
        session_id, seal = reference.split(':')
        artifacts, manifest, _ = verify_archive(arguments.archives, session_id, seal, True)
        verification = json.loads((artifacts / (PREFIX + 'verification.json')).read_bytes())
        batch = verification['batch']
        if (type(batch) is not int or batch not in range(4) or batch in batches
                or verification['status'] != 'DECLARED_TWO_FILE_BATCH_ACQUIRED'):
            raise RuntimeError('Duplicate or undeclared successful batch')
        batches.add(batch)
        receipts = json.loads((artifacts / (PREFIX + 'completed-files.json')).read_bytes())
        records = check_receipts(artifacts, manifest, session_id, seal, PREFIX, receipts, planned)
        if [item['url'] for item in records] != [record['url'] for _, _, record in planned[10+batch*2:12+batch*2]]:
            raise RuntimeError('Batch receipt membership differs')
        facts.extend(records)
    facts.sort(key=lambda item: next(index for index, (_, _, record) in enumerate(planned) if record['url'] == item['url']))
    if len(facts) != 18 or len({item['url'] for item in facts}) != 18 or sum(item['bytes'] for item in facts) != original.TOTAL:
        raise RuntimeError('Complete measured inventory not established')
    write(output / 'complete-file-index.json', dict(schema='OPENTARGETS_DIRECT_MULTI_ARCHIVE_INDEX_V1',
        status='ALL_18_SEALED_FILE_FACTS_INDEXED_NOT_SOURCE_QUALIFIED',
        release='26.09', files=facts, total_bytes=original.TOTAL,
        metadata_session=original.SOURCE_SESSION, metadata_manifest_sha256=original.SOURCE_SEAL,
        old_task_success_not_inferred=True, row_semantics_not_yet_qualified=True,
        complete_source_node_or_scientific_release_granted=False, g0_granted=False))
    print('COMPLETE_FILE_INDEX=18 OLD_TASK_SUCCESS_NOT_INFERRED ROW_SEMANTICS_NOT_GRANTED G0=false')


if __name__ == '__main__':
    main()
