"""Reproduce legacy family publication/fallback defects using self-contained toy inputs."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '7c240cf387439f820ac07a72aa67deac6f0406ef'
SOURCE = 'plugins/frozen-b-project/scripts/project.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') or not os.environ.get('TMPDIR'):
        raise RuntimeError('Managed evidence and disposable scratch required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-b-family-transport'
    output.mkdir(mode=0o700)
    baseline = Path(os.environ['TMPDIR']) / 'legacy-family.py'
    baseline.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + SOURCE]))
    paths = [ROOT / SOURCE, ROOT / 'plugins/frozen-b-project/scripts/run-intake.py',
             ROOT / 'plugins/frozen-b-project/scripts/run-family.py',
             ROOT / 'tests/test_frozen_b_project.py', Path(__file__)]
    identities = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    code = '''
import importlib.util,json,sys,unittest
from tests import test_frozen_b_project as tests
if sys.argv[1] != 'CURRENT':
    spec=importlib.util.spec_from_file_location('legacy_family',sys.argv[1])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tests.project=module
    names=['test_failed_family_publication_removes_only_its_own_links',
           'test_successful_links_cannot_publish_replaced_or_modified_family',
           'test_family_requires_actual_official_adjustment_and_never_recomputes_missing_values']
    suite=unittest.TestSuite(tests.FrozenProjectTests(name) for name in names)
else:
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(tests.FrozenProjectTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))
with open(sys.argv[2],'x') as handle:json.dump(summary,handle,indent=2)
sys.exit(0 if result.wasSuccessful() else 1)
'''
    records = {}
    for label, source, expected in [('baseline', str(baseline), 1), ('repaired', 'CURRENT', 0)]:
        with (output / (label + '.stdout.log')).open('x') as stdout, (output / (label + '.stderr.log')).open('x') as stderr:
            result = subprocess.run([sys.executable, '-B', '-c', code, source, str(output / (label + '.json'))],
                                    cwd=ROOT, stdout=stdout, stderr=stderr, timeout=60)
        record = json.loads((output / (label + '.json')).read_text())
        if result.returncode != expected or record['skipped'] or record['errors']:
            raise RuntimeError('Unexpected toy test execution: ' + label)
        if label == 'baseline' and (record['tests_run'] != 3 or record['failures'] < 3):
            raise RuntimeError('All three legacy counterexample tests must actually fail')
        if label == 'repaired' and (record['tests_run'] != 12 or record['failures']):
            raise RuntimeError('All twelve fixed family contracts must execute')
        records[label] = dict(exit=result.returncode, **record)
    if identities != {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}:
        raise RuntimeError('Family source changed during proof')
    record = dict(status='FAMILY_MECHANICAL_TRANSPORT_REPAIRED_OFFICIAL_R_PRODUCER_AND_DAG_STILL_REQUIRED',
                  baseline_commit=BASELINE, baseline_source_sha256=digest(baseline), source_sha256=identities,
                  actual=records, synthetic_only=True, official_R_executed=False,
                  daemon_deployment_verified=False, scientific_authorization_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
