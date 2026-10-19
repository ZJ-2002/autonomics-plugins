import hashlib
import importlib.util
import inspect
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSEMBLY = ROOT / 'research-adapters/frozen-a-family-assembly'
ADJUSTMENT = ROOT / 'research-adapters/frozen-a-family-adjustment'
SPEC = importlib.util.spec_from_file_location('iut_frozen_family_binding', ASSEMBLY / 'scripts/family.py')
FAMILY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FAMILY)


class IutReuseBindingTests(unittest.TestCase):
    def test_exact_previously_repaired_assembly_and_adjustment_sources(self):
        for filename, expected in (
            (ASSEMBLY / 'manifest.toml', 'a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf'),
            (ASSEMBLY / 'scripts/family.py', '338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a'),
            (ADJUSTMENT / 'manifest.toml', '55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da'),
            (ADJUSTMENT / 'scripts/adjust.R', 'debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412')):
            self.assertEqual(hashlib.sha256(filename.read_bytes()).hexdigest(), expected)

    def test_complete_frozen_denominators_remain_276_edges_288_paths(self):
        self.assertEqual(FAMILY.COUNTS, {'A_PRIMARY_EDGES': 88, 'A_EXPANDED_EDGES': 188, 'A_PRIMARY_PATHS': 36, 'A_EXPANDED_PATHS': 252})
        self.assertEqual(sum(value for key, value in FAMILY.COUNTS.items() if key.endswith('EDGES')), 276)
        self.assertEqual(sum(value for key, value in FAMILY.COUNTS.items() if key.endswith('PATHS')), 288)
        self.assertEqual(len(FAMILY.SOURCES), 9)

    def test_strict_iut_does_not_silently_remove_missing_components(self):
        source = inspect.getsource(FAMILY.assemble)
        self.assertIn('Strict IUT must propagate missing components', source)
        self.assertIn('None if first is None or second is None else max(first, second)', source)
        self.assertIn('MISSING_COMPONENT', source)

    def test_loader_executes_the_verified_buffer_without_reopening(self):
        source = inspect.getsource(FAMILY.helpers)
        self.assertIn('payload = read(path, expected_size=SOURCES[7][1])', source)
        self.assertIn('checksum(payload) == SOURCES[7][2]', source)
        self.assertIn('exec(compile(payload, str(path)', source)
        self.assertNotIn('SourceFileLoader', source)

    def test_replacement_is_explicit_not_native_boolean_alias(self):
        nodes = tomllib.loads((ASSEMBLY / 'manifest.toml').read_text())['nodes']
        self.assertEqual({item['kind'] for item in nodes}, {'frozen_a_family_assemble', 'frozen_a_family_publish'})
        self.assertEqual([len(item['ports']['inputs']) for item in nodes], [10, 8])
        self.assertTrue(all(len(item['ports']['outputs']) == 4 for item in nodes))
        self.assertEqual(FAMILY.FUNCTIONS, ['primary_p', 'strict_conjunction', 'assert_locked_ids'])


if __name__ == '__main__':
    unittest.main()
