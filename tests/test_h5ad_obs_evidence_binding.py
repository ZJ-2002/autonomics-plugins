"""Metadata-card checks only; functional evidence is the sealed native I/O suite."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class H5ADObsEvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        self.card = json.loads((ROOT / 'evidence/h5ad-obs-source-reconciliation-20261019.json').read_text())

    def test_original_native_io_is_not_mislabelled_as_an_author_package(self):
        self.assertTrue(self.card['original_node_native_IO_not_new_Rust_statistical_method'])
        self.assertFalse(self.card['direct_official_AnnData_runtime_claimed'])
        self.assertEqual(self.card['statistical_official_layer'], 'NOT_APPLICABLE')

    def test_exact_published_node_source_and_called_resolvers_are_bound(self):
        self.assertEqual(self.card['current_source']['path'], 'crates/node-bundles/nodes-io/src/h5ad_obs_to_dataframe.rs')
        self.assertEqual(self.card['current_source']['sha256'],
                         'd537173c057f80de38a999d3b4373dad24d15c4f2b183a894c9a48edd7fe77f8')
        self.assertEqual(len(self.card['called_path_resolvers_identical_to_published_tested_versions']), 3)

    def test_existing_complete_functional_cases_are_not_new_recomputations(self):
        self.assertEqual(self.card['reused_positive_full_schema_value_SQL_cases'], 16)
        self.assertEqual(self.card['reused_specific_refusals'], 20)
        self.assertEqual(self.card['reused_actual_DAGs'], 7)
        self.assertEqual(self.card['new_source_repairs'], 0)
        self.assertEqual(self.card['new_builds_or_method_recomputations'], 0)

    def test_normalization_and_deployment_boundaries_are_explicit(self):
        self.assertTrue(self.card['dictionary_key_width_and_empty_category_type_are_explicit_normalizations'])
        self.assertFalse(self.card['current_whole_engine_or_daemon_certified'])
        self.assertFalse(self.card['scientific_release_granted'])
        self.assertFalse(self.card['g0_granted'])


if __name__ == '__main__':
    unittest.main()
