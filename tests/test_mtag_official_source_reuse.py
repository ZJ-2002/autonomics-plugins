import hashlib
import json
from pathlib import Path
import tomllib
import unittest


FAMILY = Path(__file__).resolve().parents[1] / 'plugins' / 'mtag-official'


class SourceReuseTests(unittest.TestCase):
    def test_entry_script_is_the_retained_verified_source(self):
        lock = json.loads((FAMILY / 'reuse-lock.json').read_text())
        self.assertEqual(hashlib.sha256((FAMILY / 'scripts/mtag.py').read_bytes()).hexdigest(), lock['unchanged_entry_sha256'])

    def test_only_explicit_identity_and_provenance_docs_changed(self):
        lock = json.loads((FAMILY / 'reuse-lock.json').read_text())
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest.pop('plugin_name'), 'mtag-official')
        manifest['image'].pop('upstream')
        self.assertEqual(manifest['nodes'][0].pop('kind'), 'mtag_official')
        manifest['nodes'][0].pop('doc')
        encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), lock['manifest_semantics_except_explicit_rename_and_provenance_docs_sha256'])

    def test_explicit_two_input_four_output_contract_is_not_legacy(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        ports = manifest['nodes'][0]['ports']
        self.assertEqual([port['type'] for port in ports['inputs']], ['file', 'file'])
        self.assertEqual([port['path'] for port in ports['outputs']], ['mtag_results.tar', 'mtag.log', 'mtag_artifact_index.tsv', 'mtag_audit.json'])


if __name__ == '__main__':
    unittest.main()
