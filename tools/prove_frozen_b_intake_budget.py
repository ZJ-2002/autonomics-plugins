"""Seal fixed-source intake counterexamples without real cohort data or containers."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '646ab3c22f4dfb2002138d1f2718ff47122a8538'
SOURCE = 'plugins/frozen-b-project/scripts/project.py'


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-b-intake-budget'
    output.mkdir(mode=0o700)
    baseline = Path(os.environ['TMPDIR']) / 'intake-baseline.py'
    baseline.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + SOURCE]))
    phase = sys.argv[1]
    if phase not in ['baseline', 'repaired']:
        raise RuntimeError('Explicit baseline or repaired phase required')
    code = '''
import importlib.util,json,sys,unittest
from tests import test_frozen_b_intake_budget as tests
if sys.argv[1] != 'CURRENT':
    spec=importlib.util.spec_from_file_location('intake_baseline',sys.argv[1])
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    tests.project=source
suite=unittest.defaultTestLoader.loadTestsFromTestCase(tests.FrozenIntakeBudgetTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
with open(sys.argv[2],'x') as handle:
    json.dump(dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)),handle,indent=2)
sys.exit(0 if result.wasSuccessful() else 1)
'''
    source = str(baseline) if phase == 'baseline' else 'CURRENT'
    files = [ROOT / SOURCE, ROOT / 'tests/test_frozen_b_intake_budget.py', Path(__file__)]
    identities = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        result = subprocess.run([sys.executable, '-B', '-c', code, source, str(output / 'tests.json')],
                                cwd=ROOT, stdout=stdout, stderr=stderr, timeout=60)
    record = json.loads((output / 'tests.json').read_text())
    expected = dict(tests_run=5, failures=3, errors=1, skipped=0) if phase == 'baseline' else dict(tests_run=5, failures=0, errors=0, skipped=0)
    if record != expected or result.returncode != (1 if phase == 'baseline' else 0):
        raise RuntimeError('Unexpected counterexample execution: ' + json.dumps(record))
    if identities != {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}:
        raise RuntimeError('Source changed during proof')
    verification = dict(phase=phase, baseline_commit=BASELINE, baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        source_sha256=identities, execution=record, synthetic_only=True, containers_executed=False,
        production_changed=False, scientific_authorization_granted=False, g0_granted=False,
        memory_peak_measured=False, budget_contract_not_an_oom_guarantee=True)
    (output / 'VERIFICATION.json').write_text(json.dumps(verification, indent=2) + '\n')


if __name__ == '__main__':
    main()
