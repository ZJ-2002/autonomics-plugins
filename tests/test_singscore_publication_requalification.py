"""Self-cleaning stdlib transport toys, not official scoring or DAG certification."""

import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools import prove_singscore_publication_requalification as driver

REFUSAL = (ValueError, RuntimeError)


def report_fixture(positive=True):
    nodes = []
    for port in range(3):
        nodes.append(dict(id='input' + str(port), node_type='file_reference', status='success', reused=False,
                          port_assignments={'0': {}}))
    error = None if positive else dict(kind='node_error', message='ERROR: toy input refusal')
    nodes.append(dict(id='analysis', node_type='singscore_bspec', reused=False,
        status='success' if positive else 'failed', error=error,
        port_assignments={str(port): {} for port in range(3)} if positive else {},
        execution=dict(exit_code=0 if positive else 1, image=driver.IMAGE, image_digest=driver.IMAGE.split('@')[1])))
    return dict(engine_source_revision='toy-verified-engine', scope=driver.SCOPE, plugin_name='singscore',
        original_manifest_sha256=driver.MANIFEST_SHA, additional_plugin_identities=[], input_hashing='ContentRequired',
        incremental=False, max_concurrency=1, native_statistical_factories_registered=False,
        current_daemon_verified=False, scientific_authorized=False, g0_granted=False,
        first_run=dict(nodes=nodes, ok=positive, errors={} if positive else {'analysis': error}))


