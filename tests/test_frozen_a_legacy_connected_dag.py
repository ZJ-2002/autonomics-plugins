"""Self-cleaning toy contracts; no official runtime, graph or study certification."""

import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools import prove_frozen_a_legacy_connected_dag as driver


class ConnectedDagContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = [self.root / ('source-' + str(index) + '.input') for index in range(21)]
        self.work = self.root / 'work'
        self.work.mkdir()
        self.job = driver.make_job(self.work, self.paths)
        self.facts = [dict(path=str(path), source='source' + str(index), bytes=11, sha256='a' * 64)
            for index, path in enumerate(self.paths)]
        self.methods = {kind: dict(expected_image='official@sha256:' + 'b' * 64)
            for kind in driver.STAGES.values()}
        self.build = dict(engine_commit='c' * 40)

    def report(self, negative=False):
        nodes = []
        for entry in self.job['nodes']:
            node = dict(id=entry['id'], node_type=entry['kind'], status='success', reused=False,
                port_assignments={}, inputs=[])
            if entry['kind'] == 'file_reference':
                node['port_assignments'] = {'0': dict(path=entry['spec']['path'], format='file',
                    fingerprint=dict(size=11, content_hash='sha256:' + 'a' * 64))}
            elif negative and entry['id'] in ['gate', 'assemble', 'adjust', 'publish']:
                node.update(status='skipped', execution=None, skipped_because='mr')
            else:
                node['execution'] = dict(exit_code=2 if negative and entry['id'] == 'mr' else 0,
                    image='official@sha256:' + 'b' * 64, image_digest='sha256:' + 'b' * 64)
                if negative and entry['id'] == 'mr':
                    node['status'] = 'failed'
            nodes.append(node)
        panel = dict(host_source=str(driver.raw_dag.PANEL_HOST), manifest_sha256=driver.raw_dag.PANEL_MANIFEST,
            digest=driver.raw_dag.PANEL_DIGEST, catalog_bundle=driver.raw_dag.PANEL_ID,
            payload_files=[dict(path=f'1000G.EUR.QC.{chromosome}.{suffix}')
                for chromosome in range(1, 23) for suffix in ['bed', 'bim', 'fam']])
        value = dict(scope=driver.REPORT_SCOPE, engine_source_revision=self.build['engine_commit'],
            input_hashing='ContentRequired', max_concurrency=1, incremental=False, scope_permits_mr=True,
            explicit_replay_scope_allows_fit=True, is_connected_scope=True,
            plugin_name=self.job['expected_plugin_name'], original_manifest_sha256=self.job['plugin_manifest_sha256'],
            effective_synthetic_manifest_sha256=None, connected_source_facts_before=self.facts,
            connected_source_facts_after=copy.deepcopy(self.facts), additional_plugin_identities=[dict(
                plugin_name=row['expected_plugin_name'], original_manifest_sha256=row['plugin_manifest_sha256'],
                script_sha256=row['script_sha256'], panels=[]) for row in self.job['additional_plugins']],
            locked_actual_panel_source_before=panel, locked_actual_panel_source_after=copy.deepcopy(panel),
            panel_transport='TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT',
            first_run=dict(errors={'mr': {'message': 'toy refusal'}} if negative else {}, nodes=nodes))
        value.update({name: False for name in ['current_daemon_verified', 'native_statistical_factories_registered',
            'real_overlap_classes_assigned', 'panel_bindings_are_explicit_synthetic_overrides', 'scientific_authorized', 'g0_granted']})
        return value

    def check(self, value, negative=False):
        return driver.validate_report(value, self.job, self.build, self.facts, self.methods, negative=negative)

    def test_exact_topology_has_twenty_one_sources_and_seven_methods(self):
        driver.validate_job(self.job, self.paths)
        self.assertEqual(len(self.job['nodes']), 28)
        self.assertEqual(len(self.job['edges']), 65)
        self.assertEqual(len(driver.STAGES), 7)

    def test_full_cases_execute_refusal_first_but_report_canonical_observed_order(self):
        self.assertEqual(driver.execution_cases(), [True, False])
        refusal = dict(case='MR-output-conflict', observed='actual-refusal-result')
        positive = dict(case='positive', observed='actual-positive-result')
        cases = [refusal, positive]
        canonical, actual_order = driver.complete_case_inventory(cases)
        self.assertEqual(actual_order, ['MR-output-conflict', 'positive'])
        self.assertEqual([case['case'] for case in canonical], ['positive', 'MR-output-conflict'])
        self.assertIs(canonical[0], positive)
        self.assertIs(canonical[1], refusal)
        self.assertEqual(cases, [refusal, positive])

    def test_missing_positive_or_wrong_execution_order_cannot_be_sorted_into_full_success(self):
        refusal = dict(case='MR-output-conflict')
        positive = dict(case='positive')
        for cases in [[], [refusal], [positive], [positive, refusal], [refusal, refusal],
                [refusal, dict(case='unknown')], [refusal, positive, positive]]:
            with self.subTest(cases=cases), self.assertRaises(RuntimeError):
                driver.complete_case_inventory(cases)

    def test_raw_and_connected_mount_roles_are_separate(self):
        self.assertIn('/locked-inputs/8/', self.job['nodes'][8]['spec']['path'])
        self.assertIn('/connected-inputs/9/', self.job['nodes'][9]['spec']['path'])

    def test_all_nine_mr_ports_enter_only_gate(self):
        records = [row for row in self.job['edges'] if row['from'] == 'mr']
        self.assertEqual({(row['from_port'], row['to'], row['to_port']) for row in records},
            {(index, 'gate', index) for index in range(9)})

    def test_gate_request_is_the_only_assembly_request_source(self):
        self.assertEqual([row for row in self.job['edges'] if row['to'] == 'assemble' and row['to_port'] == 9],
            [{'from': 'gate', 'from_port': 0, 'to': 'assemble', 'to_port': 9}])

    def test_missing_or_crosswired_edge_is_rejected(self):
        for mode in ['missing', 'crosswired', 'duplicate']:
            value = copy.deepcopy(self.job)
            if mode == 'missing':
                value['edges'].pop()
            elif mode == 'crosswired':
                value['edges'][0]['to_port'] = 200
            else:
                value['edges'].append(value['edges'][0])
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                driver.validate_job(value, self.paths)

    def test_synthetic_scope_and_method_parameters_are_rejected(self):
        for mode in ['scope', 'parameter', 'image-field']:
            value = copy.deepcopy(self.job)
            if mode == 'scope':
                value['scope'] = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
            elif mode == 'parameter':
                value['nodes'][-1]['spec'] = {'primary_p': .01}
            else:
                value['image'] = 'unreviewed:latest'
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                driver.validate_job(value, self.paths)

    def test_bool_port_cannot_impersonate_integer(self):
        value = copy.deepcopy(self.job)
        value['edges'][0]['from_port'] = False
        with self.assertRaises(RuntimeError):
            driver.validate_job(value, self.paths)

    def test_typed_json_rejects_bool_for_number_and_missing_key(self):
        for actual in [dict(threads=True), {}, dict(threads=1, extra=False)]:
            with self.subTest(actual=actual), self.assertRaises(RuntimeError):
                driver.exact_json(actual, dict(threads=1))

    def test_exact_fifty_three_guard_inventory(self):
        names = sorted(driver.builder.GUARDS)
        log = '\n'.join('test ' + name + ' ... ok' for name in names)
        log += '\ntest result: ok. 53 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
        execution = dict(exit=0, required_tests=names, observed_passed_tests=names)
        driver.validate_guard_inventory(log, execution)
        for mode in ['skip', 'duplicate', 'renamed', 'bool-exit']:
            altered = copy.deepcopy(execution)
            current = log
            if mode == 'skip':
                current = current.replace('test ' + names[0] + ' ... ok', 'test ' + names[0] + ' ... ignored')
            elif mode == 'duplicate':
                current += '\ntest ' + names[0] + ' ... ok\n'
            elif mode == 'renamed':
                current = current.replace(names[0], 'unreviewed_guard')
            else:
                altered['exit'] = False
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                driver.validate_guard_inventory(current, altered)

    def test_positive_actual_report_contract(self):
        self.assertEqual(len(self.check(self.report())), 28)

    def test_negative_requires_four_causally_skipped_stages(self):
        self.assertEqual(len(self.check(self.report(True), True)), 28)
        value = self.report(True)
        next(node for node in value['first_run']['nodes'] if node['id'] == 'publish')['skipped_because'] = 'gate'
        with self.assertRaises(RuntimeError):
            self.check(value, True)

    def test_failed_positive_and_wrong_error_schema_are_rejected(self):
        for mode in ['method', 'errors-map', 'cache']:
            value = self.report()
            if mode == 'method':
                value['first_run']['nodes'][-1]['status'] = 'failed'
            elif mode == 'errors-map':
                value['first_run']['errors'] = []
            else:
                value['first_run']['nodes'][0]['reused'] = True
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                self.check(value)

    def test_source_mutation_panel_loss_and_scientific_upgrade_are_rejected(self):
        for mode in ['source', 'panel', 'authority', 'primary', 'engine']:
            value = self.report()
            if mode == 'source':
                value['connected_source_facts_after'][0]['sha256'] = 'd' * 64
            elif mode == 'panel':
                value['locked_actual_panel_source_after']['payload_files'].pop()
            elif mode == 'authority':
                value['scientific_authorized'] = True
            elif mode == 'primary':
                value['is_connected_scope'] = False
            else:
                value['engine_source_revision'] = 'd' * 40
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                self.check(value)

    def test_source_reference_hash_and_complete_identity_are_required(self):
        for mode in ['hash', 'missing', 'duplicate']:
            value = self.report()
            if mode == 'hash':
                value['first_run']['nodes'][0]['port_assignments']['0']['fingerprint']['content_hash'] = None
            elif mode == 'missing':
                value['first_run']['nodes'].pop()
            else:
                value['first_run']['nodes'][-1] = value['first_run']['nodes'][0]
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                self.check(value)

    def test_negative_cannot_have_unrelated_error_or_normal_mr_port(self):
        for mode in ['extra-error', 'normal-port']:
            value = self.report(True)
            if mode == 'extra-error':
                value['first_run']['errors']['raw'] = {'message': 'OOM'}
            else:
                next(row for row in value['first_run']['nodes'] if row['id'] == 'mr')['port_assignments'] = {'0': {}}
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                self.check(value, True)

    def test_bound_copy_bytes_and_fingerprint_are_checked(self):
        source = self.root / 'upstream.tsv'
        source.write_bytes(b'toy full payload\n')
        scratch = self.root / 'scratch'
        workspace = scratch / 'owned'
        inputs = workspace / '.autonomics/inputs'
        inputs.mkdir(parents=True)
        staged = inputs / 'input-0.tsv'
        staged.write_bytes(source.read_bytes())
        node = dict(id='assemble', node_type=driver.STAGES['assemble'], port_assignments={'0': dict(path=str(workspace / 'assembly.tsv'))},
            inputs=[{'from': 'mr', 'from_port': 0, 'to_port': 0, 'path': str(source), 'kind': 'File',
                'fingerprint': dict(size=source.stat().st_size, content_hash='sha256:' + driver.digest(source))}])
        nodes = {'mr': {'port_assignments': {'0': dict(path=str(source))}}}
        job = {'edges': [{'from': 'mr', 'from_port': 0, 'to': 'assemble', 'to_port': 0}]}
        methods = {node['node_type']: dict(stage_in_mode='copy')}
        observed = driver.checked_bindings(self.work, node, nodes, job, methods, scratch, [])
        self.assertEqual(len(observed), 1)
        staged.write_bytes(b'wrong bytes')
        with self.assertRaises(RuntimeError):
            driver.checked_bindings(self.work, node, nodes, job, methods, scratch, [])

    def test_raw_no_extension_staging_requires_direct_canonical_symlink(self):
        source = self.root / 'plink'
        source.write_bytes(b'toy binary')
        scratch = self.root / 'scratch'
        workspace = scratch / 'owned'
        inputs = workspace / '.autonomics/inputs'
        inputs.mkdir(parents=True)
        (inputs / 'input-0').symlink_to(source)
        reference = dict(path='vfs:///locked-inputs/6/plink')
        node = dict(id='raw', node_type=driver.STAGES['raw'], port_assignments={'0': dict(path=str(workspace / 'result.tsv'))},
            inputs=[{'from': 'source0', 'from_port': 0, 'to_port': 0, 'path': reference['path'], 'kind': 'File',
                'fingerprint': dict(size=10, content_hash='sha256:' + driver.digest(source))}])
        nodes = {'source0': {'port_assignments': {'0': reference}}}
        job = {'edges': [{'from': 'source0', 'from_port': 0, 'to': 'raw', 'to_port': 0}]}
        methods = {node['node_type']: dict(stage_in_mode='symlink')}
        self.assertTrue(driver.checked_bindings(self.work, node, nodes, job, methods, scratch, [dict(path=str(source))])[0]['staged_is_symlink'])
        (inputs / 'input-0').unlink()
        (inputs / 'input-0').write_bytes(source.read_bytes())
        with self.assertRaises(RuntimeError):
            driver.checked_bindings(self.work, node, nodes, job, methods, scratch, [dict(path=str(source))])

    def test_evidence_copy_rejects_foreign_destination(self):
        target = self.root / 'existing'
        target.mkdir()
        (target / 'foreign').write_bytes(b'preserve')
        with self.assertRaises(RuntimeError):
            driver.evidence_copy(self.work, target, {}, {})
        self.assertEqual((target / 'foreign').read_bytes(), b'preserve')

    def test_wrong_binding_role_and_fingerprint_are_rejected(self):
        source = self.root / 'upstream.tsv'
        source.write_bytes(b'complete toy\n')
        scratch = self.root / 'scratch'
        workspace = scratch / 'owned'
        inputs = workspace / '.autonomics/inputs'
        inputs.mkdir(parents=True)
        (inputs / 'input-0.tsv').write_bytes(source.read_bytes())
        original = dict(id='assemble', node_type=driver.STAGES['assemble'], port_assignments={'0': dict(path=str(workspace / 'assembly.tsv'))},
            inputs=[{'from': 'mr', 'from_port': 0, 'to_port': 0, 'path': str(source), 'kind': 'File',
                'fingerprint': dict(size=source.stat().st_size, content_hash='sha256:' + driver.digest(source))}])
        nodes = {'mr': {'port_assignments': {'0': dict(path=str(source))}}}
        job = {'edges': [{'from': 'mr', 'from_port': 0, 'to': 'assemble', 'to_port': 0}]}
        methods = {original['node_type']: dict(stage_in_mode='copy')}
        for mode in ['path', 'kind', 'from-port', 'size', 'hash']:
            node = copy.deepcopy(original)
            binding = node['inputs'][0]
            if mode == 'path':
                binding['path'] = '/foreign.tsv'
            elif mode == 'kind':
                binding['kind'] = 'DataFrame'
            elif mode == 'from-port':
                binding['from_port'] = 1
            elif mode == 'size':
                binding['fingerprint']['size'] += 1
            else:
                binding['fingerprint']['content_hash'] = 'sha256:' + '0' * 64
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                driver.checked_bindings(self.work, node, nodes, job, methods, scratch, [])

    def test_copy_stage_symlink_is_not_accepted_as_a_regular_copy(self):
        source = self.root / 'upstream.tsv'
        source.write_bytes(b'toy\n')
        scratch = self.root / 'scratch'
        workspace = scratch / 'owned'
        inputs = workspace / '.autonomics/inputs'
        inputs.mkdir(parents=True)
        (inputs / 'input-0.tsv').symlink_to(source)
        node = dict(id='assemble', node_type=driver.STAGES['assemble'], port_assignments={'0': dict(path=str(workspace / 'assembly.tsv'))},
            inputs=[{'from': 'mr', 'from_port': 0, 'to_port': 0, 'path': str(source), 'kind': 'File',
                'fingerprint': dict(size=4, content_hash='sha256:' + driver.digest(source))}])
        nodes = {'mr': {'port_assignments': {'0': dict(path=str(source))}}}
        job = {'edges': [{'from': 'mr', 'from_port': 0, 'to': 'assemble', 'to_port': 0}]}
        with self.assertRaises(RuntimeError):
            driver.checked_bindings(self.work, node, nodes, job, {node['node_type']: dict(stage_in_mode='copy')}, scratch, [])

    def test_nonterminal_or_unknown_exit_build_is_rejected_before_metadata(self):
        archives = Path.home() / '.local/state/autonomics/validation-archives'
        archive = archives / ('d' * 32)
        root = archive / 'artifacts/permanent/build'
        runner = root / driver.builder.EXAMPLE
        record = root / 'build-record.json'
        fake_session = mock.mock_open(read_data=json.dumps(dict(state='CLEANED', worker_exit_status=True, launcher_exit_status=0)).encode())
        with mock.patch.object(driver, 'regular', side_effect=lambda path: path), \
                mock.patch.object(driver, 'digest', return_value=driver.BUILDER_SHA), \
                mock.patch.object(driver, 'verify_archive', return_value=dict(positive_worker_exit_verified=True)), \
                mock.patch.object(Path, 'open', fake_session), self.assertRaisesRegex(RuntimeError, 'successful terminal build'):
            driver.checked_build(runner, record, 'e' * 64, self.work)

    def test_missing_direct_replay_success_cannot_be_inherited_from_a_title(self):
        with mock.patch.object(driver, 'verify_archive', return_value=dict(positive_worker_exit_verified=False)), \
                mock.patch.object(Path, 'read_bytes', return_value=json.dumps(dict(state='CLEANED', worker_exit_status=0, launcher_exit_status=0)).encode()), \
                self.assertRaisesRegex(RuntimeError, 'truly terminal'):
            driver.checked_references(self.work)

    def test_parent_environment_is_not_modified_by_job_generation(self):
        before = dict(os.environ)
        driver.make_job(self.work, self.paths)
        self.assertTrue(dict(os.environ) == before, 'Job generation must not mutate the parent environment')

    def failed_diagnostic_fixture(self):
        permanent = self.root / 'permanent'
        permanent.mkdir()
        scratch = self.root / 'official-plugin-container-workspaces' / self.work.name
        method = scratch / 'ab' / 'owned-method'
        logs = method / '.autonomics/logs'
        logs.mkdir(parents=True)
        stderr = logs / 'stderr.log'
        stderr.write_text('BLOCKED: explicit toy failed method; keep the exact diagnostic\n')
        receipt = self.work / 'task-receipts/100-200-1'
        receipt.mkdir(parents=True)
        (receipt / 'task.json').write_text(json.dumps(dict(spec=dict(id='harmonise', kind=driver.STAGES['harmonise']))))
        (receipt / 'attempt.json').write_text(json.dumps(dict(task_id='harmonise', status='failed', exit_code=2)))
        (receipt / 'status.json').write_text(json.dumps(dict(status='failed')))
        report = self.report()
        node = next(row for row in report['first_run']['nodes'] if row['id'] == 'harmonise')
        node.update(status='failed', error=dict(message='explicit toy failed method'))
        node['execution'].update(exit_code=2, workspace=str(receipt), stderr_log=dict(path=str(stderr),
            fingerprint=dict(size=stderr.stat().st_size, content_hash='sha256:' + driver.digest(stderr))), stdout_log=None)
        report['first_run']['errors'] = {'harmonise': {'message': 'explicit toy failed method'}}
        return permanent, scratch, stderr, report

    def test_failed_report_and_method_stderr_survive_validation_and_scratch_cleanup(self):
        permanent, scratch, stderr, report = self.failed_diagnostic_fixture()
        destination = permanent / 'failed-positive'
        def process(command, **keywords):
            if '--validate-job' in command:
                return subprocess.CompletedProcess(command, 0, json.dumps(dict(scope=driver.SCOPE,
                    connected_source_facts=self.facts, job_validated_without_execution=True,
                    containers_started=False, scientific_results_computed=False, g0_granted=False)), '')
            (self.work / 'dag-report.json').write_text(json.dumps(report))
            return subprocess.CompletedProcess(command, 0, 'actual toy runner terminal output\n', '')
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent), TMPDIR=str(self.root)), \
                mock.patch.object(driver.subprocess, 'run', side_effect=process), \
                self.assertRaisesRegex(RuntimeError, 'Every positive method'):
            driver.run_graph(Path('/toy-runner'), self.build, self.work, self.methods, self.facts, {}, failure_output=destination)
        shutil.rmtree(scratch)
        shutil.rmtree(self.work)
        archived = json.loads((destination / 'dag-report.json').read_bytes())
        self.assertEqual(archived['first_run']['errors'], report['first_run']['errors'])
        self.assertIn('explicit toy failed method', (destination / 'execution-logs/harmonise.stderr').read_text())
        self.assertTrue((destination / 'task-receipts/100-200-1/attempt.json').is_file())
        self.assertTrue((destination / 'runner-exit.json').is_file())
        receipt = json.loads((destination / 'failure-diagnostics.json').read_bytes())
        self.assertFalse(receipt['successful_graph_claimed'])
        self.assertEqual(receipt['status'], 'FAILED_GRAPH_DIAGNOSTICS_RETAINED_NOT_PASS')

    def test_failure_capture_never_copies_foreign_logs_raw_inputs_or_entire_scratch(self):
        permanent, scratch, stderr, report = self.failed_diagnostic_fixture()
        foreign = self.root / 'foreign-private.log'
        foreign.write_bytes(b'FOREIGN_NOT_A_METHOD_LOG\n')
        next(row for row in report['first_run']['nodes'] if row['id'] == 'harmonise')['execution']['stderr_log'] = dict(path=str(foreign))
        (self.work / 'dag-report.json').write_text(json.dumps(report))
        (self.work / 'raw.input').write_bytes(b'NOT_A_REQUIRED_DIAGNOSTIC')
        (scratch / 'raw-payload').write_bytes(b'NOT_TO_BE_COPIED')
        destination = permanent / 'failed-positive'
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent), TMPDIR=str(self.root)):
            receipt = driver.preserve_failure_diagnostics(self.work, destination, RuntimeError('toy rejection'))
        self.assertFalse((destination / 'execution-logs/harmonise.stderr').exists())
        self.assertFalse((destination / 'raw.input').exists())
        self.assertFalse((destination / 'raw-payload').exists())
        self.assertEqual(foreign.read_bytes(), b'FOREIGN_NOT_A_METHOD_LOG\n')
        self.assertTrue(any(row['member'] == 'execution-logs/harmonise.stderr' for row in receipt['omitted']))

    def test_post_graph_comparison_failure_also_retains_narrow_report(self):
        permanent, scratch, stderr, report = self.failed_diagnostic_fixture()
        (self.work / 'dag-report.json').write_text(json.dumps(report))
        destination = permanent / 'failed-after-validation'
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent), TMPDIR=str(self.root)), \
                self.assertRaisesRegex(ValueError, 'comparison refused'):
            with driver.retain_case_failure(self.work, destination):
                raise ValueError('comparison refused')
        self.assertTrue((destination / 'dag-report.json').is_file())
        self.assertIn('explicit toy failed method', (destination / 'execution-logs/harmonise.stderr').read_text())
        self.assertFalse(json.loads((destination / 'failure-diagnostics.json').read_bytes())['successful_graph_claimed'])

    def test_missing_or_invalid_report_still_retains_bounded_owned_census(self):
        permanent, scratch, stderr, report = self.failed_diagnostic_fixture()
        logs = scratch / '12' / ('a' * 62) / '.autonomics/logs'
        logs.mkdir(parents=True)
        (logs / 'stderr.log').write_bytes(b'ACTUAL_TOY_RUNNER_CRASH_CAUSE\n')
        (self.work / 'task-receipts/100-200-1/stdout.log').write_bytes(b'OWNED_NATIVE_STDOUT\n')
        for mode in ['missing', 'invalid']:
            if mode == 'invalid':
                (self.work / 'dag-report.json').write_bytes(b'{invalid SDK JSON')
            destination = permanent / ('failed-' + mode)
            with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent), TMPDIR=str(self.root)):
                record = driver.preserve_failure_diagnostics(self.work, destination, RuntimeError('toy runner crash'))
            self.assertIn('ACTUAL_TOY_RUNNER_CRASH_CAUSE',
                (destination / ('workspace-diagnostics/12' + 'a' * 62 + '.stderr')).read_text())
            self.assertEqual((destination / 'task-receipts/100-200-1/stdout.log').read_bytes(), b'OWNED_NATIVE_STDOUT\n')
            self.assertFalse(record['successful_graph_claimed'])

    def test_timeout_captured_streams_are_persisted_without_inventing_exit(self):
        permanent = self.root / 'permanent'
        permanent.mkdir()
        for label in ['admission', 'runner']:
            work = self.root / ('timeout-' + label)
            work.mkdir()
            destination = permanent / label
            failure = subprocess.TimeoutExpired(['/toy-runner'], 5,
                output=b'PARTIAL_ACTUAL_STDOUT\n', stderr=b'PARTIAL_ACTUAL_STDERR\n')
            with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent), TMPDIR=str(self.root)), \
                    mock.patch.object(driver.subprocess, 'run', side_effect=failure), \
                    self.assertRaises(subprocess.TimeoutExpired) as caught:
                with driver.retain_case_failure(work, destination):
                    driver.captured_run(['/toy-runner'], work, label, capture_output=True, text=True, timeout=5)
            self.assertIs(caught.exception, failure)
            self.assertEqual((destination / (label + '.stdout')).read_bytes(), b'PARTIAL_ACTUAL_STDOUT\n')
            self.assertEqual((destination / (label + '.stderr')).read_bytes(), b'PARTIAL_ACTUAL_STDERR\n')
            exit_record = json.loads((destination / (label + '-exit.json')).read_bytes())
            self.assertIsNone(exit_record['actual_exit'])
            self.assertTrue(exit_record['timed_out'])

    def test_original_post_verifier_runs_once_on_success_and_primary_failure(self):
        for failed in [False, True]:
            output = self.root / ('finalization-failed' if failed else 'finalization-success')
            output.mkdir()
            error = ValueError('ORIGINAL_GRAPH_CAUSE')
            with mock.patch.object(driver, 'observed_stops', return_value=[]) as stops, \
                    mock.patch.object(driver.raw, 'original_postcheck', return_value=dict(actual_exit=0)) as post:
                if failed:
                    with self.assertRaises(ValueError) as caught:
                        with driver.finalize_execution([], self.root, output):
                            raise error
                    self.assertIs(caught.exception, error)
                else:
                    with driver.finalize_execution([], self.root, output) as result:
                        pass
                    self.assertEqual(result['post']['actual_exit'], 0)
                self.assertEqual(stops.call_count, 1)
                self.assertEqual(post.call_count, 1)
            self.assertTrue((output / 'execution-finalization.json').is_file())

    def test_post_failure_is_independent_and_never_replaces_original_cause(self):
        for primary in [False, True]:
            output = self.root / ('secondary-with-primary' if primary else 'secondary-only')
            output.mkdir()
            error = ValueError('ORIGINAL_GRAPH_CAUSE')
            with mock.patch.object(driver, 'observed_stops', return_value=[]), \
                    mock.patch.object(driver.raw, 'original_postcheck', side_effect=RuntimeError('REAL_POSTCHECK_REFUSED')) as post:
                if primary:
                    with self.assertRaises(ValueError) as caught:
                        with driver.finalize_execution([], self.root, output):
                            raise error
                    self.assertIs(caught.exception, error)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'post-verification failed'):
                        with driver.finalize_execution([], self.root, output):
                            pass
                self.assertEqual(post.call_count, 1)
            record = json.loads((output / 'execution-finalization.json').read_bytes())
            self.assertFalse(record['finalization_succeeded'])
            self.assertIn('original_whole_root_post_verifier', record['errors'])
            self.assertFalse(record['successful_graph_claimed'])

    def refusal_workspace_fixture(self):
        root = Path(tempfile.mkdtemp(dir=self.root))
        permanent = root / 'permanent'
        destination = permanent / 'proxy-negative'
        records = destination / 'actual-container-create'
        records.mkdir(parents=True)
        workspace_root = root / 'owned-workspaces'
        workspace = workspace_root / 'ab' / ('c' * 62)
        (workspace / '.autonomics').mkdir(parents=True)
        marker = workspace / driver.mr.OUTPUTS[0]
        marker.write_bytes(driver.oci.FOREIGN)
        lock = workspace / driver.SDK_WORKSPACE_LOCK
        lock.write_bytes(b'')
        lock.chmod(0o644)
        marker_identity = driver.oci.regular_fact(marker)
        record = dict(workspace=str(workspace), foreign_before=dict(path=str(marker), identity=marker_identity),
            foreign_after=copy.deepcopy(marker_identity))
        configuration = dict(workspace_root=workspace_root, records=records)
        return permanent, destination, workspace, configuration, record

    def test_refusal_census_records_exact_marker_and_flat_metadata_without_claiming_pass(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)):
            result = driver.verify_refusal_workspace(configuration, record)
        retained = json.loads((destination / 'MR-refusal-workspace-census.json').read_bytes())
        self.assertEqual(retained, result)
        self.assertEqual({row['name'] for row in retained['entries']}, {'.autonomics', driver.SDK_WORKSPACE_LOCK, driver.mr.OUTPUTS[0]})
        self.assertEqual(retained['original_marker_identity'], record['foreign_before']['identity'])
        self.assertEqual(retained['observed_marker_after'], record['foreign_after'])
        self.assertFalse(retained['successful_graph_claimed'])
        self.assertFalse(retained['unknown_file_bodies_read'])
        self.assertFalse(retained['recursive_workspace_copy'])

    def test_flat_workspace_failure_preserves_unknown_names_after_scratch_cleanup_without_reading_bodies(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        unknown = workspace / 'UNKNOWN_SDK_METADATA_NOT_YET_QUALIFIED'
        unknown.write_bytes(b'UNKNOWN_BODY_MUST_NOT_BE_READ_OR_ARCHIVED')
        original = Path.open
        def guarded_open(path, *arguments, **keywords):
            if path == unknown:
                raise AssertionError('Unknown workspace file body was opened')
            return original(path, *arguments, **keywords)
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                mock.patch.object(Path, 'open', guarded_open), \
                self.assertRaisesRegex(RuntimeError, 'may contain only the controlled foreign output'):
            driver.verify_refusal_workspace(configuration, record)
        shutil.rmtree(workspace.parent.parent)
        retained = json.loads((destination / 'MR-refusal-workspace-census.json').read_bytes())
        entry = next(row for row in retained['entries'] if row['name'] == unknown.name)
        self.assertEqual(entry['kind'], 'regular')
        self.assertEqual(entry['bytes'], len(b'UNKNOWN_BODY_MUST_NOT_BE_READ_OR_ARCHIVED'))
        self.assertNotIn('sha256', entry)
        self.assertNotIn('UNKNOWN_BODY_MUST_NOT_BE_READ_OR_ARCHIVED', json.dumps(retained))
        self.assertFalse(retained['successful_graph_claimed'])

    def test_refusal_census_does_not_weaken_the_no_normal_mr_product_assertion(self):
        for name in driver.mr.OUTPUTS[1:]:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            (workspace / name).write_bytes(b'UNEXPECTED_NORMAL_RESULT')
            with self.subTest(name=name), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    self.assertRaisesRegex(RuntimeError, 'may contain only the controlled foreign output'):
                driver.verify_refusal_workspace(configuration, record)
            retained = json.loads((destination / 'MR-refusal-workspace-census.json').read_bytes())
            self.assertIn(name, {row['name'] for row in retained['entries']})
            self.assertEqual(driver.oci.regular_fact(workspace / driver.mr.OUTPUTS[0]), record['foreign_after'])

    def test_refusal_flat_inventory_is_bounded_and_overflow_evidence_survives_rejection(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        for index in range(64):
            (workspace / ('unknown-' + str(index))).write_bytes(b'not read')
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                self.assertRaisesRegex(RuntimeError, 'exceeds the bounded diagnostic'):
            driver.verify_refusal_workspace(configuration, record)
        retained = json.loads((destination / 'MR-refusal-workspace-census.json').read_bytes())
        self.assertEqual(len(retained['entries']), retained['entry_limit'])
        self.assertEqual(retained['entry_limit'], 64)
        self.assertTrue(retained['truncated'])
        self.assertFalse(retained['successful_graph_claimed'])

    def test_sdk_empty_lock_is_bound_to_the_exact_compiled_source_contract(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)):
            result = driver.verify_refusal_workspace(configuration, record)
        origin = result['sdk_workspace_lock_source']
        self.assertEqual(origin['engine_commit'], '2bfbe45fa895076277e2d227f648a59be5dd67d0')
        self.assertEqual(origin['path'], 'crates/container-runtime/src/gc.rs')
        self.assertEqual(origin['blob_sha1'], 'e0f96819fc7307955114d8a149f8c71c58e02460')
        self.assertEqual(origin['sha256'], '8fa2f948b04c75401ee3514c7fb20cbc9367146aff6d7ff34c69b120f929087c')
        self.assertTrue(result['lock_file_presence_does_not_prove_lock_held'])
        post = json.loads((destination / 'MR-refusal-workspace-census-postcheck.json').read_bytes())
        self.assertTrue(post['metadata_unchanged'])
        self.assertEqual(post['marker_identity'], record['foreign_after'])

    def test_sdk_lock_nonempty_symlink_hardlink_and_directory_are_not_allowed(self):
        for mode in ['nonempty', 'empty-symlink', 'empty-hardlink', 'directory']:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            lock = workspace / driver.SDK_WORKSPACE_LOCK
            lock.unlink()
            target = workspace.parent.parent.parent / ('outside-' + mode)
            target.write_bytes(b'')
            if mode == 'nonempty':
                lock.write_bytes(b'not an SDK lock payload')
            elif mode == 'empty-symlink':
                lock.symlink_to(target)
            elif mode == 'empty-hardlink':
                os.link(target, lock)
            else:
                lock.mkdir()
            with self.subTest(mode=mode), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    self.assertRaisesRegex(RuntimeError, 'SDK workspace lock must be'):
                driver.verify_refusal_workspace(configuration, record)
            self.assertEqual(target.read_bytes(), b'')
            retained = json.loads((destination / 'MR-refusal-workspace-census.json').read_bytes())
            self.assertFalse(retained['successful_graph_claimed'])

    def test_sdk_lock_without_owner_write_or_with_unsafe_permission_bits_is_refused(self):
        for mode in [0o444, 0o400, 0o646, 0o666, 0o744, 0o4744]:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            lock = workspace / driver.SDK_WORKSPACE_LOCK
            lock.chmod(mode)
            with self.subTest(mode=mode), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    self.assertRaisesRegex(RuntimeError, 'safe owner read-write permissions'):
                driver.verify_refusal_workspace(configuration, record)
            self.assertEqual(lock.stat().st_mode & 0o7777, mode)

    def test_foreign_sdk_lock_owner_or_group_metadata_is_refused(self):
        for field in ['st_uid', 'st_gid']:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            original = os.scandir
            @contextmanager
            def scanned(path):
                with original(path) as entries:
                    wrapped = []
                    for entry in entries:
                        observed = entry.stat(follow_symlinks=False)
                        if entry.name == driver.SDK_WORKSPACE_LOCK:
                            values = {name: getattr(observed, name) for name in ['st_dev', 'st_ino', 'st_uid', 'st_gid',
                                'st_mode', 'st_size', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns']}
                            values[field] += 1
                            altered = SimpleNamespace(**values)
                            wrapped.append(SimpleNamespace(name=entry.name, stat=lambda follow_symlinks=False: altered))
                        else:
                            wrapped.append(entry)
                    yield iter(wrapped)
            with self.subTest(field=field), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    mock.patch.object(driver.os, 'scandir', scanned), \
                    self.assertRaisesRegex(RuntimeError, 'SDK workspace lock must be'):
                driver.verify_refusal_workspace(configuration, record)

    def test_lock_changed_after_the_permanent_census_is_rejected_with_postcheck_evidence(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        original = json.dump
        def changed(value, handle, **keywords):
            result = original(value, handle, **keywords)
            if Path(handle.name).name == 'MR-refusal-workspace-census.json':
                (workspace / driver.SDK_WORKSPACE_LOCK).write_bytes(b'changed after census')
            return result
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                mock.patch.object(driver.json, 'dump', changed), self.assertRaisesRegex(RuntimeError, 'metadata changed after'):
            driver.verify_refusal_workspace(configuration, record)
        post = json.loads((destination / 'MR-refusal-workspace-census-postcheck.json').read_bytes())
        self.assertFalse(post['metadata_unchanged'])
        self.assertFalse(post['successful_graph_claimed'])

    def test_missing_or_changed_marker_cannot_be_accepted_by_the_sdk_lock_exception(self):
        for mode in ['missing-before', 'changed-after', 'missing-after']:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            marker = workspace / driver.mr.OUTPUTS[0]
            if mode == 'missing-before':
                marker.unlink()
            original = json.dump
            def changed(value, handle, **keywords):
                result = original(value, handle, **keywords)
                if Path(handle.name).name == 'MR-refusal-workspace-census.json':
                    if mode == 'changed-after':
                        marker.write_bytes(b'changed marker')
                    elif mode == 'missing-after':
                        marker.unlink()
                return result
            with self.subTest(mode=mode), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    mock.patch.object(driver.json, 'dump', changed), self.assertRaises(RuntimeError):
                driver.verify_refusal_workspace(configuration, record)
            self.assertTrue((destination / 'MR-refusal-workspace-census.json').is_file())
            self.assertTrue((destination / 'MR-refusal-workspace-census-postcheck.json').is_file())

    def test_unknown_flat_directory_or_link_remains_a_strict_refusal(self):
        for mode in ['directory', 'dangling-link', 'file-link']:
            permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
            unknown = workspace / 'unknown-entry'
            if mode == 'directory':
                unknown.mkdir()
            elif mode == 'dangling-link':
                unknown.symlink_to(workspace / 'not-present')
            else:
                unknown.symlink_to(workspace / driver.mr.OUTPUTS[0])
            with self.subTest(mode=mode), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                    self.assertRaisesRegex(RuntimeError, 'may contain only the controlled foreign output'):
                driver.verify_refusal_workspace(configuration, record)

    def test_sdk_metadata_directory_cannot_be_replaced_by_a_symlink(self):
        permanent, destination, workspace, configuration, record = self.refusal_workspace_fixture()
        metadata = workspace / '.autonomics'
        metadata.rmdir()
        target = workspace.parent.parent.parent / 'foreign-metadata'
        target.mkdir()
        metadata.symlink_to(target, target_is_directory=True)
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), \
                self.assertRaisesRegex(RuntimeError, 'regular owned SDK metadata directory'):
            driver.verify_refusal_workspace(configuration, record)

    def test_official_rds_comparator_is_full_and_not_python_parsing(self):
        for marker in ['readRDS', 'identical(typeof(actual), typeof(expected))',
            'identical(attributes(actual), attributes(expected))', 'complete(actual[[position]], expected[[position]])',
            'identical(actual, expected)', 'c("MR", "ADJUSTMENT")', '"4.6.1"']:
            self.assertIn(marker, driver.RDS_COMPARE)
        self.assertNotIn('tolerance=', driver.RDS_COMPARE)


if __name__ == '__main__':
    unittest.main()
