import gzip
import json
import os
from pathlib import Path
import subprocess
import unittest


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['PLINK2_BOUNDARY_EVIDENCE']).resolve()
        cls.root.mkdir(exist_ok=False)
        cls.panel = Path(os.environ['PLINK2_BOUNDARY_PANEL']).resolve(strict=True)
        cls.script = Path(os.environ.get('PLINK2_SCRIPT_OVERRIDE',
            str(Path(__file__).resolve().parents[1] / 'scripts/clump.sh'))).resolve(strict=True)
        cls.image = 'ghcr.io/auto-nomics/autonomics/plink2@sha256:998315bf1c34c1c7ef276e93ca6c043dd1982c027c7264325505a9a0adc6d1d2'
        if not (cls.panel / '1000G.EUR.QC.1.bed').is_file():
            raise RuntimeError('Real executable synthetic panel required; missing dependencies are not skips')

    def check(self, changes=None, fixture=None, diagnostic=None, succeed=False):
        directory = self.root / self.id().split('.')[-1]
        directory.mkdir()
        (directory / 'input.tsv').write_text('SNP\tP\nrs1003\t1e-12\nrs1002\t2e-12\n')
        environment = {'AUTONOMICS_INPUT0': '/work/input.tsv', 'AUTONOMICS_OUTPUT0': '/work/result.log',
            'AUTONOMICS_OUTPUT1': '/work/result.clumps', 'AUTONOMICS_OUTPUT2': '/work/chromosomes.tsv',
            'PLINK2_CLUMP_INPUT_FORMAT': 'twosamplemr', 'PLINK2_CLUMP_CHR': '1', 'PLINK2_CLUMP_P1': '5e-8',
            'PLINK2_CLUMP_P2': '1e-6', 'PLINK2_CLUMP_R2': '.001', 'PLINK2_CLUMP_KB': '10000'}
        environment.update(changes or {})
        protected = fixture(directory) if fixture else []
        before = {str(filename): filename.read_bytes() for filename in protected}
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=2g',
            '--mount', f'type=bind,src={directory},dst=/work',
            '--mount', f'type=bind,src={self.panel},dst=/panels/plink_ref,ro=true',
            '--mount', f'type=bind,src={self.script},dst=/script.sh,ro=true', '--entrypoint', 'sh']
        for name, value in environment.items():
            command += ['--env', name + '=' + value]
        command += [self.image, '/script.sh']
        result = subprocess.run(command, capture_output=True, timeout=60)
        (directory / 'stdout.txt').write_bytes(result.stdout)
        (directory / 'stderr.txt').write_bytes(result.stderr)
        (directory / 'execution.json').write_text(json.dumps({'command': command, 'exit': result.returncode,
            'target_diagnostic': diagnostic, 'G0': False}, indent=2) + '\n')
        if succeed:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return directory
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr.decode())
        for filename in protected:
            self.assertEqual(filename.read_bytes(), before[str(filename)])
        for name in ['result.clumps', 'chromosomes.tsv']:
            filename = directory / name
            if filename not in protected and not filename.is_symlink():
                self.assertFalse(filename.exists(), 'Rejected input published analytical table')

    def existing(self, name):
        def fixture(directory):
            filename = directory / name
            filename.write_text('PREEXISTING\n')
            return [filename]
        return fixture

    def input_text(self, text):
        def fixture(directory):
            (directory / 'input.tsv').write_text(text)
            return []
        return fixture

    def test_existing_log(self):
        self.check(fixture=self.existing('result.log'), diagnostic='Existing output must not be overwritten')

    def test_existing_clumps(self):
        self.check(fixture=self.existing('result.clumps'), diagnostic='Existing output must not be overwritten')

    def test_existing_chromosomes(self):
        self.check(fixture=self.existing('chromosomes.tsv'), diagnostic='Existing output must not be overwritten')

    def test_input_output_alias(self):
        self.check({'AUTONOMICS_OUTPUT1': '/work/input.tsv'},
            fixture=lambda directory: [directory / 'input.tsv'], diagnostic='Existing output must not be overwritten')

    def test_duplicate_output_paths(self):
        self.check({'AUTONOMICS_OUTPUT1': '/work/result.log'}, diagnostic='Output paths must be distinct')

    def test_missing_output_port(self):
        self.check({'AUTONOMICS_OUTPUT2': ''}, diagnostic='All declared input/output ports are required')

    def test_missing_input(self):
        self.check({'AUTONOMICS_INPUT0': '/work/absent.tsv'}, diagnostic='Input must be a regular file')

    def test_input_directory(self):
        self.check({'AUTONOMICS_INPUT0': '/work'}, diagnostic='Input must be a regular file')

    def test_fractional_chromosome(self):
        self.check({'PLINK2_CLUMP_CHR': '1.5'}, diagnostic='chr must be an integer in 1..22')

    def test_zero_chromosome(self):
        self.check({'PLINK2_CLUMP_CHR': '0'}, diagnostic='chr must be an integer in 1..22')

    def test_exponent_chromosome(self):
        self.check({'PLINK2_CLUMP_CHR': '1e1'}, diagnostic='chr must be an integer in 1..22')

    def test_chromosome_overflow(self):
        self.check({'PLINK2_CLUMP_CHR': '23'}, diagnostic='chr must be an integer in 1..22')

    def test_fractional_window(self):
        self.check({'PLINK2_CLUMP_KB': '1.5'}, diagnostic='clump_kb must be a positive integer')

    def test_p2_below_p1(self):
        self.check({'PLINK2_CLUMP_P2': '1e-9'}, diagnostic='clump_p2 must be >= clump_p1')

    def test_nonfinite_threshold(self):
        self.check({'PLINK2_CLUMP_P1': 'NaN'}, diagnostic='Clump thresholds must be finite numbers in 0..1')

    def test_invalid_r2(self):
        self.check({'PLINK2_CLUMP_R2': '1.1'}, diagnostic='Clump thresholds must be finite numbers in 0..1')

    def test_r2_one(self):
        self.check({'PLINK2_CLUMP_R2': '1'}, diagnostic='official 1-2^-44 boundary')

    def test_r2_official_exact_boundary(self):
        self.check({'PLINK2_CLUMP_R2': str(1 - 2 ** -44)}, diagnostic='official 1-2^-44 boundary')

    def test_r2_nearly_one(self):
        self.check({'PLINK2_CLUMP_R2': '.9999999999999999'}, diagnostic='official 1-2^-44 boundary')

    def test_unknown_layout(self):
        self.check({'PLINK2_CLUMP_INPUT_FORMAT': 'other'}, diagnostic='unsupported input_format')

    def test_duplicate_header(self):
        self.check(fixture=self.input_text('SNP\tP\tP\nrs1003\t1e-12\t2e-12\n'), diagnostic='Duplicate report header')

    def test_missing_p_column(self):
        self.check(fixture=self.input_text('SNP\tother\nrs1003\t1e-12\n'), diagnostic='Required report columns missing')

    def test_invalid_input_p(self):
        self.check(fixture=self.input_text('SNP\tP\nrs1003\tInf\n'), diagnostic='Invalid report P value')

    def test_ragged_input(self):
        self.check(fixture=self.input_text('SNP\tP\nrs1003\t1e-12\textra\n'), diagnostic='Ragged report row')

    def test_empty_input(self):
        self.check(fixture=self.input_text(''), diagnostic='Report header is required')

    def test_blank_header(self):
        self.check(fixture=self.input_text('SNP\tP\t\nrs1003\t1e-12\tNA\n'),
            diagnostic='Report header names must not be empty')

    def test_empty_identifier(self):
        self.check(fixture=self.input_text('SNP\tP\n\t1e-12\n'), diagnostic='Variant identifier is empty')

    def test_malformed_csv(self):
        self.check({'PLINK2_CLUMP_INPUT_FORMAT': 'ieu_open_gwas'},
            fixture=self.input_text('variant,pval\n"rs1003"junk,1e-12\n'), diagnostic='Malformed CSV after closing quote')

    def test_multiline_identifier(self):
        self.check({'PLINK2_CLUMP_INPUT_FORMAT': 'ieu_open_gwas'},
            fixture=self.input_text('variant,pval\n"rs1003\nother",1e-12\n'),
            diagnostic='Report fields must be single PLINK tokens')

    def test_corrupt_gzip(self):
        def fixture(directory):
            compressed = bytearray(gzip.compress(b'SNP\tP\nrs1003\t1e-12\n', mtime=0))
            compressed[-8] ^= 1
            (directory / 'input.tsv').write_bytes(compressed)
            return []
        self.check(fixture=fixture, diagnostic='Compressed report is invalid')

    def test_csv_is_normalized_without_changing_ids_or_p(self):
        directory = self.check({'PLINK2_CLUMP_INPUT_FORMAT': 'ieu_open_gwas'},
            fixture=self.input_text('variant,pval\n"rs1003",1e-12\n"rs1002",2e-12\n'), succeed=True)
        self.assertIn('rs1003', (directory / 'result.clumps').read_text())

    def test_empty_signal_is_a_header_only_table(self):
        directory = self.check(fixture=self.input_text('SNP\tP\nrs1003\t0.9\n'), succeed=True)
        lines = (directory / 'result.clumps').read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('SOURCE_CHR\t#CHROM\tPOS\tID\tP\t'))

    def test_all_autosomes_have_one_header_only(self):
        text = 'SNP\tP\n'
        for chromosome in range(1, 23):
            for line in (self.panel / f'1000G.EUR.QC.{chromosome}.bim').read_text().splitlines():
                text += line.split()[1] + '\t1e-12\n'
        directory = self.check({'PLINK2_CLUMP_CHR': ''}, fixture=self.input_text(text), succeed=True)
        lines = (directory / 'result.clumps').read_text().splitlines()
        self.assertEqual(sum('#CHROM' in line for line in lines), 1)
        self.assertEqual((directory / 'chromosomes.tsv').read_text().splitlines(),
            ['chr\t' + str(chromosome) for chromosome in range(1, 23)])


if __name__ == '__main__':
    unittest.main()
