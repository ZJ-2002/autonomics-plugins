import csv
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE = os.environ.get('MVMR_TEST_IMAGE', 'ghcr.io/zj-2002/mvmr@sha256:b7a098030b3380f96de8c9fde5017a00b870e59d8553090cf97b6b96919be6ea')


def r_array(values):
    return 'c(' + ','.join(json.dumps(value, ensure_ascii=False) for value in values) + ')'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = pathlib.Path(self.temporary.name)
        with (ROOT / 'fixtures/rawdat_mvmr.csv').open(newline='') as source:
            reader = csv.DictReader(source)
            self.header = reader.fieldnames
            self.rows = list(reader)
        self.values = {
            'MVMR_BETA_YG': 'SBP_beta', 'MVMR_SEBETA_YG': 'SBP_se',
            'MVMR_BETA_XG': 'LDL_beta HDL_beta', 'MVMR_SEBETA_XG': 'LDL_se HDL_se',
            'MVMR_BETA_XG_R': r_array(['LDL_beta', 'HDL_beta']),
            'MVMR_SEBETA_XG_R': r_array(['LDL_se', 'HDL_se']),
            'MVMR_GENCOV_COLUMNS_R': 'c()', 'MVMR_LABEL_COLUMN': 'SNP',
            'MVMR_STRENGTH': 'true', 'MVMR_STRHET': 'true',
            'MVMR_PLEIOTROPY': 'true', 'MVMR_QHET': 'false',
            'MVMR_PCOR': '1,0.3;0.3,1',
        }

    def tearDown(self):
        if destination := os.environ.get('MVMR_TEST_EVIDENCE'):
            target = pathlib.Path(destination) / self.id().rsplit('.', 1)[1]
            target.mkdir(parents=True, exist_ok=False)
            for filename in self.directory.iterdir():
                if filename.is_file():
                    (target / filename.name).write_bytes(filename.read_bytes())
        self.temporary.cleanup()

    def run_node(self, raw=None):
        if raw is None:
            with (self.directory / 'input.tsv').open('w', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=self.header, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, quotechar=None)
                writer.writeheader()
                writer.writerows(self.rows)
        else:
            (self.directory / 'input.tsv').write_text(raw)
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=2g',
                   '-v', str(self.directory) + ':/work:Z', '-v', str(ROOT / 'scripts') + ':/scripts:ro,Z']
        for key, value in self.values.items():
            command.extend(['-e', key + '=' + value])
        for key, value in {'AUTONOMICS_INPUT0': '/work/input.tsv', 'AUTONOMICS_OUTPUT0': '/work/result.RDS',
                           'AUTONOMICS_OUTPUT1': '/work/result.log'}.items():
            command.extend(['-e', key + '=' + value])
        command.extend(['--entrypoint', 'Rscript', IMAGE, '/scripts/mvmr.R'])
        completed = subprocess.run(command, capture_output=True, timeout=90)
        (self.directory / 'stdout.txt').write_bytes(completed.stdout)
        (self.directory / 'stderr.txt').write_bytes(completed.stderr)
        (self.directory / 'execution.json').write_text(json.dumps({'command': command, 'returncode': completed.returncode}, indent=2))
        return completed

    def rejected(self, raw=None):
        completed = self.run_node(raw)
        self.assertNotEqual(completed.returncode, 0, completed.stdout.decode())
        self.assertFalse((self.directory / 'result.RDS').exists())
        self.assertTrue((self.directory / 'result.log').is_file(), completed.stderr.decode())
        self.assertIn('ERROR:', (self.directory / 'result.log').read_text())

    def test_official_two_exposures(self):
        completed = self.run_node()
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertGreater((self.directory / 'result.RDS').stat().st_size, 0)
        self.assertGreater((self.directory / 'result.log').stat().st_size, 0)

    def test_zero_covariance_author_default(self):
        self.values['MVMR_PCOR'] = ''
        completed = self.run_node()
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())

    def test_nonfinite_effect(self):
        self.rows[0]['LDL_beta'] = 'NaN'
        self.rejected()

    def test_nonfinite_official_results_fail_closed(self):
        for row in self.rows:
            row['SBP_beta'] = str(float(row['SBP_beta']) * 1e300)
        self.rejected()

    def test_zero_standard_error(self):
        self.rows[0]['LDL_se'] = '0'
        self.rejected()

    def test_negative_standard_error(self):
        self.rows[0]['SBP_se'] = '-0.01'
        self.rejected()

    def test_duplicate_snp(self):
        self.rows[1]['SNP'] = self.rows[0]['SNP']
        self.rejected()

    def test_empty_snp(self):
        self.rows[0]['SNP'] = ''
        self.rejected()

    def test_duplicate_header(self):
        self.rejected('SNP\tLDL_beta\tLDL_beta\nrs1\t1\t2\n')

    def test_ragged_input(self):
        self.rejected('SNP\tLDL_beta\tHDL_beta\nrs1\t1\t2\t3\n')

    def test_duplicate_exposure_selection(self):
        self.values['MVMR_BETA_XG'] = 'LDL_beta LDL_beta'
        self.values['MVMR_BETA_XG_R'] = r_array(['LDL_beta', 'LDL_beta'])
        self.rejected()

    def test_selected_column_missing(self):
        self.values['MVMR_BETA_YG'] = 'unknown'
        self.rejected()

    def test_invalid_boolean(self):
        self.values['MVMR_STRENGTH'] = 'anything'
        self.rejected()

    def test_pcor_dimension_must_match_exposures(self):
        self.values['MVMR_PCOR'] = '1,0,0;0,1,0;0,0,1'
        self.rejected()

    def test_pcor_out_of_range(self):
        self.values['MVMR_PCOR'] = '1,1.1;1.1,1'
        self.rejected()

    def test_pcor_asymmetric(self):
        self.values['MVMR_PCOR'] = '1,0.3;0.3000002,1'
        self.rejected()

    def test_pcor_indefinite(self):
        self.values['MVMR_BETA_XG'] = 'LDL_beta HDL_beta Trg_beta'
        self.values['MVMR_SEBETA_XG'] = 'LDL_se HDL_se Trg_se'
        self.values['MVMR_BETA_XG_R'] = r_array(['LDL_beta', 'HDL_beta', 'Trg_beta'])
        self.values['MVMR_SEBETA_XG_R'] = r_array(['LDL_se', 'HDL_se', 'Trg_se'])
        self.values['MVMR_PCOR'] = '1,0.9,0.9;0.9,1,-0.9;0.9,-0.9,1'
        self.rejected()

    def covariance(self):
        self.values['MVMR_PCOR'] = ''
        columns = ['cov11', 'cov12', 'cov21', 'cov22']
        self.values['MVMR_GENCOV_COLUMNS_R'] = r_array(columns)
        self.header += columns
        for row in self.rows:
            first, second = float(row['LDL_se']), float(row['HDL_se'])
            row.update({'cov11': str(first ** 2), 'cov12': str(0.3 * first * second),
                        'cov21': str(0.3 * first * second), 'cov22': str(second ** 2)})

    def test_covariance_sources_mutually_exclusive(self):
        self.covariance()
        self.values['MVMR_PCOR'] = '1,0.3;0.3,1'
        self.rejected()

    def test_covariance_full_matrix_columns_required(self):
        self.covariance()
        self.values['MVMR_GENCOV_COLUMNS_R'] = r_array(['cov11', 'cov12', 'cov22'])
        self.rejected()

    def test_covariance_asymmetric(self):
        self.covariance()
        self.rows[0]['cov21'] = '0'
        self.rejected()

    def test_covariance_diagonal_consistent_with_standard_errors(self):
        self.covariance()
        self.rows[0]['cov11'] = str(float(self.rows[0]['cov11']) * 2)
        self.rejected()

    def test_covariance_indefinite(self):
        self.covariance()
        self.rows[0]['cov12'] = self.rows[0]['cov21'] = '1'
        self.rejected()

    def test_covariance_nonfinite(self):
        self.covariance()
        self.rows[0]['cov11'] = 'Inf'
        self.rejected()

    def test_rank_deficient_exposures(self):
        for row in self.rows:
            row['HDL_beta'] = row['LDL_beta']
        self.rejected()

    def test_no_residual_degrees_of_freedom(self):
        self.rows = self.rows[:2]
        self.rejected()

    def test_existing_result_must_not_be_overwritten(self):
        (self.directory / 'result.RDS').write_bytes(b'previous result')
        completed = self.run_node()
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual((self.directory / 'result.RDS').read_bytes(), b'previous result')

    def test_existing_log_must_not_be_overwritten(self):
        (self.directory / 'result.log').write_bytes(b'previous log')
        completed = self.run_node()
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual((self.directory / 'result.log').read_bytes(), b'previous log')

    def test_expression_in_array_is_not_evaluated(self):
        self.values['MVMR_BETA_XG_R'] = 'c(system("touch /work/injected"))'
        self.rejected()
        self.assertFalse((self.directory / 'injected').exists())

    def test_multiple_array_expressions_are_rejected(self):
        self.values['MVMR_BETA_XG_R'] = 'c("LDL_beta","HDL_beta"); system("touch /work/injected")'
        self.rejected()
        self.assertFalse((self.directory / 'injected').exists())

    def test_no_lossy_legacy_array_fallback(self):
        self.values['MVMR_BETA_XG_R'] = ''
        self.rejected()

    def test_named_array_entries_are_rejected(self):
        self.values['MVMR_BETA_XG_R'] = 'c(first="LDL_beta",second="HDL_beta")'
        self.rejected()

    def test_qhet_requires_pcor_not_arbitrary_covariance(self):
        self.covariance()
        self.values['MVMR_QHET'] = 'true'
        self.rejected()

    def test_pcor_trailing_separator_is_rejected(self):
        self.values['MVMR_PCOR'] += ';'
        self.rejected()

    def test_non_syntactic_column_names(self):
        rename = {'LDL_beta': 'LDL beta', 'HDL_beta': 'β "HDL" \\beta'}
        self.header = [rename.get(column, column) for column in self.header]
        self.rows = [{rename.get(column, column): value for column, value in row.items()} for row in self.rows]
        self.values['MVMR_BETA_XG_R'] = r_array(list(rename.values()))
        completed = self.run_node()
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())

    def test_provided_per_snp_covariance(self):
        self.covariance()
        completed = self.run_node()
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())


if __name__ == '__main__':
    unittest.main()
