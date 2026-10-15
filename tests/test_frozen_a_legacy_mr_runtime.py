import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('legacy_a_runtime_under_test', ROOT / 'tools/prove_frozen_a_legacy_mr_runtime.py')
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def fixture_summary():
    return dict(schema='FROZEN_A_REAL_39_LEGACY_OFFICIAL_REFERENCE_V1', variants=39, seed=432202610,
        R='4.6.1', TwoSampleMR='0.7.11', original_run_A_block_sha256=TOOL.BLOCK_SHA,
        original_scientific_source_sha256=TOOL.METHOD_SHA, original_scientific_statements_unchanged=True,
        whole_original_cli_executed=False, original_verifier_not_faked=True, outer_whole_project_verifier_required=True,
        overlap_class='O2', primary_p_source='NA', all_main_primary_missing=True, all_main_adjustment_one=True,
        six_complete_TSVs_byte_equal=True, six_complete_TSVs_readback_equal=True,
        complete_RDS_object_identical=True, RDS_numeric_tolerance=0, input_harmonised_object_identical=True,
        independent_official_call_sequence=['mr', 'mr_heterogeneity', 'mr_pleiotropy_test', 'mr_leaveoneout', 'mr', 'mr', 'mr'],
        methods=['mr_ivw', 'mr_egger_regression', 'mr_weighted_median'], official_namespace_function_count=171,
        official_namespace_aggregate_sha256=TOOL.qualification.PACKAGE_FUNCTIONS_SHA,
        package_description_sha256=TOOL.qualification.PACKAGE_DESCRIPTION_SHA, observed_RemoteSha=None,
        all_nine_current_ports_checked=True, full_provenance_contract_checked=True, complete_log_checked=True,
        log_byte_equal_to_original_cli_claimed=False,
        adapter_added_fields_disclosed=['p_raw_exploratory', 'contract', 'qualified_input_serialization', 'RDS', 'diagnostic_log', 'provenance'],
        actual_DAG_executed=False, new_independent_scientific_evidence=False, MRlap_executed=False,
        other_275_edges_executed=False, production_changed=False, scientific_authorization_granted=False, g0_granted=False,
        tables=[dict(port=index, name=name, complete_bytes_equal=True, complete_readback_equal=True, rows=3)
            for index, name in enumerate(TOOL.OUTPUTS[:6])])


