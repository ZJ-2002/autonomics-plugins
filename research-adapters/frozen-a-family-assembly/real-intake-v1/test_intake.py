"""Self-cleaning toy source fixtures: no study data or scientific signatures."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'tests'))
import test_frozen_a_family_assembly as fixtures
spec = importlib.util.spec_from_file_location('real_intake_target', HERE / 'intake.py')
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FrozenAFamilyAssemblyTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.family = fixtures.family
        for module in [intake, intake.seen]:
            patch = mock.patch.object(module, 'family', self.family)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(intake, 'require', self.family.require)
        patch.start()
        self.addCleanup(patch.stop)
        decisions = [dict(edge_id='E'+str(i), overlap_class='PENDING', evidence_file='', usual_MR_eligible='PENDING',
            MRlap_applicability='PENDING', diagnostics_file='', primary_p_source='UNASSIGNED', p_primary='',
            ivw_parallel='IF_ESTIMABLE', method_selected_from_p='NO', status='NOT_FROZEN') for i in range(276)]
        payload = self.family.tsv(decisions, list(decisions[0]))
        self.fixture.inputs[3].write_bytes(payload)
        self.fixture.sources[3] = (self.fixture.sources[3][0], len(payload), self.family.checksum(payload))
        self.source = self.root / 'result.tsv'
        self.source.write_bytes(b'edge\tmethod\tp\tstatus\treason\nE0\tIVW\t0.02\tESTIMATED\t\nE1\tMRlap_corrected\tNA\tFAILED\tworker exit 1\nE2\tIVW\tNA\tNOT_ESTIMABLE\tno instruments\n')
        self.rds = self.root / 'original.RDS'
        self.rds.write_bytes(b'OPAQUE_TOY_RDS_IDENTITY_NOT_OFFICIAL_R_OBJECT')
        sha = self.family.checksum(self.source.read_bytes())
        self.request = dict(schema=intake.REQUEST, scope=intake.SCOPE,
            sources=[dict(source_id='s', path=str(self.source), sha256=sha)],
            seen_history=[dict(source_id='s', sha256=sha, declaration='ALREADY_SEEN_NOT_INDEPENDENT', seen_at='2026-01-01T00:00:00+00:00')],
            edges=[dict(analysis_id='E0', status='ESTIMATED', source_id='s', selector=dict(edge='E0'), p_column='p',
                estimator='IVW', analysis_id_column='edge', method_column='method', status_column='status', failure_reason_column=None,
                rds=dict(path=str(self.rds), sha256=self.family.checksum(self.rds.read_bytes())))])
        self.request_path = self.root / 'request.json'

    def run_request(self):
        self.request_path.write_bytes(self.family.json_bytes(self.request))
        products = intake.assemble(self.fixture.inputs[:9], self.request_path)
        return self.family.table(products['real-family.tsv']), self.family.table(products['real-vectors.tsv']), json.loads(products['real-assembly.json'])

    def test_estimate_and_rds_preserved_with_missing_primary(self):
        rows, vectors, receipt = self.run_request()
        self.assertEqual((len(rows), len(vectors), receipt['registered_total_unchanged']), (564, 840, 696))
        self.assertEqual((rows[0]['execution_status'], rows[0]['observed_p'], rows[0]['p_primary']), ('ESTIMATED', '0.02', 'NA'))
        self.assertEqual(receipt['edge_evidence'][0]['rds']['sha256'], self.request['edges'][0]['rds']['sha256'])
        self.assertTrue(all(row['p_primary'] == 'NA' and row['p_for_adjustment'] == '1' for row in vectors))
        self.assertEqual(rows[276]['primary_qualification'], 'MISSING_COMPONENT_PRIMARY')
        self.assertEqual(rows[1]['execution_status'], 'NOT_RUN')

    def test_failure_unestimable_and_not_run_are_distinct(self):
        for identifier, status, method in [('E1', 'FAILED', 'MRlap_corrected'), ('E2', 'NOT_ESTIMABLE', 'IVW')]:
            self.request['edges'].append(dict(analysis_id=identifier, status=status, source_id='s', selector=dict(edge=identifier),
                p_column=None, estimator=method, analysis_id_column='edge', method_column='method', status_column='status', failure_reason_column='reason', rds=None))
        rows, unused, receipt = self.run_request()
        self.assertEqual([row['execution_status'] for row in rows[:4]], ['ESTIMATED','FAILED','NOT_ESTIMABLE','NOT_RUN'])
        self.assertEqual(receipt['edge_evidence'][1]['original_row']['reason'], 'worker exit 1')
        self.assertEqual(receipt['path_dependencies'][0]['component_execution_status'], ['ESTIMATED','FAILED'])

    def test_identity_and_selector_rejections(self):
        for mutation in ['source', 'rds', 'selector', 'method', 'status', 'id', 'row_id']:
            old = copy.deepcopy(self.request)
            if mutation == 'source': self.request['sources'][0]['sha256'] = '0'*64
            if mutation == 'rds': self.request['edges'][0]['rds']['sha256'] = '0'*64
            if mutation == 'selector': self.request['edges'][0]['selector'] = {'method': 'IVW'}
            if mutation == 'method': self.request['edges'][0]['estimator'] = 'MRlap_corrected'
            if mutation == 'status': self.request['edges'][0]['status'] = 'FAILED'
            if mutation == 'row_id': self.request['edges'][0]['analysis_id'] = 'E1'
            if mutation == 'id': self.request['edges'][0]['analysis_id'] = 'FOREIGN'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.run_request()
            self.request = old

    def test_qualification_or_primary_overrides_rejected(self):
        for key in ['approved', 'p_primary', 'overlap_class', 'usual_eligible', 'qualification_receipt']:
            self.request['edges'][0][key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'overrides forbidden'): self.run_request()
            del self.request['edges'][0][key]

    def test_unversioned_decision_change_rejected(self):
        rows = self.family.table(self.fixture.inputs[3].read_bytes())
        rows[0]['overlap_class'] = 'O0'
        payload = self.family.tsv(rows, list(rows[0]))
        self.fixture.inputs[3].write_bytes(payload)
        self.fixture.sources[3] = (self.fixture.sources[3][0], len(payload), self.family.checksum(payload))
        with self.assertRaisesRegex(ValueError, 'versioned contract'): self.run_request()

    def test_missing_rds_and_missing_history_rejected(self):
        self.request['edges'][0]['rds'] = None
        with self.assertRaisesRegex(ValueError, 'RDS identity'): self.run_request()
        self.request['seen_history'] = []
        with self.assertRaises(ValueError): self.run_request()

    def test_bounded_history_is_not_retimestamped(self):
        history = self.root / 'history.tsv'
        history.write_bytes(b'analysis_id\tfirst_result_viewed_at\tstatus\tallowed_identity\r\nE0\tON_OR_BEFORE_2026-01-01_EXACT_FIRST_VIEW_UNKNOWN\tLEGACY_PIPELINE_ANALYZED\tLEGACY_EXPLORATORY_TECHNICAL_REANALYSIS\r\n')
        self.request['seen_history'] = [dict(source_id='s', sha256=self.request['sources'][0]['sha256'],
            declaration='ALREADY_SEEN_NOT_INDEPENDENT', precision='ON_OR_BEFORE_DATE', upper_bound_date='2026-01-01',
            exact_first_view_known=False, history_file=dict(path=str(history), sha256=self.family.checksum(history.read_bytes())), analysis_ids=['E0'])]
        unused, unused_vectors, receipt = self.run_request()
        saved = receipt['sources'][0]['history']
        self.assertNotIn('seen_at', saved)
        self.assertFalse(saved['exact_first_view_known'])
        self.assertTrue(saved['original_history_rows'][0]['raw_row_utf8'].endswith('\r\n'))

    def test_exact_existing_o2_decision_and_ivw_missing_primary(self):
        row = dict(edge_id='A_X01_M06', overlap_class='O2',
            evidence_file='03_AUDIT/G0_v4.3.2_2026-10-11/A_MINIMUM_INPUT_CARD.json',
            usual_MR_eligible='INPUTS_QUALIFIED;OVERLAP_UNRESOLVED',
            MRlap_applicability='NOT_QUALIFIED_NOT_ENABLED',
            diagnostics_file='03_AUDIT/G0_v4.3.2_2026-10-11/A_HARMONIZATION_QUALIFICATION.json',
            primary_p_source='NA', p_primary='NA', ivw_parallel='EXPLORATORY_ONLY',
            method_selected_from_p='NO', status='LOCKED_O2_PRIMARY_NA')
        self.assertEqual(intake.pending_decision(row), 'OVERLAP_UNRESOLVED')
        row['primary_p_source'] = 'IVW'
        with self.assertRaises(ValueError): intake.pending_decision(row)

    def test_estimated_path_keeps_qualification_missing(self):
        payload = self.source.read_bytes().replace(b'E1\tMRlap_corrected\tNA\tFAILED\tworker exit 1', b'E1\tIVW\t0.2\tESTIMATED\t')
        self.source.write_bytes(payload)
        digest = self.family.checksum(payload)
        self.request['sources'][0]['sha256'] = digest
        self.request['seen_history'][0]['sha256'] = digest
        record = copy.deepcopy(self.request['edges'][0])
        record.update(analysis_id='E1', selector=dict(edge='E1'))
        self.request['edges'].append(record)
        rows, unused, receipt = self.run_request()
        self.assertEqual((rows[276]['execution_status'], rows[276]['p_primary'], rows[276]['primary_qualification']),
            ('ESTIMATED', 'NA', 'MISSING_COMPONENT_PRIMARY'))

    def test_old_scopes_not_accepted(self):
        self.request['scope'] = intake.seen.SCOPE
        with self.assertRaises(ValueError): self.run_request()


if __name__ == '__main__':
    unittest.main()
