import hashlib
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CachexiaContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((ROOT / 'manifest.toml').read_text())

    def test_legacy_node_is_not_silently_replaced(self):
        legacy = next(node for node in self.manifest['nodes'] if node['kind'] == 'hyprcoloc')
        identity = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(identity, '7495a47419a74e5a1c5fe9adc1dbd844dce0f4d52de44387e77e465a1d3ecbc4')

    def test_image_is_the_proved_official_digest(self):
        self.assertEqual(self.manifest['image']['reference'],
            'ghcr.io/auto-nomics/autonomics/hyprcoloc@sha256:395a36903d3c3ed6c753aef85f5b0a57044f86968e4d79804e4cc85f36aa5617')

    def test_strict_node_has_all_explicit_input_and_output_ports(self):
        node = next(node for node in self.manifest['nodes'] if node['kind'] == 'cachexia_hyprcoloc_official')
        self.assertEqual(len(node['ports']['inputs']), 6)
        self.assertEqual([port['path'] for port in node['ports']['outputs']],
            ['hyprcoloc_summary.tsv', 'hyprcoloc.RDS', 'hyprcoloc.log', 'snps.tsv', 'audit.tsv', 'traits.tsv'])
        self.assertEqual(node['command']['script_file'], 'scripts/hyprcoloc.R')
        self.assertNotIn('params', node)

    def test_published_script_is_the_numerically_verified_source(self):
        self.assertEqual(hashlib.sha256((ROOT / 'scripts/hyprcoloc.R').read_bytes()).hexdigest(),
            'c3710fe380902b6c729fa02f62e67393a6cf010f473b3e6bb90ed63c432c7ecb')

    def test_node_names_do_not_collide(self):
        kinds = [node['kind'] for node in self.manifest['nodes']]
        self.assertEqual(len(kinds), len(set(kinds)))
        self.assertEqual(len(kinds), 2)


if __name__ == '__main__':
    unittest.main()
