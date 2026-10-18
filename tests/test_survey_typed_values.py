import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'research-adapters/cachexia-survey-typed-values/scripts/typed_values.py'
SPEC = importlib.util.spec_from_file_location('survey_typed_values', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def upstream(payload):
    request = json.dumps({'scope': 'TECHNICAL_ONLY_NOT_G0', 'input_role': 'SYNTHETIC_TECHNICAL_INPUT',
        'scientific_qualification': 'NOT_GRANTED', 'analysis_role': MODULE.ROLE, 'mode': 'mean', 'test_id': '0001'})
    return {'request_json': request, 'contract_sha256': hashlib.sha256(request.encode()).hexdigest(),
        'status': 'TECHNICAL_PASS_NOT_SCIENTIFIC', 'G0_granted': False,
        'scientific_qualification_granted': False, 'resident_deployment_granted': False,
        'output0_sha256': hashlib.sha256(payload).hexdigest(), 'summary_rows': 1}


class SurveyTypedValuesTests(unittest.TestCase):
    def payload(self, value='1.25', kind='FINITE'):
        return ('test_id\trow_id\tfield\tvalue\tvalue_kind\n0001\tfield_1\tresult/x\t' + value + '\t' + kind + '\n').encode()

    def test_lexical_ids_and_source_positions_are_exact(self):
        payload = self.payload()
        result = MODULE.parse_summary(payload, upstream(payload))
        self.assertEqual(result['test_id'], ['0001'])
        self.assertEqual(result['source_position'], [0])
        self.assertEqual(result['value'], [1.25])

    def test_missing_and_nan_remain_distinct_null_states(self):
        for kind in ('MISSING', 'NAN'):
            payload = self.payload('NA', kind)
            result = MODULE.parse_summary(payload, upstream(payload))
            self.assertEqual(result['value'], [None])
            self.assertEqual(result['value_kind'], [kind])

    def test_wrong_summary_hash_is_refused(self):
        payload = self.payload()
        audit = upstream(payload)
        audit['output0_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            MODULE.parse_summary(payload, audit)

    def test_missing_cannot_become_zero(self):
        payload = self.payload('0', 'MISSING')
        with self.assertRaises(ValueError):
            MODULE.parse_summary(payload, upstream(payload))

    def test_ragged_extra_field_is_refused(self):
        payload = self.payload().rstrip() + b'\textra\n'
        with self.assertRaises(ValueError):
            MODULE.parse_summary(payload, upstream(payload))

    def test_wrong_row_coordinate_is_refused(self):
        payload = self.payload().replace(b'field_1', b'field_2')
        with self.assertRaises(ValueError):
            MODULE.parse_summary(payload, upstream(payload))

    def test_foreign_or_dangling_outputs_are_not_touched(self):
        for dangling in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                outputs = [root / name for name in ('values.parquet', 'audit.json', 'log.txt', 'schema.json')]
                if dangling:
                    outputs[1].symlink_to(root / 'absent')
                else:
                    outputs[1].write_text('FOREIGN')
                environment = {'AUTONOMICS_OUTPUT' + str(index): str(path) for index, path in enumerate(outputs)}
                with patch.dict(os.environ, environment):
                    self.assertEqual(MODULE.main(), 2)
                self.assertFalse(any(path.exists() for path in (outputs[0], outputs[2], outputs[3])))
                self.assertTrue(outputs[1].is_symlink() if dangling else outputs[1].read_text() == 'FOREIGN')

    def test_invalid_input_publishes_only_blocked_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('input0', 'input1'):
                (root / name).write_text('{}')
            names = ('values.parquet', 'audit.json', 'log.txt', 'schema.json')
            environment = {'AUTONOMICS_OUTPUT' + str(index): str(root / name) for index, name in enumerate(names)}
            environment.update({'AUTONOMICS_INPUT0': str(root / 'input0'), 'AUTONOMICS_INPUT1': str(root / 'input1'),
                                'AUTONOMICS_INPUT_COUNT': '2'})
            with patch.dict(os.environ, environment):
                self.assertEqual(MODULE.main(), 2)
            self.assertEqual(json.loads((root / 'audit.json').read_text())['status'], 'BLOCKED')
            self.assertFalse((root / 'values.parquet').exists())
            self.assertFalse((root / 'schema.json').exists())


if __name__ == '__main__':
    unittest.main()
