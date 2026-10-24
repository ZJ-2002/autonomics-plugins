import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile


BASE = Path(__file__).resolve().parent
SCHEMA = 'A_TWOSAMPLEMR_CARRIER_CONCORDANCE_V1'
SELECTOR_FIELDS = {'id.exposure', 'id.outcome', 'method'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    require(len({key for key, value in pairs}) == len(pairs), 'Duplicate JSON key')
    return dict(pairs)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def ordinary_bytes(filename):
    filename = Path(filename).absolute()
    require(filename.resolve(strict=True) == filename and filename.is_file(), 'Canonical ordinary source required')
    require(filename.stat().st_size <= 32*1024**2, 'Source byte budget exceeded')
    return filename.read_bytes()


def verify(tsv_path, rds_path, request, rscript='/usr/bin/Rscript'):
    require(isinstance(request, dict) and set(request) == {'schema', 'scope', 'tsv_sha256', 'rds_sha256', 'selectors'}, 'Exact request keys required')
    require(request['schema'] == SCHEMA and request['scope'] == 'CARRIER_CONCORDANCE_ONLY_NOT_PRIMARY_AUTHORITY', 'Concordance-only scope required')
    selectors = request['selectors']
    require(isinstance(selectors, list) and selectors and all(isinstance(row, dict) and set(row) == SELECTOR_FIELDS and all(isinstance(value, str) and value for value in row.values()) for row in selectors), 'Explicit trait and method selectors required')
    identities = [tuple(row[field] for field in sorted(SELECTOR_FIELDS)) for row in selectors]
    require(len(identities) == len(set(identities)), 'Duplicate selector')
    tsv = ordinary_bytes(tsv_path)
    rds = ordinary_bytes(rds_path)
    require(sha(tsv) == request['tsv_sha256'] and sha(rds) == request['rds_sha256'], 'Source SHA mismatch')
    reader = csv.DictReader(io.StringIO(tsv.decode('utf-8')), delimiter='\t', strict=True)
    rows = list(reader)
    require(reader.fieldnames and not any(None in row or any(value is None for value in row.values()) for row in rows), 'Ragged TSV')
    require(len(rows) == len(selectors), 'Complete source row set required')
    for selector in selectors:
        require(sum(all(row.get(key) == value for key, value in selector.items()) for row in rows) == 1, 'Selector must identify exactly one source row')
    decoder = (BASE/'decode.R').read_bytes()
    environment = {name:value for name,value in os.environ.items() if not name.endswith(('_API_KEY', '_TOKEN', '_JWT'))}
    with tempfile.TemporaryDirectory(prefix='a-carrier-concordance-', dir=os.environ.get('TMPDIR')) as scratch:
        directory = Path(scratch)
        copied = directory/'input.rds'
        copied.write_bytes(rds)
        copied.chmod(0o600)
        code = directory/'decode.R'
        code.write_bytes(decoder)
        actual = directory/'canonical.tsv'
        result = subprocess.run([rscript, '--vanilla', str(code), str(copied), str(actual)], env=environment, capture_output=True, timeout=30)
        require(result.returncode == 0, 'Pinned RDS schema/reader refused the source')
        require(actual.read_bytes() == tsv, 'RDS canonical TSV serialization differs')
    require(ordinary_bytes(tsv_path) == tsv and ordinary_bytes(rds_path) == rds and (BASE/'decode.R').read_bytes() == decoder, 'Source changed during verification')
    return {'schema':SCHEMA, 'status':'CARRIER_SERIALIZATION_CONCORDANCE', 'rows':len(rows),
            'tsv_sha256':sha(tsv), 'rds_sha256':sha(rds), 'decoder_sha256':sha(decoder),
            'comparison':'EXACT_R_4_6_1_WRITE_TABLE_BYTES_ALL_COLUMNS_AND_ROWS',
            'binary64_equality_of_TSV_and_RDS_claimed':False,
            'rounding_tolerance_fitted_after_results':False,
            'primary_authority_granted':False, 'scientific_release_granted':False, 'g0_granted':False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tsv', required=True)
    parser.add_argument('--rds', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    request = json.loads(ordinary_bytes(args.request), object_pairs_hook=unique_object)
    receipt = verify(args.tsv, args.rds, request)
    with open(args.output, 'x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
