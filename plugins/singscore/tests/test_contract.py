import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


FAMILY = Path(__file__).resolve().parents[1]
MANIFEST = tomllib.loads((FAMILY / 'manifest.toml').read_text())
IMAGE = MANIFEST['image']['reference']
SCRIPT = Path(os.environ.get('SINGSCORE_TEST_SCRIPT', FAMILY / 'scripts/singscore.sh'))


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def write_table(filename, header, rows):
    with filename.open('w', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)


class SingscoreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['podman', 'image', 'exists', IMAGE], check=True)

    def setUp(self):
        destination = os.environ.get('SINGSCORE_EVIDENCE_DIRECTORY')
        if destination:
            self.root = Path(destination) / self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(prefix='singscore-contract-')
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.genes = ['g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8']
        self.sample_ids = ['S1', 'S2', 'S3']
        self.values = [[1, 8, 3], [1, 7, 4], [3, 6, 4], [4, 5, 2],
                       [5, 4, 1], [6, 3, 6], [7, 2, 7], [8, 1, 8]]
        self.signature = [('g1', 'up'), ('g2', 'up'), ('g7', 'down'), ('g8', 'down')]
        self.metadata = [('S1', 'case'), ('S2', 'control'), ('S3', 'case')]
        self.output = self.root / 'output'
        self.output.mkdir()

    def prepare(self):
        write_table(self.root / 'matrix.tsv', ['gene'] + self.sample_ids,
                    [[gene] + values for gene, values in zip(self.genes, self.values)])
        write_table(self.root / 'signature.tsv', ['gene', 'direction'], self.signature)
        write_table(self.root / 'samples.tsv', ['sample', 'group'], self.metadata)

    def run_container(self, script, extra=(), name='node'):
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none',
                   '--cpus=2', '--memory=2g', '-v', f'{self.root}:/work',
                   '-v', f'{script}:/program.R:ro']
        command.extend(extra)
        command.extend(['--entrypoint', 'Rscript', IMAGE, '--vanilla', '/program.R'])
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (self.root / f'{name}.stdout.txt').write_text(completed.stdout)
        (self.root / f'{name}.stderr.txt').write_text(completed.stderr)
        record = dict(command=command, returncode=completed.returncode,
                      script_sha256=digest(script), image=IMAGE, G0=False,
                      artifacts={filename.name: digest(filename)
                                 for filename in self.output.iterdir() if filename.is_file()})
        (self.root / f'{name}.execution.json').write_text(json.dumps(record, indent=2) + '\n')
        return completed

    def run_node(self, prepare=True):
        if prepare:
            self.prepare()
        variables = {'AUTONOMICS_INPUT0': '/work/matrix.tsv',
                     'AUTONOMICS_INPUT1': '/work/signature.tsv',
                     'AUTONOMICS_INPUT2': '/work/samples.tsv',
                     'AUTONOMICS_OUTPUT0': '/work/output/scores.tsv',
                     'AUTONOMICS_OUTPUT1': '/work/output/score.RDS',
                     'AUTONOMICS_OUTPUT2': '/work/output/run.log'}
        extra = [part for key, value in variables.items() for part in ['-e', f'{key}={value}']]
        return self.run_container(SCRIPT, extra)

    def assert_rejected(self):
        completed = self.run_node()
        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertFalse((self.output / 'scores.tsv').exists())
        self.assertFalse((self.output / 'score.RDS').exists())
        self.assertTrue((self.output / 'run.log').is_file(), completed.stderr)
        self.assertIn('ERROR', (self.output / 'run.log').read_text())

    def assert_official(self):
        completed = self.run_node()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        with (self.output / 'scores.tsv').open() as handle:
            reader = csv.DictReader(handle, delimiter='\t')
            self.assertEqual(reader.fieldnames, ['sample', 'TotalScore', 'group'])
            scores = list(reader)
        self.assertEqual([row['sample'] for row in scores], self.sample_ids)
        groups = dict(self.metadata)
        self.assertEqual([row['group'] for row in scores], [groups[sample] for sample in self.sample_ids])
        self.assertTrue(all(math.isfinite(float(row['TotalScore'])) for row in scores))
        self.assertGreater((self.output / 'run.log').stat().st_size, 0)
        encoded = lambda values: 'c(' + ','.join(json.dumps(value, ensure_ascii=False) for value in values) + ')'
        expression = 'matrix(' + encoded([value for row in self.values for value in row]) + \
                     f', nrow={len(self.genes)}, byrow=TRUE, dimnames=list(' + \
                     encoded(self.genes) + ',' + encoded(self.sample_ids) + '))'
        up = encoded([gene for gene, direction in self.signature if direction == 'up'])
        down = [gene for gene, direction in self.signature if direction == 'down']
        call = f'singscore::simpleScore(expected_rank, upSet={up}, centerScore=TRUE, knownDirection=TRUE'
        if down:
            call += ', downSet=' + encoded(down)
        call += ')'
        reference = self.root / 'official_reference.R'
        reference.write_text('suppressMessages(library(singscore))\n' +
                             'stopifnot(packageVersion("singscore") == "1.32.0")\n' +
                             f'expected_expr <- {expression}\n' +
                             'expected_rank <- singscore::rankGenes(expected_expr, tiesMethod="average", stableGenes=NULL)\n' +
                             f'expected_simple <- {call}\n' +
                             'saveRDS(list(rank=expected_rank, simple=expected_simple), "/work/official_reference.RDS")\n' +
                             'actual <- readRDS("/work/output/score.RDS")\n' +
                             'stopifnot(identical(actual$rank_data, expected_rank))\n' +
                             'stopifnot(isTRUE(all.equal(actual$simple, expected_simple, tolerance=1e-12, check.attributes=TRUE)))\n' +
                             'stopifnot(identical(actual$scores$sample, colnames(expected_expr)))\n' +
                             'stopifnot(all(is.finite(actual$simple$TotalScore)))\n' +
                             'print(sessionInfo())\ncat("INDEPENDENT_OFFICIAL_REFERENCE_PASS\\n")\n')
        reference_result = self.run_container(reference, name='official-reference')
        self.assertEqual(reference_result.returncode, 0, reference_result.stderr)
        self.assertIn('INDEPENDENT_OFFICIAL_REFERENCE_PASS', reference_result.stdout)
        return scores

    def test_bidirectional_official_rank_and_all_scores(self):
        self.assert_official()

    def test_up_only_official_rank_and_all_scores(self):
        self.signature = self.signature[:2]
        self.assert_official()

    def test_all_ties_official_rank_and_all_scores(self):
        self.values = [[4, 4, 4] for gene in self.genes]
        self.assert_official()

    def test_lexical_gene_sample_and_group_ids(self):
        self.genes[:3] = ['001', '1', 'NA']
        self.signature = [('001', 'up'), ('NA', 'up'), ('g7', 'down'), ('g8', 'down')]
        self.sample_ids = ['001', '1', 'NA']
        self.metadata = [('NA', 'NA'), ('1', '001'), ('001', '1')]
        self.assert_official()

    def test_matrix_sample_order_is_preserved(self):
        self.sample_ids.reverse()
        self.values = [list(reversed(row)) for row in self.values]
        self.assert_official()

    def test_metadata_permutation_does_not_change_scores(self):
        self.metadata.reverse()
        self.assert_official()

    def test_gene_row_permutation_does_not_change_scores(self):
        self.genes.reverse()
        self.values.reverse()
        self.assert_official()

    def test_one_sample_official_rank_and_all_scores(self):
        self.sample_ids = self.sample_ids[:1]
        self.metadata = self.metadata[:1]
        self.values = [row[:1] for row in self.values]
        self.assert_official()

    def test_group_labels_do_not_enter_scores(self):
        self.metadata = [('S1', 'other'), ('S2', 'case'), ('S3', 'control')]
        self.assert_official()

    def test_missing_sample_metadata_is_rejected(self):
        self.metadata.pop()
        self.assert_rejected()

    def test_extra_sample_metadata_is_rejected(self):
        self.metadata.append(('extra', 'case'))
        self.assert_rejected()

    def test_duplicate_sample_metadata_is_rejected(self):
        self.metadata.append(self.metadata[0])
        self.assert_rejected()

    def test_blank_group_is_rejected(self):
        self.metadata[0] = ('S1', '')
        self.assert_rejected()

    def test_blank_sample_is_rejected(self):
        self.metadata[0] = ('', 'case')
        self.assert_rejected()

    def test_duplicate_matrix_sample_is_rejected(self):
        self.sample_ids[1] = self.sample_ids[0]
        self.assert_rejected()

    def test_duplicate_matrix_gene_is_rejected(self):
        self.genes[1] = self.genes[0]
        self.assert_rejected()

    def test_blank_matrix_gene_is_rejected(self):
        self.genes[2] = ''
        self.assert_rejected()

    def test_duplicate_signature_gene_is_rejected(self):
        self.signature.append(self.signature[0])
        self.assert_rejected()

    def test_overlapping_signature_directions_are_rejected(self):
        self.signature.append(('g1', 'down'))
        self.assert_rejected()

    def test_empty_signature_is_rejected(self):
        self.signature = []
        self.assert_rejected()

    def test_missing_signature_gene_is_rejected(self):
        self.signature.append(('absent', 'up'))
        self.assert_rejected()

    def test_down_only_signature_is_rejected(self):
        self.signature = self.signature[2:]
        self.assert_rejected()

    def test_unknown_signature_direction_is_rejected(self):
        self.signature[0] = ('g1', 'unknown')
        self.assert_rejected()

    def test_nonfinite_expression_is_rejected(self):
        self.values[0][0] = 'Inf'
        self.assert_rejected()

    def test_nan_expression_is_rejected(self):
        self.values[0][0] = 'NaN'
        self.assert_rejected()

    def test_missing_expression_is_rejected(self):
        self.values[0][0] = 'NA'
        self.assert_rejected()

    def test_nonnumeric_expression_is_rejected(self):
        self.values[0][0] = 'not-a-number'
        self.assert_rejected()

    def test_ragged_expression_is_rejected(self):
        self.values[0].pop()
        self.assert_rejected()

    def test_degenerate_full_background_signature_is_rejected(self):
        self.signature = [(gene, 'up') for gene in self.genes]
        self.assert_rejected()

    def test_preexisting_score_is_not_overwritten(self):
        filename = self.output / 'scores.tsv'
        filename.write_text('existing historical artifact\n')
        original = digest(filename)
        completed = self.run_node()
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(digest(filename), original)
        self.assertFalse((self.output / 'score.RDS').exists())

    def test_ragged_signature_is_rejected(self):
        self.signature.append(('g4', 'up', 'unexpected'))
        self.assert_rejected()


if __name__ == '__main__':
    unittest.main(verbosity=2)
