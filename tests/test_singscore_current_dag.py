from pathlib import Path
import shutil
import tempfile
import unittest

from tools import prove_singscore_current_dag as proof
from tools.prove_singscore_graph_controls import missing_metadata_cause
from tools.prove_singscore_joined_readback import reference_path


class CurrentSingscoreDagTests(unittest.TestCase):
    def test_joined_readback_cannot_escape_or_invent_the_sealed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'actual.RDS').write_bytes(b'toy')
            self.assertEqual(reference_path('/work/actual.RDS',root),'/reference/actual.RDS')
            for value in ['/elsewhere/actual.RDS','/work/../actual.RDS','/work/missing.RDS']:
                with self.assertRaises(RuntimeError): reference_path(value,root)

    def test_missing_port_control_requires_the_exact_node_and_port_or_method_guard(self):
        self.assertTrue(missing_metadata_cause('Error: PortDisconnected { node: "analysis", port: 2 }'))
        self.assertTrue(missing_metadata_cause('All three declared input and output ports are required'))
        for value in ['PortDisconnected { node: "other", port: 2 }','PortDisconnected { node: "analysis", port: 1 }','generic input error 2']:
            self.assertFalse(missing_metadata_cause(value))

    def test_three_literal_inputs_no_parameters_and_no_panel_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'source'
            (source/'scripts').mkdir(parents=True)
            for name in ['manifest.toml','scripts/singscore.sh']:
                shutil.copyfile(proof.ROOT/'plugins/singscore'/name,source/name)
            job=proof.job_for(root,source)
            self.assertEqual(len(job['nodes']),4)
            self.assertEqual(len(job['edges']),3)
            self.assertEqual([edge['to_port'] for edge in job['edges']],[0,1,2])
            self.assertEqual(job['nodes'][-1]['spec'],{})
            self.assertEqual(job['bundles'],[])
            self.assertEqual(job['panel_overrides'],[])
            self.assertEqual(job['scope'],'TECHNICAL_PLUGIN_DAG_NOT_G0')

    def test_refusal_reference_requires_one_explicit_method_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            stderr=root/'node.stderr.txt'
            stderr.write_text('ERROR: exact contract violation\n')
            self.assertEqual(proof.expected_error(root),'ERROR: exact contract violation')
            for content in ['generic failure\n','ERROR: one\nERROR: two\n']:
                stderr.write_text(content)
                with self.assertRaises(RuntimeError): proof.expected_error(root)

    def test_changed_reference_seal_cannot_be_used_as_new_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'SEALED_FILES.json').write_text('[]\n')
            with self.assertRaises(RuntimeError): proof.reference(root)


if __name__=='__main__': unittest.main()
