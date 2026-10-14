import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from tools import prove_bulk_current_chain as proof


class BulkCurrentChainTests(unittest.TestCase):
    def test_four_node_three_family_graph_has_all_five_raw_file_edges(self):
        families = {name: proof.ROOT / 'plugins' / family for name, family in [
            ('aggregate', 'pseudobulk'), ('deseq2', 'deseq2'), ('limma', 'bulk-rnaseq')]}
        job = proof.job_for(Path('/unused/toy'), families)
        self.assertEqual(job['expected_plugin_name'], 'pseudobulk')
        self.assertEqual([entry['expected_plugin_name'] for entry in job['additional_plugins']], ['deseq2', 'bulk-rnaseq'])
        self.assertEqual(len(job['nodes']), 4)
        self.assertEqual(len(job['edges']), 5)
        self.assertEqual(job['nodes'][2]['spec']['fit_type'], 'mean')
        self.assertEqual(job['nodes'][2]['spec']['lfc_shrink'], 'none')
        self.assertEqual(job['nodes'][3]['spec']['normalization'], 'tmm')
        self.assertTrue(all(entry['panel_overrides'] == [] for entry in job['additional_plugins']))

    def test_csv_reader_keeps_quotes_leading_zero_and_literal_missing_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'quoted.tsv'
            filename.write_text('gene_id\t"sample""name"\t0001\n"gene""id"\tNA\tNULL\n')
            self.assertEqual(proof.table(filename), [['gene_id', 'sample"name', '0001'], ['gene"id', 'NA', 'NULL']])
            filename.write_text('gene_id\t"unclosed\n')
            with self.assertRaises(csv.Error): proof.table(filename)

    def test_numeric_oracle_requires_exact_ids_missing_masks_and_finite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected, actual = root / 'expected.tsv', root / 'actual.tsv'
            expected.write_text('gene_id\tp\tmissing\n0001\t0.001\tNA\n')
            actual.write_bytes(expected.read_bytes())
            self.assertEqual(proof.numeric_table(actual, expected, 1e-12)['finite_fields'], 1)
            for value in ['gene_id\tp\tmissing\n1\t0.001\tNA\n', 'gene_id\tp\tmissing\n0001\t0.001\t0\n',
                          'gene_id\tp\tmissing\n0001\tNaN\tNA\n', 'gene_id\tp\tmissing\n0001\t0.01\tNA\n']:
                actual.write_text(value)
                with self.assertRaises(RuntimeError): proof.numeric_table(actual, expected, 1e-12)

    def test_stage_receipt_requires_exact_upstream_port_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scratch = root / 'scratch'
            workspace = scratch / 'consumer'
            stage = workspace / '.autonomics/inputs/input-0.tsv'
            stage.parent.mkdir(parents=True)
            original = root / 'source.tsv'
            original.write_bytes(b'EXACT_QUOTED_BYTES')
            stage.write_bytes(original.read_bytes())
            analysis = dict(inputs=[dict(to_port=0, from_port=0, fingerprint=dict(size=original.stat().st_size), **{'from': 'aggregate'})])
            self.assertEqual(proof.bound_inputs(analysis, [original], 'aggregate', scratch, workspace), 1)
            for mutation in ['port', 'source', 'bytes']:
                changed = copy.deepcopy(analysis)
                stage.write_bytes(original.read_bytes())
                if mutation == 'port': changed['inputs'][0]['from_port'] = 1
                elif mutation == 'source': changed['inputs'][0]['from'] = 'other'
                else: stage.write_bytes(b'WRONG')
                with self.assertRaises(RuntimeError): proof.bound_inputs(changed, [original], 'aggregate', scratch, workspace)

    def test_report_normalization_requires_actual_hashes_and_keeps_all_semantic_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'table.tsv'
            path.write_bytes(b'GENE\tVALUE\n')
            import hashlib
            identity = dict(path=path.name, md5=hashlib.md5(path.read_bytes()).hexdigest())
            report = dict(inputs=dict(counts=identity), outputs=dict(result=copy.deepcopy(identity)), method=dict(threshold=.1, release=False))
            actual = proof.normalized_report(report, dict(counts=path), dict(result=path))
            self.assertEqual(actual['method'], report['method'])
            changed = copy.deepcopy(report)
            changed['outputs']['result']['md5'] = '0' * 32
            with self.assertRaises(RuntimeError): proof.normalized_report(changed, dict(counts=path), dict(result=path))


if __name__ == '__main__': unittest.main()
