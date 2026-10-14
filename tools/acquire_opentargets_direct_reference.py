"""Acquire the complete pre-audited official direct overall/annotation files, not study results."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_opentargets_bulk_metadata import BASE, archived_metadata


SOURCE_SESSION = '5addbe9b7690453b84ee54154486ab42'
SOURCE_SEAL = 'e89ad960f9fd8304724e0dc615e726c00c9ca3d768951cc054d064f7f6ef8842'
SELECTED = {'association_overall_direct': 14, 'target': 3, 'disease': 1}
TOTAL = 867128423
FILE_LIMIT = 128 * 1024**2


def validate_resource(dataset, record):
    parsed = urlsplit(record['url'])
    prefix = BASE + dataset + '/'
    name = parsed.path.rsplit('/', 1)[-1]
    if (dataset not in SELECTED or record['url'] != prefix + name
            or parsed.scheme != 'https' or parsed.hostname != 'ftp.ebi.ac.uk'
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r'[A-Za-z0-9_.-]+[.]parquet', name) or '..' in name
            or record['status'] != 200 or not 12 <= record['bytes'] <= FILE_LIMIT
            or not isinstance(record['etag'], str) or not record['etag']
            or not isinstance(record['last_modified'], str) or not record['last_modified']):
        raise RuntimeError('Exact pre-audited official file identity required')
    return name


def check_response(response, record):
    if (response.status != 200 or response.url != record['url']
            or response.headers.get('Content-Length') != str(record['bytes'])
            or response.headers.get('ETag') != record['etag']
            or response.headers.get('Last-Modified') != record['last_modified']
            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'
            or response.headers.get('Content-Range') is not None):
        raise RuntimeError('Official full-file response identity differs; no redirect/range/retry fallback')


def acquire(record, temporary, destination):
    digest = hashlib.sha256()
    received = 0
    started = time.monotonic()
    request = Request(record['url'], headers={'If-Match': record['etag'], 'Accept-Encoding': 'identity',
        'User-Agent': 'autonomics-official-source-technical-audit/1.0'})
    with urlopen(request, timeout=60) as response:
        check_response(response, record)
        with temporary.open('xb') as output:
            while True:
                block = response.read(min(1024**2, record['bytes'] - received + 1))
                if not block: break
                received += len(block)
                if received > record['bytes'] or time.monotonic() - started > 900:
                    raise RuntimeError('Full-file byte/time budget exceeded')
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    if received != record['bytes']:
        raise RuntimeError('Official file truncated')
    with temporary.open('rb') as source:
        header = source.read(4)
        source.seek(-4, 2)
        if header != b'PAR1' or source.read(4) != b'PAR1':
            raise RuntimeError('Ordinary Parquet file framing differs')
    os.link(temporary, destination)
    temporary.unlink()
    return dict(url=record['url'], bytes=received, sha256=digest.hexdigest(), etag=record['etag'],
        last_modified=record['last_modified'], sha256_is_measured_not_author_published=True,
        seconds=time.monotonic()-started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'opentargets-direct-reference-files'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    records = archived_metadata(arguments.archives / SOURCE_SESSION, SOURCE_SEAL, output)
    selected = {record['dataset']: record for record in records if record['dataset'] in SELECTED}
    if set(selected) != set(SELECTED) or any(len(selected[name]['files']) != count for name, count in SELECTED.items()):
        raise RuntimeError('Complete declared 18-file inventory required')
    total = sum(record['bytes'] for dataset in selected.values() for record in dataset['files'])
    if total != TOTAL or shutil.disk_usage(output).free < 20 * 1024**3:
        raise RuntimeError('Source bytes or conservative technical free-space admission differs')
    planned = []
    for dataset in SELECTED:
        for record in selected[dataset]['files']:
            planned.append((dataset, validate_resource(dataset, record), record))
    (output / 'predeclared.json').write_text(json.dumps(dict(release='26.09', datasets=SELECTED,
        files=len(planned), expected_bytes=total, no_scientific_source_selection=True,
        source_changes_or_network_retries_not_allowed=True, g0_granted=False), indent=2) + '\n')
    completed = []
    for dataset, name, record in planned:
        directory = output / 'files' / dataset
        directory.mkdir(parents=True, exist_ok=True)
        temporary = Path(os.environ['TMPDIR']) / ('opentargets-' + dataset + '-' + name + '.partial')
        time.sleep(2)
        receipt = acquire(record, temporary, directory / name)
        receipt.update(dataset=dataset, relative_path=(directory / name).relative_to(output).as_posix())
        completed.append(receipt)
        (output / 'completed-files.json').write_text(json.dumps(completed, indent=2) + '\n')
        print(dataset, len(completed), '/', len(planned), 'FILE_VERIFIED', flush=True)
    if len(completed) != 18 or sum(record['bytes'] for record in completed) != TOTAL:
        raise RuntimeError('Complete acquisition not achieved')
    (output / 'verification.json').write_text(json.dumps(dict(status='ALL_PREAUDITED_DIRECT_OVERALL_ANNOTATION_FILES_ACQUIRED',
        release='26.09', files=completed, total_bytes=TOTAL,
        source_metadata_session=SOURCE_SESSION, source_metadata_manifest_sha256=SOURCE_SEAL,
        measured_raw_file_identities_not_row_semantics=True, all_partition_schemas_or_membership_not_yet_qualified=True,
        original_live_API_incomplete_record_not_rewritten=True, production_or_frozen_study_source_changed=False,
        complete_source_node_or_scientific_release_granted=False, g0_granted=False), indent=2) + '\n')
    print('VERIFIED_COMPLETE_RAW_FILES=18 BYTES=867128423 ROW_SEMANTICS_NOT_GRANTED G0=false')


if __name__ == '__main__': main()
