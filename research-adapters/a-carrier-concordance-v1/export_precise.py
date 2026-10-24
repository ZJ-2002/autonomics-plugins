import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile


SCHEMA = 'A_PRECISE_MR_CARRIER_EXPORT_V1'
SELECTOR_FIELDS = {'id.exposure', 'id.outcome', 'method'}
BASE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_bytes(path):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and path.is_file(), 'Canonical ordinary source required')
    require(path.stat().st_size <= 32 * 1024 ** 2, 'Source byte budget exceeded')
    return path.read_bytes()


def extract(tsv, rds, request, rscript='/usr/bin/Rscript'):
    require(type(request) is dict and set(request) == {'schema', 'scope', 'tsv_sha256', 'rds_sha256', 'selectors'}, 'Exact request keys required')
    require(request['schema'] == SCHEMA and request['scope'] == 'LOSSLESS_CARRIER_CONVERSION_NOT_PRIMARY_AUTHORITY', 'Export-only contract required')
    selectors = request['selectors']
    require(type(selectors) is list and selectors and all(type(row) is dict and set(row) == SELECTOR_FIELDS and
        all(type(value) is str and value for value in row.values()) for row in selectors), 'Explicit complete selectors required')
    selector_keys = [tuple(row[key] for key in sorted(SELECTOR_FIELDS)) for row in selectors]
    require(len(selector_keys) == len(set(selector_keys)), 'Duplicate selector')
    original = source_bytes(tsv)
    rds_bytes = source_bytes(rds)
    require(sha(original) == request['tsv_sha256'] and sha(rds_bytes) == request['rds_sha256'], 'Input SHA mismatch')
    rows = list(csv.DictReader(io.StringIO(original.decode()), delimiter='\t', strict=True))
    require(len(rows) == len(selectors) and all(None not in row and all(value is not None for value in row.values()) for row in rows), 'Complete rectangular source required')
    require(all(sum(all(row.get(key) == value for key, value in selector.items()) for row in rows) == 1 for selector in selectors), 'Selector must identify exactly one original row')
    program = (BASE / 'export_precise.R').read_bytes()
    environment = {name:os.environ[name] for name in ['PATH', 'HOME', 'LANG', 'LC_ALL'] if name in os.environ}
    with tempfile.TemporaryDirectory(prefix='a-precise-carrier-', dir=os.environ.get('TMPDIR')) as scratch:
        root = Path(scratch)
        for name, raw in [('input.tsv', original), ('input.rds', rds_bytes), ('export.R', program)]:
            (root / name).write_bytes(raw)
        result = subprocess.run([rscript, '--vanilla', str(root / 'export.R'), str(root / 'input.rds'),
            str(root / 'input.tsv'), str(root / 'precise.tsv'), str(root / 'readback.txt')],
            env=environment, capture_output=True, timeout=30)
        require(result.returncode == 0, 'Pinned official-object export or binary64 readback refused')
        exported = (root / 'precise.tsv').read_bytes()
        expected = [SCHEMA, 'rows=' + str(len(rows)),
            'numeric_cells_binary64_exact=' + str(6 * len(rows)), 'primary_authority_granted=false', 'g0_granted=false']
        require((root / 'readback.txt').read_text().splitlines() == expected, 'Complete binary64 readback receipt required')
    require(source_bytes(tsv) == original and source_bytes(rds) == rds_bytes and
        (BASE / 'export_precise.R').read_bytes() == program, 'Source changed during conversion')
    return exported, dict(schema=SCHEMA, rows=len(rows), numeric_cells_binary64_exact=6 * len(rows),
        original_tsv_sha256=sha(original), original_rds_sha256=sha(rds_bytes),
        output_sha256=sha(exported), R_program_sha256=sha(program),
        original_tsv_is_not_claimed_binary64_exact=True, derived_carrier_not_historical_restoration=True,
        original_and_output_files_not_modified_by_function=True,
        original_primary_missing_preserved=True, primary_authority_granted=False,
        scientific_release_granted=False, g0_granted=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tsv', required=True)
    parser.add_argument('--rds', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    def unique_object(pairs):
        require(len(pairs) == len(dict(pairs)), 'Duplicate JSON key')
        return dict(pairs)
    request = json.loads(source_bytes(args.request), object_pairs_hook=unique_object)
    payload, receipt = extract(args.tsv, args.rds, request)
    output = Path(args.output).absolute()
    require(output.parent.resolve(strict=True) == output.parent, 'Canonical output parent required')
    output.mkdir(mode=0o700)
    (output / 'precise.tsv').write_bytes(payload)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
