"""Self-cleaning synthetic contracts for the two publication-repair DAG driver."""

import ast
import hashlib
import json
import os
import sys
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import prove_b_publication_dag as proof


class BPublicationDAGTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def family(self, label):
        directory = self.root / ('source-' + label)
        directory.mkdir()
        pseudobulk = label == 'pseudobulk'
        manifest = dict(plugin_name='pseudobulk' if pseudobulk else 'single-cell',
            image=dict(reference=proof.runtime.PB_IMAGE if pseudobulk else proof.runtime.subset.IMAGE))
        return dict(source=directory, manifest=manifest,
            definition=dict(kind=proof.METHODS[label]),
            identities={'manifest.toml': dict(sha256='a' * 64),
                'scripts/method.py': dict(sha256='b' * 64)})

    def binding_fixture(self, linked=False):
        work = self.root / 'graph'
        work.mkdir()
        source = work / 'input.h5ad'
        source.write_bytes(b'SYNTHETIC_IO_ONLY_NOT_H5AD')
        scratch = self.root / 'scratch'
        staged = scratch / '.autonomics/inputs/input-0.h5ad'
        staged.parent.mkdir(parents=True)
        if linked:
            staged.symlink_to(source)
        else:
            staged.write_bytes(source.read_bytes())
        method = dict(inputs=[dict(from_port=0, to_port=0, path='vfs:///input.h5ad',
            fingerprint=dict(size=source.stat().st_size,
                content_hash='sha256:' + hashlib.sha256(source.read_bytes()).hexdigest()))])
        method['inputs'][0]['from'] = 'input'
        return work, method, scratch, staged

    def test_exact_runtime_and_fixed_source_identities_are_pinned(self):
        self.assertEqual(proof.DIRECT_SESSION, '3916f488e09e4ded99b39890cfc4cf68')
        self.assertEqual(proof.DIRECT_SEAL, '001806a1bd052088aefe6e663624c6b859d6252b8b839779e45569f332f568ef')
        self.assertEqual(proof.runtime.PINNED['plugins/pseudobulk/scripts/pseudobulk_counts.py'],
                         'd1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109')
        self.assertEqual(proof.runtime.PINNED['plugins/single-cell/scripts/score_genes.py'],
                         'dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774')
        self.assertEqual(proof.admission.PARENT, '11f061589473cb8e4fa57d364ad7107108245de1')
        self.assertEqual(len(proof.admission.GUARDS), 23)

    def test_pseudobulk_job_keeps_two_nodes_one_edge_and_legal_method_refusal(self):
        family = self.family('pseudobulk')
        job = proof.wire_job(proof.job_for(self.root, family))
        self.assertEqual(job['scope'], 'TECHNICAL_PLUGIN_DAG_NOT_G0')
        self.assertEqual([node['kind'] for node in job['nodes']], ['file_reference', 'pseudobulk_counts'])
        self.assertEqual(job['edges'], [{'from': 'input', 'from_port': 0, 'to': 'analysis', 'to_port': 0}])
        self.assertEqual(job['nodes'][1]['spec']['min_cells'], 1)
        negative = proof.job_for(self.root, family, negative=True)
        self.assertEqual(negative['nodes'][1]['spec']['condition_column'], 'TECHNICAL_MISSING_CONDITION')
        self.assertEqual(negative['nodes'][1]['spec']['min_cells'], 1)
        self.assertEqual(job['panel_overrides'], [])
        self.assertEqual(job['bundles'], [])

    def test_scoring_job_retains_original_parameters_and_explicit_nonmodel_override(self):
        family = self.family('score')
        work = self.root / 'score'
        work.mkdir()
        job = proof.wire_job(proof.job_for(work, family))
        self.assertEqual(json.loads(job['nodes'][1]['spec']['gene_sets']), {'score': ['G0', 'G1']})
        self.assertEqual(job['nodes'][1]['spec']['ctrl_size'], 50)
        self.assertEqual(job['nodes'][1]['spec']['random_state'], 0)
        self.assertEqual(job['panel_overrides'][0]['synthetic_bundle'], proof.PANEL_ID)
        self.assertEqual(job['panel_overrides'][0]['mount'], '/panels/celltypist_model')
        self.assertIn('NONMODEL', job['bundles'][0]['desc'])
        self.assertFalse(any(path.suffix == '.pkl' for path in work.rglob('*')))

    def test_scoring_refusal_selects_all_present_genes_not_invalid_parameter_preflight(self):
        work = self.root / 'negative'
        work.mkdir()
        job = proof.job_for(work, self.family('score'), negative=True)
        self.assertEqual(json.loads(job['nodes'][1]['spec']['gene_sets']),
                         {'score': ['G' + str(index) for index in range(100)]})
        self.assertEqual(job['nodes'][1]['spec']['ctrl_size'], 50)

    def test_unused_panel_manifest_and_payload_are_complete_and_hash_bound(self):
        bundle, hashes = proof.panel_fixture(self.root)
        directory = self.root / proof.PANEL_VPATH.lstrip('/')
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertEqual(manifest['id'], bundle['ident'])
        self.assertEqual(manifest['digest'], bundle['digest'])
        self.assertEqual([row['path'] for row in manifest['files']], ['NOT_A_MODEL.txt'])
        self.assertEqual((directory / 'NOT_A_MODEL.txt').read_bytes(), proof.PANEL_PAYLOAD)
        self.assertIn(b'THIS IS NOT A CELLTYPIST MODEL', proof.PANEL_PAYLOAD)
        self.assertEqual(hashes, {proof.PANEL_VPATH: hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()})

    def test_regular_staging_retains_exact_owned_input_bytes_and_role(self):
        work, method, scratch, staged = self.binding_fixture()
        result = proof.checked_input(work, method, scratch)
        self.assertEqual(result['mode'], 'REGULAR_BYTE_COPY')
        self.assertEqual(result['sha256'], hashlib.sha256(staged.read_bytes()).hexdigest())

    def test_default_symlink_staging_is_only_the_same_owned_input_target(self):
        work, method, scratch, staged = self.binding_fixture(linked=True)
        self.assertEqual(proof.checked_input(work, method, scratch)['mode'], 'EXACT_OWNED_SOURCE_SYMLINK')
        other = work / 'other.h5ad'
        other.write_bytes((work / 'input.h5ad').read_bytes())
        staged.unlink()
        staged.symlink_to(other)
        with self.assertRaises(ValueError):
            proof.checked_input(work, method, scratch)

    def test_wrong_role_port_hash_or_staged_bytes_cannot_pass_binding(self):
        work, method, scratch, staged = self.binding_fixture()
        for field, replacement in [('to_port', 1), ('from', 'other'), ('path', 'vfs:///other.h5ad')]:
            changed = json.loads(json.dumps(method))
            changed['inputs'][0][field] = replacement
            with self.assertRaises(ValueError):
                proof.checked_input(work, changed, scratch)
        staged.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            proof.checked_input(work, method, scratch)

    def test_original_manifest_resources_are_not_weakened_by_the_driver(self):
        pseudobulk = tomllib.loads((proof.ROOT / 'plugins/pseudobulk/manifest.toml').read_text())
        score = tomllib.loads((proof.ROOT / 'plugins/single-cell/manifest.toml').read_text())
        first = next(node for node in pseudobulk['nodes'] if node['kind'] == 'pseudobulk_counts')
        second = next(node for node in score['nodes'] if node['kind'] == 'gene_set_score')
        self.assertEqual((first['resources']['cpus'], first['resources']['memory']), (4, '8g'))
        self.assertEqual((second['resources']['cpus'], second['resources']['memory']), (2.0, '8Gi'))
        self.assertNotIn('stage_in_mode', first)
        self.assertNotIn('stage_in_mode', second)

    def test_whole_object_comparator_uses_pinned_existing_prefix_not_qc_report_contract(self):
        self.assertEqual(proof.fact(proof.comparator_source())['sha256'], proof.QC_SHA)
        ast.parse(proof.COMPARATOR)
        self.assertIn('compare.body[:boundary]', proof.COMPARATOR)
        self.assertIn('target.id=="report"', proof.COMPARATOR)
        self.assertIn('WHOLE_H5AD_TRANSPORT_COMPARISON_NOT_QC_REEVALUATION', proof.COMPARATOR)
        self.assertIn('whole_AnnData_and_HDF5_checked', proof.COMPARATOR)

    def test_comparator_writes_real_json_newline_not_a_literal_escape(self):
        source = ast.parse(proof.COMPARATOR)
        final_statement = source.body[-1]
        namespace = dict(root=self.root, json=json, result=dict(whole_AnnData_and_HDF5_checked=True))
        exec(compile(ast.Module(body=[final_statement], type_ignores=[]), 'toy-comparator-write', 'exec'), namespace)
        raw = (self.root / 'whole-object-comparison.json').read_bytes()
        self.assertTrue(raw.endswith(b'\n'))
        self.assertFalse(raw.endswith(b'\\n'))
        self.assertTrue(json.loads(raw)['whole_AnnData_and_HDF5_checked'])

    def test_default_launcher_records_only_actual_constraints_and_original_managed_backend(self):
        shim = self.root / 'managed-shim'
        shim.write_text('SYNTHETIC_NOT_EXECUTED')
        output = self.root / 'output'
        output.mkdir()
        temporary = self.root / 'tmp'
        temporary.mkdir()
        with mock.patch.dict(os.environ, {'AUTONOMICS_PODMAN_PROGRAM': str(shim)}):
            record = proof.default_launcher([str(shim), '--cgroup-manager=cgroupfs'], temporary, output)
            command = ['podman', 'create', '--name', 'toy-run', '--cpus', '2', '--memory', '8Gi',
                '--mount', 'type=bind,source=/toy,destination=/panels/celltypist_model,readonly',
                '--env', 'SYNTHETIC_NOT_A_SECRET=value']
            with mock.patch.object(sys, 'argv', command), mock.patch.object(os, 'execv') as execute:
                exec(compile(record[2].read_text(), str(record[2]), 'exec'), {})
            execute.assert_called_once_with(str(shim), [str(shim), '--cgroup-manager=cgroupfs', *command[1:]])
        rows = (output / 'actual-container-create.jsonl').read_text().splitlines()
        self.assertEqual(len(rows), 1)
        observed = json.loads(rows[0])
        self.assertEqual(observed['name'], 'toy-run')
        self.assertEqual(observed['memory'], '8Gi')
        self.assertEqual(len(observed['panel_mounts']), 1)
        self.assertNotIn('SYNTHETIC_NOT_A_SECRET', rows[0])

    def test_failed_direct_seal_is_rejected_before_private_reference_access(self):
        with mock.patch.object(proof, 'DIRECT_SESSION', 'PENDING'):
            with self.assertRaises(ValueError):
                proof.checked_direct(self.root)

    def test_real_executable_copy_abi_returns_path_and_original_identity_not_tuple_argv(self):
        original = self.root / 'sealed-runner'
        original.write_bytes(b'SYNTHETIC_EXECUTABLE_BYTES_NOT_EXECUTED')
        temporary = self.root / 'runner-copy'
        temporary.mkdir()
        expected = proof.admission.file_identity(original)
        executable, identity = proof.copy_runner(original, temporary)
        self.assertIsInstance(executable, Path)
        self.assertEqual(executable, temporary / 'official_plugin_dag')
        self.assertEqual(identity, expected)
        self.assertEqual(executable.read_bytes(), original.read_bytes())
        self.assertEqual(proof.admission.file_identity(original), expected)
        self.assertEqual(executable.stat().st_mode & 0o777, 0o700)


if __name__ == '__main__':
    unittest.main()
