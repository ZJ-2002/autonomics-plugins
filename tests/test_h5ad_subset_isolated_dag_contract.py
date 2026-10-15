"""Dependency-free contracts for bounded subset DAG proof orchestration."""

import ast
import copy
import hashlib
import inspect
from pathlib import Path
import tempfile
import tomllib
import unittest

from tools import prove_h5ad_subset_isolated_dag as proof


class H5adSubsetIsolatedDagContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        family = proof.ROOT / 'plugins/single-cell'
        self.manifest = tomllib.loads((family / 'manifest.toml').read_text())
        self.identities = {item['command']['script_file']: {'sha256': hashlib.sha256(
            (family / item['command']['script_file']).read_bytes()).hexdigest()}
            for item in self.manifest['nodes']}
        self.identities['tests/qc_compare.py'] = {'sha256': proof.SOURCES['tests/qc_compare.py']}
        self.job = proof.job_for(self.root, self.root / 'source', self.manifest, self.identities, 'cell_id')

    def report(self, positive=True):
        return {
            'scope': 'TECHNICAL_PLUGIN_DAG_NOT_G0',
            'engine_source_revision': proof.ENGINE,
            'plugin_name': 'single-cell',
            'original_manifest_sha256': proof.SOURCES['manifest.toml'],
            'max_concurrency': 1,
            'incremental': False,
            'input_hashing': 'ContentRequired',
            'additional_plugin_identities': [],
            'native_statistical_factories_registered': False,
            'panel_bindings_are_explicit_synthetic_overrides': True,
            'actual_research_panels_qualified': False,
            'current_daemon_verified': False,
            'scientific_authorized': False,
            'g0_granted': False,
            'first_run': {
                'nodes': [
                    {'id': 'input0', 'node_type': 'file_reference', 'status': 'success'},
                    {'id': 'input1', 'node_type': 'file_reference', 'status': 'success'},
                    {'id': 'analysis', 'node_type': 'h5ad_subset_by_obs',
                     'status': 'success' if positive else 'failed', 'reused': False,
                     'execution': {'image': proof.IMAGE, 'image_digest': proof.IMAGE.split('@')[1],
                                   'exit_code': 0 if positive else 2},
                     'port_assignments': [{'port': 0}, {'port': 1}] if positive else []},
                ],
                'errors': [] if positive else ['method exited nonzero'],
            },
        }

    def assert_refused(self, report, positive=True):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            proof.validate_report(report, self.job, positive=positive)

    def test_preserves_exact_eleven_positive_inventory(self):
        self.assertEqual(proof.POSITIVES, {'dense', 'csr', 'csc', 'group-many-to-one', 'all-cells',
            'lexical-numeric', 'single-cell', 'prior-params', 'no-raw', 'no-X', 'nonfinite-X'})

    def test_nineteen_method_refusals_are_distinct_from_five_direct_controls(self):
        self.assertEqual(set(proof.NEGATIVES), {'unknown', 'unknown-partial', 'unknown-group',
            'duplicate-request', 'duplicate-group', 'empty-request', 'null-request', 'integer-request',
            'empty-string', 'tab-request', 'numeric-group', 'absent-column', 'duplicate-obs',
            'duplicate-var', 'missing-group', 'zero-cells', 'zero-genes', 'missing-selection-column',
            'corrupt-selection'})
        self.assertEqual(proof.DIRECT_ONLY, {'existing-h5ad', 'existing-report', 'aliased-outputs',
            'input-overwrite', 'ordinary-second-link-failure'})
        self.assertFalse(set(proof.NEGATIVES) & proof.DIRECT_ONLY)
        self.assertFalse(proof.POSITIVES & (set(proof.NEGATIVES) | proof.DIRECT_ONLY))

    def test_job_has_exact_three_nodes_two_typed_edges_and_hashed_file_inputs(self):
        self.assertEqual(self.job['nodes'], [
            {'id': 'input0', 'kind': 'file_reference',
             'spec': {'path': 'vfs:///input.h5ad', 'format': 'h5ad', 'hash_content': True}},
            {'id': 'input1', 'kind': 'file_reference',
             'spec': {'path': 'vfs:///selection.parquet', 'format': 'parquet', 'hash_content': True}},
            {'id': 'analysis', 'kind': 'h5ad_subset_by_obs', 'spec': {'join_column': 'cell_id'}},
        ])
        self.assertEqual(self.job['edges'], [
            {'from': 'input0', 'from_port': 0, 'to': 'analysis', 'to_port': 0},
            {'from': 'input1', 'from_port': 0, 'to': 'analysis', 'to_port': 1},
        ])

    def test_job_keeps_original_manifest_and_script_identity_not_comparator_as_script(self):
        self.assertEqual(self.job['scope'], 'TECHNICAL_PLUGIN_DAG_NOT_G0')
        self.assertEqual(self.job['expected_plugin_name'], 'single-cell')
        self.assertEqual(self.job['plugin_manifest'], str(self.root / 'source/manifest.toml'))
        self.assertEqual(self.job['plugin_manifest_sha256'],
            '5288e9c7ac552f318b93c67f107fd45dcddf12d9396c38e00e6950e3bede9c42')
        self.assertEqual(len(self.job['script_sha256']), 10)
        self.assertEqual(set(self.job['script_sha256']),
            {item['command']['script_file'] for item in self.manifest['nodes']})
        self.assertEqual(self.job['script_sha256']['scripts/subset_by_obs.py'],
            '4d1afc22f291ab80b92033308319306db30b1a779ef873466920e6040fa87b5b')
        self.assertNotIn('tests/qc_compare.py', self.job['script_sha256'])
        self.assertEqual(self.job['additional_plugins'], [])

    def test_job_panel_alias_preserves_real_bundle_digest_and_explicit_transport_role(self):
        self.assertEqual(self.job['panel_overrides'], [{'binding': 'model',
            'declared_bundle': 'wjixiang/catalog-celltypist-models-pan-immune',
            'mount': '/panels/celltypist_model', 'synthetic_bundle': proof.ALIAS}])
        self.assertEqual(self.job['panel_manifest_sha256'], {proof.PANEL_PATH: proof.PANEL_SHA})
        self.assertEqual(len(self.job['bundles']), 1)
        bundle = self.job['bundles'][0]
        self.assertEqual(bundle['ident'], proof.ALIAS)
        self.assertEqual(bundle['vpath'], proof.PANEL_PATH)
        self.assertEqual(bundle['source'], proof.PANEL_PATH)
        self.assertEqual(bundle['digest'], proof.PANEL_DIGEST)
        self.assertIn('unchanged real canonical model bytes', bundle['desc'])
        self.assertIn('models not loaded', bundle['desc'])

    def test_join_column_is_explicitly_preserved_for_each_group_route(self):
        for value in ['cell_id', 'donor', 'number', 'missing', 'bad']:
            with self.subTest(join_column=value):
                job = proof.job_for(self.root, self.root / 'source', self.manifest, self.identities, value)
                self.assertEqual(job['nodes'][2]['spec'], {'join_column': value})
                self.assertEqual(job['edges'], self.job['edges'])

    def test_valid_positive_and_failed_reports_return_actual_method(self):
        for positive in [True, False]:
            report = self.report(positive)
            self.assertIs(proof.validate_report(report, self.job, positive=positive), report['first_run']['nodes'][2])

    def test_report_rejects_scope_engine_manifest_and_plugin_identity_drift(self):
        for field, value in [('scope', 'REAL_STUDY'), ('engine_source_revision', '0' * 40),
                             ('original_manifest_sha256', '0' * 64), ('plugin_name', 'renamed')]:
            with self.subTest(field=field):
                report = self.report()
                report[field] = value
                self.assert_refused(report)

    def test_report_rejects_cache_resource_policy_or_additional_factory_drift(self):
        for field, value in [('max_concurrency', True), ('max_concurrency', 2), ('incremental', True),
                             ('input_hashing', 'Metadata'), ('additional_plugin_identities', [{}]),
                             ('native_statistical_factories_registered', True)]:
            with self.subTest(field=field, value=value):
                report = self.report()
                report[field] = value
                self.assert_refused(report)

    def test_report_never_upgrades_transport_or_scientific_authority(self):
        for field, value in [('panel_bindings_are_explicit_synthetic_overrides', False),
                             ('actual_research_panels_qualified', True), ('current_daemon_verified', True),
                             ('scientific_authorized', True), ('g0_granted', True)]:
            with self.subTest(field=field):
                report = self.report()
                report[field] = value
                self.assert_refused(report)

    def test_report_rejects_missing_extra_duplicate_or_wrong_source_nodes(self):
        for mode in ['missing', 'extra', 'duplicate', 'wrong-kind', 'failed-source']:
            with self.subTest(mode=mode):
                report = self.report()
                nodes = report['first_run']['nodes']
                if mode == 'missing':
                    nodes.pop(0)
                elif mode == 'extra':
                    nodes.append(copy.deepcopy(nodes[0]))
                elif mode == 'duplicate':
                    nodes[0]['id'] = 'input1'
                elif mode == 'wrong-kind':
                    nodes[0]['node_type'] = 'source_sql'
                else:
                    nodes[0]['status'] = 'failed'
                self.assert_refused(report)

    def test_report_rejects_wrong_method_kind_image_digest_or_reused_execution(self):
        for mode in ['kind', 'image', 'digest', 'reuse', 'missing-execution', 'bool-exit']:
            with self.subTest(mode=mode):
                report = self.report()
                method = report['first_run']['nodes'][2]
                if mode == 'kind':
                    method['node_type'] = 'h5ad_qc_filter'
                elif mode == 'image':
                    method['execution']['image'] = 'unversioned:latest'
                elif mode == 'digest':
                    method['execution']['image_digest'] = 'sha256:' + '0' * 64
                elif mode == 'reuse':
                    method['reused'] = True
                elif mode == 'missing-execution':
                    method.pop('execution')
                else:
                    method['execution']['exit_code'] = False
                self.assert_refused(report)

    def test_report_rejects_status_and_graph_error_disagreement(self):
        for positive in [True, False]:
            for field in ['status', 'errors']:
                with self.subTest(positive=positive, field=field):
                    report = self.report(positive)
                    if field == 'status':
                        report['first_run']['nodes'][2]['status'] = 'failed' if positive else 'success'
                    else:
                        report['first_run']['errors'] = ['failure'] if positive else []
                    self.assert_refused(report, positive)

    def test_positive_nonzero_exit_and_failed_normal_ports_are_rejected(self):
        report = self.report()
        report['first_run']['nodes'][2]['execution']['exit_code'] = 2
        self.assert_refused(report)
        report = self.report(False)
        report['first_run']['nodes'][2]['port_assignments'] = [{'port': 0}]
        self.assert_refused(report, False)

    def test_engine_preflight_branch_is_separate_and_requires_no_method_dispatch(self):
        main = ast.parse(inspect.getsource(proof.main))
        branches = [node for node in ast.walk(main) if isinstance(node, ast.If)
                    and isinstance(node.test, ast.Name) and node.test.id == 'preflight']
        self.assertEqual(len(branches), 2)
        post_run = branches[1]
        source = ast.unparse(ast.Module(body=post_run.body, type_ignores=[]))
        self.assertIn('PortDisconnected', source)
        self.assertIn('ENGINE_INPUT_COMPLETENESS', source)
        self.assertIn('actual_method_executed=False', source)
        self.assertIn('not scratch.exists()', source)
        self.assertIn('not observed_cgroups', source)
        self.assertNotIn('validate_report', source)
        self.assertNotIn('specific_refusal', source)

    def test_full_driver_method_refusal_checks_exit_diagnostic_and_all_absent_outputs(self):
        source = inspect.getsource(proof.main)
        self.assertIn("expected_exit = 3 if name == 'corrupt-selection' else 2", source)
        self.assertIn("method['execution']['exit_code'] == expected_exit", source)
        self.assertIn('NEGATIVES[name] in diagnostic', source)
        self.assertIn("for filename in ['output.h5ad', 'report.json']", source)
        self.assertIn('normal_results_absent=True', source)

    def test_full_driver_reuses_sealed_oracle_without_author_regeneration(self):
        source = inspect.getsource(proof.main)
        self.assertIn("shutil.copyfile(original / 'fresh-author.h5ad'", source)
        self.assertIn("digest(original / 'fresh-author.h5ad') == digest(original / 'output.h5ad')", source)
        self.assertNotIn('.write_h5ad(', source)
        self.assertNotIn('fixture(', source)
        self.assertIn('compare(root/name)', proof.COMPARE)

    def test_actual_input_bindings_require_correct_sources_ports_and_content(self):
        originals, bindings = [], []
        scratch = self.root / 'scratch'
        staged = scratch / 'container/.autonomics/inputs'
        staged.mkdir(parents=True)
        for index, name in enumerate(['input.h5ad', 'selection.parquet']):
            original = self.root / 'originals' / name
            original.parent.mkdir(exist_ok=True)
            original.write_bytes(('toy-port-' + str(index)).encode())
            (self.root / name).write_bytes(original.read_bytes())
            (staged / ('input-' + str(index) + original.suffix)).write_bytes(original.read_bytes())
            originals.append(original)
            bindings.append({'to_port': index, 'from': 'input' + str(index), 'from_port': 0,
                'path': 'vfs:///' + name,
                'fingerprint': {'size': original.stat().st_size, 'content_hash': 'sha256:' + proof.digest(original)}})
        self.assertEqual(len(proof.check_inputs(self.root, originals, {'inputs': bindings}, scratch)), 2)
        for field, value in [('from', 'input1'), ('from_port', 1), ('to_port', 1),
                             ('path', 'vfs:///other.h5ad')]:
            with self.subTest(field=field):
                wrong = copy.deepcopy(bindings)
                wrong[0][field] = value
                with self.assertRaises(ValueError):
                    proof.check_inputs(self.root, originals, {'inputs': wrong}, scratch)
        (staged / 'input-0.h5ad').write_bytes(b'different')
        with self.assertRaises(ValueError):
            proof.check_inputs(self.root, originals, {'inputs': bindings}, scratch)

    def test_actual_output_ports_use_exact_run_not_first_matching_artifact_directory(self):
        scratch = self.root / 'scratch'
        scratch.mkdir()
        definition = next(item for item in self.manifest['nodes'] if item['kind'] == 'h5ad_subset_by_obs')
        assignments = {}
        selected = []
        for index, port in enumerate(definition['ports']['outputs']):
            live = scratch / port['path']
            live.write_bytes(('published-' + str(index)).encode())
            for run_name in ['earlier-run', 'actual-run']:
                published = self.root / definition['artifact_prefix'].lstrip('/') / run_name / port['path']
                published.parent.mkdir(parents=True, exist_ok=True)
                published.write_bytes(live.read_bytes() if run_name == 'actual-run' else b'foreign-earlier')
                if run_name == 'actual-run':
                    selected.append(published)
            assignments[str(index)] = {'path': str(live), 'format': port['format'],
                'fingerprint': {'size': live.stat().st_size, 'content_hash': 'sha256:' + proof.digest(live)}}
        method = {'execution': {'run_name': 'actual-run'}, 'port_assignments': assignments}
        self.assertEqual(proof.check_ports(self.root, definition, method, scratch), selected)
        selected[0].write_bytes(b'wrong-current-output')
        with self.assertRaises(ValueError):
            proof.check_ports(self.root, definition, method, scratch)

    def test_actual_output_port_inventory_and_run_path_traversal_are_rejected(self):
        definition = next(item for item in self.manifest['nodes'] if item['kind'] == 'h5ad_subset_by_obs')
        for assignments in [None, {}, {'0': {}}, {'0': {}, '1': {}, '2': {}}]:
            with self.subTest(assignments=assignments):
                with self.assertRaises(ValueError):
                    proof.check_ports(self.root, definition, {'port_assignments': assignments}, self.root)
        for run_name in ['', '.', '..', '../foreign', 'parent/child']:
            with self.subTest(run_name=run_name):
                with self.assertRaises(ValueError):
                    proof.check_ports(self.root, definition,
                        {'execution': {'run_name': run_name}, 'port_assignments': {'0': {}, '1': {}}}, self.root)

    def linked_inputs(self):
        originals, bindings, links = [], [], []
        scratch = self.root / 'scratch'
        staged = scratch / 'container/.autonomics/inputs'
        staged.mkdir(parents=True)
        for index, name in enumerate(['input.h5ad', 'selection.parquet']):
            original = self.root / 'originals' / name
            original.parent.mkdir(exist_ok=True)
            original.write_bytes(('linked-toy-' + str(index)).encode())
            owned = self.root / name
            owned.write_bytes(original.read_bytes())
            link = staged / ('input-' + str(index) + original.suffix)
            link.symlink_to(owned)
            originals.append(original)
            links.append(link)
            bindings.append({'to_port': index, 'from': 'input' + str(index), 'from_port': 0,
                'path': 'vfs:///' + name,
                'fingerprint': {'size': original.stat().st_size, 'content_hash': 'sha256:' + proof.digest(original)}})
        return originals, bindings, links, scratch

    def test_exact_owned_input_symlinks_are_accepted_without_weakening_regular_fact(self):
        originals, bindings, links, scratch = self.linked_inputs()
        before = {path: path.lstat() for path in links}
        records = proof.check_inputs(self.root, originals, {'inputs': bindings}, scratch)
        self.assertEqual([row['staging_mode'] for row in records], ['exact_owned_input_symlink'] * 2)
        self.assertEqual([row['port'] for row in records], [0, 1])
        for link in links:
            self.assertEqual(link.lstat(), before[link])
            with self.assertRaises(ValueError):
                proof.fact(link)

    def test_staged_symlink_to_identical_foreign_target_or_indirect_alias_is_rejected(self):
        originals, bindings, links, scratch = self.linked_inputs()
        foreign = self.root / 'foreign.h5ad'
        foreign.write_bytes(originals[0].read_bytes())
        alias = self.root / 'indirect.h5ad'
        alias.symlink_to(self.root / 'input.h5ad')
        for target in [foreign, alias]:
            with self.subTest(target=target.name):
                links[0].unlink()
                links[0].symlink_to(target)
                with self.assertRaises(ValueError):
                    proof.check_inputs(self.root, originals, {'inputs': bindings}, scratch)
                self.assertEqual(foreign.read_bytes(), originals[0].read_bytes())

    def test_boolean_input_port_numbers_are_not_integer_port_identities(self):
        originals, bindings, links, scratch = self.linked_inputs()
        for index, field, value in [(0, 'to_port', False), (1, 'to_port', True), (0, 'from_port', False)]:
            with self.subTest(index=index, field=field):
                changed = copy.deepcopy(bindings)
                changed[index][field] = value
                with self.assertRaises(ValueError):
                    proof.check_inputs(self.root, originals, {'inputs': changed}, scratch)

    def transport(self):
        directory = self.root / 'transport'
        directory.mkdir()
        for name in ['manifest.json', 'model.bin']:
            (directory / name).write_bytes(('owned-' + name).encode())
        current = directory.lstat()
        identity = current.st_dev, current.st_ino, current.st_mode
        owned = {path.name: proof.fact(path) for path in directory.iterdir()}
        return directory, identity, owned

    def test_transport_retirement_removes_only_unchanged_complete_owned_members(self):
        directory, identity, owned = self.transport()
        proof.retire_transport_copy(directory, identity, owned)
        self.assertFalse(directory.exists())

    def test_transport_retirement_preserves_foreign_extra_member_and_all_owned_files(self):
        directory, identity, owned = self.transport()
        foreign = directory / 'foreign.bin'
        foreign.write_bytes(b'foreign-do-not-delete')
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with self.assertRaises(ValueError):
            proof.retire_transport_copy(directory, identity, owned)
        self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, before)

    def test_transport_retirement_preserves_replaced_owned_file_even_with_identical_bytes(self):
        directory, identity, owned = self.transport()
        replacement = self.root / 'replacement'
        replacement.write_bytes((directory / 'model.bin').read_bytes())
        replacement.replace(directory / 'model.bin')
        before = {path.name: proof.fact(path) for path in directory.iterdir()}
        with self.assertRaises(ValueError):
            proof.retire_transport_copy(directory, identity, owned)
        self.assertEqual({path.name: proof.fact(path) for path in directory.iterdir()}, before)

    def test_execute_uses_case_owned_task_receipts_not_generic_global_root(self):
        source = ast.parse(inspect.getsource(proof.execute))
        run = next(node for node in ast.walk(source) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == 'run'
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess')
        environment = next(item.value for item in run.keywords if item.arg == 'env')
        self.assertIsInstance(environment, ast.Call)
        self.assertEqual(environment.func.id, 'dict')
        receipt = next(item.value for item in environment.keywords if item.arg == 'AUTONOMICS_DAG_TASKS_ROOT')
        self.assertEqual(ast.unparse(receipt), "str(work / 'task-receipts')")


if __name__ == '__main__':
    unittest.main()
