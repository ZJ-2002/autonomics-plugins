"""Distinguish immutable uploaded design templates from active project software records, read only."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import zipfile


EXPECTED_ZIP = '4c5af762ab1e9768a24b9446827ea367176a80407862cfc10ca09a95f44f1151'
FIELDS = ['component', 'purpose', 'version_or_commit', 'arguments_file', 'verified_example', 'status']


def rows(payload):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')), delimiter='\t')
    records = list(reader)
    if (reader.fieldnames != FIELDS or len(records) != 18
            or len({record['component'] for record in records}) != 18
            or any(set(record) != set(FIELDS) or any(value is None for value in record.values()) for record in records)):
        raise RuntimeError('Exact eighteen-row software record schema required')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', required=True, type=Path)
    parser.add_argument('--active-project', required=True, type=Path)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    with arguments.design.open('rb') as handle:
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
    if checksum != EXPECTED_ZIP:
        raise RuntimeError('Uploaded v4.3.2 source identity differs')
    with zipfile.ZipFile(arguments.design) as archive:
        names = [name for name in archive.namelist() if name.endswith('/02_EXECUTION/SOFTWARE_LOCK.tsv')]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 1024**2:
            raise RuntimeError('Exactly one bounded uploaded software record required')
        template_bytes = archive.read(names[0])
    active_path = arguments.active_project / '02_EXECUTION/SOFTWARE_LOCK.tsv'
    active_bytes = active_path.read_bytes()
    if len(active_bytes) > 1024**2: raise RuntimeError('Bounded active software record required')
    template, active = rows(template_bytes), rows(active_bytes)
    if {record['component'] for record in template} != {record['component'] for record in active}:
        raise RuntimeError('Active record no longer describes the same software requirement set')
    changes = []
    for before in template:
        after = next(record for record in active if record['component'] == before['component'])
        if before != after:
            changes.append(dict(component=before['component'],
                uploaded_version=before['version_or_commit'], uploaded_status=before['status'],
                active_version=after['version_or_commit'], active_status=after['status']))
    if active_path.read_bytes() != active_bytes: raise RuntimeError('Active software record changed during audit')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'study-software-surfaces'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    result = dict(schema='UPLOADED_TEMPLATE_VS_ACTIVE_SOFTWARE_RECORD_READONLY_V1',
        source_zip_sha256=checksum, uploaded_software_sha256=hashlib.sha256(template_bytes).hexdigest(),
        active_software_sha256=hashlib.sha256(active_bytes).hexdigest(), software_requirements=18,
        changed_rows=changes,
        active_records_are_not_replaced_by_upload_template=True,
        generic_plugin_versions_are_not_automatically_equivalent_to_active_method_locks=True,
        locked_status_is_an_observed_record_not_new_scientific_authorization=True,
        scientific_payloads_or_empirical_results_read=False, software_or_study_files_changed=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('READONLY_SOFTWARE_SURFACES=2 CHANGED_ROWS=' + str(len(changes)) + ' G0=false')


if __name__ == '__main__': main()
