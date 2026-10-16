import argparse
import json
import os
from pathlib import Path
import sys
import unittest

# Imports and nested test processes must not dirty canonical plugin sources.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.catalog import ROOT, check_lock


class EvidenceResult(unittest.TextTestResult):
    def startTest(self, test):
        self.executed.append(test.id())
        super().startTest(test)

    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.executed = []


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    managed = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    parser.add_argument('--output', type=Path, required=managed is None,
                        default=Path(managed) / 'SOURCE_CHECKS.json' if managed else None)
    arguments = parser.parse_args()
    required = json.loads((ROOT / 'quality/required-tests.json').read_text())['test_ids']
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    complete = bool(required) and sorted(result.executed) == sorted(required) and not result.skipped
    source_catalog = {}
    source_error = None
    try:
        source_catalog = check_lock(ROOT)
    except (OSError, ValueError, KeyError) as error:
        source_error = str(error)
    report = dict(required_test_ids=required, executed_test_ids=result.executed, tests_run=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                  complete=complete, source_lock_matches=source_error is None, source_error=source_error,
                  canonical_families=source_catalog.get('canonical_families'),
                  canonical_kinds=source_catalog.get('canonical_kinds'), scientific_certified=False, G0=False)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    if source_error is not None or not complete or not result.wasSuccessful():
        sys.exit(1)
