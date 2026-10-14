import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from tools import build_frozen_a_project_dag as graph

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/twosamplemr-v432-a'


class FrozenAProjectDagTests(unittest.TestCase):
    def test_graph_binds_the_fixed_five_hash_enabled_inputs_in_method_port_order(self):
        request = graph.build()
        self.assertEqual(set(request), {'script', 'dry_run', 'timeout_ms'})
        self.assertTrue(request['dry_run'])
        self.assertEqual(request['timeout_ms'], 5000)
        script = request['script']
        self.assertEqual(script.count('node('), 6)
        self.assertEqual(script.count('edge('), 5)
        self.assertEqual(script.count('hash_content: true'), 5)
        self.assertIn('node("frozen_a_mr", "' + graph.METHOD_KIND + '", #{});', script)
        for port, (name, uri) in enumerate(graph.INPUTS):
            self.assertIn(json.dumps(uri), script)
            self.assertIn(f'edge("frozen_a_{name}", 0, "frozen_a_mr", {port});', script)
            self.assertTrue(uri.startswith('vfs://'))
        self.assertEqual([uri.rsplit('/', 1)[1] for _, uri in graph.INPUTS], [
            'A_FROZEN_EXPLORATORY_INPUT.tsv', 'A_ANALYSIS_CONFIG.json',
            'G0_V432_CERTIFICATE.json', 'R_DEPENDENCY_LOCK.tsv', 'frozen-method-proof.json'])
        self.assertTrue(script.endswith('commit();\n'))
        for invented in ['output_dir:', 'artifact_prefix:', 'file_transform', 'run_dag(', '/home/']:
            self.assertNotIn(invented, script)

    def test_method_manifest_declares_actual_r_entry_and_all_nine_outputs(self):
        manifest = tomllib.loads((PLUGIN / 'manifest.toml').read_text())
        node = manifest['nodes'][0]
        self.assertEqual(graph.METHOD_KIND, manifest['plugin_name'] + '/' + node['kind'])
        self.assertEqual(len(node['ports']['inputs']), 5)
        self.assertEqual(len(node['ports']['outputs']), 9)
        self.assertEqual([p['path'] for p in node['ports']['outputs']], [
            'ALL_METHODS_EXPLORATORY.tsv', 'HETEROGENEITY.tsv', 'EGGER_INTERCEPT.tsv',
            'ALL_LEAVE_ONE_OUT.tsv', 'ALL_REGION_SENSITIVITIES.tsv', 'QUALIFIED_INPUT.tsv',
            'twosamplemr_v432_a.RDS', 'twosamplemr_v432_a.log', 'INPUT_METHOD_PROVENANCE.json'])
        source = (PLUGIN / node['command']['script_file']).read_text()
        self.assertEqual(node['command']['interpreter'], 'Rscript')
        self.assertIn('packageVersion("TwoSampleMR")) == "0.7.11"', source)
        self.assertIn('getRversion()) == "4.6.1"', source)
        self.assertIn('TwoSampleMR::mr(h, method_list = methods)', source)
        self.assertEqual(node['artifact_prefix'], '/artifacts/twosamplemr_v432_a_exploratory')
        self.assertEqual(node.get('params', {}), {})

    def test_prefix_is_the_only_graph_customization_and_cannot_inject_script(self):
        script = graph.build('a_review_2')['script']
        self.assertIn('node("a_review_2_mr"', script)
        for bad in ['', '2a', '../a', 'a-b', 'a"; commit();', 'a' * 62]:
            with self.assertRaises(ValueError):
                graph.build(bad)

    def test_cli_creates_request_exclusively_without_opening_study_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'request.json'
            command = [sys.executable, '-B', str(ROOT / 'tools/build_frozen_a_project_dag.py'),
                       '--output', str(output)]
            subprocess.run(command, check=True, capture_output=True)
            before = output.read_bytes()
            self.assertEqual(json.loads(before), graph.build())
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
