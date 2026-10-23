import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import test_frozen_a_family_assembly as fixture_module

family = fixture_module.family

SPEC = importlib.util.spec_from_file_location('seen_replay_target', ROOT / 'research-adapters/frozen-a-family-assembly/replay/seen_real_v1.py')
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class SeenRealReplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.FrozenAFamilyAssemblyTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.patch = mock.patch.object(replay, 'family', family)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.root = self.fixture.root
        self.source = self.root / 'seen-results.tsv'
        self.source.write_bytes(b'edge\tmethod\tp\nE0\tIVW\t0.02\nE1\tIVW\t0.20\nE2\tIVW\t0.50\n')
        digest = family.checksum(self.source.read_bytes())
        self.request = dict(schema=replay.REQUEST, scope=replay.SCOPE,
            sources=[dict(source_id='seen-three', path=str(self.source), sha256=digest)],
            seen_history=[dict(source_id='seen-three', sha256=digest, seen_at='2026-01-01T00:00:00+00:00',
                declaration='ALREADY_SEEN_NOT_INDEPENDENT')],
            edges=[dict(analysis_id='E' + str(index), status='ESTIMATED', source_id='seen-three',
                selector=dict(edge='E' + str(index), method='IVW'), p_column='p', estimator='IVW_EXPLORATORY') for index in range(3)])
        self.request_path = self.root / 'request.json'

    def run_request(self):
        self.request_path.write_bytes(family.json_bytes(self.request))
        products = replay.assemble(self.fixture.inputs[:9], self.request_path)
        return family.table(products['replay-family.tsv']), family.table(products['replay-vectors.tsv']), json.loads(products['replay-assembly.json'])

    def test_full_families_and_primary_separation(self):
        rows, vectors, receipt = self.run_request()
        self.assertEqual(len(rows), 564)
        self.assertEqual(len(vectors), 840)
        self.assertEqual(len({row['vector_id'] for row in vectors}), 6)
        self.assertTrue(all(row['p_primary'] == 'NA' for row in rows))
        self.assertTrue(all(row['primary_qualification'] == 'NOT_EVALUATED_NOT_GRANTED' for row in rows))
        self.assertEqual(next(row for row in rows if row['analysis_id'] == 'P0')['replay_p_raw'], '0.2')
        self.assertEqual(next(row for row in rows if row['analysis_id'] == 'E3')['technical_status'], 'NOT_RUN')
        self.assertEqual(receipt['registered_total_unchanged'], 696)
        self.assertFalse(receipt['primary_results_published'])
        self.assertFalse(receipt['scientific_family_complete'])
        self.assertFalse(receipt['MR_estimates_computed'])

    def test_missing_component_stays_na_and_adjusts_as_one(self):
        self.request['edges'] = self.request['edges'][:1]
        rows, vectors, receipt = self.run_request()
        path = next(row for row in rows if row['analysis_id'] == 'P0')
        self.assertEqual((path['technical_status'], path['replay_p_raw'], path['replay_p_for_adjustment']), ('NOT_RUN', 'NA', '1'))
        self.assertTrue(all(row['replay_p_for_adjustment'] == '1' for row in vectors if row['replay_p_raw'] == 'NA'))

    def test_failed_and_not_estimable_are_not_not_run(self):
        self.request['edges'][1].update(status='FAILED', p_column=None)
        self.request['edges'][2].update(status='NOT_ESTIMABLE', p_column=None)
        rows, unused, receipt = self.run_request()
        statuses = {row['analysis_id']: row['technical_status'] for row in rows}
        self.assertEqual(statuses['E1'], 'FAILED')
        self.assertEqual(statuses['E2'], 'NOT_ESTIMABLE')
        self.assertEqual(statuses['E3'], 'NOT_RUN')
        self.assertEqual(statuses['P0'], 'FAILED')

    def test_duplicate_or_unknown_id_rejected(self):
        for identifier in ['E0', 'OUTSIDE_FROZEN_UNIVERSE']:
            with self.subTest(identifier=identifier):
                self.request['edges'][1]['analysis_id'] = identifier
                with self.assertRaises(ValueError):
                    self.run_request()

    def test_source_hash_drift_rejected(self):
        self.source.write_bytes(self.source.read_bytes().replace(b'0.02', b'0.03'))
        with self.assertRaisesRegex(ValueError, 'source bytes changed'):
            self.run_request()

    def test_view_history_required_and_bound(self):
        for mutation in ['missing', 'hash', 'independent']:
            with self.subTest(mutation=mutation):
                request = copy.deepcopy(self.request)
                if mutation == 'missing':
                    self.request['seen_history'] = []
                elif mutation == 'hash':
                    self.request['seen_history'][0]['sha256'] = '0' * 64
                else:
                    self.request['seen_history'][0]['declaration'] = 'NEW_INDEPENDENT_VALIDATION'
                with self.assertRaises(ValueError):
                    self.run_request()
                self.request = request

    def test_ambiguous_row_rejected(self):
        self.request['edges'][0]['selector'] = {'method': 'IVW'}
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.run_request()

    def test_nonfinite_missing_and_invalid_probabilities_rejected(self):
        for value in ['nan', 'Inf', '-0.1', '1.1', 'NA']:
            with self.subTest(value=value):
                content = b'edge\tmethod\tp\nE0\tIVW\t' + value.encode() + b'\nE1\tIVW\t0.2\nE2\tIVW\t0.5\n'
                self.source.write_bytes(content)
                digest = family.checksum(content)
                self.request['sources'][0]['sha256'] = digest
                self.request['seen_history'][0]['sha256'] = digest
                with self.assertRaises(ValueError):
                    self.run_request()

    def test_primary_or_eligibility_override_rejected(self):
        for key in ['p_primary', 'overlap_class', 'mrlap_eligible', 'usual_eligible', 'qualification_receipt']:
            with self.subTest(key=key):
                self.request['edges'][0][key] = True
                with self.assertRaisesRegex(ValueError, 'overrides are forbidden'):
                    self.run_request()
                del self.request['edges'][0][key]

    def test_failed_result_cannot_smuggle_probability(self):
        self.request['edges'][0]['status'] = 'FAILED'
        with self.assertRaisesRegex(ValueError, 'cannot supply a P'):
            self.run_request()

    def test_existing_primary_scope_is_not_widened(self):
        with self.assertRaises(ValueError):
            family.scope_scenario(replay.SCOPE, 'SEEN_REAL')

    def test_future_view_history_rejected(self):
        self.request['seen_history'][0]['seen_at'] = '9999-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'cannot be in the future'):
            self.run_request()

    def test_duplicate_history_source_and_unused_source_rejected(self):
        self.request['seen_history'].append(copy.deepcopy(self.request['seen_history'][0]))
        self.request['sources'].append(copy.deepcopy(self.request['sources'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate view history'):
            self.run_request()

    def test_path_with_unestimable_component_remains_unestimable(self):
        self.request['edges'][1].update(status='NOT_ESTIMABLE', p_column=None)
        rows, unused, receipt = self.run_request()
        path = next(row for row in rows if row['analysis_id'] == 'P0')
        self.assertEqual((path['technical_status'], path['replay_p_raw']), ('NOT_ESTIMABLE', 'NA'))

    def test_new_r_stage_uses_frozen_official_definition_only(self):
        script = (ROOT / 'research-adapters/frozen-a-family-assembly/replay/adjust_seen_v1.R').read_text()
        self.assertIn('2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd', script)
        self.assertIn('adjusted <- official$adjust_full(raw, method)', script)
        self.assertIn('new.env(parent = asNamespace("stats"))', script)
        self.assertNotIn('p_primary <-', script)

    def bounded_history(self, upper='2026-01-01'):
        history_path = self.root / 'RESULT_EXPOSURE_LOG.tsv'
        payload = ('analysis_id\tfirst_result_viewed_at\tstatus\tallowed_identity\r\n' + ''.join(
            'E' + str(index) + '\tON_OR_BEFORE_' + upper + '_EXACT_FIRST_VIEW_UNKNOWN\tLEGACY_PIPELINE_ANALYZED\tLEGACY_EXPLORATORY_TECHNICAL_REANALYSIS\r\n'
            for index in range(3))).encode()
        history_path.write_bytes(payload)
        self.request['seen_history'] = [dict(source_id='seen-three', sha256=self.request['sources'][0]['sha256'],
            declaration='ALREADY_SEEN_NOT_INDEPENDENT', precision='ON_OR_BEFORE_DATE', upper_bound_date=upper,
            exact_first_view_known=False, history_file=dict(path=str(history_path), sha256=family.checksum(payload)),
            analysis_ids=['E0', 'E1', 'E2'])]

    def test_unknown_first_view_preserves_upper_bound_and_original_rows(self):
        self.bounded_history()
        unused, unused_vectors, receipt = self.run_request()
        history = receipt['sources'][0]['history']
        self.assertFalse(history['exact_first_view_known'])
        self.assertNotIn('seen_at', history)
        self.assertEqual(history['upper_bound_basis'], 'ANALYSIS_ID_HISTORY_NOT_RESULT_BYTE_FIRST_VIEW')
        self.assertEqual(len(history['original_history_rows']), 3)
        first = history['original_history_rows'][0]
        self.assertTrue(first['raw_row_utf8'].endswith('\r\n'))
        self.assertEqual(first['raw_row_sha256'], family.checksum(first['raw_row_utf8'].encode()))
        self.assertEqual(first['original_row']['first_result_viewed_at'], 'ON_OR_BEFORE_2026-01-01_EXACT_FIRST_VIEW_UNKNOWN')

    def test_future_upper_bound_rejected(self):
        self.bounded_history('9999-01-01')
        with self.assertRaisesRegex(ValueError, 'cannot be in the future'):
            self.run_request()

    def test_mixed_time_precision_or_wrong_history_mapping_rejected(self):
        self.bounded_history()
        self.request['seen_history'][0]['seen_at'] = '2026-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'XOR'):
            self.run_request()
        del self.request['seen_history'][0]['seen_at']
        self.request['seen_history'][0]['analysis_ids'] = ['E0', 'E1']
        with self.assertRaisesRegex(ValueError, 'exactly match selected'):
            self.run_request()


if __name__ == '__main__':
    unittest.main()
