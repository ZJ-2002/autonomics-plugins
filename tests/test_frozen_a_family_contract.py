import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tools import prove_frozen_a_family_contract as proof


COUNTS = dict(A_PRIMARY_EDGES=3, A_EXPANDED_EDGES=3, A_PRIMARY_PATHS=1, A_EXPANDED_PATHS=1)


def assert_ids(actual, expected):
    actual, expected = list(actual), list(expected)
    if len(set(actual)) != len(actual) or len(set(expected)) != len(expected) or set(actual) != set(expected):
        raise ValueError('Exact unique IDs required')


def checked_p(value):
    if value is None:
        return None
    if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Invalid toy P')
    return value


def fixture():
    edges = [dict(edge_id='EDGE_' + str(index), family='A_PRIMARY_EDGES' if index < 3 else 'A_EXPANDED_EDGES')
             for index in range(6)]
    paths = [dict(path_id='PATH_' + str(index), family=family, xm_edge_id='EDGE_0', my_edge_id='EDGE_1',
        xy_edge_id='EDGE_2', test='max(p_XM,p_MY)', correction='BY', select_by_pairwise_significance='NO',
        product_p_can_promote='NO') for index, family in enumerate(['A_PRIMARY_PATHS', 'A_EXPANDED_PATHS'])]
    ledger = [dict(analysis_id=row.get('edge_id', row.get('path_id')), family_id=row['family'],
        status='NOT_ESTIMABLE', p_raw='NA', p_for_adjustment='1') for row in edges + paths]
    decisions = [dict(edge_id=row['edge_id']) for row in edges]
    locks = [dict(family_id=family, status='LOCKED', n_tests=str(count)) for family, count in COUNTS.items()]
    multiplicity = [dict(family_id=family, locked_count=str(count)) for family, count in COUNTS.items()]

    def primary_p(overlap, ivw, mrlap, *, usual_eligible, mrlap_eligible, rules):
        ivw, mrlap = checked_p(ivw), checked_p(mrlap)
        value = ivw if overlap == 'O0' and usual_eligible else mrlap if overlap == 'O1' and usual_eligible and mrlap_eligible else None
        return dict(p=value, method='toy', reason='toy')

    helpers = types.SimpleNamespace(assert_locked_ids=mock.Mock(side_effect=assert_ids),
        primary_p=mock.Mock(side_effect=primary_p), strict_conjunction=mock.Mock(side_effect=lambda first, second:
            None if first is None or second is None else max(first, second)))
    return edges, paths, ledger, decisions, locks, multiplicity, helpers


