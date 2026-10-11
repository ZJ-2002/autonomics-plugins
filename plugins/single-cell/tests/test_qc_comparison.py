"""Exact integer comparison must not collapse differences above 2**53."""

import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import compare_value


class ExactIntegerComparisonTests(unittest.TestCase):
    def test_dense_unit_difference_above_float64_exact_range(self):
        with self.assertRaises(AssertionError):
            compare_value(np.array([2**53], dtype=np.int64), np.array([2**53 + 1], dtype=np.int64))

    def test_sparse_unit_difference_above_float64_exact_range(self):
        with self.assertRaises(AssertionError):
            compare_value(sparse.csr_matrix(np.array([[2**53]], dtype=np.int64)),
                          sparse.csr_matrix(np.array([[2**53 + 1]], dtype=np.int64)))

    def test_dataframe_unit_difference_above_float64_exact_range(self):
        with self.assertRaises(AssertionError):
            compare_value(pd.DataFrame({"total_counts": np.array([2**53], dtype=np.int64)}),
                          pd.DataFrame({"total_counts": np.array([2**53 + 1], dtype=np.int64)}))


if __name__ == "__main__":
    output = Path(sys.argv[1])
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExactIntegerComparisonTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "integer_payloads_checked_exactly": True, "G0": False}
    with output.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    if result.testsRun != 3 or result.skipped or not result.wasSuccessful():
        raise SystemExit(1)
