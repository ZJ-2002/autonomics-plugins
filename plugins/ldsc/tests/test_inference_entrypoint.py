"""Pinned CLI logging/input contract; no h2/rg numerical acceptance."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class InferenceEntrypointTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        bindir=self.root/'bin';bindir.mkdir()
        stub=bindir/'python';stub.write_text('''#!/usr/bin/python3
import os,json,sys
from pathlib import Path
assert sys.argv[1]=='/opt/cachexia-official-ldsc/ldsc.py'
args=sys.argv[2:];Path(os.environ['CAPTURE']).write_text(json.dumps(args))
prefix=args[args.index('--out')+1]
Path(prefix+'.log').write_text('OFFICIAL_EXACTLY_ONCE\\n'+('ERROR computing rg for phenotype 2/2\\n' if os.environ.get('SWALLOWED')=='1' else ''))
if os.environ.get('FAIL')=='1':print('PROCESS_FAILURE');sys.exit(9)
''');stub.chmod(0o700)
        self.first=self.root/'first source.tsv';self.first.write_bytes(b'FIRST COMPLETE SOURCE')
        self.second=self.root/'second source.tsv';self.second.write_bytes(b'SECOND COMPLETE SOURCE')
        self.env={'PATH':str(bindir)+':/usr/bin:/bin','HOME':str(self.root),'CAPTURE':str(self.root/'argv.json'),
            'AUTONOMICS_WORKDIR':str(self.root),'AUTONOMICS_INPUT0':str(self.first),'AUTONOMICS_INPUT1':str(self.second),
            'AUTONOMICS_OUTPUT0':str(self.root/'published.log'),'LDSC_N_BLOCKS':'200','LDSC_RG_N_BLOCKS':'200'}

    def run_method(self,method,extra=None):
        return subprocess.run(['/bin/sh',str(ROOT/'scripts'/f'{method}.sh')],env={**self.env,**(extra or {})},capture_output=True,text=True,timeout=10)

    def test_h2_actual_log_and_literal_optional_arguments(self):
        value='literal; $(touch '+str(self.root/'INJECTED')+')'
        result=self.run_method('h2',{'LDSC_CHISQ_MAX':value,'LDSC_INTERCEPT_H2':'1.2'})
        self.assertEqual(result.returncode,0,result.stderr);argv=json.loads((self.root/'argv.json').read_text())
        self.assertEqual(argv[argv.index('--h2')+1],str(self.first));self.assertEqual(argv[argv.index('--chisq-max')+1],value)
        self.assertEqual(argv[argv.index('--intercept-h2')+1],'1.2');self.assertFalse((self.root/'INJECTED').exists())
        self.assertEqual((self.root/'published.log').read_text(),'OFFICIAL_EXACTLY_ONCE\n')

    def test_rg_preserves_both_original_inputs_and_single_official_log(self):
        result=self.run_method('rg');self.assertEqual(result.returncode,0,result.stderr)
        argv=json.loads((self.root/'argv.json').read_text());self.assertEqual(argv[argv.index('--rg')+1],str(self.first)+','+str(self.second))
        self.assertEqual((self.root/'published.log').read_text(),'OFFICIAL_EXACTLY_ONCE\n')

    def test_real_declared_ports_never_alias_the_official_internal_log(self):
        import tomllib
        manifest=tomllib.loads((ROOT/'manifest.toml').read_text())
        for method in ['h2','rg']:
            with self.subTest(method=method):
                node=next(row for row in manifest['nodes'] if row['kind']=='ldsc_'+method)
                output=self.root/node['ports']['outputs'][0]['path']
                result=self.run_method(method,{'AUTONOMICS_OUTPUT0':str(output)})
                self.assertEqual(result.returncode,0,result.stderr)
                argv=json.loads((self.root/'argv.json').read_text())
                internal=Path(argv[argv.index('--out')+1]+'.log')
                self.assertNotEqual(internal,output)
                self.assertEqual(output.read_text(),'OFFICIAL_EXACTLY_ONCE\n')
                self.assertEqual(output.read_bytes(),internal.read_bytes())

    def test_gzip_private_materialization_for_both_methods(self):
        for method in ['h2','rg']:
            with self.subTest(method=method):
                paths=[]
                for i,raw in enumerate([self.first.read_bytes(),self.second.read_bytes()]):
                    p=self.root/f'original-{i}.gz'
                    with gzip.open(p,'wb') as f:f.write(raw)
                    paths.append(str(p))
                result=self.run_method(method,{'AUTONOMICS_INPUT0':paths[0],'AUTONOMICS_INPUT1':paths[1]})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual((self.root/'.autonomics/input-0.tsv').read_bytes(),self.first.read_bytes())
                if method=='rg':self.assertEqual((self.root/'.autonomics/input-1.tsv').read_bytes(),self.second.read_bytes())

    def test_swallowed_pair_failure_is_a_failed_method_with_diagnostic_log(self):
        result=self.run_method('rg',{'SWALLOWED':'1'});self.assertEqual(result.returncode,2)
        self.assertIn('Official LDSC reported',result.stderr)
        self.assertIn('ERROR computing rg for phenotype',(self.root/'published.log').read_text())

    def test_actual_nonzero_method_exit_preserves_failure_diagnostics(self):
        for method in ['h2','rg']:
            with self.subTest(method=method):
                result=self.run_method(method,{'FAIL':'1'});self.assertEqual(result.returncode,9)
                log=(self.root/'published.log').read_text();self.assertIn('PROCESS_FAILURE',log);self.assertIn('OFFICIAL_EXACTLY_ONCE',log)

    def test_missing_official_log_is_not_a_successful_empty_artifact(self):
        (self.root/'bin/python').write_text('#!/bin/sh\nexit 0\n')
        for method in ['h2','rg']:
            with self.subTest(method=method):self.assertNotEqual(self.run_method(method).returncode,0)

    def test_author_stdout_is_preserved_when_the_author_file_log_is_empty(self):
        (self.root/'bin/python').write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nargs=sys.argv[2:]\nPath(args[args.index("--out")+1]+".log").write_text("")\nprint("ACTUAL_AUTHOR_RESULT")\nprint("AUTHOR_WARNING",file=sys.stderr)\n')
        for method in ['h2','rg']:
            with self.subTest(method=method):
                result=self.run_method(method)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual((self.root/'published.log').read_text(),'ACTUAL_AUTHOR_RESULT\n')
                self.assertEqual(result.stderr,'AUTHOR_WARNING\n')

if __name__=='__main__':unittest.main()
