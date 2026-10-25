import copy
import importlib.util
from pathlib import Path
import tomllib
import unittest


FAMILY = Path(__file__).resolve().parents[1]
TYPED = FAMILY.parent / 'cachexia-lcmm-typed-values'
specification = importlib.util.spec_from_file_location('lcmm_typed_v2', TYPED / 'scripts/typed_values.py')
typed = importlib.util.module_from_spec(specification)
specification.loader.exec_module(typed)


class TechnicalV2Tests(unittest.TestCase):
    def fixture(self, version=2, role='EMPIRICAL_TECHNICAL_INPUT'):
        request = dict(schema_version=version, scope='TECHNICAL_ONLY_NOT_G0',
            scientific_qualification='NOT_GRANTED', input_role=role,
            analysis_role='TRAJECTORY_TECHNICAL_NOT_LANDMARK_OR_BIOLOGICAL_SUBTYPE'
            if version == 2 else 'SYNTHETIC_TRAJECTORY_TECHNICAL_NOT_LANDMARK_PREDICTION')
        audit = dict(status='TECHNICAL_PASS_NOT_SCIENTIFIC', G0_granted=False, resident_deployment_granted=False)
        if version == 2:
            audit.update(request)
        return audit, request

    def test_original_four_lcmm_kinds_and_contracts_remain_explicit(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(len(manifest['nodes']), 8)
        for old, new in zip(manifest['nodes'][:4], manifest['nodes'][4:]):
            self.assertEqual(new['kind'], old['kind'] + '_v2')
            self.assertEqual(new['ports'], old['ports'])
            self.assertEqual(new['resources'], old['resources'])
            self.assertNotIn('AUTONOMICS_TECHNICAL_CONTRACT_VERSION', old['command']['env'])
            expected = dict(old['command']['env'], AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
            self.assertEqual(new['command']['env'], expected)
            self.assertEqual(new['command']['script_file'], old['command']['script_file'])

    def test_typed_v2_keeps_ports_columns_and_source_position(self):
        manifest = tomllib.loads((TYPED / 'manifest.toml').read_text())
        old, new = manifest['nodes']
        self.assertEqual(new['kind'], old['kind'] + '_v2')
        self.assertEqual(new['ports'], old['ports'])
        self.assertEqual(new['resources'], old['resources'])
        self.assertNotIn('env', old['command'])
        self.assertEqual(new['command']['env'], {'AUTONOMICS_TECHNICAL_CONTRACT_VERSION': '2'})
        self.assertEqual(typed.FIELDS, ['test_id', 'row_id', 'field', 'value', 'value_kind'])

    def test_typed_v2_accepts_both_roles_and_retains_exact_provenance(self):
        for role in ['EMPIRICAL_TECHNICAL_INPUT', 'SYNTHETIC_TECHNICAL_INPUT']:
            audit, request = self.fixture(role=role)
            original = copy.deepcopy((audit, request))
            self.assertEqual(typed.validate_provenance(audit, request, '2'), request)
            self.assertEqual((audit, request), original)

    def test_typed_v1_output_metadata_unchanged_and_cross_version_rejected(self):
        audit, request = self.fixture(version=1, role='SYNTHETIC_TECHNICAL_INPUT')
        self.assertEqual(typed.validate_provenance(audit, request, '1'), {})
        with self.assertRaises(ValueError):
            typed.validate_provenance(audit, request, '2')
        audit, request = self.fixture()
        with self.assertRaises(ValueError):
            typed.validate_provenance(audit, request, '1')

    def test_typed_request_and_audit_provenance_must_match(self):
        for field in ['schema_version', 'scope', 'analysis_role', 'scientific_qualification', 'input_role']:
            audit, request = self.fixture()
            audit[field] = 1 if field == 'schema_version' else 'SYNTHETIC_TECHNICAL_INPUT'
            with self.subTest(field=field), self.assertRaises(ValueError):
                typed.validate_provenance(audit, request, '2')

    def test_typed_boolean_schema_is_not_version_one(self):
        audit, request = self.fixture(version=1, role='SYNTHETIC_TECHNICAL_INPUT')
        request['schema_version'] = True
        with self.assertRaises(ValueError):
            typed.validate_provenance(audit, request, '1')

    def test_typed_no_scientific_permission_or_unknown_version(self):
        for field in ['G0_granted', 'resident_deployment_granted', 'status']:
            audit, request = self.fixture()
            audit[field] = 'APPROVED' if field == 'status' else True
            with self.subTest(field=field), self.assertRaises(ValueError):
                typed.validate_provenance(audit, request, '2')
        audit, request = self.fixture()
        with self.assertRaises(ValueError):
            typed.validate_provenance(audit, request, '3')


if __name__ == '__main__':
    unittest.main()