class FrozenALegacyRuntimeDraftTests(unittest.TestCase):
    def rejected(self, value):
        with self.assertRaises((RuntimeError, ValueError)):
            TOOL.validate_summary(value)

    def test_execution_requires_explicit_request_before_any_side_effect(self):
        with mock.patch.object(TOOL.Path, 'mkdir') as create:
            with self.assertRaisesRegex(ValueError, 'Explicit --execute'):
                TOOL.main([])
        create.assert_not_called()

    def test_branch_extraction_checks_order_identity_and_uniqueness(self):
        begin, end = '} else if(mode=="run-A") {\n', '\n} else if(mode=="run-B") {'
        body = '  ORIGINAL_TOY_STATEMENT\n'
        source = 'preamble\n' + begin + body + end + '\nnext branch'
        with mock.patch.object(TOOL, 'BLOCK_SHA', hashlib.sha256(body.encode()).hexdigest()):
            self.assertEqual(TOOL.run_a_block(source), body)
            for invalid in (source.replace(body, body + '\n'), source + begin, source + end, end + begin + body):
                with self.subTest(source=invalid):
                    with self.assertRaises((RuntimeError, ValueError)):
                        TOOL.run_a_block(invalid)

    def test_summary_complete_proposed_contract_positive(self):
        self.assertEqual(TOOL.validate_summary(fixture_summary()), fixture_summary())

    def test_summary_rejects_primary_and_scope_promotions(self):
        changes = [('overlap_class', 'O1'), ('primary_p_source', 'IVW'), ('all_main_primary_missing', False),
            ('all_main_adjustment_one', False), ('whole_original_cli_executed', True), ('original_verifier_not_faked', False)]
        changes += [(name, True) for name in ('actual_DAG_executed', 'new_independent_scientific_evidence',
            'MRlap_executed', 'other_275_edges_executed', 'production_changed', 'scientific_authorization_granted', 'g0_granted')]
        for name, wrong in changes:
            value = fixture_summary()
            value[name] = wrong
            with self.subTest(name=name):
                self.rejected(value)

    def test_summary_rejects_missing_tables_duplicate_ports_and_loose_numeric_scope(self):
        for transform in (lambda value: value['tables'].pop(),
                lambda value: value['tables'].__setitem__(1, copy.deepcopy(value['tables'][0])),
                lambda value: value['tables'][0].__setitem__('rows', True),
                lambda value: value['tables'][0].__setitem__('port', False),
                lambda value: value.__setitem__('variants', True),
                lambda value: value.__setitem__('RDS_numeric_tolerance', 1e-12),
                lambda value: value.__setitem__('RDS_numeric_tolerance', False),
                lambda value: value.__setitem__('official_namespace_function_count', True)):
            value = fixture_summary()
            transform(value)
            self.rejected(value)

    def test_summary_rejects_changed_original_sequence_or_package_identity(self):
        for name, wrong in [('original_run_A_block_sha256', 'a' * 64),
                ('original_scientific_source_sha256', 'b' * 64), ('methods', ['mr_ivw']),
                ('independent_official_call_sequence', ['mr']),
                ('official_namespace_aggregate_sha256', 'c' * 64), ('observed_RemoteSha', 'invented')]:
            value = fixture_summary()
            value[name] = wrong
            with self.subTest(name=name):
                self.rejected(value)

    def test_summary_requires_complete_log_provenance_and_explicit_added_wrapper_fields(self):
        for name, wrong in [('complete_log_checked', False), ('full_provenance_contract_checked', False),
                ('log_byte_equal_to_original_cli_claimed', True), ('adapter_added_fields_disclosed', []),
                ('all_nine_current_ports_checked', False), ('six_complete_TSVs_readback_equal', False)]:
            value = fixture_summary()
            value[name] = wrong
            self.rejected(value)

    def test_current_and_reference_commands_are_serial_bounded_no_pull_and_fixed_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, inputs, output = [Path(temporary) / name for name in ('source', 'inputs', 'output')]
            for reference in (False, True):
                arguments = TOOL.command(['/owned/shim', '--cgroup-manager=cgroupfs'], source, inputs, output, reference)
                for expected in ('--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
                        '--userns=keep-id', TOOL.IMAGE, 'R_LIBS_USER=/nonexistent'):
                    self.assertIn(expected, arguments)
                self.assertNotIn('--detach', arguments)
                self.assertNotIn(str(TOOL.STUDY), arguments)
                self.assertTrue(arguments[-1].startswith('/source/'))
                if not reference:
                    self.assertEqual(sum(argument.startswith('AUTONOMICS_INPUT') for argument in arguments), 5)
                    self.assertEqual(sum(argument.startswith('AUTONOMICS_OUTPUT') for argument in arguments), 9)

    def test_reference_source_is_frozen_and_only_two_original_guard_statements_move(self):
        source = (ROOT / TOOL.INNER).read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), TOOL.INNER_SHA)
        self.assertIn('identical(excluded, c(4L, 5L))', source)
        self.assertIn('for (statement in program$retained) eval(statement, envir=scope)', source)
        self.assertIn('utils::write.table(x, file, ...)', source)
        self.assertNotIn('TwoSampleMR::mr(', source)
        self.assertNotIn('TwoSampleMR::mr_heterogeneity(', source)
        self.assertNotIn('.libPaths(', source)
        self.assertNotIn('system2 <-', source)
        self.assertIn('original_library_path_injection_executed=FALSE', source)
        self.assertIn('if (sys.nframe() == 0L) main()', source)

    def test_all_five_inputs_and_nine_already_seen_references_remain_exact(self):
        self.assertEqual(len(TOOL.INPUTS), 4)
        self.assertEqual(len(TOOL.OLD_HASHES), 9)
        self.assertEqual(TOOL.OLD_HASHES[5], TOOL.INPUTS[0][1])
        self.assertEqual(len(TOOL.OUTPUTS), len(set(TOOL.OUTPUTS)))
        self.assertEqual(len(TOOL.OUTPUTS), 9)
        self.assertEqual(TOOL.PINS[TOOL.PLUGIN + 'scripts/mr.R'],
            '33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe')
        self.assertEqual(TOOL.PINS[TOOL.PLUGIN + 'contracts/frozen-method-proof.json'],
            'a79c4469321bcef7ffabb9f94ad557ca185409bd9177868a3c158d8debb484c2')

    def test_summary_rejects_inexact_serialized_or_complete_object_comparisons(self):
        for field in ('six_complete_TSVs_byte_equal', 'six_complete_TSVs_readback_equal',
                'complete_RDS_object_identical', 'input_harmonised_object_identical'):
            value = fixture_summary()
            value[field] = False
            self.rejected(value)
        value = fixture_summary()
        value['tables'][3]['complete_bytes_equal'] = False
        self.rejected(value)


if __name__ == '__main__':
    unittest.main()
