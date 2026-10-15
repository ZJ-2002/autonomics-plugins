import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import prove_frozen_a_family_dag as proof


class FrozenAFamilyDAGTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.work = self.root / 'toy-family'
        self.work.mkdir()
        self.environment = mock.patch.dict(os.environ, TMPDIR=str(self.root))
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.revision = 'a' * 40
        self.case = 'BOUNDARY'
        self.facts = dict(toy_only=True, no_official_method_executed=True)
        for index in range(9):
            (self.work / ('source' + str(index) + '.input')).write_bytes(('TOY ROLE ' + str(index)).encode())
        (self.work / 'request.json').write_text('{"toy_only":true}\n')
        self.methods = {kind: dict(expected_image='toy-' + stage + '@sha256:' + str(index) * 64)
            for index, (stage, kind) in enumerate(proof.STAGES.items(), 1)}

    def report(self, *, negative=False):
        job = proof.make_job(self.work, self.case)
        scratch = self.root / 'official-plugin-container-workspaces' / self.work.name
        scratch.mkdir(parents=True, exist_ok=True)
        records = []
        for index, entry in enumerate(job['nodes']):
            identifier = entry['id']
            skipped = negative and identifier in ('adjust', 'publish')
            failed = negative and identifier == 'assemble'
            node = dict(id=identifier, node_type=entry['kind'], reused=False,
                status='skipped' if skipped else 'failed' if failed else 'success', port_assignments={})
            if skipped:
                node.update(execution=None, skipped_because='assemble')
            else:
                receipt = self.work / 'task-receipts' / (str(index + 1) + '-1-1')
                receipt.mkdir(parents=True, exist_ok=True)
                task_path = receipt / 'task.json'
                execution = dict(exit_code=2 if failed else 0, workspace=str(receipt),
                    task_manifest=dict(path=str(task_path)))
                if identifier in proof.STAGES:
                    image = self.methods[entry['kind']]['expected_image']
                    execution.update(image=image, image_digest=image.split('@', 1)[1])
                    logs = scratch / identifier / '.autonomics/logs'
                    logs.mkdir(parents=True, exist_ok=True)
                    for stream in ['stdout', 'stderr']:
                        path = logs / (stream + '.log')
                        path.write_text('Analysis IDs do not equal frozen family' if failed else 'TOY METHOD LOG')
                        execution[stream + '_log'] = dict(path=str(path))
                    if failed:
                        (logs.parents[1] / 'assembly.log').write_text('Analysis IDs do not equal frozen family\n')
                        node['error'] = dict(message='Analysis IDs do not equal frozen family')
                else:
                    filename = self.work / entry['spec']['path'].removeprefix('vfs:///')
                    node['port_assignments'] = {'0': dict(path=entry['spec']['path'], format='file',
                        fingerprint=dict(size=filename.stat().st_size, content_hash='sha256:' + proof.digest(filename)))}
                node['execution'] = execution
                task_path.write_text(json.dumps(dict(spec=dict(id=identifier, kind=entry['kind']), resources={})))
                execution['task_manifest']['fingerprint'] = dict(size=task_path.stat().st_size)
                (receipt / 'attempt.json').write_text(json.dumps(dict(task_id=identifier, executor='local',
                    status=node['status'], exit_code=execution['exit_code'], workspace=str(receipt),
                    task_manifest=execution['task_manifest'])))
                (receipt / 'status.json').write_text(json.dumps(dict(status=node['status'])))
            records.append(node)
        return dict(scope=proof.REPORT_SCOPE, family_case=self.case, input_hashing='ContentRequired',
            max_concurrency=1, incremental=False, plugin_name='frozen-a-family-assembly',
            original_manifest_sha256=proof.PINS['frozen-a-family-assembly']['manifest.toml'],
            additional_plugin_identities=[dict(plugin_name='frozen-a-family-adjustment',
                original_manifest_sha256=proof.PINS['frozen-a-family-adjustment']['manifest.toml'],
                script_sha256={'scripts/adjust.R': proof.PINS['frozen-a-family-adjustment']['scripts/adjust.R']}, panels=[])],
            effective_synthetic_manifest_sha256=None, current_daemon_verified=False,
            native_statistical_factories_registered=False, explicit_replay_scope_allows_fit=False,
            real_overlap_classes_assigned=False, mr_computed=False,
            panel_bindings_are_explicit_synthetic_overrides=False, scientific_authorized=False,
            g0_granted=False, engine_source_revision=self.revision,
            frozen_family_source_facts_before=self.facts, frozen_family_source_facts_after=self.facts,
            first_run=dict(errors=['TOY MEMBERSHIP REFUSAL'] if negative else [], nodes=records,
                resource=dict(memory=dict(enabled=True, source='cgroup_v2', error=None, trigger=None,
                    sample_count=1, threshold_ratio=0.9, sample_interval_ms=250,
                    peak=dict(source='cgroup_v2', limit_bytes=2147483648, charged_bytes=200, usage_bytes=100)))))

    def check(self, report, *, negative=False, job=None):
        with mock.patch.object(proof, 'source_facts', return_value=self.facts), \
                mock.patch.object(proof, 'definitions', return_value=self.methods):
            return proof.check_family_report(report, self.work, self.case, negative=negative,
                expected_revision=self.revision, job=job)

    def graph(self, *, negative=False):
        report = self.report(negative=negative)
        (self.work / 'dag-report.json').write_text(json.dumps(report))
        (self.work / 'artifacts').mkdir()
        job = proof.make_job(self.work, self.case)
        calls = []
        admission = dict(scope=proof.SCOPE, family_case=self.case, frozen_family_source_facts=self.facts,
            job_validated_without_execution=True, containers_started=False,
            scientific_results_computed=False, g0_granted=False)
        def runner_stub(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, json.dumps(admission) if '--validate-job' in command else '', '')
        def port_stub(work, definition, node, scratch):
            directory = work / 'artifacts' / node['id']
            directory.mkdir()
            result = []
            for name in proof.runtime.OUTPUTS[proof.STAGES[node['id']]]:
                path = directory / name
                path.write_bytes(b'TOY ONLY; NO SCIENTIFIC METHOD EXECUTED')
                result.append(path)
            return result
        with mock.patch.object(proof, 'source_facts', return_value=self.facts), \
                mock.patch.object(proof, 'definitions', return_value=self.methods), \
                mock.patch.object(proof.subprocess, 'run', side_effect=runner_stub), \
                mock.patch.object(proof, 'actual_ports', side_effect=port_stub), \
                mock.patch.object(proof, 'dispatched_bindings', side_effect=lambda work, node, nodes, edges, scratch:
                    [edge for edge in edges if edge['to'] == node['id']]):
            ports, nodes = proof.graph(Path('/toy/nonexecuted-runner'), dict(engine_commit=self.revision),
                self.work, job, self.methods, negative=negative)
        return ports, nodes, calls

    def test_three_technical_cases_have_exact_thirteen_nodes_twenty_two_edges(self):
        for case in proof.SCENARIOS:
            job = proof.make_job(self.work, case)
            self.assertEqual((len(job['nodes']), len(job['edges'])), (13, 22))
            self.assertEqual(len({node['id'] for node in job['nodes']}), 13)
            self.assertEqual(job['scope'], proof.SCOPE)
            self.assertEqual(job['family_case'], case)
            self.assertEqual([node['kind'] for node in job['nodes'][-3:]], list(proof.runtime.KINDS))
            self.assertEqual(job['run_root'], str(self.work))
            self.assertEqual(len(job['additional_plugins']), 1)

    def test_exact_port_roles_preserve_official_adjuster_and_registry_inputs(self):
        job = proof.make_job(self.work, self.case)
        roles = {(edge['to'], edge['to_port']): (edge['from'], edge['from_port']) for edge in job['edges']}
        self.assertEqual(len(roles), 22)
        self.assertEqual([roles['adjust', port] for port in range(4)],
            [('assemble', 1), ('assemble', 0), ('assemble', 2), ('source8', 0)])
        self.assertEqual([roles['publish', port] for port in range(8)],
            [('assemble', 0), ('assemble', 1), ('assemble', 2), ('adjust', 0),
             ('adjust', 1), ('adjust', 2), ('source0', 0), ('source1', 0)])
        self.assertTrue(all(node['spec'] == {} for node in job['nodes'][-3:]))

    def test_source_refs_use_temporary_roles_with_full_hashing_not_canonical_payload_paths(self):
        job = proof.make_job(self.work, self.case)
        for index, node in enumerate(job['nodes'][:9]):
            self.assertEqual(node, dict(id='source' + str(index), kind='file_reference',
                spec=dict(path='vfs:///source' + str(index) + '.input', format='file', hash_content=True)))
        self.assertEqual(job['nodes'][9]['spec']['path'], 'vfs:///request.json')
        self.assertEqual((job['bundles'], job['panel_overrides'], job['panel_manifest_sha256']), ([], [], {}))

    def test_unknown_or_research_scenario_is_rejected_before_execution(self):
        for case in ['REAL_RESEARCH', 'G0_PASS', '', None]:
            with self.assertRaises(RuntimeError):
                proof.make_job(self.work, case)

    def test_complete_mock_report_accepts_all_three_actual_method_identities(self):
        self.assertEqual(len(self.check(self.report())), 13)

    def test_rewired_omitted_duplicate_edges_and_wrong_kind_cannot_pass_report(self):
        original = proof.make_job(self.work, self.case)
        changed = []
        for mutate in [lambda job: job['edges'].pop(),
                lambda job: job['edges'].__setitem__(-1, copy.deepcopy(job['edges'][0])),
                lambda job: job['edges'][10].__setitem__('from_port', 0),
                lambda job: job['nodes'][-1].__setitem__('kind', 'adjust_pvalues')]:
            job = copy.deepcopy(original)
            mutate(job)
            changed.append(job)
        report = self.report()
        for job in changed:
            with self.assertRaisesRegex(RuntimeError, 'Exact dedicated'):
                self.check(report, job=job)

    def test_wrong_scope_revision_authority_or_official_identity_is_rejected(self):
        baseline = self.report()
        for key, value in [('scope', 'TECHNICAL_PLUGIN_DAG_NOT_G0'), ('engine_source_revision', 'b' * 40),
                ('max_concurrency', True), ('scientific_authorized', True), ('mr_computed', True),
                ('current_daemon_verified', True), ('effective_synthetic_manifest_sha256', '0' * 64),
                ('additional_plugin_identities', [])]:
            report = copy.deepcopy(baseline)
            report[key] = value
            with self.assertRaises(RuntimeError):
                self.check(report)

    def test_missing_duplicate_reused_or_wrong_actual_node_cannot_pass(self):
        baseline = self.report()
        for mutate in [lambda rows: rows.pop(), lambda rows: rows.__setitem__(-1, copy.deepcopy(rows[0])),
                lambda rows: rows[0].__setitem__('reused', True),
                lambda rows: rows[-1].__setitem__('node_type', 'generic-python')]:
            report = copy.deepcopy(baseline)
            mutate(report['first_run']['nodes'])
            with self.assertRaises(RuntimeError):
                self.check(report)

    def test_unexecuted_oom_bool_exit_or_changed_image_is_not_positive_method_proof(self):
        baseline = self.report()
        for execution in [None, dict(exit_code=137), dict(exit_code=True),
                dict(exit_code=0, image='wrong', image_digest='sha256:' + '0' * 64)]:
            report = copy.deepcopy(baseline)
            report['first_run']['nodes'][-1]['execution'] = execution
            with self.assertRaises(RuntimeError):
                self.check(report)

    def test_source_identity_or_reference_content_hash_drift_is_rejected(self):
        baseline = self.report()
        for mutate in [lambda report: report.__setitem__('frozen_family_source_facts_after', {}),
                lambda report: report['first_run']['nodes'][0]['port_assignments']['0']['fingerprint'].__setitem__('content_hash', 'sha256:' + '0' * 64),
                lambda report: report['first_run']['nodes'][0]['port_assignments']['0'].__setitem__('path', 'vfs:///source1.input')]:
            report = copy.deepcopy(baseline)
            mutate(report)
            with self.assertRaises(RuntimeError):
                self.check(report)

    def test_foreign_membership_failure_accepts_only_assembly_failed_and_two_causal_skips(self):
        nodes = self.check(self.report(negative=True), negative=True)
        self.assertEqual(len([node for node in nodes.values() if node['status'] != 'skipped']), 11)
        self.assertEqual([nodes[stage]['skipped_because'] for stage in ['adjust', 'publish']], ['assemble', 'assemble'])

    def test_failed_assembly_cannot_publish_or_allow_downstream_execution(self):
        baseline = self.report(negative=True)
        for mutate in [lambda nodes: nodes[-3]['port_assignments'].__setitem__('0', {}),
                lambda nodes: nodes[-1].__setitem__('execution', {'exit_code': 0}),
                lambda nodes: nodes[-1].__setitem__('status', 'success'),
                lambda nodes: nodes[-2].__setitem__('skipped_because', 'unrelated')]:
            report = copy.deepcopy(baseline)
            mutate(report['first_run']['nodes'])
            with self.assertRaises(RuntimeError):
                self.check(report, negative=True)

    def test_mock_graph_records_thirteen_owned_attempts_and_twenty_two_bindings(self):
        ports, nodes, calls = self.graph()
        report = json.loads((self.work / 'graph-verification.json').read_text())
        self.assertEqual((report['actual_executed_nodes'], report['actual_skipped_nodes'],
            report['actual_published_ports']), (13, 0, 12))
        self.assertEqual(sum(map(len, report['actual_bindings'].values())), 22)
        self.assertEqual(len(list((self.work / 'task-receipts').iterdir())), 13)
        self.assertEqual(len(ports), 3)
        self.assertEqual(len(nodes), 13)
        self.assertEqual(len(calls), 2)
        self.assertIn('--validate-job', calls[0][0])
        self.assertEqual(calls[1][1]['env']['AUTONOMICS_DAG_TASKS_ROOT'], str(self.work / 'task-receipts'))
        self.assertFalse(report['plugin_resources_to_native_task_budget_proven'])

    def test_mock_foreign_id_failure_records_only_eleven_attempts_ten_bindings_and_two_skips(self):
        ports, nodes, calls = self.graph(negative=True)
        report = json.loads((self.work / 'graph-verification.json').read_text())
        self.assertEqual((report['actual_executed_nodes'], report['actual_skipped_nodes'],
            report['actual_published_ports']), (11, 2, 0))
        self.assertEqual(sum(map(len, report['actual_bindings'].values())), 10)
        self.assertEqual(len(list((self.work / 'task-receipts').iterdir())), 11)
        self.assertEqual(ports, {})
        self.assertEqual(len(calls), 2)
        self.assertIsNone(nodes['adjust']['execution'])
        self.assertTrue((self.work / 'expected-refusal.stderr').is_file())
        self.assertIn('Analysis IDs do not equal frozen family',
            (self.work / 'expected-refusal.log').read_text())

    def evidence_fixture(self):
        for name in proof.REPORT_FILES:
            (self.work / name).write_bytes(('TOY REPORT ' + name).encode())
        receipts = self.work / 'task-receipts' / '1-1-1'
        receipts.mkdir(parents=True)
        for name in ['task.json', 'attempt.json', 'status.json']:
            (receipts / name).write_text('{"toy_only":true}\n')
        junk = self.work / 'private-original-payload'
        junk.mkdir()
        (junk / 'never-archive.raw').write_bytes(b'PRIVATE TOY RAW MUST NOT BE COPIED')
        return receipts

    def test_evidence_archives_only_explicit_reports_and_owned_receipts_not_source_payloads(self):
        self.evidence_fixture()
        copied = proof.evidence_copy(self.work, self.root / 'evidence')
        self.assertEqual(len(copied), len(proof.REPORT_FILES) + 3)
        self.assertFalse((self.root / 'evidence/source0.input').exists())
        self.assertFalse((self.root / 'evidence/request.json').exists())
        self.assertFalse((self.root / 'evidence/private-original-payload').exists())
        record = json.loads((self.root / 'evidence/copied-evidence.json').read_text())
        self.assertFalse(record['required_source_copies_archived'])
        self.assertFalse(record['scratch_workspace_archived'])

    def test_evidence_rejects_missing_required_report_or_existing_destination(self):
        self.evidence_fixture()
        (self.work / proof.REPORT_FILES[0]).unlink()
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            proof.evidence_copy(self.work, self.root / 'missing-report')
        destination = self.root / 'existing'
        destination.mkdir()
        with self.assertRaises(RuntimeError):
            proof.evidence_copy(self.work, destination)

    def test_foreign_symlink_task_receipts_cannot_enter_permanent_evidence(self):
        receipts = self.evidence_fixture()
        foreign = self.root / 'foreign.json'
        foreign.write_text('{}')
        (receipts / 'task.json').unlink()
        (receipts / 'task.json').symlink_to(foreign)
        with self.assertRaises(RuntimeError):
            proof.evidence_copy(self.work, self.root / 'foreign-evidence')
        self.assertEqual(foreign.read_text(), '{}')

    def test_evidence_products_cannot_escape_owned_graph_or_change_declared_port_order(self):
        self.evidence_fixture()
        paths = []
        for name in proof.runtime.OUTPUTS[proof.STAGES['assemble']]:
            path = self.root / name
            path.write_bytes(b'FOREIGN TOY PRODUCT')
            paths.append(path)
        with self.assertRaisesRegex(RuntimeError, 'inside its temporary graph root'):
            proof.evidence_copy(self.work, self.root / 'outside-products', ports={'assemble': paths})
        with self.assertRaisesRegex(RuntimeError, 'four declared'):
            proof.evidence_copy(self.work, self.root / 'reordered-products', ports={'assemble': paths[::-1]})

    def test_successful_method_null_stderr_is_preserved_as_absent_not_a_fake_log(self):
        receipts = self.evidence_fixture()
        scratch = self.root / 'official-plugin-container-workspaces' / self.work.name
        logs = scratch / 'assemble/.autonomics/logs'
        logs.mkdir(parents=True)
        stdout = logs / 'stdout.log'
        stdout.write_text('TOY SUCCESS WITHOUT STDERR')
        nodes = dict(assemble=dict(execution=dict(workspace=str(receipts),
            stdout_log=dict(path=str(stdout)), stderr_log=None)))
        copied = proof.evidence_copy(self.work, self.root / 'null-stderr', nodes=nodes)
        self.assertIn('execution-logs/assemble.stdout', copied)
        self.assertNotIn('execution-logs/assemble.stderr', copied)
        self.assertEqual((self.root / 'null-stderr/execution-logs/assemble.stdout').read_text(),
            'TOY SUCCESS WITHOUT STDERR')

    def test_exact_owned_attempt_stdout_is_preserved_but_another_attempt_path_is_rejected(self):
        receipts = self.evidence_fixture()
        stdout = receipts / 'stdout.log'
        stdout.write_text('TOY EXECUTOR-OWNED STDOUT')
        nodes = dict(assemble=dict(execution=dict(workspace=str(receipts),
            stdout_log=dict(path=str(stdout)), stderr_log=None)))
        copied = proof.evidence_copy(self.work, self.root / 'owned-attempt-stdout', nodes=nodes)
        self.assertIn('execution-logs/assemble.stdout', copied)
        other = self.work / 'task-receipts/2-1-1'
        other.mkdir()
        for name in ['task.json', 'attempt.json', 'status.json']:
            (other / name).write_text('{"toy_only":true}\n')
        foreign = other / 'stdout.log'
        foreign.write_text('ANOTHER ATTEMPT MUST NOT BE ADOPTED')
        changed = copy.deepcopy(nodes)
        changed['assemble']['execution']['stdout_log']['path'] = str(foreign)
        with self.assertRaises(RuntimeError):
            proof.evidence_copy(self.work, self.root / 'other-attempt-stdout', nodes=changed)
        self.assertEqual(foreign.read_text(), 'ANOTHER ATTEMPT MUST NOT BE ADOPTED')

    def guard_fixture(self, names=None):
        names = sorted(proof.builder.GUARDS) if names is None else names
        text = '\n'.join('test ' + name + ' ... ok' for name in names)
        text += '\ntest result: ok. 37 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
        return text, dict(exit=0, required_tests=sorted(proof.builder.GUARDS), observed_passed_tests=names)

    def test_exact_thirty_seven_actual_guard_names_and_zero_exit_are_required(self):
        text, execution = self.guard_fixture()
        proof.validate_guard_inventory(text, execution)
        self.assertEqual(len(proof.builder.GUARDS), 37)

    def test_missing_duplicate_renamed_or_additional_guard_is_not_complete_build_proof(self):
        baseline = sorted(proof.builder.GUARDS)
        for names in [baseline[:-1], [*baseline[:-1], baseline[0]],
                [*baseline[:-1], 'family_tests::renamed_unapproved_guard'],
                [*baseline, 'family_tests::extra_unreviewed_guard']]:
            text, execution = self.guard_fixture(names)
            with self.assertRaises(RuntimeError):
                proof.validate_guard_inventory(text, execution)

    def test_skipped_filtered_failed_or_noninteger_guard_execution_cannot_pass(self):
        text, execution = self.guard_fixture()
        for changed in [text.replace('0 ignored', '1 ignored'), text.replace('0 filtered out', '1 filtered out'),
                text.replace('0 failed', '1 failed'), text.replace(' ... ok', ' ... ignored', 1)]:
            with self.assertRaises(RuntimeError):
                proof.validate_guard_inventory(changed, execution)
        for exit_code in [True, None, 1]:
            with self.assertRaises(RuntimeError):
                proof.validate_guard_inventory(text, dict(execution, exit=exit_code))

    def test_recorded_guard_inventory_cannot_disagree_with_actual_log(self):
        text, execution = self.guard_fixture()
        for changed in [dict(execution, required_tests=execution['required_tests'][:-1]),
                dict(execution, observed_passed_tests=execution['observed_passed_tests'][::-1])]:
            with self.assertRaises(RuntimeError):
                proof.validate_guard_inventory(text, changed)


if __name__ == '__main__':
    unittest.main()
