import hashlib
from pathlib import Path
import tomllib
import unittest
from tests.conditional_v2_baseline import assert_current_source, assert_manifest_extension, published_bytes


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-lcmm'


class LcmmPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.source = (FAMILY / 'scripts/lcmm.R').read_text()

    def test_existing_manifest_and_image_remain_unchanged(self):
        assert_manifest_extension(self, 'cachexia-lcmm', 4)
        self.assertEqual(self.manifest['image']['reference'],
                         'ghcr.io/zj-2002/lcmm-official@sha256:dd7f8a68d27a1002d5f6b004ca2ad24fc92cc7db43773500963363f92f8828d5')

    def test_four_modes_preserve_declared_ports_and_offline_limits(self):
        modes = {node['command']['env']['CACHEXIA_LCMM_MODE']: node for node in self.manifest['nodes'][:4]}
        self.assertEqual(set(modes), {'fit', 'predict', 'compare', 'bind'})
        for mode, node in modes.items():
            self.assertEqual(len(node['ports']['inputs']), 3)
            self.assertEqual(len(node['ports']['outputs']), 3 if mode == 'bind' else 6)
            self.assertEqual(node['resources'],
                             {'cpus': 1.0, 'memory': '2Gi', 'network': 'isolated', 'pull_policy': 'never'})

    def test_official_calls_are_not_replaced_by_native_arithmetic(self):
        for token in ('do.call(lcmm::hlme', 'lcmm::predictY(parent$fit',
                      'do.call(lcmm::summarytable', 'SYNTHETIC_TECHNICAL_INPUT',
                      'No autonomous class selection/missingness handling'):
            self.assertIn(token, self.source)

    def test_publication_has_private_staging_and_owned_rollback(self):
        for token in ('Refusing to overwrite existing output', 'Sys.readlink(filename)',
                      'do.call(Sys.setenv, as.list(original_outputs))', 'failed_fit.rds',
                      'file.link(sources[[position]], targets[[position]])',
                      'identical(file_identity(owned$path), owned$identity)'):
            self.assertIn(token, self.source)

    def test_verified_wrapper_identity_is_explicit(self):
        assert_current_source(self, 'research-adapters/cachexia-lcmm/scripts/lcmm.R')
        current = published_bytes('research-adapters/cachexia-lcmm/scripts/lcmm.R')
        audit_repair = b'request_json = jsonlite::toJSON(request, auto_unbox = TRUE, digits = 17, null = "null")'
        self.assertEqual(current.count(audit_repair), 1)
        binder_only = current.replace(audit_repair, audit_repair.replace(b'digits = 17', b'digits = NA'), 1)
        self.assertEqual(hashlib.sha256(binder_only).hexdigest(),
                         '15e7a0516716420198fa80652777696040d422d0437c45dfaa9dd6d51ba2e1e0')
        repaired = b'jsonlite::write_json(request, Sys.getenv("AUTONOMICS_OUTPUT0"), auto_unbox = TRUE, pretty = TRUE, digits = 17, null = "null")'
        self.assertEqual(binder_only.count(repaired), 1)
        original = binder_only.replace(repaired, repaired.replace(b'digits = 17', b'digits = NA'), 1)
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '92bedf32d5c48070df0354b0ee08c0d0f64e0fcb7cf44d7abd0da2945a0d43d8')


if __name__ == '__main__':
    unittest.main()
