import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/pseudobulk'


class H5ADExportInterfaceTests(unittest.TestCase):
    def test_original_four_ports_and_parameters_remain(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        node = next(row for row in manifest['nodes'] if row['kind'] == 'h5ad_export_matrix')
        self.assertEqual(node['ports']['inputs'], [{'type': 'file'}])
        self.assertEqual([row['path'] for row in node['ports']['outputs']], ['x_matrix.long.parquet', 'obs.tsv', 'var.tsv', 'h5ad_export.log'])
        self.assertEqual(set(node['params']), {'layer', 'chunk'})
        self.assertEqual(node['params']['layer']['default'], 'X')
        self.assertEqual(node['params']['chunk']['default'], 2000)
        self.assertEqual(node['command']['script_file'], 'scripts/h5ad_export_matrix.py')

    def test_direct_official_selected_element_and_exact_values(self):
        source = (FAMILY / 'scripts/h5ad_export_matrix.py').read_text()
        ast.parse(source)
        self.assertIn('ad.io.read_elem', source)
        self.assertIn('ad.io.sparse_dataset', source)
        self.assertIn('represented exactly', source)
        self.assertIn('sparse integer sum exceeds the original storage dtype', source)
        self.assertNotIn('matrix loaded fully', source)
        self.assertNotIn('np.asarray(block, dtype=np.float64)', source)

    def test_publication_and_complete_metadata_diagnostics(self):
        source = (FAMILY / 'scripts/h5ad_export_matrix.py').read_text()
        self.assertIn('metadata_schema_json', source)
        self.assertIn('missing_rows', source)
        self.assertIn('os.path.lexists', source)
        self.assertIn('os.link(staging, target)', source)
        self.assertIn('os.path.samestat', source)
        self.assertIn('input H5AD changed during export', source)
        self.assertIn('NOT_VERIFIED', source)

    def test_required_actual_runtime_driver_has_no_skip(self):
        source = (FAMILY / 'tests/test_export_assurance.py').read_text()
        ast.parse(source)
        self.assertIn('PASS_COMPLETE_EXACT_EXPORT_AND_NEGATIVE_BOUNDARIES', source)
        self.assertIn('sparse-duplicate-cancellation', source)
        self.assertIn('second-link-rollback', source)
        self.assertIn('ad.read_h5ad(source)', source)
        self.assertIn('np.testing.assert_array_equal', source)
        self.assertNotIn('skip', source.lower())


if __name__ == '__main__':
    unittest.main()
