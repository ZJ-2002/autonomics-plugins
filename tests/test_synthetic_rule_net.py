"""Run the shipped synthetic-only reference tests; no scientific admission."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research-adapters/synthetic-rule-net/scripts"


class SyntheticRuleNetTests(unittest.TestCase):
    def test_original_synthetic_regressions(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "test_synthetic.py")],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TOTAL 53 checks, 0 failed", result.stdout)

    def test_semantic_counterexamples(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "test_semantics.py")],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 12 tests", result.stderr)
        self.assertIn("OK", result.stderr)
