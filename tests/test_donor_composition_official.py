import hashlib
import csv
import io
import json
from pathlib import Path
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/donor-composition-official'


class DonorCompositionOfficialTests(unittest.TestCase):
    def test_manifest_exact_two_inputs_five_outputs_no_method_defaults(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        node = manifest['nodes'][0]
        self.assertEqual(node['kind'], 'donor_composition_official')
        self.assertEqual(len(node['ports']['inputs']), 2)
        self.assertEqual(len(node['ports']['outputs']), 5)
        self.assertNotIn('params', node)
        self.assertEqual(node['resources']['network'], 'isolated')
        self.assertIn('@sha256:78f195b8', manifest['image']['reference'])

    def test_embedded_original_independent_reference_bytes_unchanged(self):
        source = (FAMILY / 'scripts/donor_composition.R').read_text()
        core = source.split('OFFICIAL_REFERENCE_SOURCE <- r"---(', 1)[1].split(')---"', 1)[0].encode()
        self.assertEqual(len(core), 4093)
        self.assertEqual(hashlib.sha256(core).hexdigest(),
                         '53c3bd5d1ffaa254ad1161a3d325f722f99c7816753c7ebdb4bc02e5416e7001')

    def test_actual_R_contract_and_publication_helpers_without_fit(self):
        result = subprocess.run(['Rscript', '--vanilla', str(ROOT / 'tests/donor_composition_official_contract.R'),
            str(FAMILY / 'scripts/donor_composition.R')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout.strip())
        self.assertGreaterEqual(evidence['checks'], 35)
        self.assertEqual(evidence['statistical_fits'], 0)
        expected = [['label', 'value'], ['NA', ''], ['0001', '1'], ['供者甲', '2'], ['T"quoted', '3'], ['back\\slash', '4']]
        self.assertEqual(len(evidence['actual_writer_TSVs']), 2)
        for payload in evidence['actual_writer_TSVs']:
            self.assertEqual(list(csv.reader(io.StringIO(payload), delimiter='\t')), expected)


if __name__ == '__main__':
    unittest.main()
