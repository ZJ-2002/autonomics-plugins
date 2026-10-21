import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct


ROOT = Path('/home/zj-normal/Work/autonomics')
SESSION = '9805916fef7b4d7ba060347bbb8aa2b6'
SEAL = '3d31c6ca6ae72bfabe73baab5e5c46d3cd02fad82d3fd3a5f048c111d0f544a9'
PREFIX = 'permanent/lcmm-combined-pipeline/'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    specification = importlib.util.spec_from_file_location('sealed', ROOT / 'results/generic-node-production-20261019/issue_eight_plugin_scoped_admission_20261019.py')
    sealed = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(sealed)
    proof = sealed.sealed_member(SESSION, SEAL, PREFIX + 'verification.json')
    require(proof['passed'] and not proof['current_resident_DAG_claimed'], 'Scoped combined graph proof required')
    archive = sealed.ARCHIVES / SESSION / 'artifacts'
    manifest = json.loads((archive / 'MANIFEST.json').read_text())

    def member(name):
        relative = PREFIX + name
        payload = (archive / relative).read_bytes()
        expected = manifest['files'][relative]
        require(len(payload) == expected['bytes'] and hashlib.sha256(payload).hexdigest() == expected['sha256'],
                'Sealed materialization member changed')
        return payload

    expected = list(csv.DictReader(io.StringIO(member('positive/compare-ports/summary.tsv').decode()), delimiter='\t'))
    observed = list(csv.DictReader(io.StringIO(member('positive/materialized.csv').decode())))
    require(len(expected) == len(observed) == 13804 and all(None not in row for row in observed), 'Whole row universe differs')
    positions = [int(row['source_position']) for row in observed]
    require(sorted(positions) == list(range(len(expected))), 'Missing or duplicated materialized source positions')
    observed.sort(key=lambda row: int(row['source_position']))
    finite, missing = 0, 0
    for source, actual in zip(expected, observed, strict=True):
        require(all(source[field] == actual[field] for field in ['test_id', 'row_id', 'field', 'value_kind']),
                'Lexical coordinate or numeric kind changed')
        if source['value_kind'] in {'MISSING', 'NAN'}:
            require(actual['value'] == '', 'Missing value became a number')
            missing += 1
        else:
            require(struct.pack('>d', float(source['value'])) == struct.pack('>d', float(actual['value'])),
                    'Materialized Float64 bits changed')
            finite += 1
    negative = json.loads(member('negative-source-hash/dag-report.json'))
    nodes = {row['id']: row for row in negative['first_run']['nodes']}
    skipped = [name for name, row in nodes.items() if row['status'] == 'skipped']
    require(len(skipped) == 9 and all(nodes[name]['status'] == 'skipped' for name in
        ['bindfit2', 'fit2', 'bindpred', 'predict', 'bindcompare', 'compare', 'typed', 'reader', 'sink']),
        'Full downstream failure propagation differs')
    stops = json.loads(member('owned-container-stops.json'))
    require(len(stops) == 10 and all(row['remaining'] == 0 and row['actual_exit'] == 0 for row in stops),
            'All ten owned containers must be stopped')
    source = ROOT.parent / 'autonomics-plugins/tools/prove_lcmm_combined_pipeline.py'
    require(source.read_bytes() == member('driver.py'), 'Relocated public driver differs from actually executed bytes')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'lcmm-combined-materialization-review'
    output.mkdir(mode=0o700)
    record = dict(schema='LCMM_COMBINED_GRAPH_MATERIALIZATION_REVIEW_V1', passed=True,
        proof_session=SESSION, proof_seal=SEAL, finite_fields=finite, missing_fields=missing,
        lexical_axes_and_source_positions_exact=True, Float64_bits_exact=True,
        downstream_skipped=9, owned_containers_stopped=10, new_method_executions=0,
        relocated_public_driver_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        research_inputs_used=False, new_software_admissions=0, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(record))


if __name__ == '__main__':
    main()
