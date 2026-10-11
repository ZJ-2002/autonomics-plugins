import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest


FAMILY = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = os.environ.get('MRLAP_BOUNDARY_EVIDENCE')
        assets = os.environ.get('MRLAP_BOUNDARY_ASSETS')
        if not evidence or not assets or not (Path(assets)/'eur_w_ld_chr').is_dir():
            raise RuntimeError('New evidence directory and real local LD assets are required; no skip')
        cls.root = Path(evidence)
        cls.assets = Path(assets)
        cls.root.mkdir(exist_ok=False)

    def run_case(self, change, diagnostic, preexisting=None):
        directory = self.root/self._testMethodName
        directory.mkdir()
        (directory/'gwas.tsv').write_text('rsid\tchr\tpos\ta1\ta2\tbeta\tse\tN\nrs1\t1\t100\tA\tG\t0.1\t0.1\t10000\n')
        (directory/'ivs.txt').write_text('rs1\n')
        environment = {'AUTONOMICS_INPUT0':'/case/gwas.tsv','AUTONOMICS_INPUT1':'/case/gwas.tsv',
            'AUTONOMICS_INPUT2':'/case/ivs.txt','AUTONOMICS_OUTPUT0':'/case/summary.tsv',
            'AUTONOMICS_OUTPUT1':'/case/result.RDS','AUTONOMICS_OUTPUT2':'/case/result.txt',
            'AUTONOMICS_OUTPUT3':'/case/result.log','MRLAP_EXPOSURE':'Exposure','MRLAP_OUTCOME':'Outcome',
            'MRLAP_SEED':'1','MRLAP_LD_PATH':'/panels/ldsc_assets/eur_w_ld_chr',
            'MRLAP_HM3_PATH':'/panels/ldsc_assets/w_hm3.noMHC.snplist'}
        if preexisting is not None:
            (directory/preexisting).write_bytes(b'PREEXISTING_BYTES_MUST_NOT_CHANGE')
        change(directory,environment)
        original = Path(os.environ.get('MRLAP_SCRIPT_OVERRIDE',str(FAMILY/'scripts/mrlap.sh')))
        executed = directory/'executed-wrapper.R'
        executed.write_bytes(original.read_bytes())
        command = ['podman','run','--rm','--pull=never','--network=none','--cpus=1','--memory=2g',
            '--workdir','/case','--entrypoint','Rscript','--mount',f'type=bind,src={directory},dst=/case',
            '--mount',f'type=bind,src={self.assets},dst=/panels/ldsc_assets,ro=true']
        for name, value in environment.items():
            command += ['--env',name+'='+value]
        command += [IMAGE,'--vanilla','/case/executed-wrapper.R']
        result = subprocess.run(command,capture_output=True,timeout=60)
        (directory/'wrapper.stdout.txt').write_bytes(result.stdout)
        (directory/'wrapper.stderr.txt').write_bytes(result.stderr)
        (directory/'wrapper.execution.json').write_text(json.dumps({'command':command,'exit':result.returncode,
            'script_sha256':hashlib.sha256(executed.read_bytes()).hexdigest(),
            'manifest_sha256':hashlib.sha256((FAMILY/'manifest.toml').read_bytes()).hexdigest(),
            'expected_diagnostic':diagnostic,'G0':False},indent=2)+'\n')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(diagnostic,result.stdout.decode()+result.stderr.decode())
        if preexisting is not None:
            self.assertEqual((directory/preexisting).read_bytes(),b'PREEXISTING_BYTES_MUST_NOT_CHANGE')
        for name in ['summary.tsv','result.RDS','result.txt']:
            if name!=preexisting:
                self.assertFalse((directory/name).exists())

    def test_fractional_seed(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_SEED='1.5'),'seed must be an integer')

    def test_exponent_seed(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_SEED='1e0'),'seed must be an integer')

    def test_zero_seed(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_SEED='0'),'seed must be an integer')

    def test_overflow_seed(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_SEED='2147483648'),'seed must be an integer')

    def test_missing_input_port(self):
        self.run_case(lambda directory,environment: environment.update(AUTONOMICS_INPUT0=''),'All declared input/output ports')

    def test_missing_output_port(self):
        self.run_case(lambda directory,environment: environment.update(AUTONOMICS_OUTPUT1=''),'All declared input/output ports')

    def test_output_alias(self):
        self.run_case(lambda directory,environment: environment.update(AUTONOMICS_OUTPUT0='/case/result.RDS'),'Output paths must be distinct')

    def test_log_input_alias(self):
        self.run_case(lambda directory,environment: environment.update(AUTONOMICS_OUTPUT3='/case/gwas.tsv'),'Existing output must not be overwritten')

    def test_existing_log(self):
        self.run_case(lambda directory,environment: None,'Existing output must not be overwritten',preexisting='result.log')

    def test_existing_rds(self):
        self.run_case(lambda directory,environment: None,'Existing output must not be overwritten',preexisting='result.RDS')

    def test_existing_summary(self):
        self.run_case(lambda directory,environment: None,'Existing output must not be overwritten',preexisting='summary.tsv')

    def test_existing_text(self):
        self.run_case(lambda directory,environment: None,'Existing output must not be overwritten',preexisting='result.txt')

    def test_dangling_output_symlink(self):
        self.run_case(lambda directory,environment: (directory/'result.RDS').symlink_to('/case/missing-target'),
                      'Existing output must not be overwritten')

    def test_missing_input_file(self):
        self.run_case(lambda directory,environment: environment.update(AUTONOMICS_INPUT0='/case/missing.tsv'),
                      'Input files must exist')

    def test_empty_iv_list(self):
        self.run_case(lambda directory,environment: (directory/'ivs.txt').write_text(''),'instrument list is empty')

    def test_blank_iv_row(self):
        self.run_case(lambda directory,environment: (directory/'ivs.txt').write_text('rs1\n\n'),'Invalid instrument identifiers')

    def test_whitespace_iv(self):
        self.run_case(lambda directory,environment: (directory/'ivs.txt').write_text(' rs1\n'),'Invalid instrument identifiers')

    def test_duplicate_iv(self):
        self.run_case(lambda directory,environment: (directory/'ivs.txt').write_text('rs1\nrs1\n'),'Duplicate instrument identifiers')

    def test_label_newline(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_EXPOSURE='trait\nextra'),'Trait labels must not contain')

    def test_label_tab(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_OUTCOME='trait\textra'),'Trait labels must not contain')

    def test_missing_ld_directory(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_LD_PATH='/case/missing-ld'),'LD directory must exist')

    def test_missing_hm3_file(self):
        self.run_case(lambda directory,environment: environment.update(MRLAP_HM3_PATH='/case/missing-hm3'),'HM3 file must exist')


if __name__=='__main__':
    unittest.main()
