import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import tomllib
import unittest


FAMILY = Path(__file__).resolve().parents[1]
MANIFEST = tomllib.loads((FAMILY / 'manifest.toml').read_text())
NODE = next(node for node in MANIFEST['nodes'] if node['kind'] == 'coloc_abf')
IMAGE = MANIFEST['image']['reference']


def fixture():
    columns = ['snp1','b1','v1','maf1','pv1','snp2','b2','v2','maf2','pv2']
    records = []
    for index in range(8):
        beta1 = [0.02,-0.03,0.09,0.66,0.13,-0.09,0.04,0.01][index]
        beta2 = [0.04,-0.05,0.12,0.58,0.11,-0.06,0.01,0.03][index]
        records.append([f'rs{index+1}',repr(beta1),'0.01','0.22',repr(math.erfc(abs(beta1)/math.sqrt(0.02))),
                        f'rs{index+1}',repr(beta2),'0.014','0.27',repr(math.erfc(abs(beta2)/math.sqrt(0.028)))])
    settings = {'dataset1_type':'quant','dataset1_snp':'snp1','dataset1_beta':'b1','dataset1_varbeta':'v1',
                'dataset1_sd_y':1.1,'dataset2_type':'quant','dataset2_snp':'snp2',
                'dataset2_beta':'b2','dataset2_varbeta':'v2','dataset2_sd_y':0.9}
    return columns, records, settings


def r_vector(values, numeric=False):
    return 'c('+','.join(values if numeric else [json.dumps(value) for value in values])+')'


def reference_program(columns, records, settings):
    lines = ['.libPaths(c("/reference-library",.libPaths()))',
             'stopifnot(normalizePath(find.package("coloc"))=="/reference-library/coloc")',
             'stopifnot(as.character(packageVersion("coloc"))=="5.2.3")']
    for index in [1,2]:
        arguments = []
        for field, author_name in [('snp','snp'),('beta','beta'),('varbeta','varbeta'),('pvalues','pvalues'),('maf','MAF')]:
            column = settings.get(f'dataset{index}_{field}')
            if column:
                values = [record[columns.index(column)] for record in records]
                arguments.append(author_name+'='+r_vector(values,field!='snp'))
        arguments.append('type='+json.dumps(settings[f'dataset{index}_type']))
        for field, author_name in [('n','N'),('s','s'),('sd_y','sdY')]:
            if f'dataset{index}_{field}' in settings:
                arguments.append(author_name+'='+repr(settings[f'dataset{index}_{field}']))
        lines.append(f'dataset_{index} <- list('+','.join(arguments)+')')
    priors = ','.join(name+'='+repr(settings.get(name,default)) for name,default in [('p1',1e-4),('p2',1e-4),('p12',1e-5)])
    lines += ['reference <- coloc::coloc.abf(dataset_1,dataset_2,'+priors+')',
              'saveRDS(reference,"/case/reference.RDS")',
              'actual <- readRDS("/case/result.RDS")',
              'stopifnot(identical(reference,actual))',
              'cat("Entire untouched author result identical: summary, every SNP row/intermediate column, priors, classes and attributes\\n")']
    return '\n'.join(lines)+'\n'


class AbfContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = os.environ.get('ABF_TEST_EVIDENCE')
        library = os.environ.get('ABF_REFERENCE_LIBRARY')
        if not evidence or not library or not (Path(library)/'coloc/DESCRIPTION').is_file():
            raise RuntimeError('Independent author library and new evidence directory are required; no skip')
        cls.evidence = Path(evidence)
        cls.library = Path(library)
        cls.evidence.mkdir(exist_ok=False)

    def run_case(self, change=None, refusal=None, overwrite=False, alias=False):
        columns, records, settings = fixture()
        if change:
            change(columns,records,settings)
        directory = self.evidence / self._testMethodName
        directory.mkdir()
        with (directory/'input.tsv').open('w') as handle:
            writer = csv.writer(handle,delimiter='\t',quoting=csv.QUOTE_NONE,lineterminator='\n')
            writer.writerow(columns)
            writer.writerows(records)
        (directory/'settings.json').write_text(json.dumps(settings,indent=2)+'\n')
        if overwrite:
            (directory/'result.RDS').write_bytes(b'PREEXISTING_RESULT_MUST_NOT_CHANGE')
        environment = {'AUTONOMICS_INPUT0':'/case/input.tsv','AUTONOMICS_OUTPUT0':'/case/result.RDS',
                       'AUTONOMICS_OUTPUT1':'/case/result.RDS' if alias else '/case/result.log'}
        for name, definition in NODE['params'].items():
            value = settings.get(name,definition.get('default',''))
            environment['COLOC_'+name.upper()] = str(value)
        script = Path(os.environ.get('ABF_SCRIPT_OVERRIDE',str(FAMILY/'scripts/abf.R')))
        executed_script = directory / 'executed-wrapper.R'
        executed_script.write_bytes(script.read_bytes())
        command = ['podman','run','--rm','--pull=never','--network=none','--cpus=1','--memory=2g',
                   '--entrypoint','Rscript','--mount',f'type=bind,src={directory},dst=/case',
                   '--mount',f'type=bind,src={executed_script},dst=/wrapper.R,ro=true']
        for name,value in environment.items():
            command += ['--env',name+'='+value]
        command += [IMAGE,'/wrapper.R']
        started = time.monotonic()
        result = subprocess.run(command,capture_output=True,timeout=60)
        (directory/'wrapper.stdout.txt').write_bytes(result.stdout)
        (directory/'wrapper.stderr.txt').write_bytes(result.stderr)
        (directory/'wrapper.execution.json').write_text(json.dumps({'command':command,'exit':result.returncode,
            'seconds':time.monotonic()-started,'script_sha256':hashlib.sha256(executed_script.read_bytes()).hexdigest(),
            'manifest_sha256':hashlib.sha256((FAMILY/'manifest.toml').read_bytes()).hexdigest(),'G0':False},indent=2)+'\n')
        if refusal is not None:
            self.assertNotEqual(result.returncode,0)
            self.assertIn(refusal,result.stderr.decode()+result.stdout.decode())
            if overwrite:
                self.assertEqual((directory/'result.RDS').read_bytes(),b'PREEXISTING_RESULT_MUST_NOT_CHANGE')
            else:
                self.assertFalse((directory/'result.RDS').exists())
            return
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertGreater((directory/'result.log').stat().st_size,0)
        (directory/'reference.R').write_text(reference_program(columns,records,settings))
        reference_command = ['podman','run','--rm','--pull=never','--network=none','--cpus=1','--memory=2g',
                             '--entrypoint','Rscript','--mount',f'type=bind,src={directory},dst=/case',
                             '--mount',f'type=bind,src={self.library},dst=/reference-library,ro=true',
                             IMAGE,'/case/reference.R']
        comparison = subprocess.run(reference_command,capture_output=True,timeout=60)
        (directory/'reference.stdout.txt').write_bytes(comparison.stdout)
        (directory/'reference.stderr.txt').write_bytes(comparison.stderr)
        (directory/'reference.execution.json').write_text(json.dumps({'command':reference_command,
            'exit':comparison.returncode,'full_RDS_comparison':'identical','G0':False},indent=2)+'\n')
        self.assertEqual(comparison.returncode,0,comparison.stderr.decode())

    def test_quantitative_default(self):
        self.run_case()

    def test_case_control_beta_without_case_fraction(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_type='cc',dataset2_type='cc'))

    def test_mixed_trait_types(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset2_type='cc',dataset2_s=0.31))

    def test_estimated_sdY(self):
        def change(columns,records,settings):
            for index in [1,2]:
                del settings[f'dataset{index}_sd_y']
                settings[f'dataset{index}_maf'] = f'maf{index}'
                settings[f'dataset{index}_n'] = 12000
        self.run_case(change)

    def test_pvalues_quantitative(self):
        self.run_case(self.pvalue_settings)

    def test_pvalues_case_control(self):
        def change(columns,records,settings):
            self.pvalue_settings(columns,records,settings)
            settings.update(dataset1_type='cc',dataset2_type='cc',dataset1_s=0.2,dataset2_s=0.3)
        self.run_case(change)

    def test_beta_pvalue_mixed_paths(self):
        def change(columns,records,settings):
            del settings['dataset2_beta'],settings['dataset2_varbeta']
            settings.update(dataset2_pvalues='pv2',dataset2_maf='maf2',dataset2_n=11000)
        self.run_case(change)

    def test_leading_zero_ids(self):
        def change(columns,records,settings):
            for index,record in enumerate(records):
                record[0] = record[5] = f'{index+1:04d}'
        self.run_case(change)

    def test_literal_NA_id(self):
        def change(columns,records,settings):
            records[0][0] = records[0][5] = 'NA'
        self.run_case(change)

    def test_reordered_second_trait(self):
        def change(columns,records,settings):
            second = [record[5:] for record in records][::-1]
            for record,values in zip(records,second):
                record[5:] = values
        self.run_case(change)

    def test_author_partial_overlap(self):
        def change(columns,records,settings):
            records[0][5] = 'only_trait2'
        self.run_case(change)

    def test_prior_overrides(self):
        self.run_case(lambda columns,records,settings: settings.update(p1=2e-4,p2=3e-4,p12=2e-6))

    def test_zero_association_prior(self):
        self.run_case(lambda columns,records,settings: settings.update(p1=0))

    def test_author_prior_adjustment(self):
        self.run_case(lambda columns,records,settings: settings.update(p1=0.5,p2=0.5,p12=0.25))

    def test_no_association(self):
        def change(columns,records,settings):
            for record in records:
                record[1] = record[6] = '0'
        self.run_case(change)

    def test_duplicate_header(self):
        self.run_case(lambda columns,records,settings: columns.__setitem__(2,'b1'),refusal='Duplicate TSV headers')

    def test_duplicate_snp(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(0,records[1][0]),refusal='duplicated snps')

    def test_missing_column(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_beta='absent'),refusal='Missing mapped column')

    def test_empty_snp(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(0,''),refusal='Invalid SNP identifiers')

    def test_whitespace_snp(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(0,' rs1'),refusal='Invalid SNP identifiers')

    def test_infinite_beta(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(1,'Inf'),refusal='finite numbers')

    def test_zero_variance(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(2,'0'),refusal='varbeta must be positive')

    def test_invalid_numeric_token(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(1,'0.2oops'),refusal='finite numbers')

    def test_negative_sdY(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_sd_y=-1),refusal='sdY must be positive')

    def test_zero_sample_size(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_n=0),refusal='N must be positive')

    def test_invalid_case_fraction(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_type='cc',dataset1_s=1),refusal='s must be between')

    def test_invalid_maf(self):
        def change(columns,records,settings):
            settings['dataset1_maf'] = 'maf1'
            records[0][3] = '1'
        self.run_case(change,refusal='MAF must be strictly')

    def test_pvalue_greater_than_one(self):
        def change(columns,records,settings):
            self.pvalue_settings(columns,records,settings)
            records[0][4] = '1.1'
        self.run_case(change,refusal='pvalues must be in')

    def test_missing_quant_scale(self):
        self.run_case(lambda columns,records,settings: settings.pop('dataset1_sd_y'),refusal='must give sdY')

    def test_conflicting_effect_paths(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_pvalues='pv1'),refusal='exactly one of')

    def test_negative_prior(self):
        self.run_case(lambda columns,records,settings: settings.update(p12=-1e-5),refusal='Priors must be finite')

    def test_no_overwrite(self):
        self.run_case(refusal='Existing output',overwrite=True)

    def test_output_alias(self):
        self.run_case(refusal='Output paths must be distinct',alias=True)

    @staticmethod
    def pvalue_settings(columns,records,settings):
        for index in [1,2]:
            del settings[f'dataset{index}_beta'],settings[f'dataset{index}_varbeta']
            settings[f'dataset{index}_pvalues'] = f'pv{index}'
            settings[f'dataset{index}_maf'] = f'maf{index}'
            settings[f'dataset{index}_n'] = 12000


if __name__ == '__main__':
    unittest.main()
