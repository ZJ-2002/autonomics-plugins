import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'research-adapters/frozen-a-real-intake-bundle-v1/tests/test_bundle.py'
SPECIFICATION = importlib.util.spec_from_file_location('a_bundle_transport_fixtures', SOURCE)
fixtures = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(fixtures)


class BundleTransportTests(fixtures.BundleTests):
    pass


if __name__ == '__main__':
    unittest.main()
