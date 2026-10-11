import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import unittest


class LimmaBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['LIMMA_BOUNDARY_EVIDENCE']).resolve()
        cls.root.mkdir(exist_ok=False)
        cls.image = os.environ['LIMMA_BOUNDARY_IMAGE']
        if not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', cls.image):
            raise RuntimeError('Real digest-pinned method image required')
        cls.script = Path(os.environ.get('LIMMA_SCRIPT_OVERRIDE', str(Path(__file__).resolve().parents[1] / 'limma_voom_runner.R'))).resolve(strict=True)
        cls.baked = os.environ.get('LIMMA_BOUNDARY_BAKED') == '1'

    def check(self, changes=None, fixture=None, diagnostic=None, succeed=False):
        directory = self.root / self.id().split('.')[-1]
        directory.mkdir()
        generator = random.Random(10612)
        samples = ['s' + str(index) for index in range(1, 9)]
        rows = ['gene' + str(index) + '\t' + '\t'.join(str(generator.randrange(20, 2000)) for sample in samples)
            for index in range(1, 101)]
        (directory / 'counts.tsv').write_text('gene_id\t' + '\t'.join(samples) + '\n' + '\n'.join(rows) + '\n')
        (directory / 'metadata.tsv').write_text('sample_id\tcondition\tage\n' + ''.join(sample + '\t' +
            ('ctrl' if index < 4 else 'case') + '\t' + str(30 + index) + '\n' for index, sample in enumerate(samples)))
        environment = {'AUTONOMICS_INPUT0': '/work/counts.tsv', 'AUTONOMICS_INPUT1': '/work/metadata.tsv',
            'AUTONOMICS_OUTPUT0': '/work/results.tsv', 'AUTONOMICS_OUTPUT1': '/work/weights.tsv',
            'AUTONOMICS_OUTPUT2': '/work/normalized.tsv', 'AUTONOMICS_OUTPUT3': '/work/contrast.tsv',
            'AUTONOMICS_OUTPUT4': '/work/report.json', 'AUTONOMICS_LIMMA_OUTCOME': 'condition',
            'AUTONOMICS_LIMMA_CONTRAST_VAR': 'condition', 'AUTONOMICS_LIMMA_CONTRAST_LEVELS': 'ctrl,case',
            'AUTONOMICS_LIMMA_OUTCOME_MODE': 'categorical', 'AUTONOMICS_LIMMA_COVARIATES': '',
            'AUTONOMICS_LIMMA_NORMALIZATION': 'tmm', 'AUTONOMICS_LIMMA_ALPHA': '.05', 'AUTONOMICS_LIMMA_THREADS': '1'}
        environment.update(changes or {})
        protected = fixture(directory) if fixture else []
        before = {str(filename): filename.read_bytes() for filename in protected}
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--memory=2g', '--cpus=2',
            '--userns=keep-id', '--mount', f'type=bind,src={directory},dst=/work',
            '--entrypoint', '/opt/autonomics/Rscript-vanilla' if self.baked else 'Rscript']
        if not self.baked:
            command += ['--mount', f'type=bind,src={self.script},dst=/method.R,ro=true']
        for name, value in environment.items():
            command += ['--env', name + '=' + value]
        command += [self.image, '/opt/autonomics/limma_voom_runner.R'] if self.baked else [self.image, '--vanilla', '/method.R']
        result = subprocess.run(command, capture_output=True, timeout=180)
        (directory / 'stdout.txt').write_bytes(result.stdout)
        (directory / 'stderr.txt').write_bytes(result.stderr)
        (directory / 'execution.json').write_text(json.dumps({'command': command, 'exit': result.returncode,
            'source_sha256': hashlib.sha256(self.script.read_bytes()).hexdigest(), 'diagnostic': diagnostic,
            'execution_mode': 'BAKED_IMAGE_RUNNER' if self.baked else 'SOURCE_BIND_OVERRIDE',
            'G0': False}, indent=2) + '\n')
        if succeed:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertTrue(all((directory / name).stat().st_size for name in
                ['results.tsv', 'weights.tsv', 'normalized.tsv', 'contrast.tsv', 'report.json']))
            return directory
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr.decode())
        for filename in protected:
            self.assertEqual(filename.read_bytes(), before[str(filename)])
        for name in ['results.tsv', 'weights.tsv', 'normalized.tsv', 'contrast.tsv', 'report.json']:
            filename = directory / name
            if filename not in protected and not filename.is_symlink():
                self.assertFalse(filename.exists(), 'Rejected input published an analytical output')

    def existing(self, name):
        def fixture(directory):
            filename = directory / name
            filename.write_text('PREEXISTING\n')
            return [filename]
        return fixture

    def alter_counts(self, transform):
        def fixture(directory):
            filename = directory / 'counts.tsv'
            filename.write_text(transform(filename.read_text()))
            return []
        return fixture

    def alter_metadata(self, transform):
        def fixture(directory):
            filename = directory / 'metadata.tsv'
            filename.write_text(transform(filename.read_text()))
            return []
        return fixture

    def count_token(self, value):
        return self.alter_counts(lambda text: text.replace(text.splitlines()[1].split('\t')[1], value, 1))

    def test_existing_result(self):
        self.check(fixture=self.existing('results.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_weights(self):
        self.check(fixture=self.existing('weights.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_expression(self):
        self.check(fixture=self.existing('normalized.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_contrast(self):
        self.check(fixture=self.existing('contrast.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_report(self):
        self.check(fixture=self.existing('report.json'), diagnostic='existing outputs must not be overwritten')

    def test_input_output_alias(self):
        self.check({'AUTONOMICS_OUTPUT0': '/work/counts.tsv'}, fixture=lambda directory: [directory / 'counts.tsv'],
            diagnostic='existing outputs must not be overwritten')

    def test_duplicate_output(self):
        self.check({'AUTONOMICS_OUTPUT1': '/work/results.tsv'}, diagnostic='output paths must be distinct')

    def test_missing_output(self):
        self.check({'AUTONOMICS_OUTPUT4': ''}, diagnostic='all five declared output ports are required')

    def test_dangling_output(self):
        def fixture(directory):
            (directory / 'results.tsv').symlink_to('/work/missing-target')
            return []
        self.check(fixture=fixture, diagnostic='existing outputs must not be overwritten')

    def test_missing_input(self):
        self.check({'AUTONOMICS_INPUT0': '/work/absent.tsv'}, diagnostic='input must be an existing regular file')

    def test_directory_input(self):
        self.check({'AUTONOMICS_INPUT0': '/work'}, diagnostic='input must be an existing regular file')

    def test_alpha_zero(self):
        self.check({'AUTONOMICS_LIMMA_ALPHA': '0'}, diagnostic='alpha must lie strictly between 0 and 1')

    def test_alpha_one(self):
        self.check({'AUTONOMICS_LIMMA_ALPHA': '1'}, diagnostic='alpha must lie strictly between 0 and 1')

    def test_alpha_nan(self):
        self.check({'AUTONOMICS_LIMMA_ALPHA': 'NaN'}, diagnostic='alpha must lie strictly between 0 and 1')

    def test_threads_two(self):
        self.check({'AUTONOMICS_LIMMA_THREADS': '2'}, diagnostic='threads must be fixed at 1')

    def test_threads_fraction(self):
        self.check({'AUTONOMICS_LIMMA_THREADS': '1.5'}, diagnostic='threads must be fixed at 1')

    def test_unknown_mode(self):
        self.check({'AUTONOMICS_LIMMA_OUTCOME_MODE': 'other'}, diagnostic='outcome_mode must be')

    def test_unknown_normalization(self):
        self.check({'AUTONOMICS_LIMMA_NORMALIZATION': 'other'}, diagnostic='normalization must be')

    def test_contrast_wrong_column(self):
        self.check({'AUTONOMICS_LIMMA_CONTRAST_VAR': 'age'}, diagnostic='contrast_var must equal outcome_var')

    def test_duplicate_contrast_levels(self):
        self.check({'AUTONOMICS_LIMMA_CONTRAST_LEVELS': 'ctrl,ctrl'}, diagnostic='contrast_levels must be distinct')

    def test_contrast_empty_entry(self):
        self.check({'AUTONOMICS_LIMMA_CONTRAST_LEVELS': 'ctrl,case,'}, diagnostic='comma-separated parameters must not contain empty entries')

    def test_contrast_three_levels(self):
        self.check({'AUTONOMICS_LIMMA_CONTRAST_LEVELS': 'ctrl,case,other'}, diagnostic='contrast_levels must contain exactly two entries')

    def test_bad_outcome_identifier(self):
        self.check({'AUTONOMICS_LIMMA_OUTCOME': 'condition+age'}, diagnostic='simple nonreserved R identifiers')

    def test_reserved_outcome(self):
        self.check({'AUTONOMICS_LIMMA_OUTCOME': 'sample_id'}, diagnostic='simple nonreserved R identifiers')

    def test_duplicate_covariates(self):
        self.check({'AUTONOMICS_LIMMA_COVARIATES': 'age,age'}, diagnostic='covariates cannot contain duplicates')

    def test_reserved_covariate(self):
        self.check({'AUTONOMICS_LIMMA_COVARIATES': 'sample_id'}, diagnostic='is reserved')

    def test_invalid_covariate_identifier(self):
        self.check({'AUTONOMICS_LIMMA_COVARIATES': '.1'}, diagnostic='must be a simple R identifier')

    def test_ragged_extra(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene1\t', '\nextra\tgene1\t')),
            diagnostic='input rows must match the header width')

    def test_ragged_missing(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene1\t', '\ngene1')),
            diagnostic='input rows must match the header width')

    def test_blank_header(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ts1\t', '\t\t', 1)),
            diagnostic='input headers must be nonempty and unique')

    def test_embedded_nul(self):
        def fixture(directory):
            filename = directory / 'counts.tsv'
            filename.write_bytes(filename.read_bytes().replace(b'gene1\t', b'gene1\x00other\t'))
            return []
        self.check(fixture=fixture, diagnostic='input must not contain embedded NUL bytes')

    def test_control_character_id(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene1\t', '\ngene1\x07other\t')),
            diagnostic='input fields must not contain control characters')

    def test_duplicate_header(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ts2\t', '\ts1\t', 1)),
            diagnostic='input headers must be nonempty and unique')

    def test_empty_gene_id(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene1\t', '\n\t')), diagnostic='gene_id cannot be empty')

    def test_duplicate_gene_id(self):
        self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene2\t', '\ngene1\t')), diagnostic='gene_id values must be unique')

    def test_fractional_counts(self):
        self.check(fixture=self.count_token('1.5'), diagnostic='count values must be exactly representable nonnegative integers')

    def test_fraction_below_double_precision(self):
        self.check(fixture=self.count_token('20.0000000000000001'),
            diagnostic='count values must be exactly representable nonnegative integers')

    def test_fraction_at_safe_integer_ceiling(self):
        self.check(fixture=self.count_token('9007199254740991.1'),
            diagnostic='count values must be exactly representable nonnegative integers')

    def test_exact_scientific_integer_token(self):
        self.check(fixture=self.count_token('.5e1'), succeed=True)

    def test_exact_decimal_integer_token(self):
        self.check(fixture=self.count_token('20.0000000000000000'), succeed=True)

    def test_inexact_large_counts(self):
        self.check(fixture=self.count_token('9007199254740992'), diagnostic='count values must be exactly representable nonnegative integers')

    def test_negative_counts(self):
        self.check(fixture=self.count_token('-1'), diagnostic='all count values must be finite nonnegatives')

    def test_nonfinite_counts(self):
        self.check(fixture=self.count_token('Inf'), diagnostic='all count values must be finite nonnegatives')

    def test_missing_counts(self):
        self.check(fixture=self.count_token('NA'), diagnostic='all count values must be finite nonnegatives')

    def test_unknown_outcome_level(self):
        self.check(fixture=self.alter_metadata(lambda text: text.replace('ctrl', 'other', 1)),
            diagnostic='categorical outcome values must belong to contrast_levels')

    def test_missing_outcome(self):
        self.check(fixture=self.alter_metadata(lambda text: text.replace('ctrl', 'NA', 1)), diagnostic='contains missing values')

    def test_numeric_covariate_infinity(self):
        self.check({'AUTONOMICS_LIMMA_COVARIATES': 'age'},
            fixture=self.alter_metadata(lambda text: text.replace('\t30\n', '\tInf\n')), diagnostic='must be finite')

    def test_wrong_metadata_samples(self):
        self.check(fixture=self.alter_metadata(lambda text: text.replace('s1\t', 'other\t')), diagnostic='sample sets differ')

    def test_metadata_duplicate_samples(self):
        self.check(fixture=self.alter_metadata(lambda text: text.replace('s2\t', 's1\t')), diagnostic='sample_id values must be unique')

    def test_continuous_non_numeric(self):
        self.check({'AUTONOMICS_LIMMA_OUTCOME_MODE': 'continuous', 'AUTONOMICS_LIMMA_CONTRAST_LEVELS': ''},
            diagnostic='continuous outcome values must be finite numbers')

    def test_continuous_with_levels(self):
        self.check({'AUTONOMICS_LIMMA_OUTCOME': 'age', 'AUTONOMICS_LIMMA_CONTRAST_VAR': 'age',
            'AUTONOMICS_LIMMA_OUTCOME_MODE': 'continuous'}, diagnostic='CONTRAST_LEVELS only applies to categorical outcome')

    def test_zero_residual_df(self):
        def fixture(directory):
            (directory / 'metadata.tsv').write_text('sample_id\tcondition\ns1\tctrl\ns2\tcase\n')
            rows = (directory / 'counts.tsv').read_text().splitlines()
            (directory / 'counts.tsv').write_text('\n'.join('\t'.join(row.split('\t')[:3]) for row in rows) + '\n')
            return []
        self.check(fixture=fixture, diagnostic='positive residual degrees of freedom')

    def test_singular_design(self):
        self.check({'AUTONOMICS_LIMMA_COVARIATES': 'age'},
            fixture=self.alter_metadata(lambda text: '\n'.join([text.splitlines()[0]] +
                ['\t'.join(row.split('\t')[:2] + ['0' if 'ctrl' in row else '1']) for row in text.splitlines()[1:]]) + '\n'),
            diagnostic='be full rank')

    def test_zero_library(self):
        def transform(text):
            rows = text.splitlines()
            return '\n'.join([rows[0]] + ['\t'.join([row.split('\t')[0], '0'] + row.split('\t')[2:]) for row in rows[1:]]) + '\n'
        self.check(fixture=self.alter_counts(transform), diagnostic='positive total counts')

    def test_no_genes_kept(self):
        self.check(fixture=self.alter_counts(lambda text: '\n'.join([text.splitlines()[0]] +
            [row.split('\t')[0] + '\t' + '\t'.join(['1'] * 8) for row in text.splitlines()[1:]]) + '\n'),
            diagnostic='no genes remain after official filterByExpr')

    def test_literal_ids_and_sample_weight_labels(self):
        directory = self.check(fixture=self.alter_counts(lambda text: text.replace('\ngene1\t', '\n00001\t')
            .replace('\ngene2\t', '\nNA\t')), succeed=True)
        identifiers = [line.split('\t')[0] for line in (directory / 'results.tsv').read_text().splitlines()[1:]]
        self.assertEqual(identifiers[:2], ['00001', 'NA'])
        self.assertEqual((directory / 'weights.tsv').read_text().splitlines()[0],
            'gene_id\t' + '\t'.join('s' + str(index) for index in range(1, 9)))

    def test_numeric_sample_ids_and_reordered_metadata(self):
        def fixture(directory):
            for name in ['counts.tsv', 'metadata.tsv']:
                filename = directory / name
                text = filename.read_text()
                for index in range(1, 9):
                    text = text.replace('s' + str(index), str(index).zfill(2))
                if name == 'metadata.tsv':
                    text = '\n'.join([text.splitlines()[0]] + text.splitlines()[1:][::-1]) + '\n'
                filename.write_text(text)
            return []
        directory = self.check(fixture=fixture, succeed=True)
        self.assertEqual((directory / 'normalized.tsv').read_text().splitlines()[0],
            'gene_id\t' + '\t'.join(str(index).zfill(2) for index in range(1, 9)))

    def test_filter_ledger_retains_excluded_ids(self):
        directory = self.check(fixture=self.alter_counts(lambda text: text + 'excluded\t' + '\t'.join(['0'] * 8) + '\n'), succeed=True)
        report = json.loads((directory / 'report.json').read_text())
        self.assertEqual(report['gene_filter']['excluded_gene_ids'], ['excluded'])
        self.assertEqual(len(report['gene_filter']['all_gene_ids']), 101)
        self.assertEqual(len(report['gene_filter']['retained_gene_ids']), 100)


if __name__ == '__main__':
    unittest.main()