class FrozenAFamilyContractTests(unittest.TestCase):
    def test_nine_pinned_sources_and_full_four_family_counts(self):
        self.assertEqual(len(proof.SOURCES), 9)
        self.assertEqual(len({row[0] for row in proof.SOURCES}), 9)
        self.assertEqual(proof.COUNTS, dict(A_PRIMARY_EDGES=88, A_EXPANDED_EDGES=188, A_PRIMARY_PATHS=36, A_EXPANDED_PATHS=252))
        for name, size, digest in proof.SOURCES:
            self.assertFalse(Path(name).is_absolute())
            self.assertGreater(size, 0)
            self.assertRegex(digest, '^[a-f0-9]{64}$')

    def test_complete_toy_universe_uses_original_interface_without_shortening(self):
        *tables, helpers = fixture()
        proof.validate_universe(*tables, helpers, counts=COUNTS)
        self.assertEqual(helpers.assert_locked_ids.call_count, 6)

    def test_missing_duplicate_foreign_and_wrong_family_are_rejected(self):
        *tables, helpers = fixture()
        for changed in [tables[0][:-1], [*tables[0][:-1], tables[0][0]],
                        [*tables[0][:-1], dict(edge_id='FOREIGN', family='A_EXPANDED_EDGES')]]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                proof.validate_universe(changed, *tables[1:], helpers, counts=COUNTS)
        changed = copy.deepcopy(tables)
        changed[0][0]['family'] = 'A_EXPANDED_EDGES'
        with self.assertRaises(ValueError):
            proof.validate_universe(*changed, helpers, counts=COUNTS)

    def test_missing_component_and_significance_selected_paths_are_rejected(self):
        for field, value in [('xm_edge_id', 'MISSING'), ('select_by_pairwise_significance', 'YES'), ('product_p_can_promote', 'YES')]:
            *tables, helpers = fixture()
            tables[1][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                proof.validate_universe(*tables, helpers, counts=COUNTS)

    def test_synthetic_qualifications_never_change_real_decisions(self):
        edges, _, _, decisions, _, _, helpers = fixture()
        before = copy.deepcopy(decisions)
        inputs = proof.synthetic_inputs(edges)
        result = proof.edge_results(inputs, edges, helpers, {})
        self.assertEqual(decisions, before)
        self.assertEqual(result['EDGE_1']['p_raw'], .003)
        self.assertIsNone(result['EDGE_2']['p_raw'])
        self.assertIsNone(result['EDGE_3']['p_raw'])
        self.assertEqual(helpers.primary_p.call_count, 6)
        extended = [dict(edge_id='EDGE_' + str(index), family='A_PRIMARY_EDGES') for index in range(12)]
        boundary = proof.synthetic_inputs(extended)
        self.assertEqual(boundary[0]['ivw_p'], 0.)
        self.assertEqual(boundary[6]['ivw_p'], 1.)
        self.assertEqual([proof.synthetic_inputs([dict(edge_id=str(index), family='A_PRIMARY_EDGES')
            for index in range(30)])[index]['mrlap_p'] for index in [1, 7, 13, 19, 25]], [.003, .005, .007, .009, .011])

    def test_all_eight_mechanical_refusals_are_asserted(self):
        edges, paths, _, _, _, _, helpers = fixture()
        results = proof.refused_cases(proof.synthetic_inputs(edges), edges, paths, helpers, {})
        self.assertEqual(len(results), 8)
        self.assertTrue(all(row['rejected'] for row in results))

    def test_nonboolean_eligibility_is_rejected(self):
        edges, _, _, _, _, _, helpers = fixture()
        inputs = proof.synthetic_inputs(edges)
        inputs[0]['usual_eligible'] = 'YES'
        with self.assertRaisesRegex(ValueError, 'boolean'):
            proof.edge_results(inputs, edges, helpers, {})

    def test_missing_component_is_not_replaced_by_available_p(self):
        edges, paths, _, _, _, _, helpers = fixture()
        result = proof.edge_results(proof.synthetic_inputs(edges), edges, helpers, {})
        result['EDGE_0']['p_raw'] = None
        actual = proof.all_results(edges, paths, result, helpers)
        self.assertIsNone(actual['PATH_0']['p_raw'])
        helpers.strict_conjunction.side_effect = lambda first, second: second
        with self.assertRaisesRegex(ValueError, 'strict IUT'):
            proof.all_results(edges, paths, result, helpers)

    def test_ledger_raw_missing_values_are_kept_not_reclassified(self):
        _, _, ledger, _, _, _, _ = fixture()
        result = proof.ledger_results(ledger)
        self.assertTrue(all(row['p_raw'] is None and row['scope'] == proof.LEDGER for row in result.values()))
        ledger[0]['p_raw'] = '.01'
        with self.assertRaisesRegex(ValueError, 'actual frozen'):
            proof.ledger_results(ledger)

    def test_complete_vectors_include_all_rows_and_correct_methods(self):
        edges, paths, ledger, _, _, _, helpers = fixture()
        values = proof.ledger_results(ledger)
        rows = proof.vectors(values, edges, paths, helpers, counts=COUNTS)
        self.assertEqual(len(rows), 14)
        self.assertEqual(len({row['vector_id'] for row in rows}), 6)
        self.assertTrue(all(row['p_raw'] == 'NA' for row in rows))
        del values['EDGE_5']
        with self.assertRaises(ValueError):
            proof.vectors(values, edges, paths, helpers, counts=COUNTS)

    def test_original_adjustment_definition_requires_unique_single_expression(self):
        definition = 'adjust_full <- function(p,method="BH") p.adjust(ifelse(is.finite(p),p,1),method=method)\n'
        self.assertEqual(proof.adjustment_definition('unrelated\n' + definition), definition)
        for text in ['', definition * 2, 'adjust_full <- function(p) { p }\n']:
            with self.assertRaises(ValueError):
                proof.adjustment_definition(text)

    def test_source_hash_change_is_rejected_with_self_cleaning_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'toy.py'
            path.write_bytes(b'original')
            pins = [('toy.py', 8, hashlib.sha256(b'original').hexdigest())]
            with mock.patch.object(proof, 'SOURCES', pins):
                self.assertEqual(len(proof.source_records(root)), 1)
                path.write_bytes(b'modified')
                with self.assertRaisesRegex(ValueError, 'SHA'):
                    proof.source_records(root)

    def test_official_reference_comparison_cannot_silently_change_q(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'Rscript'
            binary.write_bytes(b'toy nonexecuted runtime')
            rows = [dict(vector_id=proof.SYNTHETIC + '/BOUNDARY/A_PRIMARY_EDGES/' + method, analysis_id=identifier,
                p_raw='NA' if identifier == 'missing' else '.01', method=method)
                for method in ['BH', 'BY'] for identifier in ['toy', 'missing']]

            def process(command, **kwargs):
                original = proof.read_table(Path(command[-2]))
                with Path(command[-1]).open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=[*original[0], 'q'], delimiter='\t')
                    writer.writeheader()
                    values = []
                    for row in original:
                        value = 1 if row['p_raw'] == 'NA' else .06 if row['method'] == 'BY' else .03
                        if Path(command[-1]).name == 'official-shortened-control.tsv' and row['p_raw'] != 'NA':
                            value /= 2
                        if Path(command[-1]).parent.name == 'corrupt' and Path(command[-1]).name == 'official-reference.tsv':
                            value = .9
                        values.append({**row, 'q': str(value)})
                    writer.writerows(values)
                return types.SimpleNamespace(returncode=0, stdout='R=4.6.1;stats=4.6.1;rows=4\n', stderr='')

            with mock.patch.multiple(proof, RSCRIPT=binary, RSCRIPT_SHA=proof.sha(binary), COUNTS={'A_PRIMARY_EDGES': 2}), \
                    mock.patch.dict('os.environ', TMPDIR=directory), mock.patch.object(proof.subprocess, 'run', side_effect=process) as invoked:
                self.assertEqual(proof.r_adjustments(root, rows, 'toy function\n')['exact_official_q_equal'], 4)
                self.assertEqual(invoked.call_count, 3)
                self.assertIn('stats::p.adjust', (root / 'official-reference.R').read_text())
                corrupt = root / 'corrupt'
                corrupt.mkdir()
                with self.assertRaisesRegex(ValueError, 'independent official row'):
                    proof.r_adjustments(corrupt, rows, 'toy function\n')

    def test_binary_only_or_indistinguishable_bh_by_benchmark_is_rejected(self):
        rows = [dict(vector_id=proof.SYNTHETIC + '/A_PRIMARY_EDGES/' + method, analysis_id='toy', p_raw='.01',
            method=method, q='0') for method in ['BH', 'BY']]
        with self.assertRaisesRegex(ValueError, 'interior'):
            proof.adjustment_coverage(rows, rows, families=['A_PRIMARY_EDGES'])
        for row in rows:
            row['q'] = '.1'
        with self.assertRaisesRegex(ValueError, 'distinguish BH and BY'):
            proof.adjustment_coverage(rows, rows, families=['A_PRIMARY_EDGES'])

    def test_shortened_family_must_change_nonmissing_q_without_relabelling_ids(self):
        rows = [dict(vector_id=proof.SYNTHETIC + '/A_PRIMARY_EDGES/' + method, analysis_id='toy', p_raw='.01',
            method=method, q=value) for method, value in [('BH', '.1'), ('BY', '.2')]]
        with self.assertRaisesRegex(ValueError, 'visibly change'):
            proof.adjustment_coverage(rows, rows, families=['A_PRIMARY_EDGES'])
        changed = copy.deepcopy(rows)
        changed[0]['analysis_id'] = 'foreign'
        with self.assertRaisesRegex(ValueError, 'identities'):
            proof.adjustment_coverage(rows, changed, families=['A_PRIMARY_EDGES'])

    def test_second_scenario_preserves_ids_qualifications_and_boundary_fixture(self):
        edges, paths, _, _, _, _, helpers = fixture()
        boundary = proof.synthetic_inputs(edges)
        interior = proof.synthetic_inputs(edges, 'INTERIOR')
        self.assertEqual(boundary[0]['ivw_p'], 0)
        self.assertEqual(interior[0]['ivw_p'], .002)
        for first, second in zip(boundary, interior, strict=True):
            self.assertEqual({key: value for key, value in first.items() if key not in {'scenario', 'ivw_p'}},
                {key: value for key, value in second.items() if key not in {'scenario', 'ivw_p'}})
        values = [proof.all_results(edges, paths, proof.edge_results(rows, edges, helpers, {}), helpers)
                  for rows in [boundary, interior]]
        rows = [row for value in values for row in proof.vectors(value, edges, paths, helpers, counts=COUNTS)]
        self.assertEqual(len({row['vector_id'] for row in rows}), 12)
        mixed = copy.deepcopy(interior)
        mixed[0]['scenario'] = 'BOUNDARY'
        with self.assertRaisesRegex(ValueError, 'cannot be mixed'):
            proof.edge_results(mixed, edges, helpers, {})

    def test_global_interior_coverage_cannot_hide_a_degenerate_second_family(self):
        baseline = [dict(vector_id=proof.SYNTHETIC + '/INTERIOR/' + family + '/' + method,
            analysis_id='toy', p_raw='.01', method=method, q=value)
            for family in ['A_PRIMARY_EDGES', 'A_PRIMARY_PATHS']
            for method, value in ([('BH', '.1'), ('BY', '.2')] if family.endswith('EDGES') else [('BY', '1')])]
        shortened = [{**row, 'q': '.05' if row['vector_id'].split('/')[-2].endswith('EDGES') else '1'} for row in baseline]
        with self.assertRaisesRegex(ValueError, 'Each complete synthetic family'):
            proof.adjustment_coverage(baseline, shortened, families=['A_PRIMARY_EDGES', 'A_PRIMARY_PATHS'])

    def test_mixed_scope_or_scenario_cannot_split_a_complete_family_denominator(self):
        edges, paths, ledger, _, _, _, helpers = fixture()
        for scope, scenario in [(proof.SYNTHETIC, 'INTERIOR'), (proof.LEDGER, 'REAL_FROZEN_NA_LEDGER')]:
            results = proof.all_results(edges, paths,
                proof.edge_results(proof.synthetic_inputs(edges), edges, helpers, {}), helpers)
            results['EDGE_0']['scope'], results['EDGE_0']['scenario'] = scope, scenario
            with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, 'one scope and scenario'):
                proof.vectors(results, edges, paths, helpers, counts=COUNTS)
        values = proof.ledger_results(ledger)
        rows = proof.vectors(values, edges, paths, helpers, counts=COUNTS)
        with mock.patch.object(proof, 'COUNTS', COUNTS):
            proof.validate_vector_lengths(rows)
            changed = copy.deepcopy(rows)
            changed[0]['vector_id'] = proof.SYNTHETIC + '/INTERIOR/A_PRIMARY_EDGES/BH'
            with self.assertRaisesRegex(ValueError, 'complete frozen family length'):
                proof.validate_vector_lengths(changed)

    def test_cli_requires_managed_session_before_creating_outputs(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Managed validation'):
                proof.main()


if __name__ == '__main__':
    unittest.main()
