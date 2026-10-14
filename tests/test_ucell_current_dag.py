import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import prove_ucell_current_dag as proof
from tools.prove_ucell_graph_controls import exact_cause


class CurrentUCellDagTests(unittest.TestCase):
    def test_graph_controls_require_the_exact_node_parameter_and_port(self):
        self.assertTrue(exact_cause('unknown-parameter', 'node `h5ad_ucell_score`: unknown param `unexpected_free_parameter`'))
        self.assertTrue(exact_cause('missing-input-edge', 'PortDisconnected { node: "analysis", port: 0 }'))
        for name, message in [('unknown-parameter', 'unknown param elsewhere'),
                              ('missing-input-edge', 'PortDisconnected { node: "other", port: 0 }'),
                              ('missing-input-edge', 'PortDisconnected { node: "analysis", port: 1 }'),
                              ('unrecognized-case', 'PortDisconnected { node: "analysis", port: 0 }')]:
            self.assertFalse(exact_cause(name, message))

    def test_literal_h5ad_input_and_parameter_have_no_native_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            (source / 'scripts').mkdir(parents=True)
            for name in ['manifest.toml', 'scripts/score.py']:
                shutil.copyfile(proof.ROOT / 'plugins/ucell-h5ad' / name, source / name)
            settings = {'gene_sets': '{"one":["A+","B-"]}'}
            job = proof.job_for(root, source, settings)
            self.assertEqual([node['kind'] for node in job['nodes']], ['file_reference', 'h5ad_ucell_score'])
            self.assertEqual(job['nodes'][1]['spec'], settings)
            self.assertEqual(job['nodes'][0]['spec']['format'], 'h5ad')
            self.assertEqual(len(job['edges']), 1)
            self.assertEqual(job['bundles'], [])
            self.assertEqual(job['panel_overrides'], [])

    def test_boundary_json_keeps_invalid_and_signed_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'request.json').write_text('{"original":["A"]}')
            self.assertEqual(proof.settings_for('missing-gene-sets', root), {})
            self.assertEqual(proof.settings_for('duplicate-json-key', root)['gene_sets'], '{"one":["A"],"one":["B"]}')
            self.assertEqual(proof.settings_for('malformed-json', root)['gene_sets'], 'not JSON')
            for name, value in [('ambiguous-sign', {'one': ['A+', 'A-']}), ('numeric-member', {'one': [1]}),
                                ('undefined-official-score', {'one': ['A']}), ('empty-programs', {})]:
                self.assertEqual(json.loads(proof.settings_for(name, root)['gene_sets']), value)

    def test_frozen_refusal_requires_one_specific_method_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            filename = root / 'declared-node-script.stderr.txt'
            filename.write_text('h5ad_ucell_score: refusing to overwrite existing output: /old/output.h5ad\n')
            self.assertEqual(proof.expected_error(root), 'h5ad_ucell_score: refusing to overwrite')
            for value in ['generic stderr', 'h5ad_ucell_score: one\nh5ad_ucell_score: two\n']:
                filename.write_text(value)
                with self.assertRaises(RuntimeError):
                    proof.expected_error(root)

    def test_direct_fault_and_filesystem_cases_are_not_counted_as_DAGs(self):
        self.assertEqual(proof.DIRECT, {'h5ad-exists', 'report-exists', 'dangling-output', 'output-alias',
                                       'input-overwrite', 'second-link-failure', 'R-failure'})

    def test_changed_reference_seal_is_not_accepted_as_new_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'SEALED_FILES.json').write_text('{}')
            with self.assertRaises(RuntimeError):
                proof.reference(root)


if __name__ == '__main__':
    unittest.main()
