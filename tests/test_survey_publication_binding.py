import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-survey'


class SurveyPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())

    def test_manifest_and_image_are_unchanged(self):
        self.assertEqual(hashlib.sha256((FAMILY / 'manifest.toml').read_bytes()).hexdigest(),
                         'dfd462f2393c5d8ac06a07f14e8443851bdcde5220c382fc073d3cc1a210c903')
        self.assertEqual(self.manifest['image']['reference'],
                         'localhost/cachexia-survey@sha256:8186f7fc9fa4a75023821b8f0f22634b82c2112916c426a20ee40075c4753243')

    def test_eleven_nodes_preserve_ports_and_limits(self):
        self.assertEqual(len(self.manifest['nodes']), 11)
        for node in self.manifest['nodes']:
            self.assertEqual(len(node['ports']['inputs']), 2)
            binder = node['kind'] == 'cachexia_survey_bind_contract'
            self.assertEqual(len(node['ports']['outputs']), 3 if binder else 5)
            self.assertEqual(node['resources'],
                             {'cpus': 1.0, 'memory': '2Gi', 'network': 'isolated', 'pull_policy': 'never'})

    def test_both_verified_entry_source_identities_are_explicit(self):
        for name, expected in (
                ('survey.R', 'f7d6c2bee9abf84474aaf4b3a78e35769d2bb58867c3f1b9508c9b70761c7716'),
                ('bind_contract.R', 'ee8a4ebd6a0d861a31de3d1d08a62b5c6aa953e1aa625e4dda3854ae2ab5b684')):
            self.assertEqual(hashlib.sha256((FAMILY / 'scripts' / name).read_bytes()).hexdigest(), expected)

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
