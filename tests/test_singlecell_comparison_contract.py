import ast
import copy
import json
from pathlib import Path
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPARISON = ROOT / 'plugins/single-cell/tests/qc_compare.py'
SUBSET = ROOT / 'plugins/single-cell/tests/test_subset_by_obs.py'


def load_functions(path, names, namespace):
    selected = [node for node in ast.parse(path.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise ValueError('Exact production-test helpers required')
    fragment = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(fragment)
    exec(compile(fragment, str(path), 'exec'), namespace)
    return namespace


class FakeArray:
    def __init__(self, shape, dtype='float64'):
        self.shape, self.dtype = shape, dtype


class FakeSparse(FakeArray):
    def __init__(self, shape, dtype='float64', form='csr'):
        super().__init__(shape, dtype)
        self.format = form


class FakeDataset(FakeArray):
    pass


class FakeGroup:
    pass


def report_fixture():
    cells = ['001', '1', 'α', '四', 'cell5', 'cell6']
    settings = dict(requested=['四', '001'], join_column='cell_id')
    packages = {name: 'SYNTHETIC_VERSION' for name in ['anndata', 'numpy', 'pandas', 'pyarrow', 'h5py']}
    report = dict(schema_version='2.0', operation='subset_by_obs', join_column='cell_id',
        selection_semantics='obs_names', input_cells=6, output_cells=2, input_genes=5, output_genes=5,
        requested_unique_cells=2, requested_unique_values=2, matched_unique_values=2,
        missing_cells=0, missing_values=[], requested_values=['四', '001'],
        matched_cells_per_value={'四': 1, '001': 1}, selection_order='input_H5AD_observation_order_not_request_order',
        selected_cell_ids=['001', '四'], cell_ledger=[dict(input_index=index, cell_id=cell,
            join_value=cell, retained=index in {0, 3}) for index, cell in enumerate(cells)],
        preexisting_subset_params_overwritten=False, preexisting_derived_artifacts_recomputed=False,
        matrix_policy='slice only; no normalization, mapping, QC, or scale selection',
        memory_policy='load whole AnnData; full-scale memory acceptance not established',
        donor_eligibility='NOT_VERIFIED', scientific_release='NOT_GRANTED', G0=False,
        packages=packages, input_sha256='a' * 64, selection_sha256='b' * 64, warnings=[],
        outputs=[dict(port=0, name='output.h5ad', sha256='c' * 64, bytes=32)],
        report_hash_policy='port_1_hash_recorded_externally_not_recursively')
    arguments = (settings, cells, cells, 5, 'output.h5ad', 32, 'c' * 64, 'a' * 64, 'b' * 64, False, packages)
    return report, arguments


class SingleCellComparisonContractTests(unittest.TestCase):
    def setUp(self):
        self.functions = load_functions(COMPARISON,
            ['assert_array_contract', 'assert_sparse_contract', 'assert_hdf5_object_contract'],
            dict(np=types.SimpleNamespace(asarray=lambda value: value),
                 sparse=types.SimpleNamespace(issparse=lambda value: isinstance(value, FakeSparse)),
                 h5py=types.SimpleNamespace(Dataset=FakeDataset)))
        self.reports = load_functions(SUBSET, ['strict_report_json', 'validate_subset_report'], dict(json=json))

    def test_array_scalar_broadcast_shape_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.functions['assert_array_contract'](FakeArray(()), FakeArray((2,)))
        actual, expected = FakeArray((2,)), FakeArray((2,))
        self.assertEqual(self.functions['assert_array_contract'](actual, expected), (actual, expected))

    def test_array_dtype_is_checked_independently_of_shape(self):
        with self.assertRaises(AssertionError):
            self.functions['assert_array_contract'](FakeArray((2,), 'int64'), FakeArray((2,), 'float64'))

    def test_sparse_shape_is_checked_even_with_identical_payload_metadata(self):
        with self.assertRaises(AssertionError):
            self.functions['assert_sparse_contract'](FakeSparse((1, 3)), FakeSparse((1, 2)))
        self.functions['assert_sparse_contract'](FakeSparse((1, 2)), FakeSparse((1, 2)))

    def test_sparse_format_type_and_dtype_are_checked(self):
        for actual in [FakeSparse((1, 2), form='csc'), FakeArray((1, 2)), FakeSparse((1, 2), dtype='int64')]:
            with self.subTest(actual=actual), self.assertRaises(AssertionError):
                self.functions['assert_sparse_contract'](actual, FakeSparse((1, 2)))

    def test_hdf5_dataset_shape_and_dtype_are_checked(self):
        for actual in [FakeDataset(()), FakeDataset((2,), 'int64')]:
            with self.subTest(actual=actual), self.assertRaises(AssertionError):
                self.functions['assert_hdf5_object_contract'](actual, FakeDataset((2,)))
        self.functions['assert_hdf5_object_contract'](FakeDataset((2,)), FakeDataset((2,)))

    def test_hdf5_group_dataset_substitution_is_rejected(self):
        for actual, expected in [(FakeGroup(), FakeDataset(())), (FakeDataset(()), FakeGroup())]:
            with self.subTest(expected=expected), self.assertRaises(AssertionError):
                self.functions['assert_hdf5_object_contract'](actual, expected)
        self.functions['assert_hdf5_object_contract'](FakeGroup(), FakeGroup())

    def test_strict_report_json_rejects_all_nonfinite_constants(self):
        for value in ['NaN', 'Infinity', '-Infinity']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'non-standard report number'):
                self.reports['strict_report_json']('{"warnings":[' + value + ']}')
        self.assertEqual(self.reports['strict_report_json']('{"finite":0.5}'), {'finite': .5})

    def test_strict_report_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, 'duplicate report key'):
            self.reports['strict_report_json']('{"G0":true,"G0":false}')

    def test_full_six_row_report_and_one_external_hash_receipt_are_checked(self):
        report, arguments = report_fixture()
        self.assertEqual(self.reports['validate_subset_report'](report, *arguments), 6)

    def test_omitting_unselected_ledger_rows_or_changing_row_identity_is_rejected(self):
        report, arguments = report_fixture()
        changed = copy.deepcopy(report)
        changed['cell_ledger'] = [row for row in changed['cell_ledger'] if row['retained']]
        with self.assertRaises(AssertionError):
            self.reports['validate_subset_report'](changed, *arguments)
        for field, value in [('cell_id', 'FOREIGN'), ('join_value', 'FOREIGN'), ('input_index', 99), ('retained', True)]:
            changed = copy.deepcopy(report)
            changed['cell_ledger'][1][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.reports['validate_subset_report'](changed, *arguments)

    def test_all_output_receipt_fields_and_extra_ports_are_rejected(self):
        report, arguments = report_fixture()
        for field, value in [('port', 1), ('name', 'other.h5ad'), ('sha256', 'f' * 64), ('bytes', 33)]:
            changed = copy.deepcopy(report)
            changed['outputs'][0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.reports['validate_subset_report'](changed, *arguments)
        changed = copy.deepcopy(report)
        changed['outputs'].append(dict(port=1, name='report.json'))
        with self.assertRaises(AssertionError):
            self.reports['validate_subset_report'](changed, *arguments)

    def test_authority_selection_and_derived_artifact_policies_cannot_change(self):
        report, arguments = report_fixture()
        for field, value in [('G0', True), ('scientific_release', 'GRANTED'), ('donor_eligibility', 'VERIFIED'),
                ('selection_semantics', 'requested_order'), ('selection_order', 'requested_order'),
                ('preexisting_derived_artifacts_recomputed', True), ('preexisting_subset_params_overwritten', True),
                ('matrix_policy', 'normalize'), ('memory_policy', 'bounded streaming'),
                ('report_hash_policy', 'self_hash'), ('join_column', 'other'), ('schema_version', '1.0')]:
            changed = copy.deepcopy(report)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.reports['validate_subset_report'](changed, *arguments)

    def test_boolean_counts_and_integer_ledger_status_are_not_valid_json_types(self):
        report, arguments = report_fixture()
        for field, value in [('missing_cells', False), ('G0', 0), ('preexisting_subset_params_overwritten', 0)]:
            changed = copy.deepcopy(report)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.reports['validate_subset_report'](changed, *arguments)
        changed = copy.deepcopy(report)
        changed['cell_ledger'][0]['retained'] = 1
        with self.assertRaises(AssertionError):
            self.reports['validate_subset_report'](changed, *arguments)

    def test_missing_and_extra_report_fields_are_rejected(self):
        report, arguments = report_fixture()
        for field in ['cell_ledger', 'outputs', 'warnings', 'packages']:
            changed = copy.deepcopy(report)
            del changed[field]
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.reports['validate_subset_report'](changed, *arguments)
        with self.assertRaises(AssertionError):
            self.reports['validate_subset_report']({**report, 'extra': 1}, *arguments)

    def test_group_membership_counts_and_source_order_are_preserved(self):
        report, arguments = report_fixture()
        settings, cells, _, *remaining = arguments
        values = ['d1', 'd1', 'd2', 'd2', 'd3', 'd3']
        settings = dict(requested=['d3', 'd1'], join_column='donor')
        report.update(join_column='donor', selection_semantics='obs_group_membership', output_cells=4,
            requested_values=['d3', 'd1'], matched_cells_per_value={'d3': 2, 'd1': 2},
            selected_cell_ids=[cells[index] for index in [0, 1, 4, 5]],
            cell_ledger=[dict(input_index=index, cell_id=cell, join_value=values[index], retained=index in {0, 1, 4, 5})
                         for index, cell in enumerate(cells)])
        self.assertEqual(self.reports['validate_subset_report'](report, settings, cells, values, *remaining), 6)

    def test_warning_records_require_a_list_of_strings(self):
        report, arguments = report_fixture()
        for value in [None, 'warning', [1]]:
            with self.subTest(value=value), self.assertRaises(AssertionError):
                self.reports['validate_subset_report']({**report, 'warnings': value}, *arguments)


if __name__ == '__main__':
    unittest.main()
