import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'research-adapters/frozen-a-real-intake-bundle-v1/tests/test_scale_boundaries.py'
SPECIFICATION = importlib.util.spec_from_file_location('a_bundle_scale_boundary_fixtures', SOURCE)
fixtures = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(fixtures)


class BundleScaleBoundaryTests(fixtures.BundleBoundaryTests):
    pass


if __name__ == '__main__':
    unittest.main()
