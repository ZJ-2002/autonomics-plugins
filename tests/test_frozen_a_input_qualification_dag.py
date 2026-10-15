import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import prove_frozen_a_input_qualification_dag as proof


class FrozenAInputQualificationDAGTests(unittest.TestCase):
    def setUp(self):
        self.job = proof.job_for(Path('/owned/positive'), Path('/owned/source'))
        self.build = dict(engine_commit='b' * 40)

    def report(self):
        panel = dict(host_source=str(proof.PANEL_HOST), manifest_sha256=proof.PANEL_MANIFEST,
            digest=proof.PANEL_DIGEST, catalog_bundle=proof.PANEL_ID,
            payload_files=[dict(path=f'1000G.EUR.QC.{chromosome}.{suffix}', bytes=1, sha256='sha256:' + '0' * 64,
                device=1, inode=chromosome) for chromosome in range(1, 23) for suffix in ['bed', 'bim', 'fam']])
        nodes = [dict(id=node['id'], node_type=node['kind'], status='success', reused=False,
            port_assignments={}, execution=dict(exit_code=0, image=proof.direct.IMAGE,
                image_digest=proof.direct.IMAGE.split('@', 1)[1])) for node in self.job['nodes']]
        return dict(scope='REAL_LOCKED_LEGACY_A_RAW_QC_LD_NO_MR', engine_source_revision=self.build['engine_commit'],
            input_hashing='ContentRequired', max_concurrency=1, incremental=False,
            plugin_name='frozen-a-input-qualification', original_manifest_sha256=proof.direct.SOURCE_PINS['manifest.toml'],
            additional_plugin_identities=[], native_statistical_factories_registered=False,
            explicit_replay_scope_allows_fit=False, current_daemon_verified=False, scientific_authorized=False,
            g0_granted=False, panel_bindings_are_explicit_synthetic_overrides=False,
            effective_synthetic_manifest_sha256=None, effective_manifest_sha256='a' * 64,
            panel_transport='TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT',
            locked_actual_panel_source_before=panel, locked_actual_panel_source_after=copy.deepcopy(panel),
            first_run=dict(nodes=nodes, errors=[]))

    def binding_fixture(self, root):
        scratch = root / 'scratch'
        inputs = scratch / 'method/.autonomics/inputs'
        inputs.mkdir(parents=True)
        targets, before = [], []
        nodes = {node['id']: copy.deepcopy(node) for node in self.report()['first_run']['nodes']}
        bindings = []
        for index in range(9):
            target = root / 'canonical' / str(index) / proof.direct.INPUT_PATHS[index].name
            target.parent.mkdir(parents=True)
            payload = ('toy source ' + str(index)).encode()
            target.write_bytes(payload)
            targets.append(target)
            info = target.stat()
            record = dict(bytes=info.st_size, sha256=hashlib.sha256(payload).hexdigest())
            before.append(record)
            (inputs / proof.staged_basename(index, target)).symlink_to(target)
            nodes['input' + str(index)]['port_assignments'] = {'0': dict(path=self.job['nodes'][index]['spec']['path'],
                format='file', fingerprint=dict(size=record['bytes'], content_hash='sha256:' + record['sha256']))}
            bindings.append(dict(to_port=index, **{'from': 'input' + str(index)}, from_port=0, kind='File',
                path=self.job['nodes'][index]['spec']['path'],
                fingerprint=dict(size=record['bytes'], content_hash='sha256:' + record['sha256'])))
        nodes['qualification']['inputs'] = bindings
        return scratch, nodes, nodes['qualification'], self.job, targets, before

    def stop_fixture(self, root, *, backend=None):
        session = 'a' * 32
        permanent = root / session / 'permanent'
        permanent.mkdir(parents=True)
        output = permanent / 'output'
        output.mkdir()
        owner = root / 'toy-owner.json'
        configured = ['--root', '/toy/storage', '--runroot', '/toy/run', '--tmpdir', '/toy/run/libpod-tmp', '--storage-driver', 'overlay']
        owner.write_text(json.dumps(dict(runtime_backend=configured)))
        (permanent / 'container-intents.json').write_text(json.dumps(dict(session=session,
            intents=[dict(token='b' * 32, backend=backend or [*configured, '--cgroup-manager=cgroupfs'])])))
        return permanent, output, owner, ['mock-managed-shim', *configured]

    def test_exact_job_has_nine_canonical_references_one_kind_and_nine_edges(self):
        proof.validate_job(self.job)
        self.assertEqual((len(self.job['nodes']), len(self.job['edges'])), (10, 9))
        for index, path in enumerate(proof.direct.INPUT_PATHS):
            self.assertEqual(self.job['nodes'][index]['spec']['path'], f'vfs:///locked-inputs/{index}/{path.name}')

    def test_job_construction_does_not_create_source_links_or_copy_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            proof.job_for(work, work / 'source')
            self.assertEqual(list(work.iterdir()), [])

    def test_synthetic_or_other_scope_cannot_relabel_the_job(self):
        for scope in ['TECHNICAL_PLUGIN_DAG_NOT_G0', 'LOCKED_LEGACY_A_HARMONISATION_NO_FIT_NOT_G0']:
            changed = copy.deepcopy(self.job)
            changed['scope'] = scope
            with self.assertRaises(RuntimeError):
                proof.validate_job(changed)

    def test_wrong_path_or_swapped_role_is_rejected(self):
        changed = copy.deepcopy(self.job)
        changed['nodes'][0]['spec']['path'] = 'vfs:///input0.input'
        with self.assertRaises(RuntimeError):
            proof.validate_job(changed)
        changed['nodes'][0]['spec']['path'] = changed['nodes'][1]['spec']['path']
        with self.assertRaises(RuntimeError):
            proof.validate_job(changed)

    def test_panel_override_or_missing_edge_is_rejected(self):
        for key, value in [('panel_overrides', [dict(synthetic_bundle='fake')]), ('locked_panel_source', '/other'),
                           ('edges', self.job['edges'][:-1])]:
            changed = copy.deepcopy(self.job)
            changed[key] = value
            with self.assertRaises(RuntimeError):
                proof.validate_job(changed)

    def test_complete_actual_success_report_is_checked(self):
        self.assertEqual(len(proof.validate_report(self.report(), self.job, self.build)), 10)

    def test_failed_unexecuted_or_wrong_version_method_cannot_pass(self):
        for execution in [None, dict(exit_code=137), dict(exit_code=True), dict(exit_code=0, image='other')]:
            value = self.report()
            value['first_run']['nodes'][-1]['execution'] = execution
            with self.assertRaises(RuntimeError):
                proof.validate_report(value, self.job, self.build)

    def test_reuse_kind_substitution_or_missing_node_cannot_pass(self):
        for mutation in ['reused', 'kind', 'missing']:
            value = self.report()
            if mutation == 'reused':
                value['first_run']['nodes'][0]['reused'] = True
            elif mutation == 'kind':
                value['first_run']['nodes'][-1]['node_type'] = 'twosamplemr'
            else:
                value['first_run']['nodes'].pop()
            with self.assertRaises(RuntimeError):
                proof.validate_report(value, self.job, self.build)

    def test_raw_manifest_must_explicitly_not_be_synthetic(self):
        for key, value in [('effective_synthetic_manifest_sha256', 'f' * 64),
                           ('panel_bindings_are_explicit_synthetic_overrides', True), ('explicit_replay_scope_allows_fit', True)]:
            report = self.report()
            report[key] = value
            with self.assertRaises(RuntimeError):
                proof.validate_report(report, self.job, self.build)
        report = self.report()
        del report['effective_synthetic_manifest_sha256']
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build)

    def test_original_panel_metadata_change_or_duplicate_payload_is_rejected(self):
        report = self.report()
        report['locked_actual_panel_source_after']['payload_files'][0]['inode'] += 1
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build)
        report = self.report()
        for key in ['locked_actual_panel_source_before', 'locked_actual_panel_source_after']:
            report[key]['payload_files'][1] = copy.deepcopy(report[key]['payload_files'][0])
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build)

    def test_nine_actual_symlink_bindings_preserve_canonical_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.binding_fixture(Path(temporary))
            observations = proof.bound_source_facts(*fixture)
            self.assertEqual(len(observations), 9)
            self.assertTrue(all(item['source_is_canonical_no_copy'] for item in observations))

    def test_regular_stage_copy_is_not_zero_copy_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.binding_fixture(Path(temporary))
            staged = fixture[0] / 'method/.autonomics/inputs/input-0.tsv.gz'
            payload = staged.read_bytes()
            staged.unlink()
            staged.write_bytes(payload)
            with self.assertRaises(RuntimeError):
                proof.bound_source_facts(*fixture)

    def test_wrong_staged_source_target_is_rejected_even_with_same_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self.binding_fixture(root)
            staged = fixture[0] / 'method/.autonomics/inputs/input-0.tsv.gz'
            alternate = root / 'foreign-copy'
            alternate.write_bytes(staged.read_bytes())
            staged.unlink()
            staged.symlink_to(alternate)
            with self.assertRaises(RuntimeError):
                proof.bound_source_facts(*fixture)

    def test_compound_gzip_and_extensionless_plink_staged_names_are_exact(self):
        self.assertEqual(proof.staged_basename(0, proof.direct.INPUT_PATHS[0]), 'input-0.tsv.gz')
        self.assertEqual(proof.staged_basename(1, proof.direct.INPUT_PATHS[1]), 'input-1.tsv.gz')
        self.assertEqual(proof.staged_basename(6, proof.direct.INPUT_PATHS[6]), 'input-6')

    def test_port_sixty_prefix_cannot_fill_missing_port_six(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.binding_fixture(Path(temporary))
            staged = fixture[0] / 'method/.autonomics/inputs/input-6'
            staged.rename(staged.with_name('input-60'))
            with self.assertRaises(RuntimeError):
                proof.bound_source_facts(*fixture)

    def test_binding_path_hash_and_kind_must_match_the_actual_reference(self):
        for key, value in [('path', 'vfs:///wrong-role'), ('kind', 'DataFrame'), ('hash', None)]:
            with tempfile.TemporaryDirectory() as temporary:
                fixture = self.binding_fixture(Path(temporary))
                binding = fixture[2]['inputs'][0]
                if key == 'hash':
                    binding['fingerprint']['content_hash'] = value
                else:
                    binding[key] = value
                with self.assertRaises(RuntimeError):
                    proof.bound_source_facts(*fixture)

    def test_second_level_alias_cannot_masquerade_as_direct_canonical_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self.binding_fixture(root)
            staged = fixture[0] / 'method/.autonomics/inputs/input-0.tsv.gz'
            alias = root / 'work-alias'
            alias.symlink_to(staged.resolve(strict=True))
            staged.unlink()
            staged.symlink_to(alias)
            with self.assertRaises(RuntimeError):
                proof.bound_source_facts(*fixture)

    def test_stoppage_query_requires_both_exact_labels_and_recorded_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            permanent, output, owner, prefix = self.stop_fixture(Path(temporary))
            result = subprocess.CompletedProcess([], 0, '[]', '')
            with mock.patch.object(proof.direct, 'OWNER', owner), mock.patch.object(proof.subprocess, 'run', return_value=result) as run:
                observed = proof.stopped_owned_containers(prefix, output, permanent)
            command = run.call_args.args[0]
            self.assertIn('label=autonomics.validation.session=' + permanent.parent.name, command)
            self.assertIn('label=autonomics.validation.intent=' + 'b' * 32, command)
            self.assertEqual(observed[0]['containers_remaining'], 0)

    def test_live_owned_container_or_foreign_backend_is_not_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            permanent, output, owner, prefix = self.stop_fixture(Path(temporary))
            result = subprocess.CompletedProcess([], 0, '[{"Id":"still-live"}]', '')
            with mock.patch.object(proof.direct, 'OWNER', owner), mock.patch.object(proof.subprocess, 'run', return_value=result):
                with self.assertRaises(RuntimeError):
                    proof.stopped_owned_containers(prefix, output, permanent)
        with tempfile.TemporaryDirectory() as temporary:
            permanent, output, owner, prefix = self.stop_fixture(Path(temporary), backend=['--root', '/foreign'])
            with mock.patch.object(proof.direct, 'OWNER', owner):
                with self.assertRaises(RuntimeError):
                    proof.stopped_owned_containers(prefix, output, permanent)

    def test_structural_refusal_is_not_claimed_as_a_method_exit_two(self):
        marker = 'raw A input ports must directly bind their exact read-only canonical source mount'
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            proof.rejected_job_observation(subprocess.CompletedProcess([], 1, '', marker), work, None, None)
            for result in [subprocess.CompletedProcess([], 2, '', marker), subprocess.CompletedProcess([], 137, '', marker),
                           subprocess.CompletedProcess([], 1, '', 'unrelated startup error')]:
                with self.assertRaises(RuntimeError):
                    proof.rejected_job_observation(result, work, None, None)
            with self.assertRaises(RuntimeError):
                proof.rejected_job_observation(subprocess.CompletedProcess([], 1, '', marker), work, None, 'new-container-intent')


if __name__ == '__main__':
    unittest.main()
