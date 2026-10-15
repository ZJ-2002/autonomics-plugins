import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import prove_frozen_a_family_runtime as proof


def payload(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenAFamilyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prefix = ['toy-managed-shim', '--root', '/toy/store', '--runroot', '/toy/run']

    def definition(self, kind=None):
        kind = proof.KINDS[0] if kind is None else kind
        directory = self.root / 'toy-method'
        directory.mkdir()
        (directory / 'method.py').write_text('raise AssertionError("toy method must never execute")\n')
        return dict(directory=directory, image='toy-image@sha256:' + '0' * 64,
            node=dict(kind=kind, ports=dict(inputs=[dict(type='file') for _ in range(8 if kind == proof.KINDS[2] else 10)],
                outputs=[dict(path=name) for name in proof.OUTPUTS[kind]]),
                command=dict(interpreter='python3', script_file='method.py',
                    env=dict(FROZEN_A_FAMILY_MODE='publish' if kind == proof.KINDS[2] else 'assemble', PYTHONDONTWRITEBYTECODE='1'))))

    def input_paths(self):
        result = []
        for index in range(10):
            path = self.root / ('toy-input-' + str(index))
            path.write_bytes(('TOY INPUT ' + str(index)).encode())
            result.append(path)
        return result

    def case(self):
        directory = self.root / 'BOUNDARY'
        directory.mkdir()
        rows = []
        for family, count in proof.contract.COUNTS.items():
            for index in range(count):
                missing = index % 4 == 0
                rows.append(dict(analysis_id=family + '_' + str(index), family_id=family,
                    scope=proof.contract.SYNTHETIC, scenario='BOUNDARY', p_raw='NA' if missing else '0.03',
                    primary_method='STRICT_IUT' if family.endswith('PATHS') else 'IVW',
                    reason='MISSING_COMPONENT' if missing else 'COMPLETE_COMPONENTS'))
        vectors = []
        for family in proof.contract.COUNTS:
            for method in ['BH', 'BY'] if family.endswith('EDGES') else ['BY']:
                for row in rows:
                    if row['family_id'] == family:
                        vectors.append(dict(vector_id='/'.join([proof.contract.SYNTHETIC, 'BOUNDARY', family, method]),
                            analysis_id=row['analysis_id'], p_raw=row['p_raw'], method=method))
        adjusted_rows = [dict(**row, q='1' if row['p_raw'] == 'NA' else '0.42') for row in vectors]
        complete = [dict(**row, p_for_adjustment='1' if row['p_raw'] == 'NA' else row['p_raw'],
            q_BH='NA' if row['family_id'].endswith('PATHS') else '1' if row['p_raw'] == 'NA' else '0.42',
            q_BY='1' if row['p_raw'] == 'NA' else '0.42', family_n=proof.contract.COUNTS[row['family_id']]) for row in rows]
        columns = ['analysis_id', 'family_id', 'scope', 'scenario', 'p_raw', 'primary_method', 'reason']
        vector_columns = ['vector_id', 'analysis_id', 'p_raw', 'method']
        all_payloads = [
            [payload(rows, columns), payload(vectors, vector_columns), b'{"output_sha256":{}}\n', b'toy assembly log'],
            [payload(adjusted_rows, [*vector_columns, 'q']), b'OPAQUE_TOY_RDS',
                json.dumps(dict(stats_version='4.6.1', output_sha256={})).encode(), b'toy adjustment log'],
            [payload(complete, [*columns, 'p_for_adjustment', 'q_BH', 'q_BY', 'family_n']),
                payload(adjusted_rows, [*vector_columns, 'q']), b'{}', b'toy publication log'],
        ]
        products = []
        for kind, contents in zip(proof.KINDS, all_payloads, strict=True):
            stage = directory / kind
            stage.mkdir()
            paths = []
            for name, content in zip(proof.OUTPUTS[kind], contents, strict=True):
                path = stage / name
                path.write_bytes(content)
                paths.append(path)
            products.append(paths)
        oracle_vectors, oracle_reference = [], []
        for scenario in [*proof.contract.SCENARIOS, 'REAL_FROZEN_NA_LEDGER']:
            for row in vectors:
                copied = dict(row, vector_id=row['vector_id'].replace('/BOUNDARY/', '/' + scenario + '/'))
                oracle_vectors.append(copied)
            for row in adjusted_rows:
                copied = dict(row, vector_id=row['vector_id'].replace('/BOUNDARY/', '/' + scenario + '/'))
                oracle_reference.append(copied)
        return directory, products[0], products[1], products[2], oracle_vectors, oracle_reference

    def test_execute_stub_records_actual_exit_and_only_declared_ports_and_environment(self):
        definition = self.definition()
        inputs = self.input_paths()
        output = self.root / 'execution'
        seen = []
        def method_stub(command, **options):
            seen.append(command)
            for name in proof.OUTPUTS[proof.KINDS[0]]:
                (output / name).write_bytes(b'NONEMPTY TOY OUTPUT; NO REAL METHOD EXECUTED')
            return subprocess.CompletedProcess(command, 0, b'toy stdout', b'')
        with mock.patch.object(proof.subprocess, 'run', side_effect=method_stub):
            products = proof.execute(self.prefix, definition, inputs, output)
        self.assertEqual(len(products), 4)
        self.assertEqual(len(seen), 1)
        command = seen[0]
        self.assertEqual(command[:len(self.prefix)], self.prefix)
        environment = [command[index + 1] for index, value in enumerate(command[:-1]) if value == '-e']
        names = [item.split('=', 1)[0] for item in environment]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), {'FROZEN_A_FAMILY_MODE', 'PYTHONDONTWRITEBYTECODE',
            *{'AUTONOMICS_INPUT' + str(index) for index in range(10)},
            *{'AUTONOMICS_OUTPUT' + str(index) for index in range(4)}})
        self.assertEqual(command[-2:], [definition['image'], '/method/source'])
        record = json.loads((output / 'execution.json').read_text())
        self.assertEqual(record['actual_exit'], 0)
        self.assertEqual([row['port'] for row in record['inputs']], list(range(10)))
        self.assertEqual(record['command'], command)

    def test_execute_rejects_oom_instead_of_counting_it_as_expected_method_refusal(self):
        definition = self.definition()
        output = self.root / 'oom'
        def method_stub(command, **options):
            (output / 'assembly.log').write_text('intended diagnostic, but this is OOM')
            return subprocess.CompletedProcess(command, 137, b'', b'intended diagnostic')
        with mock.patch.object(proof.subprocess, 'run', side_effect=method_stub):
            with self.assertRaisesRegex(RuntimeError, 'exit differs'):
                proof.execute(self.prefix, definition, self.input_paths(), output, expected_exit=2,
                    expected_diagnostic='intended diagnostic')

    def test_execute_refusal_must_match_specific_diagnostic_and_keep_normal_outputs_absent(self):
        definition = self.definition()
        output = self.root / 'wrong-refusal'
        def method_stub(command, **options):
            (output / 'assembly.log').write_text('unrelated contract failure')
            return subprocess.CompletedProcess(command, 2, b'', b'unrelated contract failure')
        with mock.patch.object(proof.subprocess, 'run', side_effect=method_stub):
            with self.assertRaisesRegex(RuntimeError, 'different reason'):
                proof.execute(self.prefix, definition, self.input_paths(), output, expected_exit=2,
                    expected_diagnostic='specific injected violation')

    def test_execute_detects_foreign_output_modified_despite_expected_refusal(self):
        definition = self.definition(proof.KINDS[2])
        output = self.root / 'foreign'
        def method_stub(command, **options):
            (output / 'family.tsv').write_bytes(b'CHANGED FOREIGN CONTENT')
            (output / 'family.log').write_text('foreign output refusal')
            return subprocess.CompletedProcess(command, 2, b'', b'foreign output refusal')
        with mock.patch.object(proof.subprocess, 'run', side_effect=method_stub):
            with self.assertRaisesRegex(RuntimeError, 'modified a foreign output'):
                proof.execute(self.prefix, definition, self.input_paths()[:8], output, expected_exit=2,
                    expected_diagnostic='foreign output refusal', foreign_outputs={'family.tsv': b'FOREIGN'})

    def test_execute_zero_exit_without_every_declared_port_cannot_pass(self):
        definition = self.definition()
        output = self.root / 'partial-ports'
        def method_stub(command, **options):
            for name in ['assembly.tsv', 'vectors.tsv', 'assembly.log']:
                (output / name).write_bytes(b'TOY PARTIAL OUTPUT')
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with mock.patch.object(proof.subprocess, 'run', side_effect=method_stub):
            with self.assertRaises((RuntimeError, FileNotFoundError)):
                proof.execute(self.prefix, definition, self.input_paths(), output)

    def test_complete_toy_case_checks_all_564_results_and_840_adjusted_rows(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)
        report = json.loads((directory / 'comparison.json').read_text())
        self.assertEqual((report['full_result_rows'], report['full_vector_rows'], report['full_q_equal']), (564, 840, 840))
        self.assertFalse(report['actual_DAG_executed'])

    def test_wrong_official_q_cannot_pass_case_comparison(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        rows = proof.tables(adjusted[0])
        rows[-1]['q'] = '0.43'
        adjusted[0].write_bytes(payload(rows, list(rows[0])))
        with self.assertRaisesRegex(RuntimeError, 'Every official q'):
            proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)

    def test_raw_na_relabelled_as_one_cannot_pass_oracle_comparison(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        rows = proof.tables(assembled[1])
        next(row for row in rows if row['p_raw'] == 'NA')['p_raw'] = '1'
        assembled[1].write_bytes(payload(rows, list(rows[0])))
        with self.assertRaisesRegex(RuntimeError, 'primary/IUT vector row'):
            proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)

    def test_final_family_denominator_and_missing_reason_cannot_change(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        baseline = proof.tables(published[0])
        for key, value in [('family_n', '87'), ('reason', 'DROPPED_MISSING'), ('p_raw', '1')]:
            rows = copy.deepcopy(baseline)
            rows[0][key] = value
            published[0].write_bytes(payload(rows, list(rows[0])))
            with self.assertRaisesRegex(RuntimeError, 'Final family changes'):
                proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)

    def test_shortened_vectors_and_complete_byte_transport_mismatch_are_rejected(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        original = assembled[1].read_bytes()
        rows = proof.tables(assembled[1])[:-1]
        assembled[1].write_bytes(payload(rows, list(rows[0])))
        with self.assertRaisesRegex(RuntimeError, 'six complete frozen vectors'):
            proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)
        assembled[1].write_bytes(original)
        published[1].write_bytes(published[1].read_bytes() + b'\n')
        with self.assertRaisesRegex(RuntimeError, 'Full published correction vector changed'):
            proof.compare_case(directory, 'BOUNDARY', assembled, adjusted, published, vectors, reference)

    def test_negative_controls_stub_exercises_exact_16_distinct_injected_contracts(self):
        directory, assembled, adjusted, published, vectors, reference = self.case()
        output = self.root / 'negative-suite'
        output.mkdir()
        boundary = output / 'BOUNDARY'
        boundary.mkdir()
        (boundary / 'request.json').write_text('{}')
        original_inputs = self.input_paths()[:9]
        edges = [dict(edge_id='E' + str(index), family='A_PRIMARY_EDGES' if index < 88 else 'A_EXPANDED_EDGES')
            for index in range(276)]
        calls = []
        def refused_stub(prefix, definition, inputs, target, **options):
            calls.append(dict(case=target.name, kind=definition['node']['kind'], inputs=inputs, options=options))
            self.assertEqual(options['expected_exit'], 2)
            self.assertTrue(options['expected_diagnostic'])
            return []
        methods = {kind: dict(node=dict(kind=kind)) for kind in proof.KINDS}
        with mock.patch.object(proof, 'execute', side_effect=refused_stub), mock.patch.object(proof.subprocess, 'run') as external:
            observed = proof.negative_controls(self.prefix, methods, output, original_inputs, edges, (assembled, adjusted))
            external.assert_not_called()
        self.assertEqual(len(observed), 16)
        self.assertEqual(len(calls), 16)
        self.assertEqual(len({call['case'] for call in calls}), 16)
        by_case = {call['case']: call for call in calls}
        self.assertEqual([sum(call['kind'] == kind for call in calls) for kind in proof.KINDS], [11, 2, 3])
        self.assertIn(b'Infinity', by_case['nonfinite-p']['inputs'][-1].read_bytes())
        changed = by_case['changed-frozen-source']
        self.assertEqual(changed['inputs'][7].read_bytes(), original_inputs[7].read_bytes() + b'\n')
        self.assertEqual(changed['options']['expected_diagnostic'], 'Frozen input size differs before reading payload')
        shortened = by_case['shortened-vector']
        self.assertEqual(len(proof.tables(shortened['inputs'][0])), 839)
        receipt = json.loads(shortened['inputs'][2].read_text())
        self.assertEqual(receipt['output_sha256']['vectors.tsv'], sha(shortened['inputs'][0]))
        wrong_method = proof.tables(by_case['wrong-path-method']['inputs'][0])
        self.assertTrue(any('/A_PRIMARY_PATHS/' in row['vector_id'] and row['method'] == 'BH' for row in wrong_method))
        self.assertEqual(json.loads(by_case['wrong-R-version']['inputs'][5].read_text())['stats_version'], '4.5.1')
        self.assertEqual(proof.tables(by_case['nonfinite-q']['inputs'][3])[0]['q'], 'NaN')
        self.assertEqual(by_case['foreign-output']['options']['foreign_outputs'], {'family.tsv': b'FOREIGN_OUTPUT_MUST_REMAIN\n'})
        self.assertEqual(9 + len(observed), 25)

    def test_rds_comparator_source_contract_requires_distinct_scenarios_and_complete_metadata(self):
        source = proof.RDS_READBACK
        for fragment in ['metadata$scenario,c("BOUNDARY","INTERIOR","REAL_FROZEN_NA_LEDGER")',
                'identical(names(payload$vectors),expected_keys)', '!anyDuplicated(c(seen,names(payload$vectors)))',
                'length(seen)==18L', 'setequal(seen,unique(reference$vector_id))',
                'identical(payload$input_sha256,expected_hashes)', 'identical(payload$adjustment_definition,definition)',
                'c("vectors.tsv","assembly.tsv","assembly-receipt.json","g0_v432_methods.R")',
                'identical(value$q,stats::p.adjust(adjusted_input,method=method))', 'identical(value$q,as.numeric(expected$q))']:
            self.assertIn(fragment, source)
        self.assertIn('identical(names(value)', source)
        self.assertIn('identical(is.na(value$p_raw),expected$p_raw=="NA")', source)

    def test_rds_readback_stub_runs_positive_and_two_specific_counterexamples(self):
        output = self.root / 'readback'
        output.mkdir()
        executable = self.root / 'toy-Rscript-not-executed'
        executable.write_bytes(b'NO RUNTIME EXECUTION')
        paths = []
        for scenario in [*proof.contract.SCENARIOS, 'REAL_FROZEN_NA_LEDGER']:
            directory = self.root / scenario / 'adjust'
            directory.mkdir(parents=True)
            path = directory / 'adjustment.RDS'
            path.write_bytes(b'OPAQUE TOY RDS')
            (directory / 'adjustment-receipt.json').write_text(json.dumps(dict(scenario=scenario,
                input_sha256={name: character * 64 for name, character in zip(
                    ['vectors.tsv', 'assembly.tsv', 'assembly-receipt.json', 'g0_v432_methods.R'], 'abcd', strict=True)})))
            paths.append(path)
        calls = []
        def r_stub(command, **options):
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 0, b'OFFICIAL_RDS_READBACK_18_VECTORS_2520_VALUES_EXACT', b'')
            marker = b'names(payload$vectors)' if len(calls) == 2 else b'payload$input_sha256'
            return subprocess.CompletedProcess(command, 1, b'', marker + b' is not TRUE')
        with mock.patch.multiple(proof.contract, RSCRIPT=executable, RSCRIPT_SHA=sha(executable), STUDY=self.root / 'toy-study'), \
                mock.patch.object(proof.subprocess, 'run', side_effect=r_stub), mock.patch.dict(os.environ, TMPDIR=str(self.root)):
            proof.official_rds_readback(output, self.root / 'toy-archives', paths)
        self.assertEqual(len(calls), 3)
        metadata = proof.tables(output / 'official-rds-input-metadata.tsv')
        self.assertEqual([row['scenario'] for row in metadata], ['BOUNDARY', 'INTERIOR', 'REAL_FROZEN_NA_LEDGER'])
        repeated = proof.tables(output / 'official-rds-repeated-scenario-object.tsv')
        self.assertEqual(repeated[1]['rds_path'], repeated[0]['rds_path'])
        changed = proof.tables(output / 'official-rds-changed-input-hash.tsv')
        self.assertEqual(changed[0]['vectors_sha'], '0' * 64)


if __name__ == '__main__':
    unittest.main()
