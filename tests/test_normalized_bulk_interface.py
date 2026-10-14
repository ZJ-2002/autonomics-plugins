import hashlib
import json
from pathlib import Path
import tomllib
import unittest

from tools import catalog

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/bulk-limma-normalized'


class NormalizedBulkTests(unittest.TestCase):
    def test_existing_method_bytes_and_image_are_preserved(self):
        lock = json.loads((PLUGIN / 'reuse-lock.json').read_text())
        for name, record in lock['files'].items():
            actual = (PLUGIN / name).read_bytes()
            original = (ROOT / record['source_path']).read_bytes()
            if name in ['scripts/run-design.R', 'scripts/run-limma.R']:
                self.assertEqual(hashlib.sha256(original).hexdigest(), record['original_sha256'])
                self.assertEqual(actual.splitlines()[2], original.splitlines()[2])
                self.assertIn(b'"AUTONOMICS_INPUT0"', actual)
                self.assertIn(b'"AUTONOMICS_OUTPUT0"', actual)
                if name == 'scripts/run-limma.R':
                    self.assertIn(b'plugin_transport_output_sha256', actual)
            else:
                self.assertEqual(actual, original)
            self.assertEqual(hashlib.sha256(actual).hexdigest(), record['sha256'])
            self.assertEqual(len(actual), record['bytes'])
        manifest = tomllib.loads((PLUGIN / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'], lock['image_reference'])
        self.assertNotEqual(lock['image_reference'], lock['historical_dependency_image_reference'])
        self.assertTrue(lock['new_image_build_completed'])
        self.assertTrue(lock['bounded_synthetic_method_acceptance_verified'])
        self.assertFalse(lock['method_acceptance_verified'])
        self.assertEqual(lock['software_lock']['limma'], '3.68.5')
        self.assertFalse(lock['scientific_authorization'])
        self.assertFalse(lock['G0'])

    def test_registered_ports_keep_actual_design_and_rds_contract(self):
        manifest = tomllib.loads((PLUGIN / 'manifest.toml').read_text())
        self.assertEqual(manifest['plugin_name'], 'bulk-limma-normalized')
        design, fit = manifest['nodes']
        self.assertEqual([len(n['ports']['inputs']) for n in (design, fit)], [5, 6])
        self.assertEqual([p['path'] for p in fit['ports']['outputs']],
                         ['results.tsv', 'audit.json', 'official.rds'])
        self.assertEqual(fit['ports']['outputs'][2]['format'], 'r_rds')
        for node in (design, fit):
            self.assertEqual(node['resources']['pull_policy'], 'never')
            self.assertEqual(node['resources']['network'], 'isolated')
            self.assertTrue(node['resources']['read_only_rootfs'])
            self.assertEqual(node['command']['interpreter'], '/opt/b-bulk/bin/Rscript-vanilla')

    def test_explicit_profile_selects_normalized_family_without_counts_method(self):
        profile = tomllib.loads(catalog.render_profile(catalog.inventory(ROOT),
                                'a' * 40, ['bulk-limma-normalized']))
        self.assertEqual(profile['plugin'][0]['subdir'], 'plugins/bulk-limma-normalized')
        self.assertEqual(profile['plugin'][0]['rev'], 'a' * 40)
        self.assertEqual(len(profile['plugin']), 1)

    def test_all_four_installed_scripts_have_real_port0_and_safe_static_surface(self):
        for directory in [PLUGIN, ROOT / 'plugins/frozen-b-project']:
            manifest = tomllib.loads((directory / 'manifest.toml').read_text())
            for node in manifest['nodes']:
                script = (directory / node['command']['script_file']).read_text()
                self.assertIn('AUTONOMICS_INPUT0', script)
                self.assertIn('AUTONOMICS_OUTPUT0', script)
                for token in ['curl ', 'wget ', 'ssh ', 'scp ', '/home/', '/Users/', '/mnt/', 'AUTONOMICS_PLUGIN_ROOT']:
                    self.assertNotIn(token, script)


if __name__ == '__main__':
    unittest.main()
