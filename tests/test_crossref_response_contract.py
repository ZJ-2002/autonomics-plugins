import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools.prove_crossref_response_contract import validate_execution


class CrossrefResponseProofTests(unittest.TestCase):
    def test_absolute_cli_entry_does_not_require_repository_cwd_or_pythonpath(self):
        driver=Path(__file__).resolve().parents[1]/'tools/prove_crossref_response_contract.py'
        environment={name:value for name,value in os.environ.items() if name!='PYTHONPATH'}
        result=subprocess.run([sys.executable,'-I','-B',str(driver),'--help'],cwd='/',env=environment,
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--engine-repository',result.stdout)

    def test_exact_regression_failures_remain_distinct_from_a_repaired_pass(self):
        text='test a ... FAILED\ntest b ... FAILED\ntest result: FAILED. 0 passed; 2 failed; 0 ignored;'
        self.assertEqual(validate_execution(text,['a','b'],expected_failure=True)['failed'],2)
        text='test a ... ok\ntest b ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored;'
        self.assertEqual(validate_execution(text,['a','b'])['passed'],2)

    def test_missing_duplicate_ignored_or_unexpected_test_cases_cannot_qualify(self):
        for text,names in [
            ('test a ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored;',['a','b']),
            ('test a ... ok\ntest a ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored;',['a','b']),
            ('test a ... ignored\ntest result: ok. 0 passed; 0 failed; 1 ignored;',['a']),
            ('test a ... FAILED\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;',['a']),
        ]:
            with self.subTest(text=text),self.assertRaises((ValueError,RuntimeError)):
                validate_execution(text,names)
