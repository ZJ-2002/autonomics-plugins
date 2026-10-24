import unittest
import os
from pathlib import Path
import subprocess
import sys

from tools.prove_biorxiv_response_contract import baseline_with_explicit_transport_seam, listed_cases


class BiorxivResponseProofTests(unittest.TestCase):
    def test_absolute_cli_entry_does_not_require_repository_cwd_or_pythonpath(self):
        driver = Path(__file__).resolve().parents[1] / 'tools/prove_biorxiv_response_contract.py'
        environment = {name:value for name,value in os.environ.items() if name != 'PYTHONPATH'}
        result = subprocess.run([sys.executable,'-I','-B',str(driver),'--help'],cwd='/',
                                env=environment,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--engine-repository',result.stdout)

    def test_baseline_changes_only_constructor_and_url_not_response_handling(self):
        signature = '    async fn fetch_from_server(&self, server: &str, doi: &str) -> Result<Option<Article>> {'
        original = 'old-prefix\n' + signature + '\nformat!("https://api.biorxiv.org/details/{server}/{doi}");\nreturn Ok(None);'
        repaired = 'endpoint: String\npub fn with_endpoint(\n' + signature + '\nnew-parser'
        result = baseline_with_explicit_transport_seam(original, repaired)
        self.assertIn('endpoint: String\npub fn with_endpoint(', result)
        self.assertIn('format!("{}/{server}/{doi}", self.endpoint)', result)
        self.assertIn('return Ok(None);', result)
        self.assertNotIn('new-parser', result)

    def test_baseline_requires_exact_unique_original_boundary_and_url(self):
        for source in ['', 'fetch_from_server', 'replacement endpoint']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                baseline_with_explicit_transport_seam(source, source)

    def test_test_inventory_is_actual_nonempty_unique_and_complete(self):
        self.assertEqual(listed_cases('case_a: test\ncase_b: test\n\n2 tests, 0 benchmarks\n'), ['case_a', 'case_b'])
        for text in ['', '0 tests, 0 benchmarks\n', 'case_a: test\n2 tests, 0 benchmarks\n',
                     'case_a: test\ncase_a: test\n2 tests, 0 benchmarks\n',
                     'case_a: test\n1 test, 1 benchmark\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                listed_cases(text)
