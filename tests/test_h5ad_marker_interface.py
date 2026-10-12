import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/single-cell'


class H5ADMarkerInterfaceTests(unittest.TestCase):
    def test_original_five_parameters_and_two_ports(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        node = next(row for row in manifest['nodes'] if row['kind'] == 'h5ad_marker_annotate')
        self.assertEqual(len(node['ports']['inputs']), 1)
        self.assertEqual([row['path'] for row in node['ports']['outputs']], ['output.h5ad', 'report.json'])
        self.assertEqual(set(node['params']), {'marker_sets', 'groupby', 'normalize', 'min_score', 'unknown_label'})
        self.assertEqual(node['command']['script_file'], 'scripts/marker_annotate.py')

    def test_custom_method_identity_multiplicity_and_publication_guards(self):
        source = (FAMILY / 'scripts/marker_annotate.py').read_text()
        ast.parse(source)
        self.assertIn('NOT_APPLICABLE_CUSTOM_ARITHMETIC_RULE', source)
        self.assertIn('effective_weights', source)
        self.assertIn('duplicate JSON key', source)
        self.assertIn('destination.lstat()', source)
        self.assertIn('input changed during marker output staging', source)
        self.assertIn('np.where(fallback, own_top', source)
        self.assertNotIn('maxima = matrix.max', source)

    def test_independent_math_and_real_boundary_tests_do_not_skip(self):
        reference = (FAMILY / 'tests/marker_reference.py').read_text()
        self.assertIn('Decimal', reference)
        self.assertIn('context.prec = 100', reference)
        self.assertIn('is_relative_to(prefix)', reference)
        tests = (FAMILY / 'tests/test_marker_assurance.py').read_text()
        self.assertIn('assert result.returncode != 0', tests)
        self.assertIn('repeat-members-retained', tests)
        self.assertIn('replacement-symlink-rollback', tests)
        self.assertNotIn('skip', tests.lower())


if __name__ == '__main__':
    unittest.main()
