import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import prove_frozen_a_harmonisation_dag as proof


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


class FrozenAHarmonisationDAGTests(unittest.TestCase):
    def setUp(self):
        self.job = proof.job_for(Path('/owned/positive'), Path('/owned/source'))
        self.build = dict(engine_commit='b' * 40)
        self.guards = {'toy_guard_' + str(index) for index in range(20)}

    def report(self):
        return dict(scope='REAL_LOCKED_LEGACY_A_HARMONISATION_NO_FIT',
            engine_source_revision=self.build['engine_commit'], input_hashing='ContentRequired',
            max_concurrency=1, incremental=False, native_statistical_factories_registered=False,
            original_manifest_sha256=proof.PINS['manifest.toml'], plugin_name='frozen-a-harmonisation',
            additional_plugin_identities=[], current_daemon_verified=False, explicit_replay_scope_allows_fit=False,
            scientific_authorized=False, g0_granted=False,
            first_run=dict(errors=[], nodes=[dict(id=record['id'], node_type=record['kind'], status='success',
                reused=False, port_assignments={}, execution=dict(exit_code=0, image=proof.IMAGE,
                    image_digest=proof.IMAGE.split('@', 1)[1])) for record in self.job['nodes']]))

    def provenance(self):
        before = {name: dict(sha256=str(index) * 64, bytes=index + 1) for index, name in enumerate(proof.INPUTS)}
        value = dict(scope='FROZEN_39_IV_LEGACY_HARMONISATION_ONLY_NOT_RAW_QC_PLINK_MR_OR_G0',
            input_sha256=[before[name]['sha256'] for name in proof.INPUTS],
            input_bytes=[before[name]['bytes'] for name in proof.INPUTS],
            adapter_sha256=proof.PINS['scripts/harmonise.R'], original_scientific_code_sha256=proof.SOURCE_SHA,
            qualify_A_block_sha256=proof.BLOCK_SHA, original_qualify_A_branch_evaluated=True,
            R='4.6.1', TwoSampleMR='0.7.11', TwoSampleMR_RemoteSha=None,
            package_description_sha256='911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531',
            package_namespace_function_count=171,
            package_namespace_aggregate_sha256='127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73',
            source_commit_supported_by_frozen_host_identity='d4df21929fdabeb2f89686ffaad0db5f56973d64',
            package_identity_proof_session=proof.IDENTITY_SESSION, package_identity_proof_manifest_sha256=proof.IDENTITY_SEAL,
            n_clumped=39, n_qualified=39, seed=432202610, additional_config_envelope_checked_without_reselection=True,
            raw_GWAS_QC_reexecuted=False, PLINK_or_LD_reexecuted=False, MR_estimates_computed=False,
            original_full_project_verifier_executed=False, scientific_authorization_granted=False,
            formal_scientific_pass_granted=False, G0=False)
        return value, before

    def guard_fixture(self):
        observed = sorted(self.guards)
        text = '\n'.join('test ' + name + ' ... ok' for name in observed)
        text += '\ntest result: ok. 20 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
        return text, dict(exit=0, required_tests=observed, observed_passed_tests=observed)

    def build_fixture(self, root):
        archives = root / 'archives'
        archive = archives / ('a' * 32)
        artifacts = archive / 'artifacts'
        directory = artifacts / 'permanent/build'
        directory.mkdir(parents=True)
        payloads = {'official_plugin_dag': b'toy runner not executable proof', 'guard-tests': b'toy guard executable',
                    'probe.rs': b'toy rust source'}
        for name, payload in payloads.items():
            (directory / name).write_bytes(payload)
        build = dict(actual_build_exit=0, parent_commit=proof.PARENT, engine_commit='b' * 40, git_tree='c' * 40,
            probe_sha256=sha(payloads['probe.rs']), changed_paths=['crates/container-plugin/examples/official_plugin_dag.rs'],
            source_unchanged=True, containers_started=False, real_study_fitted=False, production_restarted=False,
            g0_granted=False, executables=dict(runner=dict(executable='official_plugin_dag', sha256=sha(payloads['official_plugin_dag'])),
                guards=dict(executable='guard-tests', sha256=sha(payloads['guard-tests']))))
        (directory / 'build-record.json').write_text(json.dumps(build))
        (directory / 'candidate.json').write_text(json.dumps({key: build[key] for key in
            ['engine_commit', 'parent_commit', 'probe_sha256', 'git_tree', 'changed_paths']}))
        text, execution = self.guard_fixture()
        (directory / 'guards.stdout.log').write_text(text)
        execution['stdout_sha256'] = sha(text.encode())
        (directory / 'guards-execution.json').write_text(json.dumps(execution))
        for name in ['runner-build-exit.json', 'guards-build-exit.json']:
            (directory / name).write_text(json.dumps(dict(exit=0)))
        return archives, archive, directory, build

    def seal_fixture(self, archive, *, worker=0):
        artifacts = archive / 'artifacts'
        manifest = dict(schema='TECHNICAL_VALIDATION_SESSION_V1', session=archive.name,
            files={path.relative_to(artifacts).as_posix(): dict(bytes=path.stat().st_size, sha256=sha(path.read_bytes()))
                   for path in artifacts.rglob('*') if path.is_file() and path.name != 'MANIFEST.json'})
        payload = json.dumps(manifest).encode()
        (artifacts / 'MANIFEST.json').write_bytes(payload)
        seal = sha(payload)
        (archive / 'SESSION.json').write_text(json.dumps(dict(schema='TECHNICAL_VALIDATION_SESSION_V1',
            session=archive.name, state='CLEANED', worker_exit_status=worker, manifest_sha256=seal)))
        return seal

    def test_exact_seven_node_six_edge_job_is_accepted(self):
        proof.validate_job(self.job)
        self.assertEqual((len(self.job['nodes']), len(self.job['edges'])), (7, 6))

    def test_synthetic_scope_cannot_relabel_real_sources(self):
        self.job['scope'] = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
        with self.assertRaises(RuntimeError):
            proof.validate_job(self.job)

    def test_missing_or_duplicated_binding_is_rejected(self):
        for edges in [self.job['edges'][:-1], [*self.job['edges'][:-1], self.job['edges'][0]]]:
            changed = copy.deepcopy(self.job)
            changed['edges'] = edges
            with self.assertRaises(RuntimeError):
                proof.validate_job(changed)

    def test_generic_method_or_changed_source_is_rejected(self):
        for key, value in [('expected_plugin_name', 'twosamplemr'), ('plugin_manifest_sha256', '0' * 64),
                           ('script_sha256', {}), ('additional_plugins', [dict(expected_plugin_name='other')])]:
            changed = copy.deepcopy(self.job)
            changed[key] = value
            with self.assertRaises(RuntimeError):
                proof.validate_job(changed)

    def test_fit_kind_cannot_replace_qualification(self):
        self.job['nodes'][-1]['kind'] = 'twosamplemr_v432_a_exploratory'
        with self.assertRaises(RuntimeError):
            proof.validate_job(self.job)

    def test_complete_actual_success_report_is_accepted(self):
        nodes = proof.validate_report(self.report(), self.job, self.build, negative=False)
        self.assertEqual(len(nodes), 7)

    def test_unexecuted_or_failed_method_cannot_pass(self):
        for execution in [None, dict(exit_code=137), dict(exit_code=True), dict(exit_code=0, image='other')]:
            report = self.report()
            report['first_run']['nodes'][-1]['execution'] = execution
            with self.assertRaises(RuntimeError):
                proof.validate_report(report, self.job, self.build, negative=False)

    def test_wrong_engine_or_original_manifest_cannot_pass(self):
        for key, value in [('engine_source_revision', 'f' * 40), ('original_manifest_sha256', 'f' * 64),
                           ('max_concurrency', True), ('current_daemon_verified', True)]:
            report = self.report()
            report[key] = value
            with self.assertRaises(RuntimeError):
                proof.validate_report(report, self.job, self.build, negative=False)

    def test_actual_node_kind_mismatch_is_rejected(self):
        report = self.report()
        report['first_run']['nodes'][0]['node_type'] = 'datafusion_sql'
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build, negative=False)

    def test_cache_hit_or_missing_node_is_not_fresh_complete_proof(self):
        report = self.report()
        report['first_run']['nodes'][-1]['reused'] = True
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build, negative=False)
        report = self.report()
        report['first_run']['nodes'].pop(0)
        with self.assertRaises(RuntimeError):
            proof.validate_report(report, self.job, self.build, negative=False)

    def test_null_observed_remote_sha_requires_explicit_field(self):
        value, before = self.provenance()
        proof.validate_provenance(value, before)
        del value['TwoSampleMR_RemoteSha']
        with self.assertRaises(RuntimeError):
            proof.validate_provenance(value, before)

    def test_changed_official_package_identity_is_rejected(self):
        for key, changed in [('TwoSampleMR', '0.7.9'), ('package_namespace_function_count', 170),
                             ('package_description_sha256', '0' * 64), ('TwoSampleMR_RemoteSha', 'invented')]:
            value, before = self.provenance()
            value[key] = changed
            with self.assertRaises(RuntimeError):
                proof.validate_provenance(value, before)

    def test_scientific_or_raw_stage_authority_cannot_be_invented(self):
        for key in ['raw_GWAS_QC_reexecuted', 'PLINK_or_LD_reexecuted', 'MR_estimates_computed',
                    'scientific_authorization_granted', 'G0']:
            value, before = self.provenance()
            value[key] = True
            with self.assertRaises(RuntimeError):
                proof.validate_provenance(value, before)

    def test_exact_toy_guard_inventory_is_checked_without_running_executables(self):
        text, record = self.guard_fixture()
        with mock.patch.object(proof, 'GUARDS', self.guards):
            proof.validate_guard_inventory(text, record)

    def test_duplicate_or_omitted_guard_cannot_pass(self):
        text, record = self.guard_fixture()
        with mock.patch.object(proof, 'GUARDS', self.guards):
            for altered in [text.replace('test toy_guard_0 ... ok\n', ''), text + 'test toy_guard_0 ... ok\n']:
                with self.assertRaises(RuntimeError):
                    proof.validate_guard_inventory(altered, record)

    def test_ignored_filtered_or_failed_guard_summary_cannot_pass(self):
        text, record = self.guard_fixture()
        with mock.patch.object(proof, 'GUARDS', self.guards):
            for old, new in [('0 ignored', '1 ignored'), ('0 filtered out', '1 filtered out'), ('0 failed', '1 failed')]:
                with self.assertRaises(RuntimeError):
                    proof.validate_guard_inventory(text.replace(old, new), record)
            record['exit'] = 1
            with self.assertRaises(RuntimeError):
                proof.validate_guard_inventory(text, record)

    def test_unfrozen_build_identity_blocks_execution(self):
        with mock.patch.object(proof, 'PROBE_SHA', None):
            with self.assertRaisesRegex(RuntimeError, 'not yet frozen'):
                proof.checked_build(Path('/unused'), Path('/unused/runner'), Path('/unused/record'), '0' * 64)

    def test_sealed_toy_build_requires_every_actual_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards):
                checked, receipt = proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)
                self.assertEqual(checked['engine_commit'], build['engine_commit'])
                self.assertEqual(receipt['guard_count'], 20)
                (directory / 'guards.stdout.log').unlink()
                with self.assertRaises((RuntimeError, ValueError)):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_failed_build_worker_cannot_be_relabelled_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            seal = self.seal_fixture(archive, worker=1)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards):
                with self.assertRaisesRegex(RuntimeError, 'worker'):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_guard_runner_from_other_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives, archive, directory, build = self.build_fixture(root)
            seal = self.seal_fixture(archive)
            alternate = root / 'official_plugin_dag'
            alternate.write_bytes((directory / 'official_plugin_dag').read_bytes())
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards):
                with self.assertRaisesRegex(RuntimeError, 'same sealed'):
                    proof.checked_build(archives, alternate, directory / 'build-record.json', seal)

    def test_wrong_build_parent_is_rejected_even_with_valid_archive_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            build['parent_commit'] = 'f' * 40
            (directory / 'build-record.json').write_text(json.dumps(build))
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards):
                with self.assertRaises(RuntimeError):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_oom_is_not_the_expected_source_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            stderr = scratch / 'stderr.log'
            marker = 'Only the exact six frozen harmonisation inputs are supported'
            stderr.write_text(marker)
            node = dict(status='failed', error=dict(message=marker), execution=dict(exit_code=137, image=proof.IMAGE,
                image_digest=proof.IMAGE.split('@', 1)[1], stderr_log=dict(path=str(stderr))))
            with self.assertRaises(RuntimeError):
                proof.expected_refusal(node, proof.IMAGE, marker, scratch)
            node['execution']['exit_code'] = 2
            proof.expected_refusal(node, proof.IMAGE, marker, scratch)


if __name__ == '__main__':
    unittest.main()
