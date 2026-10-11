"""Exact official argv and real shell transport tests; no statistical acceptance."""
import ast
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MungeEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ldsc-munge-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.bin = self.work/'bin'; self.bin.mkdir()
        self.raw = self.work/'original GWAS.tsv'; self.raw.write_bytes(b'SNP\tA1\tA2\tN\tZ\tP\nrs1\tA\tG\t10000\t1\t0.31731050786291415\n')
        stub = self.bin/'munge_sumstats'
        stub.write_text('''#!/usr/bin/python3
import gzip,json,os,sys
from pathlib import Path
args=sys.argv[1:]
Path(os.environ['CAPTURE']).write_text(json.dumps(args))
if os.environ.get('FAIL')=='1': sys.exit(9)
prefix=args[args.index('--out')+1]
source=Path(args[args.index('--sumstats')+1])
with gzip.open(prefix+'.sumstats.gz','wb') as f:f.write(source.read_bytes())
Path(prefix+'.log').write_text('SINGLE_OFFICIAL_SUMMARY\\n')
print('SINGLE_OFFICIAL_SUMMARY')
''')
        stub.chmod(0o700)
        self.env = {'PATH':str(self.bin)+':/usr/bin:/bin','HOME':str(self.work),
            'AUTONOMICS_INPUT0':str(self.raw),'AUTONOMICS_WORKDIR':str(self.work),
            'AUTONOMICS_OUTPUT0':str(self.work/'published.sumstats.gz'),
            'AUTONOMICS_OUTPUT1':str(self.work/'published.log'),'CAPTURE':str(self.work/'argv.json')}

    def run_script(self, extra=None):
        return subprocess.run(['/bin/sh',str(ROOT/'scripts/munge.sh')],env={**self.env,**(extra or {})},
            capture_output=True,text=True,timeout=10)

    def argv(self): return json.loads((self.work/'argv.json').read_text())

    def test_input_required_and_summary_is_not_duplicated(self):
        result=self.run_script();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.argv(),['--sumstats',str(self.raw),'--out',str(self.work/'munged_sumstats')])
        self.assertEqual((self.work/'published.log').read_text(),'SINGLE_OFFICIAL_SUMMARY\n')
        with gzip.open(self.work/'published.sumstats.gz','rb') as f:self.assertEqual(f.read(),self.raw.read_bytes())

    def test_gzip_transport_uses_actual_input_and_creates_private_directory(self):
        compressed=self.work/'original input.gz'
        with gzip.open(compressed,'wb') as f:f.write(self.raw.read_bytes())
        result=self.run_script({'AUTONOMICS_INPUT0':str(compressed)});self.assertEqual(result.returncode,0,result.stderr)
        path=Path(self.argv()[self.argv().index('--sumstats')+1])
        self.assertEqual(path,self.work/'.autonomics/input-0.tsv');self.assertEqual(path.read_bytes(),self.raw.read_bytes())

    def test_every_manifest_environment_maps_to_exact_official_option(self):
        mapping={'SNP':'--snp','N_COL':'--N-col','N_CAS_COL':'--N-cas-col','N_CON_COL':'--N-con-col',
            'A1':'--a1','A2':'--a2','P':'--p','FRQ':'--frq','INFO':'--info','INFO_LIST':'--info-list',
            'SIGNED_SUMSTATS':'--signed-sumstats','NSTUDY':'--nstudy','INFO_MIN':'--info-min',
            'MAF_MIN':'--maf-min','N_MIN':'--n-min','NSTUDY_MIN':'--nstudy-min'}
        manifest=tomllib.loads((ROOT/'manifest.toml').read_text())
        env=next(n for n in manifest['nodes'] if n['kind']=='ldsc_munge')['command']['env']
        self.assertTrue({'LDSC_MUNGE_'+n for n in mapping}<=set(env))
        result=self.run_script({'LDSC_MUNGE_'+n:'value '+n for n in mapping});self.assertEqual(result.returncode,0,result.stderr)
        args=self.argv()
        for n,flag in mapping.items():self.assertEqual(args[args.index(flag)+1],'value '+n)
        tree=ast.parse((ROOT/'ldsc-python3/munge_sumstats.py').read_text())
        flags={a.value for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
            and node.func.attr=='add_argument' for a in node.args if isinstance(a,ast.Constant) and isinstance(a.value,str)}
        self.assertTrue(set(mapping.values())|{'--daner','--daner-n','--a1-inc','--sumstats','--out'}<=flags)
        self.assertNotIn('--a1-is-a2',flags)

    def test_values_remain_single_literal_arguments_without_shell_expansion(self):
        literal='Original Z column; $(touch '+str(self.work/'INJECTED')+') *'
        result=self.run_script({'LDSC_MUNGE_SIGNED_SUMSTATS':literal});self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.argv()[self.argv().index('--signed-sumstats')+1],literal)
        self.assertFalse((self.work/'INJECTED').exists())

    def test_presence_flags_and_explicit_false(self):
        result=self.run_script({'LDSC_MUNGE_DANER':'false','LDSC_MUNGE_DANER_N':'1','LDSC_MUNGE_A1_INC':'true'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('--daner',self.argv());self.assertIn('--daner-n',self.argv());self.assertIn('--a1-inc',self.argv())

    def test_unsupported_allele_option_and_malformed_presence_fail_before_command(self):
        for extra in [{'LDSC_MUNGE_A1_IS_A2':'1'},{'LDSC_MUNGE_A1_INC':'arbitrary'}]:
            with self.subTest(extra=extra):
                result=self.run_script(extra);self.assertEqual(result.returncode,2)
                self.assertFalse((self.work/'argv.json').exists());self.assertFalse((self.work/'published.sumstats.gz').exists())

    def test_official_failure_never_publishes_normal_result(self):
        result=self.run_script({'FAIL':'1'});self.assertEqual(result.returncode,9)
        self.assertFalse((self.work/'published.sumstats.gz').exists())

    def test_broken_gzip_refuses_without_invoking_method(self):
        invalid=self.work/'invalid.gz';invalid.write_bytes(b'not a compressed GWAS')
        result=self.run_script({'AUTONOMICS_INPUT0':str(invalid)})
        self.assertNotEqual(result.returncode,0);self.assertFalse((self.work/'argv.json').exists())

if __name__=='__main__':unittest.main()
