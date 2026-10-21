import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'plugins/deseq2'


class Deseq2SourceRestorationTests(unittest.TestCase):
    def test_runtime_files_match_the_qualified_deployed_snapshot(self):
        expected = {
            'manifest.toml': '00787f36aba142b551ae1db07e9d7ee629bea7faf3c91a167a3a15825f059930',
            'deseq2_runner.R': 'b74c79d0c696a3b42d89437d068509cad9edb7cba904d5929d6b6b6f2c8e5a15',
            'dds_diagnostics.R': '25b8eb17660f655853147388bcfd97e9777a2e133af3e010f684894406d77811',
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_manifest_retains_fit_policy_and_diagnostic_file_contract(self):
        manifest = tomllib.loads((ROOT / 'manifest.toml').read_text())
        nodes = {row['kind']: row for row in manifest['nodes']}
        self.assertEqual(nodes['deseq2_de']['params']['fit_policy']['default'], 'exact')
        self.assertEqual(nodes['deseq2_de']['command']['env']['AUTONOMICS_DESEQ2_FIT_POLICY'], '{{ fit_policy }}')
        diagnostic = nodes['deseq2_dds_diagnostics']
        self.assertEqual(len(diagnostic['ports']['inputs']), 2)
        self.assertEqual(len(diagnostic['ports']['outputs']), 3)
        self.assertEqual(diagnostic['command']['script_file'], 'dds_diagnostics.R')

    def test_diagnostic_preserves_identity_checks_and_does_not_refit(self):
        source = (ROOT / 'dds_diagnostics.R').read_text()
        self.assertIn('DDS does not match the original run report', source)
        self.assertIn('DDS readback requires the original DESeq2 version', source)
        self.assertIn('convergence annotation incomplete', source)
        self.assertIn('DESeq2::results(', source)
        self.assertNotIn('DESeq2::DESeq(', source)
        self.assertNotIn('DESeq2::estimateDispersions(', source)


if __name__ == '__main__':
    unittest.main()