class SingscoreRequalificationTests(unittest.TestCase):
    def test_exact_four_node_three_edge_job_has_no_method_parameters(self):
        job = driver.job_for(Path('/toy/case'), Path('/toy/source'))
        self.assertEqual(len(job['nodes']), 4)
        self.assertEqual(len(job['edges']), 3)
        self.assertEqual(job['nodes'][-1], dict(id='analysis', kind='singscore_bspec', spec={}))
        self.assertEqual({edge['to_port'] for edge in job['edges']}, {0, 1, 2})
        self.assertEqual(job['script_sha256'], {'scripts/singscore.sh': driver.SCRIPT_SHA})
        self.assertTrue(all(node['spec']['hash_content'] is True for node in job['nodes'][:3]))

    def test_complete_typed_positive_report(self):
        nodes = driver.validate_report(report_fixture(), {'engine_commit': 'toy-verified-engine'}, positive=True)
        self.assertEqual(set(nodes), {'input0', 'input1', 'input2', 'analysis'})

    def test_negative_report_requires_exact_method_exit_and_no_ports(self):
        report = report_fixture(False)
        driver.validate_report(report, {'engine_commit': 'toy-verified-engine'}, positive=False)
        for value in (2, 125, 137, None, True):
            changed = copy.deepcopy(report)
            changed['first_run']['nodes'][-1]['execution']['exit_code'] = value
            with self.subTest(value=value), self.assertRaises(REFUSAL):
                driver.validate_report(changed, {'engine_commit': 'toy-verified-engine'}, positive=False)
        changed = copy.deepcopy(report)
        changed['first_run']['nodes'][-1]['port_assignments'] = {'2': {}}
        with self.assertRaises(REFUSAL):
            driver.validate_report(changed, {'engine_commit': 'toy-verified-engine'}, positive=False)

    def test_actual_error_map_not_a_list(self):
        report = report_fixture(False)
        report['first_run']['errors'] = [report['first_run']['nodes'][-1]['error']]
        with self.assertRaises(REFUSAL):
            driver.validate_report(report, {'engine_commit': 'toy-verified-engine'}, positive=False)

    def test_source_identity_and_authority_cannot_drift(self):
        for field, value in [('engine_source_revision', 'wrong'), ('original_manifest_sha256', '0' * 64),
                             ('scientific_authorized', True), ('current_daemon_verified', True), ('g0_granted', True),
                             ('max_concurrency', True), ('input_hashing', 'Metadata')]:
            report = report_fixture()
            report[field] = value
            with self.subTest(field=field), self.assertRaises(REFUSAL):
                driver.validate_report(report, {'engine_commit': 'toy-verified-engine'}, positive=True)

    def test_unknown_or_duplicate_node_cannot_replace_input(self):
        for identifier in ('input0', 'foreign'):
            report = report_fixture()
            report['first_run']['nodes'][1]['id'] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(REFUSAL):
                driver.validate_report(report, {'engine_commit': 'toy-verified-engine'}, positive=True)

    def input_fixture(self, directory):
        work = directory / 'case'
        work.mkdir()
        scratch = directory / 'scratch'
        staging = scratch / 'aa' / ('b' * 62) / '.autonomics/inputs'
        staging.mkdir(parents=True)
        nodes = {'analysis': {'inputs': []}}
        for port, name in enumerate(driver.INPUT_NAMES):
            source = work / name
            source.write_text('toy-' + str(port) + '\n')
            identity = driver.fact(source)
            fingerprint = dict(size=identity['bytes'], content_hash='sha256:' + identity['sha256'])
            nodes['input' + str(port)] = dict(port_assignments={'0': dict(path='vfs:///' + name,
                format='tsv', fingerprint=dict(fingerprint))})
            nodes['analysis']['inputs'].append(dict(kind='File', to_port=port, **{'from': 'input' + str(port)},
                from_port=0, path='vfs:///' + name, fingerprint=dict(fingerprint)))
            (staging / ('input-' + str(port) + '.tsv')).symlink_to(source)
        return work, nodes, scratch, staging

    def test_direct_owned_staged_symlinks_are_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, nodes, scratch, staging = self.input_fixture(Path(temporary))
            self.assertEqual(len(driver.checked_inputs(work, nodes, scratch, staging.parent.parent)), 3)

    def test_input_fingerprint_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, nodes, scratch, staging = self.input_fixture(Path(temporary))
            nodes['analysis']['inputs'][1]['fingerprint']['content_hash'] = 'sha256:' + '0' * 64
            with self.assertRaises(REFUSAL):
                driver.checked_inputs(work, nodes, scratch, staging.parent.parent)

    def test_indirect_staged_link_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work, nodes, scratch, staging = self.input_fixture(root)
            alias = root / 'alias.tsv'
            alias.symlink_to(work / 'matrix.tsv')
            staged = staging / 'input-0.tsv'
            staged.unlink()
            staged.symlink_to(alias)
            with self.assertRaises(REFUSAL):
                driver.checked_inputs(work, nodes, scratch, staging.parent.parent)

    def test_timeout_stdout_and_stderr_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            error = subprocess.TimeoutExpired(['toy'], 1, output=b'partial stdout', stderr=b'specific diagnostic')
            with mock.patch.object(driver.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
                driver.run_recorded(['toy'], root, 'runner')
            self.assertEqual((root / 'runner.stderr').read_bytes(), b'specific diagnostic')
            self.assertEqual(json.loads((root / 'runner-exit.json').read_text()), dict(actual_exit=None, timed_out=True))

    def test_failed_method_logs_are_preserved_without_source_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / 'work'
            work.mkdir()
            scratch = root / 'scratch'
            method = scratch / 'ab' / ('c' * 62)
            logs = method / '.autonomics/logs'
            logs.mkdir(parents=True)
            (logs / 'stderr.log').write_text('specific refusal\n')
            (method / 'singscore.log').write_text('ERROR: specific refusal\n')
            (method / 'raw-input.tsv').write_text('never archive this payload\n')
            records = driver.preserve_logs(work, scratch)
            self.assertEqual(len(records), 2)
            self.assertEqual((work / 'preserved-logs/.autonomics__logs__stderr.log').read_text(), 'specific refusal\n')
            self.assertFalse(list((work / 'preserved-logs').rglob('raw-input.tsv')))

    def test_diagnostic_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / 'work'
            work.mkdir()
            logs = root / 'scratch/ab' / ('c' * 62) / '.autonomics/logs'
            logs.mkdir(parents=True)
            foreign = root / 'foreign'
            foreign.write_text('foreign content')
            (logs / 'stderr.log').symlink_to(foreign)
            with self.assertRaises(REFUSAL):
                driver.preserve_logs(work, root / 'scratch')
            self.assertEqual(foreign.read_text(), 'foreign content')

    def test_original_refusal_requires_one_exact_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'node.stderr.txt'
            source.write_text('ERROR: expected\n')
            self.assertEqual(driver.expected_error(root), 'ERROR: expected')
            source.write_text('ERROR: expected\nERROR: ambiguous\n')
            with self.assertRaises(REFUSAL):
                driver.expected_error(root)

    def proxy_fixture(self, temporary):
        root = Path(temporary)
        captured = root / 'captured.json'
        shim = root / 'managed-shim'
        shim.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
                        'Path(' + repr(str(captured)) + ').write_text(json.dumps(sys.argv[1:]))\n')
        shim.chmod(0o700)
        output = root / 'evidence'
        output.mkdir()
        workspace = root / 'official-plugin-container-workspaces/case/aa' / ('b' * 62)
        (workspace / '.autonomics').mkdir(parents=True)
        script = workspace / '.autonomics/script'
        script.write_text('TOY_ONLY_NOT_SCIENCE\n')
        with mock.patch.object(driver, 'SCRIPT_SHA', hashlib.sha256(script.read_bytes()).hexdigest()):
            launcher, _ = driver.install_launcher([str(shim), '--root', '/toy/store'], root, output)
        arguments = ['create', '--name', 'toy-container', '--cpus', '2', '--memory', '2000000000', '--read-only',
            '--pull', 'never', '--network', 'none', '--mount', 'type=bind,source=' + str(workspace) + ',destination=/work,rw=true']
        variables = dict(AUTONOMICS_SCRIPT='/work/.autonomics/script', AUTONOMICS_WORKDIR='/work',
            AUTONOMICS_INPUT_COUNT='3', AUTONOMICS_OUTPUT_COUNT='3')
        for port in range(3):
            variables['AUTONOMICS_INPUT' + str(port)] = '/work/.autonomics/inputs/input-' + str(port) + '.tsv'
            variables['AUTONOMICS_OUTPUT' + str(port)] = '/work/output' + str(port)
        for key, value in variables.items():
            arguments += ['--env', key + '=' + value]
        arguments.append(driver.IMAGE)
        return launcher, arguments, captured, output, script

    def test_real_proxy_subprocess_forwards_exact_backend_and_resources(self):
        original_path = os.environ.get('PATH')
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ):
            launcher, arguments, captured, output, _ = self.proxy_fixture(temporary)
            result = subprocess.run([str(launcher), *arguments], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(captured.read_text()), ['--root', '/toy/store', *arguments])
            record = json.loads((output / 'actual-container-create.jsonl').read_text())
            self.assertEqual(record['actual_memory_bytes'], 2000000000)
            self.assertFalse(record['resources_overridden'])
        self.assertEqual(os.environ.get('PATH'), original_path)

    def test_proxy_rejects_backend_override_bad_script_and_repeated_readonly(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ):
            launcher, arguments, captured, _, script = self.proxy_fixture(temporary)
            for changed in (["--root", '/foreign', *arguments], [*arguments[:-1], '--read-only', driver.IMAGE]):
                result = subprocess.run([str(launcher), *changed], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(captured.exists())
            script.write_text('wrong source\n')
            result = subprocess.run([str(launcher), *arguments], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(captured.exists())

    def test_two_real_proxy_creates_emit_two_strict_jsonl_records(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ):
            launcher, arguments, _, output, _ = self.proxy_fixture(temporary)
            for name in ('toy-first', 'toy-second'):
                changed = list(arguments)
                changed[changed.index('--name') + 1] = name
                result = subprocess.run([str(launcher), *changed], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            raw = (output / 'actual-container-create.jsonl').read_text()
            self.assertTrue(raw.endswith('\n'))
            rows = [driver.strict_json(line) for line in raw.splitlines()]
            self.assertEqual([row['run_name'] for row in rows], ['toy-first', 'toy-second'])
            self.assertNotIn('\\n', raw)

    def test_staging_must_belong_to_the_actual_create_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work, nodes, scratch, staging = self.input_fixture(root)
            other = scratch / 'ab' / ('d' * 62)
            other.mkdir(parents=True)
            with self.assertRaises(REFUSAL):
                driver.checked_inputs(work, nodes, scratch, other)

    def test_official_comparator_is_whole_object_and_six_mutants(self):
        source = (driver.ROOT / 'tools/verify_singscore_joined.R').read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), driver.VERIFIER_SHA)
        self.assertIn('identical(actual, complete)', source)
        for field in ('group', 'TotalScore', 'extra_field', 'class', 'row_names', 'nonfinite'):
            self.assertIn('"' + field + '"', source)
        self.assertIn('last-first+1L==31L', driver.AST_AND_PACKAGE)
        self.assertIn('identical(list(functions=functions,methods=methods),expected)', driver.AST_AND_PACKAGE)

    def test_graph_controls_run_actual_construction_not_early_validate_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, output = root / 'fixture', root / 'output'
            fixture.mkdir()
            output.mkdir()
            for name in driver.INPUT_NAMES:
                (fixture / name).write_text('toy\n')
            commands = []

            def refuse(command, work, label):
                commands.append(command)
                message = (b'PortDisconnected { node: "analysis", port: 2 }' if work.name == 'missing-metadata-edge'
                           else b'unknown parameter unexpected_free_parameter')
                return subprocess.CompletedProcess(command, 1, b'', message)

            with mock.patch.object(driver, 'run_recorded', side_effect=refuse):
                records = driver.graph_controls(Path('/toy/runner'), root / 'source', fixture, output)
            self.assertEqual(len(records), 2)
            self.assertTrue(all('--validate-job' not in command for command in commands))
            self.assertTrue(all(record['actual_method_execution'] is False for record in records))

    def test_graph_refusal_does_not_accept_arbitrary_nonzero_or_stderr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, output = root / 'fixture', root / 'output'
            fixture.mkdir()
            output.mkdir()
            for name in driver.INPUT_NAMES:
                (fixture / name).write_text('toy\n')
            failure = subprocess.CompletedProcess([], 137, b'', b'out of memory')
            with mock.patch.object(driver, 'run_recorded', return_value=failure), self.assertRaises(REFUSAL):
                driver.graph_controls(Path('/toy/runner'), root / 'source', fixture, output)

    def test_missing_or_modified_pinned_helper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'tools/helper.py'
            source.parent.mkdir()
            source.write_text('TOY_HELPER = True\n')
            pins = {'tools/helper.py': hashlib.sha256(source.read_bytes()).hexdigest()}
            with mock.patch.object(driver, 'HELPER_PINS', pins):
                before = driver.helper_source_facts(root)
                self.assertEqual(set(before), set(pins))
                source.write_text('TOY_HELPER = False\n')
                with self.assertRaises(ValueError):
                    driver.helper_source_facts(root)
                source.unlink()
                with self.assertRaises(FileNotFoundError):
                    driver.helper_source_facts(root)

    def test_helper_snapshot_requires_exact_bytes_and_no_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'tools/helper.py'
            source.parent.mkdir()
            source.write_text('TOY_HELPER = True\n')
            pins = {'tools/helper.py': hashlib.sha256(source.read_bytes()).hexdigest()}
            with mock.patch.object(driver, 'HELPER_PINS', pins):
                before = driver.helper_source_facts(root)
                snapshot = root / 'snapshot'
                copies = driver.snapshot_helpers(snapshot, before, root)
                self.assertEqual(source.read_bytes(), (snapshot / 'tools/helper.py').read_bytes())
                self.assertEqual(copies, driver.helper_source_facts(snapshot))
                (snapshot / 'tools/helper.py').write_text('CHANGED\n')
                with self.assertRaises(ValueError):
                    driver.helper_source_facts(snapshot)
                source.unlink()
                source.symlink_to(snapshot / 'tools/helper.py')
                with self.assertRaises(ValueError):
                    driver.helper_source_facts(root)

    def test_exact_sdk_si_memory_is_not_iec_gib(self):
        self.assertEqual(driver.MANIFEST_MEMORY, '2g')
        self.assertEqual(driver.METHOD_MEMORY_BYTES, 2_000_000_000)
        self.assertNotEqual(driver.METHOD_MEMORY_BYTES, 2 * 1024**3)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ):
            launcher, arguments, captured, output, _ = self.proxy_fixture(temporary)
            changed = list(arguments)
            changed[changed.index('--memory') + 1] = '2147483648'
            result = subprocess.run([str(launcher), *changed], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Unexpected original singscore resources', result.stderr)
            self.assertFalse(captured.exists())
            observed = driver.strict_json((output / 'observed-create-declarations.jsonl').read_text())
            self.assertEqual(observed['memory'], '2147483648')
            self.assertTrue(observed['managed_backend_not_yet_invoked'])
            self.assertFalse((output / 'actual-container-create.jsonl').exists())

    def test_zero_created_failure_is_not_started_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output'
            output.mkdir()
            (output / 'observed-create-declarations.jsonl').write_text('{"memory":"wrong"}\n')
            primary = ValueError('original specific source failure')
            observations = driver.finalize_stoppage(['/toy/shim'], root, output, primary)
            self.assertEqual(observations, [])
            value = json.loads((output / 'container-not-started.json').read_text())
            self.assertEqual(value['status'], 'NOT_STARTED_NO_MANAGED_CREATE_INTENTS_NOT_SUCCESS')
            self.assertFalse(value['container_stoppage_certified'])
            self.assertFalse(value['method_execution_proven'])
            self.assertEqual(value['proxy_observed_declarations'], 1)

    def test_runner_postcheck_uses_consistent_identity_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'toy-runner'
            source.write_text('not executable scientific code\n')
            expected = driver.admission.file_identity(source)
            self.assertNotEqual(driver.fact(source), expected)
            self.assertTrue(driver.runner_identity_unchanged(source, expected))
            source.write_text('changed\n')
            self.assertFalse(driver.runner_identity_unchanged(source, expected))

    def test_progress_checkpoints_are_unique_without_replacing_previous_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = dict(case='toy-first', actual_nodes=4)
            second = dict(case='toy-second', actual_nodes=4)
            driver.write_case_checkpoint(root, [first])
            initial = (root / 'case-checkpoints/001.json').read_bytes()
            driver.write_case_checkpoint(root, [first, second])
            self.assertEqual((root / 'case-checkpoints/001.json').read_bytes(), initial)
            current = json.loads((root / 'case-checkpoints/002.json').read_text())
            self.assertEqual(current['actual_completed_cases'], 2)
            self.assertEqual(current['completed_case_ids'], ['toy-first', 'toy-second'])
            self.assertFalse(current['complete_inventory_proven'])
            self.assertFalse((root / 'completed-cases.json').exists())
            with self.assertRaises(FileExistsError):
                driver.write_case_checkpoint(root, [first, second])

    def test_complete_31_case_host_lifecycle_uses_unique_paths_with_mocked_method_backend(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ):
            root = Path(temporary)
            permanent, scratch, reference = root / 'permanent', root / 'scratch', root / 'reference'
            permanent.mkdir()
            scratch.mkdir()
            methods = {node.name for node in driver.ast.walk(driver.ast.parse(
                (driver.ROOT / 'plugins/singscore/tests/test_contract.py').read_text()))
                if isinstance(node, driver.ast.FunctionDef) and node.name.startswith('test_')}
            cases = sorted(methods - {driver.EXISTING}) + ['official-author-example']
            self.assertEqual(len(cases), 31)
            for case in cases:
                fixture = reference / ('after-official-example-dag-final' if case == 'official-author-example' else 'after/' + case)
                fixture.mkdir(parents=True)
                for filename in driver.INPUT_NAMES:
                    (fixture / filename).write_text('SYNTHETIC_HOST_LOOP_TOY_ONLY\n')
            build_directory = root / '.local/state/autonomics/validation-archives' / driver.BUILD_SESSION / 'artifacts/build'
            build_directory.mkdir(parents=True)
            runner = build_directory / 'official_plugin_dag'
            runner.write_bytes(b'NOT_A_REAL_SDK_RUNNER\n')
            record = build_directory / 'build-record.json'
            record.write_text('{}\n')
            os.environ['AUTONOMICS_VALIDATION_PERMANENT'] = str(permanent)
            os.environ['TMPDIR'] = str(scratch)
            seen = []

            def fake_method(unused_runner, unused_build, work, unused_source, unused_definition, unused_original, unused_previous):
                seen.append(work.name)
                value = dict(case=work.name, positive=work.name in driver.POSITIVE,
                    actual_nodes=4, actual_edges=3, mock_method_and_backend_not_a_node_proof=True)
                driver.write(work / 'verification.json', value)
                created = dict(run_name='toy-' + work.name, actual_cpus=2,
                    actual_memory_bytes=driver.METHOD_MEMORY_BYTES, resources_overridden=False,
                    staged_script_sha256=driver.SCRIPT_SHA, input_count=3, output_count=3)
                with (work.parent / 'actual-container-create.jsonl').open('a') as handle:
                    handle.write(json.dumps(created) + '\n')
                return value

            command = ['toy-driver', '--runner', str(runner), '--build-record', str(record),
                '--reference', str(reference), '--runtime-backend', 'default', '--execute']
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(driver.Path, 'home', return_value=root))
                stack.enter_context(mock.patch.object(driver.sys, 'argv', command))
                stack.enter_context(mock.patch.object(driver, 'check_loaded_helpers', return_value=[]))
                stack.enter_context(mock.patch.object(driver.managed, 'cgroup_observation', return_value={'memory_max_bytes': 2 * 1024**3}))
                stack.enter_context(mock.patch.object(driver.shutil, 'disk_usage', return_value=SimpleNamespace(free=3 * 1024**3)))
                stack.enter_context(mock.patch.object(driver.admission, 'checked_build', return_value=({'engine_commit': 'TOY_ONLY'}, {})))
                stack.enter_context(mock.patch.object(driver, 'RUNNER_SHA', hashlib.sha256(runner.read_bytes()).hexdigest()))
                stack.enter_context(mock.patch.object(driver, 'checked_reference', return_value=cases))
                stack.enter_context(mock.patch.object(driver, 'checked_prior', return_value=reference))
                stack.enter_context(mock.patch.object(driver, 'runtime_backend', return_value=(['/toy/fake-backend'], {'toy_only': True})))
                stack.enter_context(mock.patch.object(driver, 'graph_controls', return_value=[{'toy': 1}, {'toy': 2}]))
                stack.enter_context(mock.patch.object(driver, 'graph', side_effect=fake_method))
                stack.enter_context(mock.patch.object(driver, 'preexisting_control', return_value={'toy_only': True}))
                stack.enter_context(mock.patch.object(driver, 'official_readback', return_value={'toy_only': True}))
                stack.enter_context(mock.patch.object(driver, 'finalize_stoppage', return_value=[{'toy_only': True}] * 33))
                with contextlib.redirect_stdout(io.StringIO()):
                    driver.main()
            output = permanent / 'singscore-publication-requalification'
            self.assertEqual(seen, cases)
            self.assertEqual(len(list((output / 'case-checkpoints').glob('*.json'))), 31)
            self.assertEqual(len(json.loads((output / 'completed-cases.json').read_text())), 31)
            self.assertEqual(json.loads((output / 'finalization.json').read_text())['secondary_errors'], [])
            self.assertTrue(all(json.loads(path.read_text())['mock_method_and_backend_not_a_node_proof'] is True
                                for path in output.glob('test_*/verification.json')))


if __name__ == '__main__':
    unittest.main()
