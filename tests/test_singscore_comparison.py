import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('singscore_comparison', Path(__file__).resolve().parents[1] / 'plugins/singscore/verify_scores.py')
COMPARISON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARISON)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.golden = self.root / 'gold.tsv'
        self.actual = self.root / 'actual.tsv'
        self.log = self.root / 'run.log'
        self.golden.write_text('sample\tTotalScore\n001\t0.25\nNA\t-0.125\n')
        self.actual.write_bytes(self.golden.read_bytes())
        self.log.write_text('official reference comparison\n')

    def verify(self):
        return COMPARISON.verify(self.golden, self.actual, self.log)

    def test_exact_lexical_sample_agreement(self):
        self.assertEqual(self.verify(), 2)

    def test_nan_is_rejected(self):
        self.actual.write_text('sample\tTotalScore\n001\tNaN\nNA\t-0.125\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_infinite_golden_is_rejected(self):
        self.golden.write_text('sample\tTotalScore\n001\tInf\nNA\t-0.125\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_sample_is_rejected(self):
        self.actual.write_text('sample\tTotalScore\n001\t9\n001\t0.25\nNA\t-0.125\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_extra_sample_is_rejected(self):
        self.actual.write_text(self.golden.read_text() + 'extra\t1\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_sample_is_rejected(self):
        self.actual.write_text('sample\tTotalScore\n001\t0.25\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_empty_tables_are_rejected(self):
        self.golden.write_text('sample\tTotalScore\n')
        self.actual.write_bytes(self.golden.read_bytes())
        with self.assertRaises(ValueError):
            self.verify()

    def test_frozen_tolerance_is_not_relaxed(self):
        self.actual.write_text('sample\tTotalScore\n001\t0.2500000001\nNA\t-0.125\n')
        with self.assertRaises(ValueError):
            self.verify()

    def test_empty_log_is_rejected(self):
        self.log.write_text('')
        with self.assertRaises(ValueError):
            self.verify()


if __name__ == '__main__':
    unittest.main(verbosity=2)
