import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-nichenet'


class NichenetPublicationBindingTests(unittest.TestCase):
    def test_frozen_manifest_and_image_unchanged(self):
        self.assertEqual(hashlib.sha256((FAMILY / 'manifest.toml').read_bytes()).hexdigest(), 'f46ff792c25585f31b018d82958faa8798e7039e731ca94721f284ae30097d7f')
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'], 'ghcr.io/zj-2002/nichenetr@sha256:f0ee4a511531f91839d2d9d9cb83535bd7f7f6b12905e26635684f8a081f0c19')

    def test_all_declared_ports_remain_explicit(self):
        definition = tomllib.loads((FAMILY / 'manifest.toml').read_text())['nodes'][0]
        self.assertEqual(len(definition['ports']['inputs']), 3)
        self.assertEqual([item['path'] for item in definition['ports']['outputs']],
            ['values.tsv', 'state.rds', 'audit.json', 'nichenet.log', 'cells.tsv', 'genes.tsv', 'geneset.tsv', 'family.tsv'])

    def test_reviewed_entry_source_identity(self):
        self.assertEqual(hashlib.sha256((FAMILY / 'scripts/h5ad_reader.R').read_bytes()).hexdigest(),
            'dadd46d027650fe31e883d97a487cca661712e6891059759fd5f2dc727c1b4c7')

    def test_explicit_exclusive_publication_and_rollback(self):
        source = (FAMILY / 'scripts/h5ad_reader.R').read_text()
        for token in ('Sys.readlink(filename)', 'private_outputs <- file.path(stage', 'status <- writer(private_outputs)',
                      'identical(file_identity(owned$path), owned$identity)', 'file.link(private_outputs[[position]], destinations[[position]])'):
            self.assertIn(token, source)

    def test_author_calls_and_complete_object_are_not_replaced(self):
        source = (FAMILY / 'scripts/h5ad_reader.R').read_text()
        for token in ('run_nichenet <- function(outputs, audit)', 'nichenetr::predict_ligand_activities(',
                      'nichenetr::get_expressed_genes(', 'nichenetr::get_weighted_ligand_target_links',
                      'nichenetr::get_weighted_ligand_receptor_links(', 'rng_after = .Random.seed', 'saveRDS(payload, outputs[[2L]]'):
            self.assertIn(token, source)


if __name__ == '__main__':
    unittest.main()
