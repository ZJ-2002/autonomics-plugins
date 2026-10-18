import hashlib
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CellChatPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((ROOT / 'plugins/cellchat/manifest.toml').read_text())
        self.definition = next(node for node in self.manifest['nodes'] if node['kind'] == 'cachexia_cellchat_official')

    def test_fixed_image_and_author_identity_remain_explicit(self):
        self.assertEqual(self.manifest['image']['reference'],
                         'ghcr.io/zj-2002/cellchat@sha256:6fdc08a21395fd2710cb9ac0d632079adb1364ae621fc4f8f809f5b368d09f4b')
        self.assertIn('75253cd0', self.manifest['image']['upstream'])

    def test_original_legacy_node_is_not_silently_modified_or_certified(self):
        legacy = next(node for node in self.manifest['nodes'] if node['kind'] == 'cellchat_inference')
        self.assertEqual(hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                         '2939d526dbf51b98e41f93752400483e1195f3aafde980810c938eb498ace035')

    def test_exact_frozen_two_input_eight_output_contract(self):
        adapter = tomllib.loads((ROOT / 'research-adapters/cachexia-cellchat/manifest.toml').read_text())
        self.assertEqual(self.definition, adapter['nodes'][0])
        self.assertEqual(len(self.definition['ports']['inputs']), 2)
        self.assertEqual(len(self.definition['ports']['outputs']), 8)
        self.assertNotIn('params', self.definition)
        self.assertEqual(self.definition['artifact_prefix'], '/artifacts/cellchat-official')
        self.assertEqual(self.definition['resources']['pull_policy'], 'never')

    def test_canonical_and_adapter_scripts_are_identical(self):
        current = (ROOT / 'plugins/cellchat/scripts/cellchat.R').read_bytes()
        self.assertEqual(current, (ROOT / 'research-adapters/cachexia-cellchat/scripts/cellchat.R').read_bytes())
        self.assertEqual(hashlib.sha256(current).hexdigest(), 'a17adb5651a755bc815c7157d54e220b7c8e7e7cc36eb40d762124392c99aeca')

    def test_official_call_and_owned_publication_are_distinct_layers(self):
        source = (ROOT / 'plugins/cellchat/scripts/cellchat.R').read_text()
        for token in ('computeCommunProb(object, type = "triMean"',
                      'Refusing to overwrite existing output', 'root <- stage',
                      'if (!file.link(source, destinations[[position]]))',
                      'identical(file_identity(owned$path), owned$identity)'):
            self.assertIn(token, source)


if __name__ == '__main__':
    unittest.main()
