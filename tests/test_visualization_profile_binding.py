from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/visualization'
PROFILE_IMAGE = 'ghcr.io/zj-2002/visualization@sha256:8f31b667355a7b3ab0fbabdac49e1c5c7f91ab81b560564efdddb3d7d59f94d6'


class VisualizationProfileBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.node = self.manifest['nodes'][0]
        self.script = (FAMILY / self.node['command']['script_file']).read_text()

    def test_exact_previously_qualified_runtime_profile(self):
        self.assertEqual(self.manifest['image']['reference'], PROFILE_IMAGE)

    def test_terminal_is_execution_metadata(self):
        self.assertEqual(len(self.manifest['nodes']), 1)
        self.assertEqual(self.node['kind'], 'visualization')
        self.assertIs(self.node['terminal'], True)

    def test_file_ports_and_single_png_are_unchanged(self):
        self.assertEqual(self.node['ports'], {
            'inputs': [{'type': 'file', 'label': 'data'}, {'type': 'file', 'label': 'r_script'}],
            'outputs': [{'path': 'plot.png', 'format': 'png'}],
        })

    def test_dimensions_and_required_encoding_contract(self):
        params = self.node['params']
        self.assertEqual(set(params), {'data_format', 'width', 'height', 'dpi'})
        self.assertEqual(params['data_format']['type'], 'string')
        self.assertNotIn('default', params['data_format'])
        for name, expected in [('width', 8.0), ('height', 6.0), ('dpi', 150.0)]:
            self.assertEqual(params[name]['type'], 'number')
            self.assertEqual(params[name]['default'], expected)
            self.assertEqual(params[name]['exclusive_min'], 0.0)

    def test_resources_interpreter_and_bindings_are_unchanged(self):
        self.assertEqual(self.node['resources'], {'cpus': 2.0, 'memory': '2Gi', 'pids_limit': 256})
        self.assertEqual(self.node['command']['interpreter'], 'Rscript')
        self.assertEqual(self.node['command']['env'], {
            'AUTONOMICS_VISUALIZATION_DATA_FORMAT': '{{ data_format }}',
            'AUTONOMICS_VISUALIZATION_WIDTH': '{{ width }}',
            'AUTONOMICS_VISUALIZATION_HEIGHT': '{{ height }}',
            'AUTONOMICS_VISUALIZATION_DPI': '{{ dpi }}',
        })

    def test_all_five_qualified_readers_remain(self):
        for name, reader in [('csv', 'read_csv_arrow'), ('tsv', 'read_tsv_arrow'), ('parquet', 'read_parquet'), ('arrow_stream', 'read_ipc_stream'), ('arrow_file', 'read_feather')]:
            self.assertIn(name + ' = arrow::' + reader + '(data_path, as_data_frame = TRUE)', self.script)

    def test_assignment_namespace_and_layer_operators_have_base_parent(self):
        self.assertIn('script_env <- new.env(parent = baseenv())', self.script)
        self.assertNotIn('parent = emptyenv()', self.script)
        self.assertIn('script_env$df <- df', self.script)
        self.assertIn('source(script_path, local = script_env)', self.script)

    def test_trusted_script_scope_does_not_claim_a_sandbox(self):
        self.assertIn('operator-reviewed frozen script', self.node['doc'])
        self.assertIn('not an', self.node['doc'])
        self.assertIn('arbitrary-code security sandbox', self.node['doc'])


if __name__ == '__main__':
    unittest.main()
