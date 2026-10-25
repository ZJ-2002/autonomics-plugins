import hashlib
from pathlib import Path
import tomllib
import unittest
from tests.conditional_v2_baseline import assert_current_source, assert_manifest_extension


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-survey'


class SurveyPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())

    def test_manifest_and_image_are_unchanged(self):
        assert_manifest_extension(self, 'cachexia-survey', 11)
        self.assertEqual(self.manifest['image']['reference'],
                         'ghcr.io/zj-2002/survey-official@sha256:6f3e6f417912b7fb2c2b344ceaa11ff6031cde7848740caf6450c4366b5fbc61')

    def test_eleven_nodes_preserve_ports_and_limits(self):
        self.assertEqual(len(self.manifest['nodes']), 22)
        for node in self.manifest['nodes']:
            self.assertEqual(len(node['ports']['inputs']), 2)
            binder = node['kind'] in {'cachexia_survey_bind_contract', 'cachexia_survey_bind_contract_v2'}
            self.assertEqual(len(node['ports']['outputs']), 3 if binder else 5)
            self.assertEqual(node['resources'],
                             {'cpus': 1.0, 'memory': '2Gi', 'network': 'isolated', 'pull_policy': 'never'})

    def test_both_verified_entry_source_identities_are_explicit(self):
        for name in ('survey.R', 'bind_contract.R'):
            assert_current_source(self, 'research-adapters/cachexia-survey/scripts/' + name)

    def test_output_protection_is_independent_of_statistical_mode(self):
        for name in ('survey.R', 'bind_contract.R'):
            source = (FAMILY / 'scripts' / name).read_text()
            for token in ('Sys.readlink(filename)', 'Refusing to overwrite existing output',
                          'status <- writer(private_outputs)', 'status == 0L',
                          'file.link(private_outputs[[position]], destinations[[position]])',
                          'identical(file_identity(owned$path), owned$identity)'):
                self.assertIn(token, source)

    def test_binding_keeps_raw_json_and_no_scientific_permission(self):
        source = (FAMILY / 'scripts/bind_contract.R').read_text()
        self.assertIn('bind_json_hash(original_bytes, resolved$input0_sha256)', source)
        self.assertIn('Serialized binding changed frozen parameters', source)
        self.assertIn('scientific_qualification_granted = FALSE', source)
        self.assertIn('SURVEY_TECHNICAL_BACKGROUND_ASSOCIATION_NOT_CANCER_MECHANISM', source)


if __name__ == '__main__':
    unittest.main()
