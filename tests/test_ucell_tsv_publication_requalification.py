"""Self-cleaning stdlib orchestration tests; no UCell, container or DAG execution."""

import copy
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import prove_ucell_tsv_publication_requalification as driver


def report(positive=True):
    rows = [dict(id='input' + str(port), node_type='file_reference', status='success', reused=False,
        port_assignments={'0': {}}) for port in range(2)]
    error = None if positive else dict(kind='node_error', message='BLOCKED: Frozen UCell parameters invalid')
    rows.append(dict(id='analysis', node_type='cachexia_ucell_official', status='success' if positive else 'failed',
        reused=False, error=error, port_assignments={str(port): {} for port in range(4)} if positive else {},
        execution=dict(exit_code=0 if positive else 2, image=driver.IMAGE, image_digest=driver.IMAGE.split('@')[1])))
    return dict(scope=driver.SCOPE, engine_source_revision=driver.ENGINE, plugin_name='cachexia-ucell',
        original_manifest_sha256=driver.MANIFEST_SHA, additional_plugin_identities=[], input_hashing='ContentRequired',
        incremental=False, max_concurrency=1, native_statistical_factories_registered=False,
        current_daemon_verified=False, scientific_authorized=False, g0_granted=False,
        first_run=dict(nodes=rows, errors={} if positive else {'analysis': error}, ok=positive))


class UCellTSVRequalificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_original_twelve_and_sixteen_inventories_are_preserved(self):
        self.assertEqual(tuple(case['name'] for case in driver.original.configurations()), driver.POSITIVE)
        self.assertEqual(len(set(driver.POSITIVE)), 12)
        self.assertEqual(len(set(driver.NEGATIVES)), 16)
        self.assertIn('negative-only', driver.POSITIVE)
        self.assertIn('first-result-link-failure', driver.NEGATIVES)

    def preflight_fixture(self):
        source = self.root / 'source'
        (source / 'scripts').mkdir(parents=True)
        (source / 'manifest.toml').write_text('synthetic manifest')
        (source / 'scripts/ucell.R').write_text('synthetic script')
        golden = self.root / 'golden'
        (golden / 'main').mkdir(parents=True)
        for name in driver.INPUTS:
            (golden / 'main' / name).write_text('SYNTHETIC INPUT\n')
        output = self.root / 'preflight'
        output.mkdir()
        return source, golden, output

    def test_preflight_constructs_real_graph_instead_of_only_validating_transport(self):
        source, golden, output = self.preflight_fixture()
        def refused(arguments, work, label, **options):
            self.assertEqual(arguments, ['/toy/runner', str(work / 'job.json')])
            self.assertEqual(label, 'construction')
            self.assertEqual(options['environment']['AUTONOMICS_DAG_TASKS_ROOT'], str(work / 'task-receipts'))
            marker = ('node `cachexia_ucell_official`: unknown param `unexpected_free_parameter`'
                if work.name == 'unknown-parameter' else 'PortDisconnected { node: "analysis", port: 1 }')
            return subprocess.CompletedProcess(arguments, 1, b'', marker.encode())
        with mock.patch.object(driver, 'run_recorded', side_effect=refused):
            records = driver.preflight(Path('/toy/runner'), source, golden, output)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record['actual_method_execution'] is False for record in records))

    def test_transport_success_cannot_be_counted_as_graph_refusal(self):
        source, golden, output = self.preflight_fixture()
        with mock.patch.object(driver, 'run_recorded', return_value=subprocess.CompletedProcess([], 0, b'', b'')), \
                self.assertRaisesRegex(ValueError, 'Exact graph preflight refusal'):
            driver.preflight(Path('/toy/runner'), source, golden, output)

    def test_unrelated_failure_cannot_be_counted_as_graph_refusal(self):
        source, golden, output = self.preflight_fixture()
        with mock.patch.object(driver, 'run_recorded', return_value=subprocess.CompletedProcess([], 1, b'', b'missing library')), \
                self.assertRaisesRegex(ValueError, 'Exact graph preflight refusal'):
            driver.preflight(Path('/toy/runner'), source, golden, output)

    def test_job_is_exact_three_nodes_two_edges_and_both_file_ports(self):
        source = self.root / 'source'
        (source / 'scripts').mkdir(parents=True)
        (source / 'manifest.toml').write_text('synthetic manifest')
        (source / 'scripts/ucell.R').write_text('synthetic script')
        parameters = dict(max_rank=1500, negative_weight=1, missing_genes='impute')
        job = driver.job_for(self.root / 'case', source, parameters)
        self.assertEqual(job['scope'], driver.SCOPE)
        self.assertEqual(len(job['nodes']), 3)
        self.assertEqual(len(job['edges']), 2)
        self.assertEqual([row['to_port'] for row in job['edges']], [0, 1])
        self.assertEqual(job['nodes'][-1], dict(id='analysis', kind='cachexia_ucell_official', spec=parameters))
        self.assertEqual(job['additional_plugins'], [])
        self.assertEqual(job['bundles'], [])
        self.assertTrue(all(row['spec']['hash_content'] is True for row in job['nodes'][:2]))

    def test_complete_positive_sdk_report(self):
        self.assertEqual(set(driver.validate_report(report(), {'engine_commit': driver.ENGINE}, positive=True)),
            {'input0', 'input1', 'analysis'})

    def test_exact_method_exit_two_not_any_failure(self):
        original = report(False)
        driver.validate_report(original, {'engine_commit': driver.ENGINE}, positive=False)
        for value in (1, 125, 137, -1, True, None):
            changed = copy.deepcopy(original)
            changed['first_run']['nodes'][-1]['execution']['exit_code'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=False)

    def test_wrong_or_mutable_engine_image_and_scope_are_rejected(self):
        for key, value in [('scope', 'SYN'), ('engine_source_revision', 'wrong'), ('plugin_name', 'ucell-h5ad'),
                ('original_manifest_sha256', '0' * 64), ('max_concurrency', True), ('incremental', True),
                ('input_hashing', 'Metadata'), ('additional_plugin_identities', [{}])]:
            changed = report()
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=True)
        for key in ('image', 'image_digest'):
            changed = report()
            changed['first_run']['nodes'][-1]['execution'][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=True)

    def test_authority_reuse_and_missing_source_cannot_pass(self):
        for key in ('native_statistical_factories_registered', 'current_daemon_verified', 'scientific_authorized', 'g0_granted'):
            changed = report()
            changed[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=True)
        for index in range(3):
            changed = report()
            changed['first_run']['nodes'][index]['reused'] = True
            with self.subTest(index=index), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=True)
        changed = report()
        changed['first_run']['nodes'].pop(0)
        with self.assertRaises(ValueError):
            driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=True)

    def test_false_failed_ports_and_wrong_error_maps_are_rejected(self):
        for value in ([], None, {'foreign': {}}, {'analysis': {'kind': 'wrong'}}):
            changed = report(False)
            changed['first_run']['errors'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=False)
        changed = report(False)
        changed['first_run']['nodes'][-1]['port_assignments'] = {'2': {}}
        with self.assertRaises(ValueError):
            driver.validate_report(changed, {'engine_commit': driver.ENGINE}, positive=False)

    def inputs(self, links=False):
        work = self.root / 'case'
        work.mkdir()
        scratch = self.root / 'scratch'
        staging = scratch / 'aa' / ('b' * 62) / '.autonomics/inputs'
        staging.mkdir(parents=True)
        nodes = {'analysis': {'inputs': []}}
        for port, name in enumerate(driver.INPUTS):
            source = work / name
            source.write_bytes((name + '\nSYNTHETIC\n').encode())
            staged = staging / ('input-' + str(port) + '.tsv')
            if links:
                staged.symlink_to(source)
            else:
                staged.write_bytes(source.read_bytes())
            fingerprint = dict(size=source.stat().st_size, content_hash='sha256:' + hashlib.sha256(source.read_bytes()).hexdigest())
            value = dict(path='vfs:///' + name, fingerprint=fingerprint)
            nodes['analysis']['inputs'].append(dict(value, **{'from': 'input' + str(port), 'from_port': 0, 'to_port': port}))
            nodes['input' + str(port)] = dict(port_assignments={'0': dict(value, format='tsv')})
        return work, nodes, scratch, staging

    def test_regular_staged_inputs_match_whole_source_bytes(self):
        work, nodes, scratch, _ = self.inputs()
        self.assertEqual(len(driver.checked_inputs(work, nodes, scratch)), 2)

    def test_direct_owned_staged_links_are_supported(self):
        work, nodes, scratch, _ = self.inputs(links=True)
        self.assertEqual(len(driver.checked_inputs(work, nodes, scratch)), 2)

    def test_foreign_staged_link_and_bool_port_are_rejected(self):
        work, nodes, scratch, staging = self.inputs(links=True)
        target = staging / 'input-0.tsv'
        target.unlink()
        foreign = self.root / 'foreign.tsv'
        foreign.write_bytes((work / 'matrix.tsv').read_bytes())
        target.symlink_to(foreign)
        with self.assertRaises(ValueError):
            driver.checked_inputs(work, nodes, scratch)
        target.unlink()
        target.symlink_to(work / 'matrix.tsv')
        nodes['analysis']['inputs'][0]['to_port'] = False
        with self.assertRaises(ValueError):
            driver.checked_inputs(work, nodes, scratch)

    def test_missing_or_incomplete_input_fingerprint_is_rejected(self):
        work, nodes, scratch, _ = self.inputs()
        nodes['analysis']['inputs'][0]['fingerprint']['content_hash'] = None
        with self.assertRaises(ValueError):
            driver.checked_inputs(work, nodes, scratch)

    def test_failure_diagnostics_use_actual_two_level_workspace(self):
        scratch = self.root / 'scratch'
        logs = scratch / 'aa' / ('b' * 62) / '.autonomics/logs'
        logs.mkdir(parents=True)
        (logs / 'stderr.log').write_text('BLOCKED: technical toy refusal')
        work = self.root / 'case'
        work.mkdir()
        rows = driver.preserve_logs(work, scratch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(Path(rows[0]['destination']).read_text(), 'BLOCKED: technical toy refusal')

    def test_timeout_keeps_partial_output_and_unknown_exit(self):
        error = subprocess.TimeoutExpired(['toy'], 1, output=b'partial-out', stderr=b'partial-error')
        with mock.patch.object(driver.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
            driver.run_recorded(['toy'], self.root, 'actual')
        self.assertEqual((self.root / 'actual.stdout').read_bytes(), b'partial-out')
        self.assertEqual(json.loads((self.root / 'actual-exit.json').read_text()), dict(actual_exit=None, timed_out=True))

    def test_old_engineering_seal_is_not_a_fallback(self):
        with mock.patch.object(driver, 'checked_archive') as observe, self.assertRaises(ValueError):
            driver.checked_engineering(self.root, 'ec81ba947425422298ea94523ec8c332', '0' * 64)
        observe.assert_not_called()

    def engineering(self):
        snapshot = self.root / 'snapshot'
        identities, identifiers = {}, []
        for name in [*driver.ENGINEERING_TESTS, 'plugins/ucell/scripts/ucell.R']:
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((driver.ROOT / name).read_bytes())
            identities[name] = dict(sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            if name in driver.ENGINEERING_TESTS:
                module = name.removesuffix('.py').replace('/', '.')
                tree = ast.parse(target.read_bytes())
                identifiers.extend(module + '.' + definition.name + '.' + method.name for definition in tree.body
                    if isinstance(definition, ast.ClassDef) for method in definition.body
                    if isinstance(method, ast.FunctionDef) and method.name.startswith('test_'))
        value = dict(schema='B_PUBLICATION_OWNERSHIP_REGRESSIONS_V1', complete=True, actual_tests_run=58,
            official_UCell_or_singscore_computation_executed=False, scientific_authorization_granted=False,
            g0_granted=False, current_sources=identities)
        execution = dict(required_test_ids=sorted(identifiers), actual_test_ids=list(reversed(identifiers)),
            complete=True, tests_run=58, failures=0, errors=0, skipped=0)
        return value, execution, snapshot

    def test_engineering_requires_all_actual_fifty_five_source_bound_ids(self):
        value, execution, snapshot = self.engineering()
        driver.validate_engineering(value, execution, snapshot)
        execution['required_test_ids'][0] = 'foreign.test_identifier'
        execution['actual_test_ids'][0] = 'foreign.test_identifier'
        with self.assertRaises(ValueError):
            driver.validate_engineering(value, execution, snapshot)

    def test_engineering_rejects_skip_boolean_counter_and_source_mismatch(self):
        value, execution, snapshot = self.engineering()
        for key, altered in [('skipped', 1), ('failures', False), ('tests_run', True)]:
            changed = dict(execution, **{key: altered})
            with self.subTest(key=key), self.assertRaises(ValueError):
                driver.validate_engineering(value, changed, snapshot)
        changed = copy.deepcopy(value)
        changed['current_sources']['plugins/ucell/scripts/ucell.R']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            driver.validate_engineering(changed, execution, snapshot)

    def test_original_boundary_selection_preserves_all_assertions_and_session_environment(self):
        source = self.root / 'tools/prove_ucell_tsv_failures.py'
        source.parent.mkdir()
        payload = '''import os
from pathlib import Path
CASES=__CASES__
def main():
 output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-failures'
 output.mkdir()
 assert len(CASES)==1
 assert os.environ['AUTONOMICS_VALIDATION_PERMANENT']==__PERMANENT__
 case=output/CASES[0]
 case.mkdir()
 stage=case/'.ucell-stage-owned'
 stage.mkdir()
 (stage/'unknown').write_text('SYNTHETIC UNKNOWN SENTINEL')
 raise RuntimeError('Owned staging directories not cleaned')
'''.replace('__CASES__', repr(list(driver.NEGATIVES))).replace('__PERMANENT__', repr(str(self.root)))
        source.write_text(payload)
        output = self.root / 'proof'
        output.mkdir()
        with mock.patch.object(driver, 'ROOT', self.root), mock.patch.dict(driver.PINS,
                {'tools/prove_ucell_tsv_failures.py': hashlib.sha256(payload.encode()).hexdigest()}), mock.patch.dict(os.environ,
                {'AUTONOMICS_VALIDATION_PERMANENT': str(self.root)}):
            records = driver.direct_boundaries(output)
        self.assertEqual(len(records), 16)
        self.assertTrue(all(not row['original_assertions_passed'] and row['original_assertions_changed'] is False for row in records))
        for name in driver.NEGATIVES:
            selected = json.loads((output / 'direct-boundaries' / name / 'selection-receipt.json').read_text())
            self.assertEqual(selected['selected_cases'], [name])
            self.assertTrue(selected['original_predicates_and_assertions_preserved'])
            self.assertTrue(selected['session_permanent_environment_unchanged'])
            self.assertRegex(selected['assertion_ast_sha256'], r'^[0-9a-f]{64}$')
            self.assertEqual(selected['only_changes'], ['main.output_assignment', 'CASES_singleton_selection'])
            self.assertEqual(records[driver.NEGATIVES.index(name)]['retained_stage_metadata'][0]['contents_read'], False)
        changed = payload.replace("raise RuntimeError('Owned staging directories not cleaned')", "raise RuntimeError('UNATTRIBUTABLE_RUNTIME_ERROR')")
        source.write_text(changed)
        failed = self.root / 'unattributed'
        failed.mkdir()
        with mock.patch.object(driver, 'ROOT', self.root), mock.patch.dict(driver.PINS,
                {'tools/prove_ucell_tsv_failures.py': hashlib.sha256(changed.encode()).hexdigest()}), mock.patch.dict(os.environ,
                {'AUTONOMICS_VALIDATION_PERMANENT': str(self.root)}), self.assertRaisesRegex(ValueError, 'runtime or dependency failure'):
            driver.direct_boundaries(failed)
        self.assertEqual([path.name for path in (failed / 'direct-boundaries').iterdir()], [driver.NEGATIVES[0]])

    def test_actual_proxy_preserves_backend_and_rejects_resource_drift(self):
        temporary = self.root / 'temporary'
        temporary.mkdir()
        output = self.root / 'proof'
        output.mkdir()
        fake = self.root / 'fake-shim.py'
        fake.write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
        workspace = temporary / 'official-plugin-container-workspaces/case/aa' / ('b' * 62)
        (workspace / '.autonomics').mkdir(parents=True)
        payload = b'TECHNICAL SCRIPT\n'
        (workspace / '.autonomics/script').write_bytes(payload)
        prefix = [sys.executable, str(fake), '--technical-owner-backend']
        with mock.patch.dict(os.environ), mock.patch.object(driver, 'SCRIPT_SHA', hashlib.sha256(payload).hexdigest()):
            launcher, _ = driver.install_launcher(prefix, temporary, output)
        arguments = ['create', '--cpus', '1', '--memory', '2147483648', '--network', 'none', '--pull', 'missing',
            '--read-only', '--name', 'toy-owned-container', '--mount', 'type=bind,source=' + str(workspace) + ',destination=/work,rw=true']
        values = dict(AUTONOMICS_SCRIPT='/work/.autonomics/script', AUTONOMICS_WORKDIR='/work', AUTONOMICS_INPUT_COUNT='2', AUTONOMICS_OUTPUT_COUNT='4')
        for stem, count in [('INPUT', 2), ('OUTPUT', 4)]:
            values.update({'AUTONOMICS_' + stem + str(port): '/work/toy-' + stem + str(port) for port in range(count)})
        for key, value in values.items():
            arguments += ['--env', key + '=' + value]
        arguments += [driver.IMAGE]
        result = subprocess.run([str(launcher), *arguments], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        offline_arguments = list(arguments)
        offline_arguments[offline_arguments.index('--pull') + 1] = 'never'
        self.assertEqual(json.loads(result.stdout), ['--technical-owner-backend', *offline_arguments])
        record = json.loads((output / 'actual-container-create.jsonl').read_text())
        self.assertEqual(record['memory_bytes'], 2147483648)
        self.assertEqual(record['original_pull'], 'missing')
        self.assertEqual(record['effective_pull'], 'never')
        changed = list(arguments)
        changed[changed.index('--pull') + 1] = 'always'
        result = subprocess.run([str(launcher), *changed], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Original isolation differs', result.stderr)
        changed = list(arguments)
        changed[changed.index('--memory') + 1] = '1000000000'
        result = subprocess.run([str(launcher), *changed], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Original UCell resources differ', result.stderr)
        result = subprocess.run([str(launcher), '--root', '/foreign', 'create'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Backend override refused', result.stderr)

    def test_cli_absolute_entry_works_outside_repository(self):
        result = subprocess.run([sys.executable, '-B', str(Path(driver.__file__).resolve()), '--help'],
            cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--engineering-seal', result.stdout)
        self.assertIn('--execute', result.stdout)

    def test_h5ad_wrapper_qualification_is_not_inherited(self):
        source = Path(driver.__file__).read_text()
        self.assertNotIn('original.reference(', source)
        self.assertNotIn('plugins/ucell-h5ad/scripts/score.py', driver.PINS)
        self.assertIn('H5AD_adapter_qualification_inherited=False', source)
        self.assertEqual(driver.BUILD_SESSION, '54d4987610d14ce7882735c715368c8e')
        self.assertEqual(driver.ENGINE, '4256643c55ae6fb50e8c867069330ed6ac2b4bc0')


if __name__ == '__main__':
    unittest.main()
