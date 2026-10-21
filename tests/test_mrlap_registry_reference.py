import copy
import hashlib
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


def stable_contract(document):
    selected = copy.deepcopy(document)
    selected['image'].pop('reference')
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


class MrlapRegistryReferenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads((ROOT / 'evidence/mrlap-registry-reference-repair-20261021.json').read_text())
        self.manifest = tomllib.loads((ROOT / 'plugins/mrlap/manifest.toml').read_text())

    def test_reference_matches_verified_replacement_not_unavailable_digest(self):
        self.assertTrue(self.evidence['old_manifest_unknown_reproduced'])
        self.assertTrue(self.evidence['anonymous_replacement_manifest_and_config_verified'])
        self.assertTrue(self.evidence['identical_config_and_uncompressed_layers'])
        self.assertEqual(self.manifest['image']['reference'], self.evidence['new_reference'])
        self.assertNotEqual(self.manifest['image']['reference'], self.evidence['old_reference'])

    def test_all_other_contract_fields_and_actual_method_script_are_unchanged(self):
        self.assertEqual(stable_contract(self.manifest), self.evidence['stable_contract_excluding_image_reference_sha256'])
        script = ROOT / 'plugins/mrlap/scripts/mrlap.sh'
        self.assertEqual(hashlib.sha256(script.read_bytes()).hexdigest(), self.evidence['script_sha256'])
        self.assertEqual(len(self.manifest['nodes'][0]['ports']['inputs']), 3)
        self.assertEqual(len(self.manifest['nodes'][0]['ports']['outputs']), 4)

    def test_repin_does_not_claim_new_statistics_or_deployment(self):
        self.assertEqual(self.evidence['new_method_executions'], 0)
        self.assertEqual(self.evidence['new_software_admissions'], 0)
        self.assertFalse(self.evidence['runtime_loaded_repin_claimed'])
        self.assertFalse(self.evidence['g0_granted'])
        self.assertFalse(self.evidence['image_rebuilt'])


if __name__ == '__main__':
    unittest.main()
