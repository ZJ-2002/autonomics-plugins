import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/mrlap'


class MrlapPublicationBindingTests(unittest.TestCase):
    def test_frozen_manifest_image_and_resources_unchanged(self):
        self.assertEqual(hashlib.sha256((FAMILY / 'manifest.toml').read_bytes()).hexdigest(), '8dcc2b973b844150f660b9fcd9209b564d4642f118ed716fc219cc4a072c81c6')
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'], 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d')
        self.assertEqual(manifest['nodes'][0]['resources']['memory'], '8Gi')

    def test_original_three_inputs_and_four_outputs_remain(self):
        node = tomllib.loads((FAMILY / 'manifest.toml').read_text())['nodes'][0]
        self.assertEqual(len(node['ports']['inputs']), 3)
        self.assertEqual([item['path'] for item in node['ports']['outputs']], ['mrlap_summary.tsv', 'mrlap.RDS', 'mrlap_result.txt', 'mrlap.log'])

    def test_reviewed_entry_and_executed_R_control_identities(self):
        for name, expected in (
            ('scripts/mrlap.sh', '7d0e4b458fa90b4804f26948f2cd837f921616b92aaad544e0a26721328cc14a'),
            ('tests/publication_controls.R', '39297e788f3638de04f7d7b29ea516fe3b4d6e4daadedc0f4ee63ffc334d229b')):
            self.assertEqual(hashlib.sha256((FAMILY / name).read_bytes()).hexdigest(), expected)

    def test_exclusive_links_and_owned_rollback_are_explicit(self):
        source = (FAMILY / 'scripts/mrlap.sh').read_text()
        for token in ('publish_mrlap_outputs <- function(writer)', 'file.link(filename, destinations[[position]])',
                      'identical(file_identity(owned$path), owned$identity)', 'else 4L',
                      'Failure log must not be a symlink', 'sys.nframe() == 0L'):
            self.assertIn(token, source)

    def test_direct_author_call_seed_and_complete_result_remain(self):
        source = (FAMILY / 'scripts/mrlap.sh').read_text()
        for token in ('res <- MRlap::MRlap(', 'do_pruning = FALSE, user_SNPsToKeep = ivs',
                      'RNGkind("Mersenne-Twister", "Inversion", "Rejection")', 'set.seed(seed_int)',
                      'saveRDS(res, rds_path)', 'required_correction_fields', 'run_mrlap <- function(outputs)'):
            self.assertIn(token, source)


if __name__ == '__main__':
    unittest.main()
