import json
from pathlib import Path
import tempfile
import unittest

from tools.catalog import check_lock, inventory


class CatalogToolingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'catalog').mkdir()
        family = self.root / 'plugins/example'
        family.mkdir(parents=True)
        (family / 'manifest.toml').write_text('plugin_name="example"\n'
            '[image]\nreference="registry/example@sha256:' + 'a' * 64
            + '"\n[[nodes]]\nkind="example"\n[nodes.ports]\noutputs=[]\n')
        self.tool = self.root / 'research-adapters/technical-proof'
        self.tool.mkdir(parents=True)
        (self.tool / 'driver.py').write_text('pass\n')
        self.write_index(['research-adapters/technical-proof'])

    def write_index(self, directories):
        (self.root / 'catalog/non-plugin-directories.json').write_text(json.dumps(
            dict(schema_version=1, directories=directories)))

    def test_explicit_tool_is_hashed_and_not_registered(self):
        result = inventory(self.root)
        self.assertEqual(result['canonical_kinds'], 1)
        self.assertEqual(len(result['families']), 1)
        tools = result['non_plugin_source_tools']
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['files'][0]['path'], 'driver.py')
        self.assertFalse(tools[0]['scientific_certified'])
        self.assertFalse(tools[0]['auto_enable'])

    def test_unlisted_missing_manifest_fails(self):
        self.write_index([])
        with self.assertRaises(FileNotFoundError):
            inventory(self.root)

    def test_manifest_cannot_be_hidden(self):
        (self.tool / 'manifest.toml').write_text('plugin_name="hidden"\n')
        with self.assertRaises(ValueError):
            inventory(self.root)

    def test_index_rejects_invalid_or_duplicate_paths(self):
        for entries in [['plugins/example'], ['research-adapters/../escape'],
                        ['research-adapters/.'], ['research-adapters/technical-proof'] * 2]:
            with self.subTest(entries=entries):
                self.write_index(entries)
                with self.assertRaises(ValueError):
                    inventory(self.root)

    def test_declared_directory_must_exist_and_contain_sources(self):
        for entries in [['research-adapters/missing'], ['research-adapters/empty']]:
            (self.root / 'research-adapters/empty').mkdir(exist_ok=True)
            self.write_index(entries)
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                inventory(self.root)

    def test_symlink_sources_and_directories_fail(self):
        (self.tool / 'link.py').symlink_to(self.tool / 'driver.py')
        with self.assertRaises(ValueError):
            inventory(self.root)
        (self.tool / 'link.py').unlink()
        (self.root / 'research-adapters/alias').symlink_to(self.tool, target_is_directory=True)
        self.write_index(['research-adapters/alias'])
        with self.assertRaises(ValueError):
            inventory(self.root)

    def test_tool_change_or_addition_invalidates_lock(self):
        lock = self.root / 'catalog/release-lock.json'
        lock.write_text(json.dumps(inventory(self.root)))
        check_lock(self.root)
        (self.tool / 'driver.py').write_text('print(1)\n')
        with self.assertRaises(ValueError):
            check_lock(self.root)
        lock.write_text(json.dumps(inventory(self.root)))
        (self.tool / 'new.py').write_text('pass\n')
        with self.assertRaises(ValueError):
            check_lock(self.root)

    def test_private_environment_file_is_still_rejected(self):
        (self.tool / '.env').write_text('TOY=not-a-credential\n')
        with self.assertRaises(ValueError):
            inventory(self.root)
