import ast
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

from tools import prove_ucell_h5ad_publication_requalification as proof


class UCellH5ADRequalificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def inventory(self):
        records = [dict(case=name, positive=name in proof.POSITIVES, actual_exit=0 if name in proof.POSITIVES else 2,
            nodes=2, edges=1, actual_task_receipts=2, actual_input_bindings=1, output_ports=2 if name in proof.POSITIVES else 0)
            for name in [*proof.POSITIVES, *proof.METHOD_REFUSALS]]
        direct = [dict(case=name, exact_refusal=True, actual_exit=3 if name == 'second-link-failure' else 2,
            actual_DAG_entered=False) for name in proof.DIRECT]
        preflight = [dict(case=name, exact_refusal=True, actual_exit=1, actual_DAG_entered=False) for name in proof.PREFLIGHTS]
        rows = [dict(case=name, finite_values_checked=148146 if index == 0 else 1,
            complete_AnnData_and_HDF5=True, complete_report_except_externally_revalidated_output_identity=True,
            numeric_atol=1e-12, numeric_rtol=0, G0=False) for index, name in enumerate(proof.POSITIVES)]
        comparison = dict(cases=rows, sealed_author_outputs_regenerated=False, explicit_HDF5_dataset_shapes_checked=True)
        return records, direct, preflight, comparison

    def create_fixture(self):
        permanent = self.root / 'permanent'
        work = permanent / 'ucell-h5ad-publication-requalification/dense'
        work.mkdir(parents=True)
        (work / 'input.h5ad').write_bytes(b'EXPLICIT_NON_H5AD_INPUT_TOY')
        allowed = self.root / 'workspaces'
        workspace = allowed / 'dense/ab' / ('c' * 62)
        staging = workspace / '.autonomics/inputs'
        staging.mkdir(parents=True)
        (staging / 'input-0.h5ad').symlink_to(work / 'input.h5ad')
        (workspace / '.autonomics/script').write_bytes((proof.ROOT / 'plugins/ucell-h5ad/scripts/score.py').read_bytes())
        environment = dict(AUTONOMICS_INPUT_COUNT='1', AUTONOMICS_OUTPUT_COUNT='2', AUTONOMICS_INPUT0='/work/.autonomics/inputs/input-0.h5ad',
            AUTONOMICS_OUTPUT0='/work/output.h5ad', AUTONOMICS_OUTPUT1='/work/report.json',
            AUTONOMICS_WORKDIR='/work', AUTONOMICS_SCRIPT='/work/.autonomics/script', SC_P_JSON_GENE_SETS='{"one":["A"]}')
        arguments = ['create', '--name', 'autonomics-container-command-1-2', '--network', 'none',
            '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,nosuid,nodev', '--pull', 'missing',
            '--user', str(os.getuid()) + ':' + str(os.getgid()), '--userns', 'keep-id', '--read-only',
            '--shm-size', '1073741824', '--cpus', '2', '--memory', '8589934592', '--pids-limit', '512']
        for name, value in environment.items():
            arguments.extend(['--env', name + '=' + value])
        arguments.extend(['--mount', 'type=bind,source=' + str(workspace) + ',destination=/work,rw=true',
            '--mount', 'type=bind,source=' + str(work) + ',destination=' + str(work) + ',readonly',
            '--workdir', '/work', '--entrypoint', 'python', proof.IMAGE, '/work/.autonomics/script'])
        return permanent, work, allowed, workspace, arguments

    def test_complete_fifty_four_original_cases_and_two_extra_controls_are_preserved(self):
        self.assertEqual(len(proof.POSITIVES), 20)
        self.assertEqual(len(proof.METHOD_REFUSALS), 26)
        self.assertEqual(len(proof.DIRECT), 7)
        self.assertEqual(len(proof.PREFLIGHTS), 3)
        self.assertEqual(len(set(proof.POSITIVES) | set(proof.METHOD_REFUSALS) | proof.DIRECT | {'missing-gene-sets'}), 54)
        proof.validate_inventory(*self.inventory())

    def test_missing_duplicate_or_oom_method_cases_cannot_count_as_complete(self):
        for mode in ['missing', 'duplicate', 'oom', 'boolean-exit', 'missing-port', 'fake-count']:
            records, direct, preflight, comparison = self.inventory()
            if mode == 'missing':
                records.pop()
            elif mode == 'duplicate':
                records[-1] = copy.deepcopy(records[0])
            elif mode == 'oom':
                records[-1]['actual_exit'] = 137
            elif mode == 'boolean-exit':
                records[0]['actual_exit'] = False
            elif mode == 'missing-port':
                records[0]['output_ports'] = 0
            else:
                records[0]['actual_task_receipts'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                proof.validate_inventory(records, direct, preflight, comparison)

    def test_direct_or_preflight_skips_and_wrong_exits_cannot_be_accepted(self):
        for mode in ['direct-oom', 'direct-not-executed', 'missing-direct', 'preflight-zero', 'preflight-entered']:
            records, direct, preflight, comparison = self.inventory()
            if mode == 'direct-oom':
                direct[0]['actual_exit'] = 137
            elif mode == 'direct-not-executed':
                direct[0]['exact_refusal'] = False
            elif mode == 'missing-direct':
                direct.pop()
            elif mode == 'preflight-zero':
                preflight[0]['actual_exit'] = 0
            else:
                preflight[0]['actual_DAG_entered'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                proof.validate_inventory(records, direct, preflight, comparison)

    def test_complete_object_comparison_cannot_drop_cases_shapes_reports_or_tolerances(self):
        for mode in ['missing', 'duplicate', 'zero', 'report', 'shape', 'rtol', 'boolean-rtol', 'G0', 'regenerated']:
            records, direct, preflight, comparison = self.inventory()
            if mode == 'missing':
                comparison['cases'].pop()
            elif mode == 'duplicate':
                comparison['cases'][-1] = copy.deepcopy(comparison['cases'][0])
            elif mode == 'zero':
                comparison['cases'][0]['finite_values_checked'] = 0
            elif mode == 'report':
                comparison['cases'][0]['complete_report_except_externally_revalidated_output_identity'] = False
            elif mode == 'shape':
                comparison['explicit_HDF5_dataset_shapes_checked'] = False
            elif mode == 'rtol':
                comparison['cases'][0]['numeric_rtol'] = 1e-8
            elif mode == 'boolean-rtol':
                comparison['cases'][0]['numeric_rtol'] = False
            elif mode == 'G0':
                comparison['cases'][0]['G0'] = True
            else:
                comparison['sealed_author_outputs_regenerated'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                proof.validate_inventory(records, direct, preflight, comparison)

    def test_reviewed_current_source_and_unchanged_nonpublication_ast_are_literal(self):
        current = proof.ROOT / 'plugins/ucell-h5ad/scripts/score.py'
        self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), proof.SCRIPT_SHA)
        self.assertEqual(proof.nonpublication_ast(current.read_bytes()), proof.NON_PUBLICATION_AST_SHA)
        self.assertEqual(hashlib.sha256((proof.ROOT / 'plugins/ucell-h5ad/manifest.toml').read_bytes()).hexdigest(), proof.MANIFEST_SHA)
        self.assertNotEqual(proof.SCRIPT_SHA, proof.BASELINE_SHA)

    def test_regression_receipt_uses_actual_fifty_two_ids_and_exact_twenty_three_h5ad_cases(self):
        archives = self.root / 'archives'
        archive = archives / proof.REGRESSION_SESSION
        root = archive / 'artifacts/permanent/b-publication-ownership'
        root.mkdir(parents=True)
        (archive / 'SESSION.json').write_text(json.dumps(dict(launcher_exit_status=0)))
        ids = ['tests.test_ucell_h5ad_publication.Case.test_' + str(index) for index in range(23)]
        ids += ['other.Case.test_' + str(index) for index in range(29)]
        execution = dict(actual_test_ids=ids, required_test_ids=ids, tests_run=52, complete=True, failures=0, errors=0, skipped=0)
        (root / 'tests-execution.json').write_text(json.dumps(execution))
        (root / 'verification.json').write_text(json.dumps(dict(current_sources={
            'plugins/ucell-h5ad/scripts/score.py': dict(bytes=19054, sha256=proof.SCRIPT_SHA)},
            official_UCell_or_singscore_computation_executed=False, g0_granted=False)))
        verified = dict(artifact_root=str(archive / 'artifacts'), positive_worker_exit_verified=True, files=14, bytes=1000)
        with mock.patch.object(proof, 'verify_archive', return_value=verified):
            result = proof.checked_regression(archives)
            self.assertEqual(len(result['actual_h5ad_tests']), 23)
            execution['actual_test_ids'] = [*ids[:-1], ids[0]]
            (root / 'tests-execution.json').write_text(json.dumps(execution))
            with self.assertRaises(ValueError):
                proof.checked_regression(archives)

    def test_explicit_source_upgrade_rejects_scoring_body_changes_without_weakening_old_hash(self):
        old = b'value = 1\ndef publish():\n    return 1\n'
        current = b'value = 1\ndef publish():\n    return 2\n'
        with mock.patch.multiple(proof, BASELINE_SHA=hashlib.sha256(old).hexdigest(), SCRIPT_SHA=hashlib.sha256(current).hexdigest(),
                NON_PUBLICATION_AST_SHA=proof.nonpublication_ast(old)):
            proof.validate_source_upgrade(old, current)
            changed = current.replace(b'value = 1', b'value = 2')
            with mock.patch.object(proof, 'SCRIPT_SHA', hashlib.sha256(changed).hexdigest()), self.assertRaises(ValueError):
                proof.validate_source_upgrade(old, changed)
            with self.assertRaises(ValueError):
                proof.validate_source_upgrade(current, current)

    def test_reference_paths_and_changed_seals_are_rejected_without_partial_qualification(self):
        for name in ['/absolute', '../escape', 'a/../escape', 'a//b', './name', 'back\\slash', '']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                proof.ordinary_member(name)
        with mock.patch.object(proof, 'REFERENCE', self.root):
            (self.root / 'SEALED_FILES.json').write_bytes(b'{}')
            (self.root / 'FINAL_VERIFICATION.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'Both original reference seals'):
                proof.checked_reference(self.root)

    def test_original_resource_declarations_and_typed_file_binding_remain_in_the_job(self):
        job = proof.job_for(self.root, self.root / 'source', {'gene_sets': '{"one":["A+"]}'})
        self.assertEqual(job['scope'], proof.SCOPE)
        self.assertEqual(job['script_sha256'], {'scripts/score.py': proof.SCRIPT_SHA})
        self.assertEqual(job['nodes'][0]['spec'], dict(path='vfs:///input.h5ad', format='h5ad', hash_content=True))
        self.assertEqual(job['nodes'][1]['spec'], {'gene_sets': '{"one":["A+"]}'})
        self.assertEqual(job['additional_plugins'], [])
        self.assertEqual(job['bundles'], [])

    def test_proxy_changes_only_pull_and_preserves_real_default_readonly_and_eight_gib(self):
        permanent, work, allowed, workspace, arguments = self.create_fixture()
        before = list(arguments)
        with mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)):
            changed, observed = proof.prepare_create(arguments, allowed)
        self.assertEqual(arguments, before)
        self.assertEqual([index for index, pair in enumerate(zip(before, changed)) if pair[0] != pair[1]], [before.index('--pull') + 1])
        self.assertEqual(changed[changed.index('--pull') + 1], 'never')
        self.assertEqual(observed['cpus'], '2')
        self.assertEqual(observed['memory'], '8589934592')
        self.assertTrue(observed['read_only_rootfs'])
        self.assertFalse(observed['original_manifest_resources_certified'])

    def test_proxy_rejects_duplicate_unknown_equals_style_or_missing_sdk_flags(self):
        permanent, work, allowed, workspace, original = self.create_fixture()
        for mode in ['duplicate', 'unknown', 'equals-style', 'missing', 'wrong-image', 'writable-root', 'foreign-mount']:
            arguments = list(original)
            if mode == 'duplicate':
                arguments[1:1] = ['--memory', '8589934592']
            elif mode == 'unknown':
                arguments[1:1] = ['--privileged']
            elif mode == 'equals-style':
                arguments[1:1] = ['--cpus=99']
            elif mode == 'missing':
                position = arguments.index('--network')
                del arguments[position:position + 2]
            elif mode == 'wrong-image':
                arguments[-2] = 'other@sha256:' + 'f' * 64
            elif mode == 'writable-root':
                arguments.remove('--read-only')
            else:
                arguments[1:1] = ['--mount', 'type=bind,source=/etc,destination=/foreign,readonly']
            with self.subTest(mode=mode), mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent)), self.assertRaises(ValueError):
                proof.prepare_create(arguments, allowed)

    def test_default_staged_link_requires_its_exact_synthetic_input_and_full_hash(self):
        permanent, work, allowed, workspace, arguments = self.create_fixture()
        identity = proof.fact(work / 'input.h5ad')
        bindings = [dict(kind='File', **{'from': 'input'}, from_port=0, to_port=0, path='vfs:///input.h5ad',
            fingerprint=dict(size=identity['bytes'], content_hash=None))]
        proof.check_staged_input(work, workspace, bindings)
        bindings[0]['fingerprint']['content_hash'] = 'sha256:' + '0' * 64
        with self.assertRaises(ValueError):
            proof.check_staged_input(work, workspace, bindings)
        bindings[0]['fingerprint']['content_hash'] = None
        link = workspace / '.autonomics/inputs/input-0.h5ad'
        link.unlink()
        link.write_bytes((work / 'input.h5ad').read_bytes())
        with self.assertRaises(ValueError):
            proof.check_staged_input(work, workspace, bindings)

    def test_timeout_partial_streams_are_evidence_not_a_zero_exit(self):
        error = subprocess.TimeoutExpired(['toy'], 1, output=b'partial stdout', stderr=b'partial stderr')
        with mock.patch.object(proof.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
            proof.captured(['toy'], self.root, 'runner')
        self.assertEqual((self.root / 'runner.stdout').read_bytes(), b'partial stdout')
        self.assertEqual((self.root / 'runner.stderr').read_bytes(), b'partial stderr')
        report = json.loads((self.root / 'runner-execution.json').read_bytes())
        self.assertIsNone(report['actual_exit'])
        self.assertTrue(report['timed_out'])

    def test_only_bounded_actual_method_logs_are_copied_on_a_failed_case(self):
        scratch = self.root / 'scratch'
        logs = scratch / 'ab' / ('c' * 62) / '.autonomics/logs'
        logs.mkdir(parents=True)
        (logs / 'stderr.log').write_bytes(b'ACTUAL SYNTHETIC METHOD DIAGNOSTIC')
        inputs = logs.parent / 'inputs'
        inputs.mkdir()
        (inputs / 'input-0.h5ad').write_bytes(b'NOT A LOG OR A COMPLETE WORKSPACE COPY')
        copied = proof.capture_method_logs(scratch, self.root / 'diagnostics')
        self.assertEqual(len(copied), 1)
        self.assertFalse(any(path.name == 'input-0.h5ad' for path in (self.root / 'diagnostics').rglob('*')))
        self.assertFalse(json.loads((self.root / 'diagnostics/captured.json').read_bytes())['complete_workspace_copied'])

    def test_reader_source_preserves_original_tolerances_and_adds_exact_dataset_shape(self):
        ast.parse(proof.COMPARISON)
        self.assertIn("actual[key].shape==expected[key].shape", proof.COMPARISON)
        self.assertIn('records.append(compare(directory))', proof.COMPARISON)
        self.assertIn('sealed_author_outputs_regenerated=False', proof.COMPARISON)
        self.assertFalse(any(value is None for value in proof.SOURCES.values()))

    def helper_fixture(self):
        base = self.root / 'helper-originals'
        path = base / 'tools/toy_helper.py'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'def toy_helper():\n    return "TECHNICAL_ONLY"\n')
        pins = {'tools/toy_helper.py': hashlib.sha256(path.read_bytes()).hexdigest()}
        return base, path, pins

    def test_pinned_helper_snapshot_uses_full_original_and_separate_snapshot_identity_schemas(self):
        base, path, pins = self.helper_fixture()
        with mock.patch.object(proof, 'HELPER_PINS', pins):
            before = proof.helper_source_facts(base)
            snapshots = proof.snapshot_helpers(self.root / 'helper-snapshots', before, base)
            self.assertEqual(proof.helper_source_facts(base), before)
            self.assertEqual(proof.helper_source_facts(self.root / 'helper-snapshots'), snapshots)
            for name in pins:
                self.assertNotEqual(before[name]['identity'], snapshots[name]['identity'])
                self.assertEqual({key: before[name][key] for key in ['bytes', 'sha256']},
                    {key: snapshots[name][key] for key in ['bytes', 'sha256']})

    def test_missing_changed_or_aliased_helpers_are_refused_before_acceptance(self):
        base, path, pins = self.helper_fixture()
        original = path.read_bytes()
        with mock.patch.object(proof, 'HELPER_PINS', pins):
            before = proof.helper_source_facts(base)
            path.write_bytes(original.replace(b'TECHNICAL_ONLY', b'MODIFIED_VALUE'))
            with self.assertRaises(ValueError):
                proof.helper_source_facts(base)
            with self.assertRaises(ValueError):
                proof.snapshot_helpers(self.root / 'bad-snapshots', before, base)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                proof.helper_source_facts(base)
            foreign = self.root / 'foreign-source.py'
            foreign.write_bytes(original)
            path.symlink_to(foreign)
            with self.assertRaises(ValueError):
                proof.helper_source_facts(base)

    def test_incomplete_or_mutated_helper_snapshots_do_not_inherit_original_source_qualification(self):
        base, path, pins = self.helper_fixture()
        with mock.patch.object(proof, 'HELPER_PINS', pins):
            before = proof.helper_source_facts(base)
            with self.assertRaises(ValueError):
                proof.snapshot_helpers(self.root / 'missing-snapshots', {}, base)
            snapshot = self.root / 'helper-snapshot'
            proof.snapshot_helpers(snapshot, before, base)
            (snapshot / 'tools/toy_helper.py').write_bytes(b'MODIFIED SNAPSHOT')
            with self.assertRaises(ValueError):
                proof.helper_source_facts(snapshot)

    def test_actual_loaded_function_bindings_belong_to_all_pinned_call_path_sources(self):
        facts = proof.helper_source_facts()
        loaded = proof.check_loaded_helpers()
        self.assertEqual(set(facts), set(proof.HELPER_PINS))
        self.assertTrue({row['source'] for row in loaded}.issubset(facts))
        self.assertIn('tools/prove_frozen_a_harmonisation.py', {row['source'] for row in loaded})
        self.assertIn('tools/prove_current_ldsc.py', {row['source'] for row in loaded})
        with mock.patch.object(proof, 'expected_refusal', lambda *arguments: None), self.assertRaises(ValueError):
            proof.check_loaded_helpers()

    def synthetic_main(self, run_root, *, fail_second_method=False, fail_reference_postcheck=False):
        reference = run_root / 'synthetic-reference-not-a-scientific-golden'
        all_names = [*proof.POSITIVES, *proof.METHOD_REFUSALS, 'missing-gene-sets', *proof.DIRECT]
        for name in all_names:
            directory = reference / ('repaired-official-v1' if name in proof.POSITIVES else 'repaired-boundaries-v1') / name
            directory.mkdir(parents=True)
            (directory / 'input.h5ad').write_bytes(('NON_H5AD_LIFECYCLE_TOY_' + name).encode())
            (directory / 'request.json').write_text('{"one":["A"]}')
            (directory / 'report.json').write_bytes(b'{"NONSCIENTIFIC_MAIN_SIMULATION":true}')
            if name == 'h5ad-exists':
                (directory / 'output.h5ad').write_bytes(b'EXISTING TECHNICAL SENTINEL')
            (directory / 'fresh-author.h5ad').write_bytes(b'NOT_AN_AUTHOR_OBJECT_UNIT_CONTROL_ONLY')
            (directory / 'author-scores.tsv').write_bytes(b'NONNUMERICAL_UNIT_CONTROL')
            (directory / 'declared-node-script.execution.json').write_text(json.dumps(dict(
                exit=3 if name == 'second-link-failure' else 2,
                command=['python', '-c', "import runpy;runpy.run_path('/source/ucell-h5ad/scripts/score.py',run_name='__main__')"])))
            (directory / 'declared-node-script.stderr.txt').write_text('h5ad_ucell_score: explicit unit-only refusal\n')
        old_source = reference / 'plugin-source/plugins/ucell-h5ad/scripts/score.py'
        old_source.parent.mkdir(parents=True)
        old_source.write_bytes(b'UNIT_ONLY_NOT_A_QUALIFIED_BASELINE')
        permanent, temporary = run_root / 'permanent', run_root / 'temporary'
        permanent.mkdir()
        temporary.mkdir()
        output = permanent / 'ucell-h5ad-publication-requalification'
        build_root = Path.home() / '.local/state/autonomics/validation-archives' / proof.BUILD_SESSION / 'artifacts/permanent/locked-b-probe-build'
        original_runner_identity = dict(bytes=4, sha256='0' * 64, identity=['UNIT_ONLY_FULL_IDENTITY_SCHEMA'])
        intended = []
        methods = []
        stopped_counts = []
        def intent(label):
            intended.append(dict(token=str(len(intended)), label=label, backend=['--cgroup-manager=cgroupfs']))
            (permanent / 'container-intents.json').write_text(json.dumps(dict(session='unit-only', intents=intended)))
        def runner_copy(original, target):
            self.assertEqual(original, build_root / 'official_plugin_dag')
            runner = target / 'official_plugin_dag'
            runner.write_bytes(b'UNIT_NOT_AN_EXECUTABLE')
            return runner, original_runner_identity
        def launch(prefix, target, destination, allowed):
            (destination / 'actual-creates').mkdir()
            return dict(os.environ)
        def receipts(work, nodes):
            result = {name: dict(status=node['status']) for name, node in nodes.items()}
            proof.write(work / 'task-receipts-verification.json', result)
            return result
        def external(command, **keywords):
            if command[0] == str(temporary / 'official_plugin_dag'):
                job = json.loads(Path(command[-1]).read_bytes())
                work = Path(job['run_root'])
                name = work.name
                if name in proof.PREFLIGHTS:
                    marker = ('node `h5ad_ucell_score`: missing required param `gene_sets`' if name == 'missing-gene-sets'
                        else 'node `h5ad_ucell_score`: unknown param `unexpected_free_parameter`' if name == 'unknown-parameter'
                        else 'PortDisconnected { node: "analysis", port: 0 }')
                    return subprocess.CompletedProcess(command, 1, '', marker)
                intent(name)
                methods.append(name)
                if fail_second_method and len(methods) == 2:
                    return subprocess.CompletedProcess(command, 137, '', 'UNIT_ONLY_INFRASTRUCTURE_FAILURE')
                positive = name in proof.POSITIVES
                workspace = temporary / 'official-plugin-container-workspaces' / name / 'ab' / ('c' * 62)
                staging = workspace / '.autonomics/inputs'
                staging.mkdir(parents=True)
                (staging / 'input-0.h5ad').symlink_to(work / 'input.h5ad')
                logs = workspace / '.autonomics/logs'
                logs.mkdir()
                stderr = logs / 'stderr.log'
                stderr.write_text('h5ad_ucell_score: explicit unit-only refusal\n' if not positive else '')
                assigned = proof.fact(work / 'input.h5ad')
                source = dict(id='input', node_type='file_reference', reused=False, status='success', port_assignments={'0': dict(
                    path='vfs:///input.h5ad', format='h5ad', fingerprint=dict(content_hash='sha256:' + assigned['sha256']))})
                execution = dict(image=proof.IMAGE, image_digest=proof.IMAGE.split('@', 1)[1], exit_code=0 if positive else 2,
                    run_name='autonomics-container-command-1-' + str(len(methods)),
                    stderr_log=dict(path=str(stderr)), output_artifacts=[])
                method = dict(id='analysis', node_type='h5ad_ucell_score', reused=False, status='success' if positive else 'failed',
                    execution=execution, port_assignments={}, inputs=[dict(**{'from': 'input'}, from_port=0, to_port=0,
                        kind='File', path='vfs:///input.h5ad', fingerprint=dict(size=assigned['bytes'], content_hash=None))],
                    error=dict(message='h5ad_ucell_score: explicit unit-only refusal'))
                if positive:
                    for index, filename in enumerate(['output.h5ad', 'report.json']):
                        path = workspace / filename
                        path.write_bytes(b'NON_H5AD_UNIT_LIFECYCLE_RESULT' if index == 0 else b'{"UNIT_ONLY":true}')
                        method['port_assignments'][str(index)] = dict(path=str(path))
                        execution['output_artifacts'].append(dict(path=str(path)))
                report = dict(scope=proof.SCOPE, engine_source_revision=proof.ENGINE, plugin_name='ucell-h5ad',
                    original_manifest_sha256=proof.MANIFEST_SHA, additional_plugin_identities=[], max_concurrency=1,
                    incremental=False, input_hashing='ContentRequired', native_statistical_factories_registered=False,
                    current_daemon_verified=False, scientific_authorized=False, g0_granted=False,
                    first_run=dict(nodes=[source, method], errors={} if positive else {'analysis': {'message': 'unit-only'}}))
                proof.write(work / 'dag-report.json', report)
                proof.write(output / 'actual-creates' / (execution['run_name'] + '.json'), dict(name=execution['run_name'],
                    image=proof.IMAGE, script_sha256=proof.SCRIPT_SHA, cpus='2', memory='8589934592',
                    effective_pull='never', network='none', read_only_rootfs=True))
                return subprocess.CompletedProcess(command, 0, '', '')
            if '/proof/compare.py' in command:
                intent('unit-only-comparison-not-an-official-reader')
                comparison = self.inventory()[3]
                proof.write(output / 'whole-object-readback.json', comparison)
                return subprocess.CompletedProcess(command, 0, b'VERIFIED_COMPLETE_H5AD_CASES 20', b'')
            if 'run' in command:
                mount = next(value for value in command if value.endswith(':/work:rw'))
                work = Path(mount.removesuffix(':/work:rw'))
                intent('unit-only-direct-' + work.name)
                return subprocess.CompletedProcess(command, 3 if work.name == 'second-link-failure' else 2,
                    b'', b'h5ad_ucell_score: explicit unit-only refusal')
            raise AssertionError('Unexpected external command in unit-only main simulation')
        def stop(prefix, managed_permanent, destination, expected):
            self.assertEqual(managed_permanent, permanent)
            self.assertEqual(expected, len(intended))
            stopped_counts.append(expected)
            rows = [dict(token=str(index), actual_exit=0, remaining=0) for index in range(expected)]
            proof.write(destination / 'owned-container-stops.json', rows)
            return rows
        actual_read_text = Path.read_text
        def read_text(path, *arguments, **keywords):
            if path == Path('/proc/meminfo'):
                return 'MemAvailable: 8388608 kB\n'
            return actual_read_text(path, *arguments, **keywords)
        loaded = proof.check_loaded_helpers()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, AUTONOMICS_VALIDATION_PERMANENT=str(permanent),
                TMPDIR=str(temporary), AUTONOMICS_PODMAN_PROGRAM='/UNIT_ONLY_NO_RUNTIME'))
            stack.enter_context(mock.patch.object(proof, 'REFERENCE', reference))
            stack.enter_context(mock.patch.object(proof, 'check_loaded_helpers', return_value=loaded))
            stack.enter_context(mock.patch.object(proof, 'checked_reference',
                side_effect=[dict(UNIT_ONLY_REFERENCE=True), ValueError('UNIT_ONLY_REFERENCE_POSTCHECK_FAILURE')]
                if fail_reference_postcheck else None, return_value=dict(UNIT_ONLY_REFERENCE=True)))
            stack.enter_context(mock.patch.object(proof, 'checked_regression', return_value=dict(UNIT_ONLY_REGRESSION=True)))
            stack.enter_context(mock.patch.object(proof, 'validate_source_upgrade', return_value=dict(UNIT_ONLY_UPGRADE=True)))
            stack.enter_context(mock.patch.object(proof.admission, 'checked_build', return_value=(dict(engine_commit=proof.ENGINE), dict(runner_sha256=proof.RUNNER_SHA))))
            stack.enter_context(mock.patch.object(proof.admission, 'executable_copy', side_effect=runner_copy))
            stack.enter_context(mock.patch.object(proof.admission, 'file_identity', return_value=original_runner_identity))
            stack.enter_context(mock.patch.object(proof.admission, 'checked_task_receipts', side_effect=receipts))
            stack.enter_context(mock.patch.object(proof.admission, 'validate_memory_report', return_value=dict(UNIT_ONLY_MEMORY=True)))
            stack.enter_context(mock.patch.object(proof.runtime, 'cgroup_observation', return_value=dict(memory_max_bytes=2 * 1024**3)))
            stack.enter_context(mock.patch.object(proof.runtime, 'default_backend', return_value=dict(UNIT_ONLY_BACKEND=True)))
            stack.enter_context(mock.patch.object(proof, 'inspect_image', return_value=dict(UNIT_ONLY_IMAGE=True)))
            stack.enter_context(mock.patch.object(proof, 'launcher', side_effect=launch))
            stack.enter_context(mock.patch.object(proof, 'actual_ports', side_effect=lambda work, definition, method, scratch:
                [Path(method['port_assignments'][str(index)]['path']) for index in range(2)]))
            stack.enter_context(mock.patch.object(proof, 'stopped', side_effect=stop))
            stack.enter_context(mock.patch.object(proof.subprocess, 'run', side_effect=external))
            stack.enter_context(mock.patch.object(proof.shutil, 'disk_usage', return_value=SimpleNamespace(free=4 * 1024**3)))
            stack.enter_context(mock.patch.object(Path, 'read_text', read_text))
            stack.enter_context(mock.patch.object(proof.sys, 'argv', [str(proof.__file__), '--execute']))
            if fail_second_method:
                with self.assertRaisesRegex(ValueError, 'Runner infrastructure failed'):
                    proof.main()
            elif fail_reference_postcheck:
                with self.assertRaisesRegex(ValueError, 'Independent UCell runtime finalization failed'):
                    proof.main()
            else:
                proof.main()
        return output, intended, methods, stopped_counts

    def test_two_complete_main_lifecycle_simulations_do_not_rewrite_exclusive_checkpoints(self):
        for iteration in range(2):
            run_root = self.root / ('unit-only-run-' + str(iteration))
            run_root.mkdir()
            output, intents, methods, stopped = self.synthetic_main(run_root)
            result = json.loads((output / 'verification.json').read_bytes())
            self.assertEqual(len(methods), 46)
            self.assertEqual(len(intents), 54)
            self.assertEqual(stopped, [54])
            self.assertEqual(len(list(output.glob('*/runner-execution.json'))), 49)
            self.assertEqual(len(list(output.glob('*/direct-execution.json'))), 7)
            self.assertEqual(len(result['actual_DAG_cases']), 46)
            self.assertFalse((output / 'dangling-output/output.h5ad').exists())
            self.assertTrue((output / 'dangling-output/dangling-retirement.json').is_file())
            self.assertTrue((output / 'helper-source-postcheck.json').is_file())
            self.assertFalse(result['g0_granted'])

    def test_partial_main_failure_retains_diagnostics_runs_postchecks_and_cannot_write_total_success(self):
        run_root = self.root / 'unit-only-failed-run'
        run_root.mkdir()
        output, intents, methods, stopped = self.synthetic_main(run_root, fail_second_method=True)
        self.assertEqual(len(methods), 2)
        self.assertEqual(stopped, [2])
        self.assertFalse((output / 'verification.json').exists())
        failure = json.loads((output / 'failure.json').read_bytes())
        self.assertEqual(len(failure['completed_DAGs']), 1)
        self.assertEqual((output / methods[1] / 'runner.stderr').read_text(), 'UNIT_ONLY_INFRASTRUCTURE_FAILURE')
        self.assertTrue((output / 'reference-postcheck.json').is_file())
        self.assertTrue((output / 'helper-source-postcheck.json').is_file())

    def test_failed_reference_finalization_does_not_prevent_independent_helper_postcheck(self):
        run_root = self.root / 'unit-only-postcheck-failed-run'
        run_root.mkdir()
        output, intents, methods, stopped = self.synthetic_main(run_root, fail_reference_postcheck=True)
        self.assertEqual(len(methods), 46)
        self.assertEqual(stopped, [54])
        self.assertFalse((output / 'verification.json').exists())
        self.assertTrue((output / 'helper-source-postcheck.json').is_file())
        self.assertTrue((output / 'resource-postcheck.json').is_file())
        failure = json.loads((output / 'postcheck-failure.json').read_bytes())
        self.assertFalse(failure['successful_qualification_claimed'])
        self.assertEqual([error['check'] for error in failure['errors']], ['reference-postcheck'])


if __name__ == '__main__':
    unittest.main()
