import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
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
        self.guards = {'toy_guard_' + str(index) for index in range(23)}
        self.kernel_pins = {name: sha(('toy ' + name).encode()) for name in proof.KERNEL_SOURCE_PINS}

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
        text += '\ntest result: ok. 23 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
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
        kernel_sources = {}
        for name, checksum in self.kernel_pins.items():
            snapshot = directory / 'kernel-source' / name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(('toy ' + name).encode())
            kernel_sources[name] = dict(sha256=checksum, bytes=snapshot.stat().st_size)
        build = dict(actual_build_exit=0, parent_commit=proof.PARENT, engine_commit='b' * 40, git_tree='c' * 40,
            probe_sha256=sha(payloads['probe.rs']), changed_paths=['crates/container-plugin/examples/official_plugin_dag.rs'],
            source_unchanged=True, containers_started=False, real_study_fitted=False, production_restarted=False,
            kernel_source_pins=kernel_sources, old_sdk_fallback_allowed=False,
            g0_granted=False, executables=dict(runner=dict(executable='official_plugin_dag', sha256=sha(payloads['official_plugin_dag'])),
                guards=dict(executable='guard-tests', sha256=sha(payloads['guard-tests']))))
        (directory / 'build-record.json').write_text(json.dumps(build))
        (directory / 'candidate.json').write_text(json.dumps({key: build[key] for key in
            ['engine_commit', 'parent_commit', 'probe_sha256', 'git_tree', 'changed_paths']} |
            dict(kernel_source_pins=self.kernel_pins)))
        (directory / 'kernel-source-pins.json').write_text(json.dumps(dict(parent_commit=proof.PARENT,
            files=kernel_sources, exported_sources_equal_committed_parent=True, old_sdk_fallback_allowed=False)))
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
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards, KERNEL_SOURCE_PINS=self.kernel_pins):
                checked, receipt = proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)
                self.assertEqual(checked['engine_commit'], build['engine_commit'])
                self.assertEqual(receipt['guard_count'], 23)
                (directory / 'guards.stdout.log').unlink()
                with self.assertRaises((RuntimeError, ValueError)):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_failed_build_worker_cannot_be_relabelled_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            seal = self.seal_fixture(archive, worker=1)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards, KERNEL_SOURCE_PINS=self.kernel_pins):
                with self.assertRaisesRegex(RuntimeError, 'worker'):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_guard_runner_from_other_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives, archive, directory, build = self.build_fixture(root)
            seal = self.seal_fixture(archive)
            alternate = root / 'official_plugin_dag'
            alternate.write_bytes((directory / 'official_plugin_dag').read_bytes())
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards, KERNEL_SOURCE_PINS=self.kernel_pins):
                with self.assertRaisesRegex(RuntimeError, 'same sealed'):
                    proof.checked_build(archives, alternate, directory / 'build-record.json', seal)

    def test_wrong_build_parent_is_rejected_even_with_valid_archive_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            build['parent_commit'] = 'f' * 40
            (directory / 'build-record.json').write_text(json.dumps(build))
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards, KERNEL_SOURCE_PINS=self.kernel_pins):
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

    def test_legacy_engine_parent_is_rejected_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            build['parent_commit'] = '4ceefbd821baab8deebb070645a2fb8b1fa8e1ba'
            (directory / 'build-record.json').write_text(json.dumps(build))
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards,
                    KERNEL_SOURCE_PINS=self.kernel_pins):
                with self.assertRaisesRegex(RuntimeError, 'reviewed parent'):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_kernel_snapshot_drift_is_rejected_even_with_new_valid_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            snapshot = directory / 'kernel-source' / next(iter(self.kernel_pins))
            snapshot.write_text('substituted memory source')
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards,
                    KERNEL_SOURCE_PINS=self.kernel_pins):
                with self.assertRaisesRegex(RuntimeError, 'snapshot differs'):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_missing_kernel_source_proof_cannot_be_replaced_by_record_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            archives, archive, directory, build = self.build_fixture(Path(temporary))
            (directory / 'kernel-source-pins.json').unlink()
            seal = self.seal_fixture(archive)
            with mock.patch.multiple(proof, PROBE_SHA=build['probe_sha256'], GUARDS=self.guards,
                    KERNEL_SOURCE_PINS=self.kernel_pins):
                with self.assertRaisesRegex(RuntimeError, 'absent'):
                    proof.checked_build(archives, directory / 'official_plugin_dag', directory / 'build-record.json', seal)

    def test_sealed_nonexecutable_runner_is_copied_without_changing_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'sealed-runner'
            original.write_bytes(b'toy executable bytes; not executed')
            original.chmod(0o600)
            temporary_root = root / 'scratch'
            temporary_root.mkdir()
            before = proof.file_identity(original)
            target, identity = proof.executable_copy(original, temporary_root)
            self.assertEqual(identity, before)
            self.assertEqual(proof.file_identity(original), before)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual(target.read_bytes(), original.read_bytes())
            with self.assertRaises(FileExistsError):
                proof.executable_copy(original, temporary_root)

    def task_fixture(self, root):
        work = root / 'case'
        directory = work / 'task-receipts/123-456-0'
        directory.mkdir(parents=True)
        manifest = directory / 'task.json'
        manifest.write_text(json.dumps(dict(spec=dict(id='input0', kind='file_reference'), resources={})))
        reference = dict(path=str(manifest), fingerprint=dict(size=manifest.stat().st_size))
        execution = dict(exit_code=0, workspace=str(directory), task_manifest=reference)
        nodes = dict(input0=dict(node_type='file_reference', status='success', execution=execution))
        (directory / 'attempt.json').write_text(json.dumps(dict(task_id='input0', executor='local', status='success',
            exit_code=0, workspace=str(directory), task_manifest=reference)))
        (directory / 'status.json').write_text(json.dumps(dict(status='success')))
        return work, directory, nodes

    def test_owned_receipts_match_actual_nodes_and_preserve_unmeasured_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, directory, nodes = self.task_fixture(Path(temporary))
            observed = proof.checked_task_receipts(work, nodes)
            self.assertEqual(observed['input0']['actual_task_resources'], {})
            self.assertEqual(set(observed['input0']['files']), {'task.json', 'attempt.json', 'status.json'})

    def test_foreign_task_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, directory, nodes = self.task_fixture(Path(temporary))
            nodes['input0']['execution']['task_manifest']['path'] = '/foreign/task.json'
            with self.assertRaisesRegex(RuntimeError, 'receipt differ'):
                proof.checked_task_receipts(work, nodes)

    def test_failed_or_missing_receipt_cannot_match_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, directory, nodes = self.task_fixture(Path(temporary))
            (directory / 'status.json').write_text(json.dumps(dict(status='failed')))
            with self.assertRaisesRegex(RuntimeError, 'receipt differ'):
                proof.checked_task_receipts(work, nodes)
            (directory / 'status.json').unlink()
            with self.assertRaises(FileNotFoundError):
                proof.checked_task_receipts(work, nodes)

    def test_repaired_memory_report_requires_actual_cgroup_observation(self):
        memory = dict(enabled=True, source='cgroup_v2', error=None, trigger=None, sample_count=1,
            threshold_ratio=0.9, sample_interval_ms=250,
            peak=dict(source='cgroup_v2', limit_bytes=2147483648, charged_bytes=100, usage_bytes=80))
        proof.validate_memory_report(dict(first_run=dict(resource=dict(memory=memory))))
        for key, value in [('source', 'system'), ('error', 'permission denied'), ('sample_count', 0),
                           ('sample_count', True), ('trigger', {'reason': 'pressure'})]:
            changed = copy.deepcopy(memory)
            changed[key] = value
            with self.assertRaises(RuntimeError):
                proof.validate_memory_report(dict(first_run=dict(resource=dict(memory=changed))))

    def test_regular_copy_stage_guard_does_not_accept_foreign_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'foreign'
            target.write_bytes(b'toy bytes')
            alias = root / 'alias'
            alias.symlink_to(target)
            with self.assertRaises(RuntimeError):
                proof.file_identity(alias)

    def stop_fixture(self, root):
        session = 'a' * 32
        permanent = root / session / 'permanent'
        permanent.mkdir(parents=True)
        output = permanent / 'output'
        output.mkdir()
        owner = root / 'toy-owner.json'
        backend = ['--root', '/toy/storage', '--runroot', '/toy/run', '--tmpdir', '/toy/run/tmp']
        owner.write_text(json.dumps(dict(runtime_backend=backend)))
        (permanent / 'container-intents.json').write_text(json.dumps(dict(session=session,
            intents=[dict(token=character * 32, backend=backend) for character in ['b', 'c']])))
        return permanent, output, owner, backend

    def test_two_owned_stoppage_queries_use_both_labels_and_actual_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            permanent, output, owner, backend = self.stop_fixture(Path(temporary))
            with mock.patch.object(proof, 'OWNER', owner), mock.patch.object(proof.subprocess, 'run') as run:
                run.return_value = type('ToyResult', (), dict(returncode=0, stdout='[]'))()
                observed = proof.stopped_owned_containers(['toy-managed-shim', *backend], output, permanent)
                self.assertEqual(len(observed), 2)
                self.assertEqual(run.call_count, 2)
                for index, call in enumerate(run.call_args_list):
                    command = call.args[0]
                    self.assertEqual(command[:1 + len(backend)], ['toy-managed-shim', *backend])
                    self.assertIn('label=autonomics.validation.session=' + 'a' * 32, command)
                    self.assertIn('label=autonomics.validation.intent=' + ['b', 'c'][index] * 32, command)

    def test_still_running_method_container_cannot_be_recorded_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            permanent, output, owner, backend = self.stop_fixture(Path(temporary))
            with mock.patch.object(proof, 'OWNER', owner), mock.patch.object(proof.subprocess, 'run') as run:
                run.return_value = type('ToyResult', (), dict(returncode=0, stdout='[{"Id":"owned-live"}]'))()
                with self.assertRaisesRegex(RuntimeError, 'not proven stopped'):
                    proof.stopped_owned_containers(['toy-managed-shim', *backend], output, permanent)

    def launcher_fixture(self, root):
        original = root / 'fake-managed-shim'
        original.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
        original.chmod(0o700)
        backend = ['--root', '/toy/storage', '--runroot', '/toy/run', '--tmpdir', '/toy/run/libpod-tmp']
        owner = root / 'owner.json'
        owner.write_text(json.dumps(dict(runtime_backend=backend)))
        temporary, output = root / 'scratch', root / 'permanent'
        temporary.mkdir()
        output.mkdir()
        return original, backend, owner, temporary, output

    def test_backend_launcher_real_fake_shim_receives_exact_prefix_and_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, backend, owner, scratch, output = self.launcher_fixture(Path(temporary))
            with mock.patch.multiple(proof, OWNER=owner, OWNER_SHA=sha(owner.read_bytes())), \
                    mock.patch.dict(os.environ, AUTONOMICS_PODMAN_PROGRAM=str(original)):
                receipt = proof.install_backend_launcher([str(original), *backend], scratch, output)
                process = subprocess.run([sys.executable, receipt['launcher_path'], 'create', '--rm', 'toy-image'],
                    capture_output=True, text=True, check=False)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(json.loads(process.stdout), [*backend, 'create', '--rm', 'toy-image'])
                self.assertEqual(os.environ['AUTONOMICS_PODMAN_PROGRAM'], str(original))
                self.assertEqual(Path(os.environ['PATH'].split(os.pathsep)[0]), scratch / 'frozen-a-owner-backend-bin')
                proof.verify_backend_launcher(receipt)

    def test_backend_launcher_rejects_override_before_fake_shim_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, backend, owner, scratch, output = self.launcher_fixture(Path(temporary))
            with mock.patch.multiple(proof, OWNER=owner, OWNER_SHA=sha(owner.read_bytes())), \
                    mock.patch.dict(os.environ, AUTONOMICS_PODMAN_PROGRAM=str(original)):
                receipt = proof.install_backend_launcher([str(original), *backend], scratch, output)
                for option in ['--root', '--runroot=/foreign', '--storage-driver=vfs', '--version', '-r']:
                    process = subprocess.run([sys.executable, receipt['launcher_path'], option, 'toy-value'],
                        capture_output=True, text=True, check=False)
                    self.assertEqual(process.returncode, 125)
                    self.assertEqual(process.stdout, '')
                    self.assertIn('backend override refused', process.stderr)

    def test_backend_launcher_child_installation_does_not_modify_parent_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, backend, owner, scratch, output = self.launcher_fixture(Path(temporary))
            before = dict(os.environ)
            script = '''import json,sys
from pathlib import Path
from tools import prove_frozen_a_harmonisation_dag as proof
original,owner,scratch,output,backend,checksum=json.loads(sys.argv[1])
proof.OWNER=Path(owner)
proof.OWNER_SHA=checksum
receipt=proof.install_backend_launcher([original,*backend],Path(scratch),Path(output))
print(json.dumps(receipt))
'''
            arguments = json.dumps([str(original), str(owner), str(scratch), str(output), backend, sha(owner.read_bytes())])
            process = subprocess.run([sys.executable, '-B', '-c', script, arguments], capture_output=True, text=True,
                cwd=proof.ROOT, env=dict(os.environ, AUTONOMICS_PODMAN_PROGRAM=str(original)), check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            receipt = json.loads(process.stdout)
            self.assertTrue(receipt['original_managed_program_unchanged'])
            self.assertFalse(receipt['shared_or_parent_environment_modified'])
            self.assertEqual(dict(os.environ), before)

    def test_backend_launcher_identity_and_owner_prefix_cannot_be_substituted(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, backend, owner, scratch, output = self.launcher_fixture(Path(temporary))
            with mock.patch.multiple(proof, OWNER=owner, OWNER_SHA=sha(owner.read_bytes())), \
                    mock.patch.dict(os.environ, AUTONOMICS_PODMAN_PROGRAM=str(original)):
                with self.assertRaisesRegex(RuntimeError, 'exactly the inspected owner'):
                    proof.install_backend_launcher([str(original), '--root', '/foreign'], scratch, output)
                receipt = proof.install_backend_launcher([str(original), *backend], scratch, output)
                Path(receipt['launcher_path']).write_text('substituted launcher')
                with self.assertRaisesRegex(RuntimeError, 'launcher.*changed'):
                    proof.verify_backend_launcher(receipt)


if __name__ == '__main__':
    unittest.main()
