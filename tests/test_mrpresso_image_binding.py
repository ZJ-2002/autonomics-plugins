"""Check the bounded MR-PRESSO image declaration, not numerical equivalence."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/zj-2002/mrpresso@sha256:5ecce3690fc69a051483463c7697df3147772c2cc69a171c5d83784b238a9ca8'


class MRPressoImageBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((ROOT / 'plugins/mrpresso/manifest.toml').read_text())

    def test_installed_owner_digest_not_missing_legacy_reference(self):
        self.assertEqual(self.manifest['image']['reference'], IMAGE)
        self.assertIn('actual package Version 1.0, R 4.5.1', self.manifest['image']['upstream'])
        self.assertIn('3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87', self.manifest['image']['upstream'])

    def test_original_one_input_two_output_contract_is_preserved(self):
        self.assertEqual(len(self.manifest['nodes']), 1)
        node = self.manifest['nodes'][0]
        self.assertEqual(node['kind'], 'mrpresso')
        self.assertEqual(node['ports']['inputs'], [{'type': 'file'}])
        self.assertEqual(node['ports']['outputs'], [
            {'path': 'mrpresso.RDS', 'format': 'r_rds'},
            {'path': 'mrpresso.log', 'format': 'mrpresso_log'}])

    def test_method_parameters_and_call_script_not_replaced_by_adapter(self):
        node = self.manifest['nodes'][0]
        self.assertEqual(node['command']['script_file'], 'scripts/mrpresso.R.sh')
        self.assertEqual(node['params']['seed']['default'], 123)
        self.assertEqual(node['params']['nb_distribution']['default'], 1000)
        self.assertIs(node['params']['outlier_test']['default'], False)
        self.assertIs(node['params']['distortion_test']['default'], False)
        self.assertIn('global test is always computed', node['params']['outlier_test']['doc'])
        self.assertIn('change in the causal estimate', node['params']['distortion_test']['doc'])
        source = (ROOT / 'plugins/mrpresso/scripts/mrpresso.R.sh').read_text()
        self.assertIn('result <- MRPRESSO::mr_presso(', source)
        self.assertEqual(node['command']['env_r_arrays'], {
            'MRPRESSO_BETA_EXPOSURE_R': 'beta_exposure',
            'MRPRESSO_SD_EXPOSURE_R': 'sd_exposure'})
        self.assertNotIn('strsplit(Sys.getenv("MRPRESSO_BETA_EXPOSURE")', source)

    def test_docker_author_commit_and_runtime_match_image_contract(self):
        dockerfile = (ROOT / 'plugins/mrpresso/Dockerfile').read_text()
        self.assertIn('rocker/r-ver:4.5.1', dockerfile)
        self.assertIn('3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87', dockerfile)


if __name__ == '__main__':
    unittest.main()
