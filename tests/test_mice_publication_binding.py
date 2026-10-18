import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-mice'
TYPED = ROOT / 'research-adapters/cachexia-mice-typed-values'


class MicePublicationBindingTests(unittest.TestCase):
    def test_both_manifests_and_images_remain_unchanged(self):
        for folder, expected in ((FAMILY, 'eec37a826352f6501d8c53b60a0ff80a2027e01995798b156d4fd0f7a51d3780'),
                                 (TYPED, '5cf91dcfff2ff4f9bbd0749d881f5dccb9a17c13040952987c07affb4d10c0e6')):
            self.assertEqual(hashlib.sha256((folder / 'manifest.toml').read_bytes()).hexdigest(), expected)
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'],
            'localhost/cachexia-mice@sha256:0a7b397b9fb5fca8128381525ab9482098445a2f29e309135464a8cd45fc0f57')

    def test_all_declared_ports_remain_explicit(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(len(manifest['nodes']), 5)
        for node in manifest['nodes']:
            binder = node['kind'] == 'cachexia_mice_bind_contract'
            self.assertEqual(len(node['ports']['inputs']), 2 if binder else 3)
            self.assertEqual(len(node['ports']['outputs']), 3 if binder else 6)
        typed = tomllib.loads((TYPED / 'manifest.toml').read_text())['nodes'][0]
        self.assertEqual(len(typed['ports']['inputs']), 2)
        self.assertEqual(len(typed['ports']['outputs']), 4)

    def test_three_verified_source_identities_are_explicit(self):
        for filename, expected in (
            (FAMILY / 'scripts/mice.R', '33d36247e60b0229965e1d2d559f91961888b7f959a82154a4996fbf4c10309e'),
            (FAMILY / 'scripts/bind_contract.R', '77c1fd5bc3025d3e6c7c70dcbdf5945493194e6e6fefa261a737bba3f7adc14a'),
            (TYPED / 'scripts/typed_values.py', 'c503512f82c82ef7cf28950e0b64cbaf3e7ccf85f445ff0d11cf23a21b9189f8')):
            self.assertEqual(hashlib.sha256(filename.read_bytes()).hexdigest(), expected)

    def test_r_entries_share_explicit_owned_publication(self):
        for name in ('mice.R', 'bind_contract.R'):
            source = (FAMILY / 'scripts' / name).read_text()
            for token in ('Sys.readlink(filename)', 'seq_len(input_count) - 1L',
                          'Refusing to overwrite existing output', 'status <- writer(private_outputs)',
                          'identical(file_identity(owned$path), owned$identity)'):
                self.assertIn(token, source)

    def test_typed_publication_and_raw_binding_do_not_change_statistics(self):
        typed = (TYPED / 'scripts/typed_values.py').read_text()
        for token in ('status = write_products(private)', 'os.link(private[position], outputs[position]',
                      '(current.st_dev, current.st_ino) == (device, inode)'):
            self.assertIn(token, typed)
        binding = (FAMILY / 'scripts/bind_contract.R').read_text()
        self.assertIn('bind_json_hash(original_bytes, resolved$input0_sha256)', binding)
        self.assertIn('No research/design changes permitted', binding)


if __name__ == '__main__':
    unittest.main()
