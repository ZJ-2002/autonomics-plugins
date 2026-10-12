import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'plugins/single-cell'


class H5ADRankInterfaceTests(unittest.TestCase):
    def test_original_three_ports_and_four_parameters(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        node = next(row for row in manifest['nodes'] if row['kind'] == 'h5ad_rank_genes_groups')
        self.assertEqual(len(node['ports']['inputs']), 1)
        self.assertEqual([row['path'] for row in node['ports']['outputs']], ['rank_genes_groups.parquet', 'report.json', 'output.h5ad'])
        self.assertEqual(set(node['params']), {'groupby', 'method', 'reference', 'n_genes'})
        self.assertEqual(node['command']['script_file'], 'scripts/rank_genes_groups.py')

    def test_explicit_original_X_recipe_and_complete_result_audit(self):
        source = (FAMILY / 'scripts/rank_genes_groups.py').read_text()
        ast.parse(source)
        self.assertIn('sc.tl.rank_genes_groups', source)
        self.assertIn('use_raw=False', source)
        self.assertIn('mask_var=None', source)
        self.assertIn('tie_correct=False', source)
        self.assertIn('tested_gene_universe', source)
        self.assertIn('NO_GENE_P_VALUES_FOR_LOGREG', source)
        self.assertIn('NOT_DONOR_OR_ANIMAL', source)
        self.assertIn('os.link(staging, target)', source)

    def test_public_whole_author_and_boundary_drivers_are_not_skipped(self):
        source = (FAMILY / 'tests/test_rank_container.py').read_text()
        self.assertIn("'wilcoxon', 't-test', 't-test_overestim_var', 'logreg'", source)
        self.assertIn('assert author.returncode == 0', source)
        self.assertIn('assert actual.returncode == 0', source)
        self.assertNotIn('skip', source.lower())
        boundary = (FAMILY / 'tests/test_rank_boundaries.py').read_text()
        self.assertIn('third-link-fault', boundary)
        self.assertIn('assert process.returncode != 0', boundary)


if __name__ == '__main__':
    unittest.main()
