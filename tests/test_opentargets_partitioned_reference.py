import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import prove_opentargets_partitioned_reference as proof


def response(count, rows):
    return dict(data=dict(meta=dict(name='author API',
        apiVersion=dict(x='26', y='9', z='0', suffix=None),
        dataVersion=dict(year='26', month='09', iteration=None)),
        disease=dict(id=proof.CONTROL, associatedTargets=dict(count=count, rows=rows,
            datasources=[dict(id='author_source', weight=1.0, propagate=True, required=False)]))))


def row(identity='ENSG00000000001'):
    return dict(score=.5, novelty=None,
        target=dict(id=identity, approvedSymbol='symbol', approvedName='', biotype=''),
        datasourceScores=[dict(id='source', score=.5)], datatypeScores=[])


class PartitionedPreflightTests(unittest.TestCase):
    def test_only_nonempty_unique_bounded_literal_ids_are_sent(self):
        valid = ['ENSG00000000001', 'ENSG00000000002']
        self.assertEqual(proof.validate_ids(valid), valid)
        for ids in [[], valid * 2, [' '], ['a/b'], [None], [['nested']], ['A'] * 3001]:
            with self.subTest(ids=ids[:3]), self.assertRaises(RuntimeError):
                proof.validate_ids(ids)
        request = proof.operation(valid)
        self.assertEqual(request['variables']['ids'], valid)
        self.assertIn('Bs: $ids', request['query'])
        self.assertIn('enableIndirect: false', request['query'])
        self.assertEqual(request['variables']['size'], 3000)
        guard = proof.operation(None)
        self.assertNotIn('Bs:', guard['query'])
        self.assertNotIn('ids', guard['variables'])
        self.assertEqual(guard['variables']['size'], 0)

    def test_exact_complete_single_page_retains_blank_and_nullable_values(self):
        original = response(1, [row()])
        before = copy.deepcopy(original)
        metadata, settings, rows = proof.check_page(original, ['ENSG00000000001'])
        self.assertEqual(rows, [row()])
        self.assertEqual(original, before)
        self.assertEqual(metadata['dataVersion']['month'], '09')
        self.assertEqual(settings[0]['weight'], 1.0)
        self.assertEqual(proof.check_page(response(0, []), ['ABSENT'])[2], [])

    def test_partial_duplicate_leaked_and_boolean_count_are_refused(self):
        for count, rows in [(2, [row()]), (2, [row(), row()]), (1, [row('LEAK')]), (True, [row()])]:
            with self.subTest(count=count, rows=rows), self.assertRaises(RuntimeError):
                proof.check_page(response(count, rows), ['ENSG00000000001', 'ENSG00000000002'])
        with self.assertRaises(RuntimeError):
            proof.check_page(response(proof.GUARD_COUNT - 1, []), None)
        with self.assertRaises(RuntimeError):
            proof.check_page(response(proof.GUARD_COUNT, [row()]), None)

    def test_versions_settings_nonfinite_scores_and_null_annotations_fail_closed(self):
        cases = []
        bad = response(1, [row()]); bad['data']['meta']['dataVersion']['month'] = '10'; cases.append(bad)
        bad = response(1, [row()]); bad['data']['disease']['associatedTargets']['datasources'][0]['weight'] = True; cases.append(bad)
        bad = response(1, [row()]); bad['data']['disease']['associatedTargets']['rows'][0]['score'] = float('nan'); cases.append(bad)
        bad = response(1, [row()]); bad['data']['disease']['associatedTargets']['rows'][0]['target']['biotype'] = None; cases.append(bad)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                proof.check_page(case, ['ENSG00000000001'])

    def test_redirects_are_not_followed_outside_four_post_budget(self):
        self.assertIsNone(proof.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid'))

    def test_seven_request_collection_uses_independent_cardinality_and_preserves_api_values(self):
        identities = [f'ID{position}' for position in range(9)]
        captured = []
        def post(output, position, request):
            captured.append(request)
            ids = request['variables'].get('ids')
            return proof.check_page(response(9, []) if ids is None else response(len(ids), [row(identity) for identity in ids]), ids)
        with tempfile.TemporaryDirectory() as directory, patch.multiple(proof, GUARD_COUNT=9, BATCH_SIZE=2), patch.object(proof,'post',side_effect=post):
            result = proof.complete_collection(Path(directory),identities)
            self.assertEqual(result['status'],'REFERENCE_COMPLETE_NOT_NODE_QUALIFIED')
            self.assertEqual(result['returned_rows'],9)
            self.assertEqual(result['filtered_counts'],[2,2,2,2,1])
            self.assertEqual(len(captured),7)
            self.assertEqual([identity for request in captured[1:6] for identity in request['variables']['ids']],identities)
            self.assertFalse((Path(directory)/'verification.json').exists())

    def test_incomplete_or_changed_collection_does_not_publish_a_complete_verdict(self):
        identities = [f'ID{position}' for position in range(9)]
        for scenario in ['missing','leaked','changed_settings']:
            def post(output, position, request):
                ids=request['variables'].get('ids')
                value=response(9,[]) if ids is None else response(len(ids),[row(identity) for identity in ids])
                if position==1 and scenario=='missing':
                    value=response(0,[])
                if position==1 and scenario=='leaked':
                    value=response(1,[row('LEAK')])
                if position==1 and scenario=='changed_settings':
                    value['data']['disease']['associatedTargets']['datasources'][0]['weight']=.5
                return proof.check_page(value,ids)
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory, patch.multiple(proof,GUARD_COUNT=9,BATCH_SIZE=2), patch.object(proof,'post',side_effect=post):
                with self.assertRaises(RuntimeError):
                    proof.complete_collection(Path(directory),identities)
                self.assertFalse((Path(directory)/'verification.json').exists())

    def test_request_deadline_does_not_overwrite_an_existing_signal_timer(self):
        with patch.object(proof.signal,'getitimer',return_value=(1.0,0.0)):
            with self.assertRaises(RuntimeError), proof.request_deadline():
                self.fail('existing timer was overwritten')


if __name__ == '__main__':
    unittest.main()
