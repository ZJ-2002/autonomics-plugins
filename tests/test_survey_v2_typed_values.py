import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-survey-typed-values'
SPECIFICATION = importlib.util.spec_from_file_location('survey_v2_typed_values', FAMILY / 'scripts/typed_values.py')
typed = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(typed)
PAYLOAD = b'test_id\trow_id\tfield\tvalue\tvalue_kind\ntoy\tfield_1\tresult/precise\t1.0000000000000002\tFINITE\ntoy\tfield_2\tresult/missing\tNA\tMISSING\n'


def audit(version=2, role='EMPIRICAL_TECHNICAL_INPUT'):
    request = dict(schema_version=version, scope='TECHNICAL_ONLY_NOT_G0', input_role=role,
        scientific_qualification='NOT_GRANTED', analysis_role=typed.ROLE, mode='mean', test_id='toy')
    text = json.dumps(request)
    result = dict(request_json=text, contract_sha256=hashlib.sha256(text.encode()).hexdigest(),
        status='TECHNICAL_PASS_NOT_SCIENTIFIC', G0_granted=False, scientific_qualification_granted=False,
        resident_deployment_granted=False, output0_sha256=hashlib.sha256(PAYLOAD).hexdigest(),
        output1_sha256='a' * 64, summary_rows=2)
    if version == 2:
        result.update(schema_version=2, input_role=role, scientific_qualification='NOT_GRANTED',
            state_schema_version=2, state_input_role=role, state_scientific_qualification='NOT_GRANTED')
    return result


class SurveyV2TypedValuesTests(unittest.TestCase):
    def test_v2_both_roles_preserve_fields_null_and_numeric_values(self):
        with patch.dict(os.environ, {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'}):
            for role in ('EMPIRICAL_TECHNICAL_INPUT', 'SYNTHETIC_TECHNICAL_INPUT'):
                columns = typed.parse_summary(PAYLOAD, audit(role=role))
                self.assertEqual(list(columns), typed.FIELDS + ['source_position'])
                self.assertEqual(columns['value'], [1.0000000000000002, None])
                self.assertEqual(columns['source_position'], [0, 1])
                self.assertEqual(columns['field'], ['result/precise', 'result/missing'])

    def test_v1_defaults_preserved_and_v2_cannot_enter_old_kind(self):
        with patch.dict(os.environ):
            os.environ.pop('AUTONOMICS_TECHNICAL_CONTRACT_VERSION', None)
            typed.parse_summary(PAYLOAD, audit(1, 'SYNTHETIC_TECHNICAL_INPUT'))
            self.assertEqual(typed.technical_provenance(audit(1, 'SYNTHETIC_TECHNICAL_INPUT')), {})
            with self.assertRaises(ValueError):
                typed.parse_summary(PAYLOAD, audit())
            with self.assertRaises(ValueError):
                typed.parse_summary(PAYLOAD, audit(2, 'SYNTHETIC_TECHNICAL_INPUT'))
        with patch.dict(os.environ, {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'}):
            with self.assertRaises(ValueError):
                typed.parse_summary(PAYLOAD, audit(1, 'SYNTHETIC_TECHNICAL_INPUT'))

    def test_v2_rejects_top_level_or_state_role_laundering(self):
        with patch.dict(os.environ, {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'}):
            for field, value in [('input_role', 'SYNTHETIC_TECHNICAL_INPUT'),
                ('state_input_role', 'SYNTHETIC_TECHNICAL_INPUT'), ('schema_version', 1),
                ('state_schema_version', 1), ('scientific_qualification', 'GRANTED'),
                ('state_scientific_qualification', 'GRANTED'), ('output1_sha256', '')]:
                with self.subTest(field=field):
                    changed = audit()
                    changed[field] = value
                    with self.assertRaises(ValueError):
                        typed.parse_summary(PAYLOAD, changed)

    def test_v2_rejects_contract_relabel_without_hash_and_scientific_grant(self):
        with patch.dict(os.environ, {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'}):
            changed = audit()
            request = json.loads(changed['request_json'])
            request['input_role'] = 'SYNTHETIC_TECHNICAL_INPUT'
            changed['request_json'] = json.dumps(request)
            with self.assertRaises(ValueError):
                typed.parse_summary(PAYLOAD, changed)
            for field in ('G0_granted', 'scientific_qualification_granted', 'resident_deployment_granted'):
                changed = audit()
                changed[field] = True
                with self.assertRaises(ValueError):
                    typed.parse_summary(PAYLOAD, changed)

    def test_v2_provenance_keeps_complete_state_identity_without_new_columns(self):
        with patch.dict(os.environ, {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'}):
            upstream = audit()
            original = copy.deepcopy(upstream)
            provenance = typed.technical_provenance(upstream)
            self.assertEqual(provenance, dict(schema_version=2, input_role='EMPIRICAL_TECHNICAL_INPUT',
                scientific_qualification='NOT_GRANTED', upstream_state_sha256='a' * 64, G0_granted=False))
            self.assertEqual(upstream, original)
            self.assertEqual(typed.FIELDS, ['test_id', 'row_id', 'field', 'value', 'value_kind'])

    def test_manifest_preserves_v1_and_only_adds_explicit_v2_same_ports(self):
        from tests.conditional_v2_baseline import published_bytes
        original = tomllib.loads(published_bytes('research-adapters/cachexia-survey-typed-values/manifest.toml').decode())
        current = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(len(current['nodes']), 2)
        self.assertEqual(current['nodes'][0], original['nodes'][0])
        self.assertEqual(current['image'], original['image'])
        new = current['nodes'][1]
        self.assertEqual(new['kind'], original['nodes'][0]['kind'] + '_v2')
        self.assertEqual(new['ports'], original['nodes'][0]['ports'])
        self.assertEqual(new['resources'], original['nodes'][0]['resources'])
        self.assertEqual(new['command']['env'], {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'})


if __name__ == '__main__':
    unittest.main()
