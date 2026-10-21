"""Review sealed pair-policy DAG products without rerunning methods or containers."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(filename):
    with filename.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--seal', required=True)
    arguments = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    checked = verify_archive(archives, arguments.session, arguments.seal)
    require(checked['positive_worker_exit_verified'], 'Successful sealed SDK execution required')
    prefix = 'permanent/r-stats-strict-pair-sdk/'
    directory = archives / arguments.session / 'artifacts' / prefix
    manifest = checked['member_identities']

    def member(name):
        require(prefix + name in manifest, 'Required sealed product absent: ' + name)
        return directory / name

    proof = json.loads(member('verification.json').read_text())
    require(proof['passed'] and proof['positive_DAGs'] == proof['refusal_DAGs'] == 1
            and proof['actual_method_containers'] == 2 and proof['current_resident_engine_equivalence_assumed'] is False,
            'Exact bounded, non-resident SDK proof required')
    definition = tomllib.loads(member('source/manifest.toml').read_text())
    outputs = next(node for node in definition['nodes'] if node['kind'] == 't_test')['ports']['outputs']
    require(len(outputs) == 5, 'Five declared output ports required')
    creations = [json.loads(line) for line in member('actual-creates.jsonl').read_text().splitlines()]
    require(len(creations) == 2, 'Exactly two owned method containers required')
    report = json.loads(member('strict-complete/dag-report.json').read_text())
    analysis = next(node for node in report['first_run']['nodes'] if node['id'] == 'analysis')
    require(analysis['status'] == 'success' and set(analysis['port_assignments']) == set(map(str, range(5))),
            'Complete successful FileRef inventory required')
    ports = []
    for index, declaration in enumerate(outputs):
        value = analysis['port_assignments'][str(index)]
        artifact = member('strict-complete/actual/' + declaration['path'])
        require(Path(value['path']) == Path(creations[0]['workspace']) / declaration['path']
                and value['format'] == declaration['format']
                and type(value['fingerprint']['size']) is int
                and value['fingerprint']['size'] == artifact.stat().st_size > 0,
                'FileRef path/format/size differs from sealed physical product')
        ports.append(dict(index=index, path=declaration['path'], format=value['format'], bytes=artifact.stat().st_size,
                          sha256=sha(artifact), FileRef_content_hash_present=value['fingerprint'].get('content_hash') is not None))
    with member('strict-complete/actual/audit.tsv').open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        audit_rows = list(reader)
        require(reader.fieldnames == ['key', 'value'] and len({row['key'] for row in audit_rows}) == len(audit_rows),
                'Unique key/value audit required')
    audit = {row['key']: row['value'] for row in audit_rows}
    require(audit['status'] == 'COMPLETED' and audit['stats_version'] == '4.6.1'
            and audit['input_sha256'] == sha(member('strict-complete/input0.tsv'))
            and audit['contract_sha256'] == sha(member('strict-complete/input1.tsv')),
            'Input and contract identities disagree with actual method audit')
    for index in range(3):
        require(audit['output' + str(index) + '_sha256'] == ports[index]['sha256'],
                'Author wrapper audit and retained analytic output disagree')
    require('COMPLETE_RDS_IDENTICAL' in member('strict-complete/RDS-readback.stdout').read_text(),
            'Actual strict full-object readback record missing')
    stopped = json.loads(member('owned-container-stops.json').read_text())
    require(len(stopped) == 2 and all(item['actual_exit'] == 0 and item['remaining'] == 0 for item in stopped),
            'Actual owned-container absence observations required')
    result = dict(schema='R_STATS_STRICT_PAIR_SEALED_PRODUCT_REVIEW_V1', passed=True,
        session=arguments.session, seal=arguments.seal,
        executed_driver_sha256=sha(member('driver.py')), source_sha256=sha(member('source/scripts/statistics.R')),
        manifest_sha256=sha(member('source/manifest.toml')), verified_output_ports=ports,
        complete_RDS_readback_record_verified=True, analytic_output_and_input_audit_sha256_verified=True,
        FileRef_content_hash_not_assumed_when_null=True,
        source_and_retained_artifact_hashes_do_not_prove_cache_reuse=True,
        owned_containers_observed_absent=2, new_methods_or_DAGs_run=0,
        current_resident_qualification=False, new_software_admissions=0,
        scientific_release_granted=False, g0_granted=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
