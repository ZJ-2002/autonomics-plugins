import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from tools import prove_ucell_tsv_dag as proof
from tools.prove_ucell_tsv_failures import CASES


class UCellTsvRepairTests(unittest.TestCase):
    def test_exact_original_official_scoring_call_not_reimplemented(self):
        source = (proof.ROOT / 'plugins/ucell/scripts/ucell.R').read_text()
        call = re.search(r'  scores <- UCell::ScoreSignatures_UCell\(.*?chunk.size = 100\)', source, re.S).group()
        self.assertEqual(hashlib.sha256(call.encode()).hexdigest(), '7753d863082e755df4ced940e9fff6ef6a937e1adb43a2485e3b6fb0f1ccad63')
        self.assertNotIn('unlink(Sys.getenv', source)
        self.assertLess(source.index('Input and output paths must be distinct'), source.index('log_connection <- file('))

    def test_declared_twelve_parameter_branches_and_signature_cases_are_fixed(self):
        cases = proof.configurations()
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({case['name'] for case in cases}), 12)
        self.assertEqual({case['parameters']['max_rank'] for case in cases}, {1000, 1500, 2000})
        self.assertEqual({case['parameters']['missing_genes'] for case in cases}, {'skip', 'impute'})
        self.assertEqual({case['parameters']['negative_weight'] for case in cases}, {0, .5, 1, 2})
        self.assertTrue({'up-only', 'negative-only', 'reordered-cells', 'reordered-genes'} <= {case['name'] for case in cases})

    def test_toy_fixture_keeps_literal_axes_and_two_file_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof.fixture(root, 'main')
            self.assertEqual((root / 'matrix.tsv').read_text().splitlines()[0], 'gene\t0001\tNA\t炎症\tC4')
            source = proof.ROOT / 'plugins/ucell'
            parameters = proof.configurations()[0]['parameters']
            job = proof.job_for(root, source, parameters)
            self.assertEqual([node['kind'] for node in job['nodes']], ['file_reference', 'file_reference', 'cachexia_ucell_official'])
            self.assertEqual(job['nodes'][-1]['spec'], parameters)
            self.assertEqual(len(job['edges']), 2)
            self.assertEqual(job['panel_overrides'], [])

    def test_fault_inventory_includes_both_owned_and_unowned_rollback_cases(self):
        self.assertEqual(len(CASES), 16)
        self.assertEqual(len(set(CASES)), 16)
        self.assertTrue({'first-result-link-failure', 'second-result-link-failure', 'audit-link-failure',
                         'foreign-replacement', 'input-change', 'hardlinked-output', 'dangling-output'} <= set(CASES))

    def test_actual_scope_receipt_keeps_loss_reproduction_and_no_scientific_release(self):
        evidence = json.loads((proof.ROOT / 'evidence/ucell-tsv-io-repair-20261015.json').read_text())
        source = proof.ROOT / 'plugins/ucell/scripts/ucell.R'
        self.assertEqual(evidence['new_method_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(evidence['counts']['current_DAGs'], 13)
        self.assertEqual(evidence['counts']['path_regressions'], 3)
        self.assertEqual(evidence['counts']['specific_failure_cases'], 16)
        self.assertEqual(evidence['before']['status'], 'DATA_LOSS_REPRODUCED')
        self.assertTrue(all(case['damaged'] for case in evidence['before']['cases']))
        self.assertFalse(evidence['production_deployed'])
        self.assertFalse(evidence['g0_granted'])

    def test_family_contract_suite_is_actually_run_without_skips(self):
        path = proof.ROOT / 'plugins/ucell/tests/test_contract.py'
        spec = importlib.util.spec_from_file_location('ucell_family_contract_requalified', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        with contextlib.redirect_stderr(io.StringIO()):
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(result.testsRun, 3)
        self.assertTrue(result.wasSuccessful())
        self.assertFalse(result.skipped)


if __name__ == '__main__':
    unittest.main()
