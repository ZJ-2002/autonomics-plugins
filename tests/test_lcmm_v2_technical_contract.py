import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-lcmm'
specification = importlib.util.spec_from_file_location('lcmm_v2_fixtures', FAMILY / 'tests/test_technical_v2.py')
fixtures = importlib.util.module_from_spec(specification)
specification.loader.exec_module(fixtures)


class LcmmV2TechnicalContractTests(fixtures.TechnicalV2Tests):
    def test_ten_actual_r_guard_groups_without_fitting(self):
        self.assertIsNotNone(shutil.which('Rscript'), 'Missing R execution is not a pass')
        environment = {name: value for name, value in os.environ.items()
                       if name in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'R_LIBS', 'R_LIBS_USER', 'R_LIBS_SITE'}}
        result = subprocess.run(['Rscript', '--vanilla', str(FAMILY / 'tests/technical_v2_guards.R'),
                                 str(FAMILY / 'scripts/lcmm.R')], env=environment,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        groups = [int(line.split()[1]) for line in result.stdout.splitlines() if line.startswith('PASS ')]
        self.assertEqual(groups, list(range(1, 11)))


if __name__ == '__main__':
    unittest.main()
