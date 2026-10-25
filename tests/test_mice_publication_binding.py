import hashlib
from pathlib import Path
import tomllib
import unittest
from tests.conditional_v2_baseline import assert_current_source, assert_manifest_extension


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-mice'
TYPED = ROOT / 'research-adapters/cachexia-mice-typed-values'


class MicePublicationBindingTests(unittest.TestCase):
    def test_both_manifests_and_images_remain_unchanged(self):
        assert_manifest_extension(self, 'cachexia-mice', 5)
        assert_manifest_extension(self, 'cachexia-mice-typed-values', 1)
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'],
                         'ghcr.io/zj-2002/mice-official@sha256:ff4c166b89842d9bfbcf8d0f8227d05057a3ae57a668d374374a60db1e425516')

    def test_all_declared_ports_remain_explicit(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(len(manifest['nodes']), 10)
        for node in manifest['nodes']:
            binder = node['kind'] in {'cachexia_mice_bind_contract', 'cachexia_mice_bind_contract_v2'}
            self.assertEqual(len(node['ports']['inputs']), 2 if binder else 3)
            self.assertEqual(len(node['ports']['outputs']), 3 if binder else 6)
        typed = tomllib.loads((TYPED / 'manifest.toml').read_text())['nodes'][0]
        self.assertEqual(len(typed['ports']['inputs']), 2)
        self.assertEqual(len(typed['ports']['outputs']), 4)

    def test_three_verified_source_identities_are_explicit(self):
        for filename in ('research-adapters/cachexia-mice/scripts/mice.R',
                         'research-adapters/cachexia-mice/scripts/bind_contract.R',
                         'research-adapters/cachexia-mice-typed-values/scripts/typed_values.py'):
            assert_current_source(self, filename)

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
        self.assertIn('No scientific/longitudinal eligibility or G0 granted', binding)


if __name__ == '__main__':
    unittest.main()
