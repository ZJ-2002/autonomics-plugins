import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import unittest


class DESeq2Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['DESEQ2_BOUNDARY_EVIDENCE']).resolve()
        cls.root.mkdir(exist_ok=False)
        cls.image = os.environ['DESEQ2_BOUNDARY_IMAGE']
        if not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', cls.image):
            raise RuntimeError('Mandatory immutable real image required')
        cls.script = Path(__file__).resolve().parents[1] / 'deseq2_runner.R'
        cls.baked = os.environ.get('DESEQ2_BOUNDARY_BAKED') == '1'

    def check(self, changes=None, fixture=None, diagnostic=None, succeed=False):
        directory = self.root / self.id().split('.')[-1]
        directory.mkdir()
        generator = random.Random(410612)
        samples = ['s' + str(index + 1) for index in range(12)]
        rows = []
        for index in range(200):
            baseline = generator.uniform(70, 1500)
            rows.append(['gene' + str(index + 1), *[str(max(1, round(generator.gammavariate(8, baseline / 8))))
                                                      for sample in samples]])
        with (directory / 'counts.tsv').open('w') as handle:
            writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
            writer.writerow(['gene_id', *samples])
            writer.writerows(rows)
        (directory / 'metadata.tsv').write_text('sample_id\tcondition\tage\n' + ''.join(
            sample + '\t' + ('ctrl' if index < 6 else 'case') + '\t' + str(20 + (index * 7) % 17) + '\n'
            for index, sample in enumerate(samples)))
        environment = {'AUTONOMICS_INPUT0': '/work/counts.tsv', 'AUTONOMICS_INPUT1': '/work/metadata.tsv',
            'AUTONOMICS_DESEQ2_CONDITION_REFERENCE': 'ctrl', 'AUTONOMICS_DESEQ2_CONDITION_TEST': 'case',
            'AUTONOMICS_DESEQ2_COVARIATES': '', 'AUTONOMICS_DESEQ2_FIT_TYPE': 'mean',
            'AUTONOMICS_DESEQ2_LFC_SHRINK': 'none', 'AUTONOMICS_DESEQ2_ALPHA': '.1',
            'AUTONOMICS_DESEQ2_THREADS': '1'}
        names = ['results.tsv', 'normalized.tsv', 'size_factors.tsv', 'dataset.rds', 'report.json']
        environment.update({'AUTONOMICS_OUTPUT' + str(index): '/work/' + name for index, name in enumerate(names)})
        environment.update(changes or {})
        protected = fixture(directory) if fixture else []
        before = {str(filename): filename.read_bytes() for filename in protected}
        command = [os.environ.get('AUTONOMICS_PODMAN_PROGRAM', 'podman'), *json.loads(os.environ.get('DESEQ2_BOUNDARY_BACKEND_JSON', '[]')), 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=3g',
            '--userns=keep-id', '--user', f'{os.getuid()}:{os.getgid()}', '--mount', f'type=bind,src={directory},dst=/work',
            '--entrypoint', '/opt/autonomics/Rscript-vanilla' if self.baked else 'Rscript']
        if not self.baked:
            command += ['--mount', f'type=bind,src={self.script},dst=/method.R,ro=true']
        for name, value in environment.items():
            command += ['--env', name + '=' + value]
        command += [self.image, '/opt/autonomics/deseq2_runner.R'] if self.baked else [self.image, '--vanilla', '/method.R']
        result = subprocess.run(command, capture_output=True, timeout=180)
        (directory / 'stdout.txt').write_bytes(result.stdout)
        (directory / 'stderr.txt').write_bytes(result.stderr)
        (directory / 'execution.json').write_text(json.dumps({'command': command, 'exit': result.returncode,
            'source_sha256': hashlib.sha256(self.script.read_bytes()).hexdigest(), 'diagnostic': diagnostic,
            'execution_mode': 'BAKED_IMAGE_RUNNER' if self.baked else 'SOURCE_BIND_OVERRIDE', 'G0': False}, indent=2) + '\n')
        if succeed:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertTrue(all((directory / name).stat().st_size for name in names))
            return directory
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr.decode())
        for filename in protected:
            self.assertEqual(filename.read_bytes(), before[str(filename)])
        for name in names:
            filename = directory / name
            if filename not in protected and not filename.is_symlink():
                self.assertFalse(filename.exists(), 'Rejected run published an analytical output')

    def counts(self, transform):
        def fixture(directory):
            filename = directory / 'counts.tsv'
            filename.write_text(transform(filename.read_text()))
            return []
        return fixture

    def metadata(self, transform):
        def fixture(directory):
            filename = directory / 'metadata.tsv'
            filename.write_text(transform(filename.read_text()))
            return []
        return fixture

    def token(self, value):
        def transform(text):
            rows = list(csv.reader(text.splitlines(), delimiter='\t'))
            rows[1][1] = value
            return '\n'.join('\t'.join(row) for row in rows) + '\n'
        return self.counts(transform)

    def existing(self, name):
        def fixture(directory):
            filename = directory / name
            filename.write_text('PREEXISTING\n')
            return [filename]
        return fixture

    def test_existing_results(self):
        self.check(fixture=self.existing('results.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_normalized(self):
        self.check(fixture=self.existing('normalized.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_size_factors(self):
        self.check(fixture=self.existing('size_factors.tsv'), diagnostic='existing outputs must not be overwritten')

    def test_existing_dataset(self):
        self.check(fixture=self.existing('dataset.rds'), diagnostic='existing outputs must not be overwritten')

    def test_existing_report(self):
        self.check(fixture=self.existing('report.json'), diagnostic='existing outputs must not be overwritten')

    def test_duplicate_outputs(self):
        self.check({'AUTONOMICS_OUTPUT1': '/work/results.tsv'}, diagnostic='output paths must be distinct')

    def test_input_output_alias(self):
        self.check({'AUTONOMICS_OUTPUT0': '/work/counts.tsv'}, fixture=lambda directory: [directory / 'counts.tsv'],
            diagnostic='existing outputs must not be overwritten')

    def test_missing_output(self):
        self.check({'AUTONOMICS_OUTPUT4': ''}, diagnostic='missing required environment variable: AUTONOMICS_OUTPUT4')

    def test_dangling_output(self):
        def fixture(directory):
            (directory / 'results.tsv').symlink_to('/work/missing-target')
            return []
        self.check(fixture=fixture, diagnostic='existing outputs must not be overwritten')

    def test_missing_output_parent(self):
        self.check({'AUTONOMICS_OUTPUT0': '/work/missing/results.tsv'}, diagnostic='output parent must exist')

    def test_missing_input(self):
        self.check({'AUTONOMICS_INPUT0': '/work/absent.tsv'}, diagnostic='input must be an existing regular file')

    def test_directory_input(self):
        self.check({'AUTONOMICS_INPUT0': '/work'}, diagnostic='input must be an existing regular file')

    def test_threads_two(self):
        self.check({'AUTONOMICS_DESEQ2_THREADS': '2'}, diagnostic='threads must be 1')

    def test_threads_fractional(self):
        self.check({'AUTONOMICS_DESEQ2_THREADS': '1.5'}, diagnostic='threads must be 1')

    def test_alpha_zero(self):
        self.check({'AUTONOMICS_DESEQ2_ALPHA': '0'}, diagnostic='alpha must be finite')

    def test_alpha_one(self):
        self.check({'AUTONOMICS_DESEQ2_ALPHA': '1'}, diagnostic='alpha must be finite')

    def test_alpha_nan(self):
        self.check({'AUTONOMICS_DESEQ2_ALPHA': 'NaN'}, diagnostic='alpha must be finite')

    def test_same_condition(self):
        self.check({'AUTONOMICS_DESEQ2_CONDITION_TEST': 'ctrl'}, diagnostic='condition_test and condition_reference must differ')

    def test_invalid_fit(self):
        self.check({'AUTONOMICS_DESEQ2_FIT_TYPE': 'bad'}, diagnostic='fit_type must be')

    def test_invalid_fit_policy(self):
        self.check({'AUTONOMICS_DESEQ2_FIT_POLICY': 'silently_change'}, diagnostic='fit_policy must be exact or native')

    def test_invalid_shrink(self):
        self.check({'AUTONOMICS_DESEQ2_LFC_SHRINK': 'bad'}, diagnostic='lfc_shrink must be')

    def test_duplicate_covariates(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age,age'}, diagnostic='covariates cannot contain duplicates')

    def test_empty_covariate_entry(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age,'}, diagnostic='covariates must not contain empty entries')

    def test_reserved_covariate(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'sample_id'}, diagnostic='sample_id and condition cannot')

    def test_invalid_covariate_name(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': '.1'},
            fixture=self.metadata(lambda text: text.replace('age', '.1')), diagnostic='covariate names must be simple R identifiers')

    def test_missing_covariate(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'absent'}, diagnostic='missing covariate columns')

    def test_covariate_inf(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age'},
            fixture=self.metadata(lambda text: text.replace('\t20\n', '\tInf\n', 1)), diagnostic='must be finite')

    def test_covariate_nan(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age'},
            fixture=self.metadata(lambda text: text.replace('\t20\n', '\tNaN\n', 1)), diagnostic='must be finite')

    def test_covariate_missing(self):
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age'},
            fixture=self.metadata(lambda text: text.replace('\t20\n', '\tNA\n', 1)), diagnostic='cannot contain missing values')

    def test_fraction(self):
        self.check(fixture=self.token('1.5'), diagnostic='finite nonnegative integers within R integer range')

    def test_rounded_fraction(self):
        self.check(fixture=self.token('20.0000000000000001'), diagnostic='finite nonnegative integers within R integer range')

    def test_integer_overflow(self):
        self.check(fixture=self.token('2147483648'), diagnostic='finite nonnegative integers within R integer range')

    def test_negative(self):
        self.check(fixture=self.token('-1'), diagnostic='finite nonnegative integers within R integer range')

    def test_counts_nan(self):
        self.check(fixture=self.token('NaN'), diagnostic='finite nonnegative integers within R integer range')

    def test_counts_inf(self):
        self.check(fixture=self.token('Inf'), diagnostic='finite nonnegative integers within R integer range')

    def test_counts_missing(self):
        self.check(fixture=self.token('NA'), diagnostic='finite nonnegative integers within R integer range')

    def test_counts_underflow(self):
        self.check(fixture=self.token('1e-1000'), diagnostic='finite nonnegative integers within R integer range')

    def test_ragged_rows(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\ngene1\textra\t')),
            diagnostic='input rows must match the header width')

    def test_empty_header(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ts1\t', '\t\t', 1)), diagnostic='input headers must be nonempty and unique')

    def test_duplicate_header(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ts2\t', '\ts1\t', 1)), diagnostic='input headers must be nonempty and unique')

    def test_duplicate_gene(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene2\t', '\ngene1\t')), diagnostic='gene_id values must be unique')

    def test_empty_gene(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\n\t')), diagnostic='gene_id cannot be empty')

    def test_nul(self):
        def fixture(directory):
            filename = directory / 'counts.tsv'
            filename.write_bytes(filename.read_bytes().replace(b'gene1\t', b'gene1\x00bad\t'))
            return []
        self.check(fixture=fixture, diagnostic='input must not contain embedded NUL bytes')

    def test_control_character(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\ngene1\x07\t')),
            diagnostic='input fields must not contain control characters')

    def test_sample_axis_mismatch(self):
        self.check(fixture=self.metadata(lambda text: text.replace('\ns1\t', '\nother\t')), diagnostic='sample sets must match exactly')

    def test_duplicate_sample(self):
        self.check(fixture=self.metadata(lambda text: text.replace('\ns2\t', '\ns1\t')), diagnostic='sample_id values must be unique')

    def test_missing_condition(self):
        self.check(fixture=self.metadata(lambda text: text.replace('\tcondition\t', '\tother\t')),
            diagnostic='sample metadata requires a condition column')

    def test_unknown_condition(self):
        self.check(fixture=self.metadata(lambda text: text.replace('\tctrl\t', '\tother\t', 1)), diagnostic='condition must contain exactly')

    def test_missing_condition_value(self):
        self.check(fixture=self.metadata(lambda text: text.replace('\tctrl\t', '\tNA\t', 1)), diagnostic='condition cannot contain missing values')

    def test_singular_design(self):
        def fixture(directory):
            filename = directory / 'metadata.tsv'
            rows = list(csv.reader(filename.read_text().splitlines(), delimiter='\t'))
            for row in rows[1:]:
                row[2] = '0' if row[1] == 'ctrl' else '1'
            filename.write_text('\n'.join('\t'.join(row) for row in rows) + '\n')
            return []
        self.check({'AUTONOMICS_DESEQ2_COVARIATES': 'age'}, fixture=fixture, diagnostic='be full rank and have positive residual')

    def test_zero_residual_df(self):
        def fixture(directory):
            counts = directory / 'counts.tsv'
            rows = list(csv.reader(counts.read_text().splitlines(), delimiter='\t'))
            counts.write_text('\n'.join('\t'.join([row[0], row[1], row[7]]) for row in rows) + '\n')
            (directory / 'metadata.tsv').write_text('sample_id\tcondition\ns1\tctrl\ns7\tcase\n')
            return []
        self.check(fixture=fixture, diagnostic='positive residual degrees of freedom')

    def test_zero_library(self):
        def fixture(directory):
            filename = directory / 'counts.tsv'
            rows = list(csv.reader(filename.read_text().splitlines(), delimiter='\t'))
            for row in rows[1:]:
                row[1] = '0'
            filename.write_text('\n'.join('\t'.join(row) for row in rows) + '\n')
            return []
        self.check(fixture=fixture, diagnostic='positive total counts')

    def test_literal_gene_axes(self):
        directory = self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\n00001\t').replace('\ngene2\t', '\nNA\t')),
            succeed=True)
        with (directory / 'results.tsv').open(newline='') as handle:
            rows = list(csv.reader(handle, delimiter='\t', strict=True))
        self.assertEqual(rows[1][0], '00001')
        self.assertEqual(rows[2][0], 'NA')
        self.assertEqual(json.loads((directory / 'report.json').read_text())['analysis']['node'], 'deseq2_de')

    def test_quoted_gene_and_sample_axes(self):
        def fixture(directory):
            replacements = {'gene1': chr(34) + 'leading', 'gene2': "O'Gene", 's1': 's' + chr(34) + 'middle', 's2': '0001'}
            for name in ['counts.tsv', 'metadata.tsv']:
                filename = directory / name
                with filename.open(newline='') as handle:
                    rows = [[replacements.get(value, value) for value in row] for row in csv.reader(handle, delimiter='\t')]
                with filename.open('w', newline='') as handle:
                    csv.writer(handle, delimiter='\t', lineterminator='\n').writerows(rows)
            return []
        directory = self.check(fixture=fixture, succeed=True)
        with (directory / 'normalized.tsv').open(newline='') as handle:
            rows = list(csv.reader(handle, delimiter='\t', strict=True))
        self.assertEqual(rows[0][1:3], ['s' + chr(34) + 'middle', '0001'])
        self.assertEqual([row[0] for row in rows[1:3]], [chr(34) + 'leading', "O'Gene"])

    def test_unclosed_quoted_field(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\n' + chr(34) + 'gene1\t')),
            diagnostic='unclosed quote')

    def test_bare_quote_in_field(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\ngene' + chr(34) + '1\t')),
            diagnostic='bare quote')

    def test_characters_after_closing_quote(self):
        self.check(fixture=self.counts(lambda text: text.replace('\ngene1\t', '\n' + chr(34) + 'gene1' + chr(34) + 'x\t')),
            diagnostic='after a closing quote')

    def test_exact_scientific_integer(self):
        self.check(fixture=self.token('.5e1'), succeed=True)

    def test_exact_decimal_integer(self):
        self.check(fixture=self.token('20.0000000000000000'), succeed=True)

    def test_all_zero_gene_retained(self):
        directory = self.check(fixture=self.counts(lambda text: text + 'zero_gene\t' + '\t'.join(['0'] * 12) + '\n'), succeed=True)
        report = json.loads((directory / 'report.json').read_text())
        self.assertEqual(report['gene_ledger']['all_zero_gene_ids'], ['zero_gene'])
        self.assertEqual(len(report['gene_ledger']['all_gene_ids']), 201)
        self.assertIn('zero_gene', report['gene_ledger']['pvalue_unavailable_gene_ids'])
