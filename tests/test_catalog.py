import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'research-adapters').mkdir()
        self.family = self.root / 'plugins/example'
        self.family.mkdir(parents=True)
        (self.family / 'scripts').mkdir()
        (self.family / 'scripts/run.py').write_text('print(1)\n')
        self.manifest = ('plugin_name="example"\n[image]\nreference="registry/image@sha256:' + 'a' * 64
                         + '"\n[[nodes]]\nkind="example"\n[nodes.command]\nscript_file="scripts/run.py"\n'
                         '[nodes.ports]\noutputs=[{path="result.tsv"}]\n')
        (self.family / 'manifest.toml').write_text(self.manifest)

    def rewrite(self, old, new):
        (self.family / 'manifest.toml').write_text(self.manifest.replace(old, new))

    def test_inventory_has_no_scientific_admission(self):
        result = catalog.inventory(self.root)
        self.assertEqual((result['canonical_families'], result['canonical_kinds']), (1, 1))
        self.assertFalse(result['G0'])
        self.assertFalse(result['families'][0]['scientific_certified'])
        self.assertFalse(result['families'][0]['auto_enable'])

    def test_missing_script_fails(self):
        (self.family / 'scripts/run.py').unlink()
        with self.assertRaises(FileNotFoundError):
            catalog.inventory(self.root)

    def test_script_traversal_fails(self):
        self.rewrite('scripts/run.py', '../outside.py')
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_script_symlink_escape_fails(self):
        (self.root / 'outside.py').write_text('pass')
        (self.family / 'scripts/run.py').unlink()
        (self.family / 'scripts/run.py').symlink_to(self.root / 'outside.py')
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_family_symlink_escape_fails(self):
        (self.root / 'research-adapters/escape').symlink_to(self.family, target_is_directory=True)
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_output_traversal_fails(self):
        self.rewrite('result.tsv', '../result.tsv')
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_mutable_image_fails(self):
        self.rewrite('registry/image@sha256:' + 'a' * 64, 'registry/image:latest')
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_duplicate_canonical_kind_fails(self):
        sibling = self.root / 'plugins/other'
        sibling.mkdir()
        (sibling / 'manifest.toml').write_text(self.manifest.replace('script_file="scripts/run.py"', 'script="pass"'))
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_research_overlap_is_not_auto_enabled(self):
        sibling = self.root / 'research-adapters/experiment'
        sibling.mkdir()
        (sibling / 'manifest.toml').write_text(self.manifest.replace('script_file="scripts/run.py"', 'script="pass"'))
        result = catalog.inventory(self.root)
        self.assertEqual(len(result['families']), 2)
        self.assertEqual(result['canonical_kinds'], 1)
        self.assertFalse(result['families'][1]['auto_enable'])

    def test_changed_source_fails_lock(self):
        (self.root / 'catalog').mkdir()
        (self.root / 'catalog/release-lock.json').write_text(json.dumps(catalog.inventory(self.root)))
        catalog.check_lock(self.root)
        (self.family / 'scripts/run.py').write_text('print(2)')
        with self.assertRaises(ValueError):
            catalog.check_lock(self.root)

    def test_added_source_fails_lock(self):
        (self.root / 'catalog').mkdir()
        (self.root / 'catalog/release-lock.json').write_text(json.dumps(catalog.inventory(self.root)))
        (self.family / 'new.py').write_text('pass')
        with self.assertRaises(ValueError):
            catalog.check_lock(self.root)

    def test_private_credential_file_fails(self):
        (self.family / '.env').write_text('not-a-real-secret')
        with self.assertRaises(ValueError):
            catalog.inventory(self.root)

    def test_invalid_relative_paths_fail(self):
        for value in ['', '/a', '../a', 'a/../b', 'a//b', 'a\\b', 'a:b', 'a\nb', './a']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalog.safe_relative(value)

    def test_profile_requires_full_pin(self):
        for revision in ['main', 'a' * 39, 'A' * 40]:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                catalog.render_profile(catalog.inventory(self.root), revision, ['example'])

    def test_profile_rejects_unknown_or_repeated_families(self):
        for names in [[], ['missing'], ['example', 'example']]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                catalog.render_profile(catalog.inventory(self.root), 'a' * 40, names)

    def test_profile_roundtrips_subdir(self):
        import tomllib
        parsed = tomllib.loads(catalog.render_profile(catalog.inventory(self.root), 'a' * 40, ['example']))
        self.assertEqual(parsed['plugin'][0]['subdir'], 'plugins/example')
        self.assertEqual(parsed['plugin'][0]['rev'], 'a' * 40)
        self.assertNotIn('path', parsed['plugin'][0])

    def test_import_verification_checks_bytes(self):
        (self.root / 'provenance').mkdir()
        filename = self.family / 'scripts/run.py'
        index = dict(plugins=[dict(directory='plugins/example', files=[dict(path='scripts/run.py',
                     bytes=len(filename.read_bytes()), sha256=hashlib.sha256(filename.read_bytes()).hexdigest())])],
                     research_adapters=[])
        (self.root / 'provenance/source-index.json').write_text(json.dumps(index))
        self.assertEqual(catalog.verify_import(self.root), 1)
        filename.write_text('different')
        with self.assertRaises(ValueError):
            catalog.verify_import(self.root)

    def test_empty_catalog_is_not_pass(self):
        (self.family / 'manifest.toml').unlink()
        with self.assertRaises(FileNotFoundError):
            catalog.inventory(self.root)


if __name__ == '__main__':
    unittest.main()
