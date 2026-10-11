import importlib.util
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('contract_guards', ROOT / 'scripts/guards.py')
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)


class ProtocolSyncTests(unittest.TestCase):
    def test_registered_protocols_require_explicit_matching_version(self):
        for version in ['4.0', '4.1', '4.2.1']:
            with self.subTest(version=version):
                self.assertEqual(guards.resolve_active_protocol({'version': version}, {'CACHEXIA_ACTIVE_PROTOCOL': version}), version)

    def test_missing_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            guards.resolve_active_protocol({'version': '4.2.1'}, {})

    def test_mismatched_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            guards.resolve_active_protocol({'version': '4.1'}, {'CACHEXIA_ACTIVE_PROTOCOL': '4.2.1'})

    def test_new_design_is_not_silently_registered(self):
        with self.assertRaises(ValueError):
            guards.resolve_active_protocol({'version': '4.3.2'}, {'CACHEXIA_ACTIVE_PROTOCOL': '4.3.2'})

    def test_v41_role_is_not_research_contract(self):
        self.assertEqual(guards.PROTOCOLS['4.1']['role'], 'ENGINEERING_REFERENCE_NOT_A_RESEARCH_CONTRACT')

    def test_all_five_nodes_declare_isolation(self):
        manifest = tomllib.loads((ROOT / 'manifest.toml').read_text())
        self.assertEqual(len(manifest['nodes']), 5)
        for node in manifest['nodes']:
            with self.subTest(kind=node['kind']):
                resources = node['resources']
                self.assertEqual(resources['network'], 'isolated')
                self.assertIs(resources['read_only_rootfs'], True)
                self.assertEqual(resources['pull_policy'], 'never')
                self.assertEqual(resources['pids_limit'], 128)


if __name__ == '__main__':
    unittest.main()
