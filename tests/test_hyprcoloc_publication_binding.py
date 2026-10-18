"""Check declarations; actual R publication and SDK controls are separate evidence."""

import hashlib
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HyPrColocPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((ROOT / 'plugins/hyprcoloc/manifest.toml').read_text())
        self.definition = next(node for node in self.manifest['nodes'] if node['kind'] == 'cachexia_hyprcoloc_official')

    def test_exact_author_image_and_existing_contract(self):
        self.assertEqual(self.manifest['image']['reference'],
            'ghcr.io/auto-nomics/autonomics/hyprcoloc@sha256:395a36903d3c3ed6c753aef85f5b0a57044f86968e4d79804e4cc85f36aa5617')
        self.assertIn('0348bbdd977be731d82e4efda115a9bed63cd44f', self.manifest['image']['upstream'])
        original = tomllib.loads((ROOT / 'research-adapters/cachexia-hyprcoloc/manifest.toml').read_text())
        self.assertEqual(self.definition, original['nodes'][0])

    def test_legacy_node_is_not_relabelled_as_repaired(self):
        legacy = next(node for node in self.manifest['nodes'] if node['kind'] == 'hyprcoloc')
        digest = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, '7495a47419a74e5a1c5fe9adc1dbd844dce0f4d52de44387e77e465a1d3ecbc4')

    def test_six_inputs_and_outputs_remain_explicit(self):
        self.assertEqual(len(self.definition['ports']['inputs']), 6)
        self.assertEqual(len(self.definition['ports']['outputs']), 6)
        self.assertNotIn('params', self.definition)
        self.assertEqual(self.definition['command']['script_file'], 'scripts/hyprcoloc.R')

    def test_both_declared_routes_use_identical_repaired_source(self):
        current = (ROOT / 'plugins/hyprcoloc/scripts/hyprcoloc.R').read_bytes()
        adapter = (ROOT / 'research-adapters/cachexia-hyprcoloc/scripts/hyprcoloc.R').read_bytes()
        self.assertEqual(current, adapter)
        self.assertEqual(hashlib.sha256(current).hexdigest(),
                         '080b6a638bde211e1f9ebd843e487d68b24708f70af6a665b4b1e93155238e6a')

    def test_author_call_and_owned_publication_are_distinct_layers(self):
        source = (ROOT / 'plugins/hyprcoloc/scripts/hyprcoloc.R').read_text()
        self.assertIn('hyprcoloc::hyprcoloc', source)
        self.assertIn('if (!file.link(source, destinations[[position]]))', source)
        self.assertIn('identical(file_identity(owned$path), owned$identity)', source)
        self.assertIn('Refusing to overwrite existing output', source)
        self.assertIn('outputs <- file.path(stage,', source)


if __name__ == '__main__':
    unittest.main()
