import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import prove_r_publication_dag as proof


SEALED_SDK_ERROR_SHAPES = {
    'positive': dict(source_session='9274e8d37bc34d0392a28ceb3a1dd726', errors={}, node_error=None),
    'negative': dict(source_session='4c608817b50f4720a52d4b470354f8d9',
        errors={'analysis': dict(kind='node_error', message='SYNTHETIC_DIAGNOSTIC_NOT_PRIVATE_LOG')},
        node_error=dict(kind='node_error', message='SYNTHETIC_DIAGNOSTIC_NOT_PRIVATE_LOG'),
        diagnostic_replaced_with_public_toy=True),
}


class RPublicationDAGTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def family(self, label):
        item = proof.direct.FAMILIES[label]
        manifest = tomllib.loads((proof.ROOT / item['manifest']).read_text())
        return dict(source=self.root / label, manifest=manifest,
            definition=next(node for node in manifest['nodes'] if node['kind'] == proof.KINDS[label]),
            identities={'manifest.toml': dict(sha256=item['manifest_sha']),
                **{node['command']['script_file']: dict(sha256='a' * 64) for node in manifest['nodes']}})

    def report(self, label='deseq2', negative=False):
        family = self.family(label)
        rows = [dict(id=name, node_type='file_reference', status='success', reused=False,
                     port_assignments={'0': {}}) for name in ('counts', 'samples')]
        rows.append(dict(id='analysis', node_type=proof.KINDS[label], reused=False,
            status='failed' if negative else 'success',
            error=copy.deepcopy(SEALED_SDK_ERROR_SHAPES['negative' if negative else 'positive']['node_error']),
            port_assignments={} if negative else {str(index): {} for index in range(5)},
            execution=dict(exit_code=1 if negative else 0, image=family['manifest']['image']['reference'],
                image_digest=family['manifest']['image']['reference'].split('@')[1])))
        return dict(scope=proof.SCOPE, engine_source_revision='e' * 40,
            original_manifest_sha256=family['identities']['manifest.toml']['sha256'],
            plugin_name=family['manifest']['plugin_name'], additional_plugin_identities=[], max_concurrency=1,
            incremental=False, input_hashing='ContentRequired', native_statistical_factories_registered=False,
            current_daemon_verified=False, scientific_authorized=False, g0_granted=False,
            first_run=dict(nodes=rows, ok=not negative,
                           errors=copy.deepcopy(SEALED_SDK_ERROR_SHAPES['negative' if negative else 'positive']['errors'])))

    def inputs(self, links=False):
        work = self.root / 'work'
        work.mkdir()
        scratch = self.root / 'scratch'
        staged = scratch / 'container/.autonomics/inputs'
        staged.mkdir(parents=True)
        nodes = {}
        bindings = []
        for port, name in enumerate(('counts', 'samples')):
            source = work / (name + '.tsv')
            source.write_bytes((name + '\nSYNTHETIC\n').encode())
            target = staged / ('input-' + str(port) + '.tsv')
            if links:
                target.symlink_to(source)
            else:
                target.write_bytes(source.read_bytes())
            fingerprint = dict(size=source.stat().st_size, content_hash='sha256:' + hashlib.sha256(source.read_bytes()).hexdigest())
            binding = dict(from_port=0, to_port=port, path='vfs:///' + name + '.tsv', fingerprint=fingerprint)
            binding['from'] = name
            bindings.append(binding)
            nodes[name] = dict(port_assignments={'0': dict(path=binding['path'], format='tsv', fingerprint=fingerprint)})
        return work, scratch, nodes, dict(inputs=bindings), staged

    def test_exact_existing_runner_build_no_new_compile_and_source_versions(self):
        self.assertEqual(proof.BUILD_SESSION, '54d4987610d14ce7882735c715368c8e')
        self.assertEqual(proof.BUILD_SEAL, 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f')
        self.assertEqual(proof.RUNNER_SHA, '636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b')
        self.assertEqual(len(proof.inherited.admission.GUARDS), 23)
        self.assertEqual(proof.direct.FAMILIES['deseq2']['packages']['DESeq2'], '1.50.2')
        self.assertEqual(proof.direct.FAMILIES['limma']['packages']['limma'], '3.66.0')

    def test_original_three_node_two_edge_jobs_have_both_exact_typed_ports(self):
        for label in proof.KINDS:
            with self.subTest(label=label):
                family = self.family(label)
                job = proof.job_for(self.root, label, family)
                self.assertEqual([node['kind'] for node in job['nodes']], ['file_reference', 'file_reference', proof.KINDS[label]])
                self.assertEqual(job['edges'], [{'from': 'counts', 'from_port': 0, 'to': 'analysis', 'to_port': 0},
                                                {'from': 'samples', 'from_port': 0, 'to': 'analysis', 'to_port': 1}])
                self.assertEqual(job['nodes'][2]['spec'], proof.PARAMETERS[label])
                self.assertEqual(job['script_sha256'], {key: value['sha256'] for key, value in family['identities'].items() if key != 'manifest.toml'})
                self.assertEqual((job['additional_plugins'], job['panel_overrides'], job['bundles']), ([], [], []))

    def test_method_parameters_and_real_environment_keep_seed_free_deterministic_branches(self):
        self.assertEqual(proof.PARAMETERS['deseq2']['fit_type'], 'mean')
        self.assertEqual(proof.PARAMETERS['deseq2']['lfc_shrink'], 'none')
        self.assertEqual(proof.PARAMETERS['limma']['normalization'], 'tmm')
        for label in proof.KINDS:
            self.assertEqual(proof.PARAMETERS[label]['threads'], 1)
            expected = proof.expected_environment(label)
            self.assertEqual(next(value for key, value in expected.items() if key.endswith('_THREADS')), '1')
            self.assertNotIn('OPENALEX_API_KEY', expected)

    def test_original_manifest_resources_are_not_rewritten_as_tiny_budget_certification(self):
        self.assertEqual(self.family('deseq2')['definition']['resources']['memory'], '4Gi')
        self.assertEqual(self.family('limma')['definition']['resources']['memory'], '6Gi')
        self.assertEqual(self.family('deseq2')['definition']['resources']['cpus'], 2.0)
        self.assertEqual(self.family('limma')['definition']['resources']['cpus'], 2.0)

    def test_positive_and_specific_refusal_reports_are_accepted(self):
        for label in proof.KINDS:
            for negative in (False, True):
                with self.subTest(label=label, negative=negative):
                    self.assertEqual(set(proof.validate_report(self.report(label, negative),
                        {'engine_commit': 'e' * 40}, self.family(label), label, negative)), {'counts', 'samples', 'analysis'})

    def test_actual_sealed_sdk_error_map_shapes_reject_lists_null_extra_keys_or_false_errors(self):
        for negative in (False, True):
            for replacement in ([], None, {'unrelated': {}}, {'analysis': None},
                                {'analysis': {'kind': 'node_error', 'message': 'not-the-actual-node-error'}}):
                report = self.report(negative=negative)
                report['first_run']['errors'] = replacement
                with self.subTest(negative=negative, replacement=replacement), self.assertRaises(ValueError):
                    proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', negative)
        report = self.report(negative=True)
        report['first_run']['errors']['extra'] = copy.deepcopy(report['first_run']['nodes'][2]['error'])
        with self.assertRaises(ValueError):
            proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', True)

    def test_wrong_scope_source_image_reuse_or_false_authority_is_rejected(self):
        mutations = [('scope', 'REAL_RESEARCH'), ('engine_source_revision', 'f' * 40),
            ('original_manifest_sha256', 'b' * 64), ('max_concurrency', True), ('incremental', True),
            ('input_hashing', 'Metadata'), ('native_statistical_factories_registered', True),
            ('scientific_authorized', True), ('current_daemon_verified', True)]
        for key, value in mutations:
            report = self.report()
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', False)
        report = self.report()
        report['first_run']['nodes'][0]['reused'] = True
        with self.assertRaises(ValueError):
            proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', False)
        report = self.report()
        report['first_run']['nodes'][2]['execution']['image_digest'] = 'sha256:' + 'b' * 64
        with self.assertRaises(ValueError):
            proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', False)

    def test_missing_source_or_environment_failure_cannot_satisfy_method_refusal(self):
        for mutation in ('missing_source', 'source_failed', 'oom', 'missing_execution', 'fake_ports'):
            report = self.report(negative=True)
            if mutation == 'missing_source':
                report['first_run']['nodes'].pop(0)
            elif mutation == 'source_failed':
                report['first_run']['nodes'][0]['status'] = 'failed'
            elif mutation == 'oom':
                report['first_run']['nodes'][2]['execution']['exit_code'] = 137
            elif mutation == 'missing_execution':
                report['first_run']['nodes'][2]['execution'] = {}
            else:
                report['first_run']['nodes'][2]['port_assignments'] = {'0': {}}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                proof.validate_report(report, {'engine_commit': 'e' * 40}, self.family('deseq2'), 'deseq2', True)

    def test_both_actual_regular_staged_inputs_require_complete_binding_hashes(self):
        work, scratch, nodes, method, staged = self.inputs()
        observed = proof.checked_inputs(work, method, nodes, scratch)
        self.assertEqual([row['source'] for row in observed], ['counts', 'samples'])
        for field, value in [('to_port', True), ('from_port', False), ('from', 'samples'), ('path', 'vfs:///wrong.tsv')]:
            changed = copy.deepcopy(method)
            changed['inputs'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                proof.checked_inputs(work, changed, nodes, scratch)
        (staged / 'input-1.tsv').write_text('changed')
        with self.assertRaises(ValueError):
            proof.checked_inputs(work, method, nodes, scratch)

    def test_direct_owned_staged_symlinks_are_allowed_but_foreign_targets_are_not(self):
        work, scratch, nodes, method, staged = self.inputs(links=True)
        self.assertEqual(len(proof.checked_inputs(work, method, nodes, scratch)), 2)
        other = work / 'foreign.tsv'
        other.write_bytes((work / 'counts.tsv').read_bytes())
        (staged / 'input-0.tsv').unlink()
        (staged / 'input-0.tsv').symlink_to(other)
        with self.assertRaises(ValueError):
            proof.checked_inputs(work, method, nodes, scratch)

    def test_noninteger_case_changes_only_one_count_without_model_or_axes_change(self):
        rows = [['gene_id', *['S' + str(index) for index in range(12)]]]
        rows += [['G' + str(index), *['17'] * 12] for index in range(200)]
        stream = io.StringIO()
        csv.writer(stream, delimiter='\t', quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(rows)
        changed = list(csv.reader(io.StringIO(proof.fractional_counts(stream.getvalue().encode()).decode()), delimiter='\t'))
        self.assertEqual(changed[1][1], '17.5')
        changed[1][1] = '17'
        self.assertEqual(changed, rows)
        with self.assertRaises(ValueError):
            proof.fractional_counts(b'gene_id\tS1\nG1\t1\n')

    def test_launcher_caps_only_technical_resources_and_preserves_original_managed_backend(self):
        shim = self.root / 'managed-shim'
        shim.write_text('NOT_EXECUTED')
        temporary = self.root / 'tmp'
        temporary.mkdir()
        with mock.patch.dict(os.environ, {'AUTONOMICS_PODMAN_PROGRAM': str(shim)}):
            launcher = proof.install_launcher([str(shim), '--cgroup-manager=cgroupfs'], temporary, self.root)
            arguments = ['podman', 'create', '--name', 'synthetic-run', '--cpus', '2', '--memory', '4294967296',
                         '--env', 'AUTONOMICS_DESEQ2_THREADS=1', '--env', 'OPENALEX_API_KEY=DO_NOT_RECORD']
            with mock.patch.object(proof.sys, 'argv', arguments), mock.patch.object(os, 'execv') as execute:
                exec(compile(launcher[2].read_text(), str(launcher[2]), 'exec'), {})
            forwarded = execute.call_args.args[1]
            self.assertEqual(forwarded[:2], [str(shim), '--cgroup-manager=cgroupfs'])
            self.assertEqual(forwarded[forwarded.index('--memory') + 1], '1073741824')
            self.assertEqual(forwarded[forwarded.index('--cpus') + 1], '1')
        record = json.loads((self.root / 'actual-container-create.jsonl').read_text())
        self.assertEqual(record['original_resources'], dict(cpus='2', memory='4294967296',
                                                          manifest_memory='4Gi', memory_bytes=4294967296))
        self.assertEqual(record['method_environment'], {'AUTONOMICS_DESEQ2_THREADS': '1'})
        self.assertEqual(record['actual_resources'], dict(cpus='1', memory='1073741824',
                                                         memory_bytes=1073741824, human_memory_label='1Gi'))
        self.assertNotIn('DO_NOT_RECORD', json.dumps(record))

    def test_real_sdk_decimal_memory_abi_accepts_only_exact_manifest_bytes(self):
        shim = self.root / 'shim'
        shim.write_text('NOT_EXECUTED')
        temporary = self.root / 'tmp'
        temporary.mkdir()
        with mock.patch.dict(os.environ, {'AUTONOMICS_PODMAN_PROGRAM': str(shim)}):
            launcher = proof.install_launcher([str(shim), '--cgroup-manager=cgroupfs'], temporary, self.root)
            for quantity, manifest in [('4294967296', '4Gi'), ('6442450944', '6Gi')]:
                arguments = ['podman', 'create', '--name', 'toy-' + manifest, '--cpus', '2', '--memory', quantity]
                with mock.patch.object(proof.sys, 'argv', arguments), mock.patch.object(os, 'execv') as execute:
                    exec(compile(launcher[2].read_text(), str(launcher[2]), 'exec'), {})
                    self.assertEqual(execute.call_args.args[1][execute.call_args.args[1].index('--memory') + 1], '1073741824')
            for quantity in ('4Gi', '6Gi', '4294967295', '6442450945', 'unlimited'):
                arguments = ['podman', 'create', '--name', 'wrong', '--cpus', '2', '--memory', quantity]
                with self.subTest(quantity=quantity), mock.patch.object(proof.sys, 'argv', arguments), mock.patch.object(os, 'execv') as execute:
                    with self.assertRaises(SystemExit):
                        exec(compile(launcher[2].read_text(), str(launcher[2]), 'exec'), {})
                    execute.assert_not_called()
        records = [json.loads(line) for line in (self.root / 'actual-container-create.jsonl').read_text().splitlines()]
        self.assertEqual([row['original_resources']['manifest_memory'] for row in records], ['4Gi', '6Gi'])
        self.assertEqual([row['original_resources']['memory_bytes'] for row in records], [4294967296, 6442450944])
        self.assertTrue(all(row['actual_resources']['memory'] == str(row['actual_resources']['memory_bytes'])
                            for row in records))

    def test_readback_argv_uses_actual_decimal_memory_not_a_human_label(self):
        actual = self.root / 'actual.rds'
        reference = self.root / 'reference.rds'
        actual.write_bytes(b'SYNTHETIC_UNIT_NOT_RDS')
        reference.write_bytes(b'SYNTHETIC_UNIT_REFERENCE_NOT_RDS')
        def fake_process(command, **kwargs):
            output = self.root / 'rds-readback/verification.json'
            output.write_text(json.dumps(dict(complete_object_equal_excluding_environment=True,
                tolerance=0, check_environment=False, R_version='4.5.3', DESeq2_version='1.50.2',
                new_statistical_fit_executed=False, independent_new_oracle_generated=False, G0=False)))
            return proof.subprocess.CompletedProcess(command, 0, '', '')
        with mock.patch.object(proof.subprocess, 'run', side_effect=fake_process) as execute:
            proof.readback_rds(['NOT_EXECUTED_SHIM', '--cgroup-manager=cgroupfs'], self.root, actual, reference)
        command = execute.call_args.args[0]
        self.assertIn('--memory=1073741824', command)
        self.assertFalse(any('1Gi' in argument or argument == '--memory=1g' for argument in command))
        self.assertIn('--cpus=1', command)
        self.assertIn('--pull=never', command)
        self.assertIn('--network=none', command)
        self.assertIn('--read-only', command)
        self.assertEqual(command[-1], '/proof/verification.json')

    def test_zero_create_failure_preserves_original_exception_and_cannot_certify_success(self):
        permanent = self.root / 'permanent'
        permanent.mkdir()
        output = permanent / 'proof'
        output.mkdir()
        original = ValueError('original proxy ABI failure')
        with mock.patch.object(proof.direct, 'stopped') as stop:
            with self.assertRaisesRegex(ValueError, 'original proxy ABI failure'):
                try:
                    raise original
                finally:
                    proof.finalize_stoppage([], permanent, output, 1, original)
            stop.assert_not_called()
        diagnostic = json.loads((output / 'zero-create-failure-diagnostic.json').read_text())
        self.assertEqual(diagnostic['recorded_proxy_creates'], 0)
        self.assertFalse(diagnostic['successful_stoppage_or_method_execution_certified'])
        with self.assertRaises(ValueError):
            proof.finalize_stoppage([], permanent, output, 5)
        (permanent / 'container-intents.json').write_text('{}')
        with mock.patch.object(proof.direct, 'stopped', return_value=list(range(5))) as stop:
            self.assertEqual(len(proof.finalize_stoppage([], permanent, output, 5)), 5)
            stop.assert_called_once_with([], permanent, output, 5)

    def test_exact_r_exit_one_and_owned_diagnostic_do_not_accept_python_or_infrastructure_exits(self):
        scratch = self.root / 'scratch'
        scratch.mkdir()
        stderr = scratch / 'stderr.log'
        marker = proof.REFUSALS['deseq2']
        stderr.write_text('Error: ' + marker + '\nExecution halted\n')
        image = proof.direct.FAMILIES['deseq2']['image']
        node = dict(status='failed', port_assignments={}, error=dict(message='R failed: ' + marker),
            execution=dict(exit_code=1, image=image, image_digest=image.split('@', 1)[1],
                           stderr_log=dict(path=str(stderr))))
        self.assertEqual(proof.expected_r_refusal(node, image, marker, scratch), stderr)
        for exit_code in (0, 2, 125, 137, -1, True):
            changed = copy.deepcopy(node)
            changed['execution']['exit_code'] = exit_code
            with self.subTest(exit=exit_code), self.assertRaises(ValueError):
                proof.expected_r_refusal(changed, image, marker, scratch)
        for mutation in ('image', 'stderr', 'message', 'ports'):
            changed = copy.deepcopy(node)
            if mutation == 'image':
                changed['execution']['image'] = image + '-wrong'
            elif mutation == 'stderr':
                other = self.root / 'foreign.log'
                other.write_text(marker)
                changed['execution']['stderr_log']['path'] = str(other)
            elif mutation == 'message':
                changed['error']['message'] = 'OOM'
            else:
                changed['port_assignments'] = {'0': {}}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                proof.expected_r_refusal(changed, image, marker, scratch)

    def test_rds_reader_is_full_exact_object_readback_not_new_fit_or_independent_oracle(self):
        self.assertIn('all.equal(reference,actual,check.environment=FALSE,tolerance=0)', proof.RDS_READER)
        self.assertIn('readRDS(arguments[[1L]])', proof.RDS_READER)
        self.assertIn('readRDS(arguments[[2L]])', proof.RDS_READER)
        self.assertNotIn('DESeq(', proof.RDS_READER)
        self.assertIn('independent_new_oracle_generated=FALSE', proof.RDS_READER)

    def report_files(self, rds=False):
        work = self.root / 'work'
        original = self.root / 'reference-inputs'
        work.mkdir()
        original.mkdir()
        direct_report = {'inputs': {}, 'outputs': {}, 'analysis': {'threads': 1, 'covariates': ['batch']}}
        actual_report = copy.deepcopy(direct_report)
        for port, (key, name) in enumerate((('count_matrix', 'counts.tsv'), ('sample_metadata', 'samples.tsv'))):
            raw = ('TOY-' + name).encode()
            (work / name).write_bytes(raw)
            (original / name).write_bytes(raw)
            digest = hashlib.md5(raw).hexdigest()
            direct_report['inputs'][key] = dict(path=name, md5=digest)
            actual_report['inputs'][key] = dict(path='input-' + str(port) + '.tsv', md5=digest)
        actual_rds = reference_rds = None
        if rds:
            first = self.root / 'actual'
            second = self.root / 'reference'
            first.mkdir()
            second.mkdir()
            actual_rds, reference_rds = first / 'deseq2_dataset.rds', second / 'deseq2_dataset.rds'
            actual_rds.write_bytes(b'TOY-ACTUAL-RDS-NOT-READ-BY-R')
            reference_rds.write_bytes(b'TOY-REFERENCE-RDS-NOT-READ-BY-R')
            direct_report['outputs']['dataset'] = dict(path=reference_rds.name, md5=hashlib.md5(reference_rds.read_bytes()).hexdigest())
            actual_report['outputs']['dataset'] = dict(path=actual_rds.name, md5=hashlib.md5(actual_rds.read_bytes()).hexdigest())
        reference_file, actual_file = self.root / 'reference.json', self.root / 'actual.json'
        reference_file.write_text(json.dumps(direct_report))
        actual_file.write_text(json.dumps(actual_report))
        return actual_file, reference_file, work, original, actual_rds, reference_rds

    def test_report_transport_exceptions_bind_each_complete_input_and_real_rds_checksum(self):
        arguments = self.report_files(rds=True)
        result = proof.compare_reports(*arguments)
        self.assertFalse(result['original_JSON_bytes_equal'])
        self.assertTrue(result['exact_remaining_JSON_fields_equal'])
        self.assertEqual([row['pointer'] for row in result['individually_verified_transport_exceptions']],
            ['/inputs/count_matrix/path', '/inputs/sample_metadata/path', '/outputs/dataset/md5'])

    def test_report_extra_keys_wrong_condition_or_fake_checksums_are_not_normalized_away(self):
        arguments = self.report_files(rds=True)
        actual_file = arguments[0]
        original = json.loads(actual_file.read_text())
        for mutation in ('extra', 'condition', 'input_md5', 'input_path', 'dataset_md5'):
            value = copy.deepcopy(original)
            if mutation == 'extra':
                value['ignored_extra'] = True
            elif mutation == 'condition':
                value['analysis']['covariates'] = []
            elif mutation == 'input_md5':
                value['inputs']['count_matrix']['md5'] = '0' * 32
            elif mutation == 'input_path':
                value['inputs']['count_matrix']['path'] = 'foreign.tsv'
            else:
                value['outputs']['dataset']['md5'] = '0' * 32
            actual_file.write_text(json.dumps(value))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                proof.compare_reports(*arguments)

    def test_json_boolean_integer_pseudo_equality_and_false_rds_tolerance_are_rejected(self):
        arguments = self.report_files(rds=True)
        value = json.loads(arguments[0].read_text())
        value['analysis']['threads'] = True
        arguments[0].write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'types'):
            proof.compare_reports(*arguments)
        self.assertFalse(proof.exact_json(False, 0))
        self.assertFalse(proof.exact_json(0.0, 0))
        self.assertFalse(proof.exact_json({'nested': [True]}, {'nested': [1]}))
        self.assertFalse(proof.exact_json({'value': 1, 'extra': 2}, {'value': 1}))
        self.assertTrue(proof.exact_json({'nested': [0, False, '1', None]}, {'nested': [0, False, '1', None]}))


if __name__ == '__main__':
    unittest.main()
