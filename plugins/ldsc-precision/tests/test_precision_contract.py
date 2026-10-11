"""Exact metadata/missingness/identity contract; not LDSC numerical evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

spec=importlib.util.spec_from_file_location('ldsc_precision',Path(__file__).resolve().parents[1]/'scripts/precision.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def config(method='rg'):
    return {'schema_version':1,'status':'FROZEN','protocol_version':'4.3.2','module_id':'A_ARCH',
        'analysis_id':'ARCH_X_M' if method=='rg' else 'ARCH_H2_X','family_id':'A_ARCH_GLOBAL' if method=='rg' else None,
        'phenotype_ids':['X','M'] if method=='rg' else ['X'],'method':method,'source_archive_sha256':'a'*64,
        'input_origin':'SYNTHETIC_TECHNICAL_ONLY','input_sha256':{'sumstats_a':'b'*64,**({'sumstats_b':'c'*64} if method=='rg' else {}),'panel_manifest':'d'*64},
        'parameters':{'n_blocks':20,'chisq_max':None},'prevalence':[None,None] if method=='rg' else [None],
        'seed':20261012,'official_runtime':{'EXPLICIT_TEST_RUNTIME_NOT_A_METHOD_APPROVAL':True},'pvalue_policy':p.ROLE}

class PrecisionContractTests(unittest.TestCase):
    def test_exact_config_and_no_h2_family(self):
        self.assertEqual(p.check_config(config(),'rg'),['sumstats_a','sumstats_b','panel_manifest'])
        self.assertEqual(p.check_config(config('h2'),'h2'),['sumstats_a','panel_manifest'])
        v=config('h2');v['family_id']='A_ARCH_GLOBAL'
        with self.assertRaises(ValueError):p.check_config(v,'h2')

    def test_unknown_extra_missing_duplicate_and_nonfinite_configuration_refused(self):
        v=config()
        for action in ['extra','missing','stale','bool_blocks','single_prevalence','negative_cutoff','inferred_origin']:
            with self.subTest(action=action):
                x=copy.deepcopy(v)
                if action=='extra':x['grant_science']=True
                elif action=='missing':x.pop('source_archive_sha256')
                elif action=='stale':x['protocol_version']='4.2.1'
                elif action=='bool_blocks':x['parameters']['n_blocks']=True
                elif action=='single_prevalence':x['prevalence']=[None,{'sample':0.2,'population':0.1}]
                elif action=='negative_cutoff':x['parameters']['chisq_max']=-1
                else:x['input_origin']='UNSEEN_BY_DEFAULT'
                with self.assertRaises(ValueError):p.check_config(x,'rg')
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'bad.json'
            for raw in [b'{"x":1,"x":2}',b'{"x":NaN}']:
                file.write_bytes(raw)
                with self.assertRaises(ValueError):p.read_json(file)

    def test_unrounded_official_p_and_raw_returned_values_retained(self):
        rg=types.SimpleNamespace(rg_ratio=0.23456789123456789,rg_se=0.08123456789123456,
            z=2.887654321098765,p=0.003883492874891234,_negative_hsq=False,
            hsq1=types.SimpleNamespace(tot=0.2),hsq2=types.SimpleNamespace(tot=0.3))
        actual=p.numeric_result([rg],'rg')
        self.assertEqual(actual['raw_p'],rg.p);self.assertEqual(actual['values']['rg'],rg.rg_ratio)
        self.assertEqual(actual['status'],'ESTIMATED');self.assertNotEqual(actual['raw_p'],float(format(rg.p,'.4g')))

    def test_official_default_out_of_bounds_retains_object_p_but_not_family_p(self):
        rg=types.SimpleNamespace(rg_ratio=1.20000000001,rg_se=0.05,z=24.0,p=1e-50,_negative_hsq=False,
            hsq1=types.SimpleNamespace(tot=0.2),hsq2=types.SimpleNamespace(tot=0.3))
        r=p.numeric_result([rg],'rg');self.assertEqual(r['status'],'NOT_ESTIMABLE');self.assertIsNone(r['raw_p'])
        self.assertEqual(r['values']['official_p'],1e-50);self.assertEqual(r['reason'],'OFFICIAL_DEFAULT_RG_OUT_OF_BOUNDS')
        rg.rg_ratio=1.2;self.assertEqual(p.numeric_result([rg],'rg')['status'],'ESTIMATED')

    def test_nonpositive_h2_and_nonfinite_se_are_missing_not_zero_p(self):
        rg=types.SimpleNamespace(rg_ratio=0.5,rg_se=0.1,z=5.,p=1e-7,_negative_hsq=True,
            hsq1=types.SimpleNamespace(tot=-0.01),hsq2=types.SimpleNamespace(tot=0.3))
        self.assertIsNone(p.numeric_result([rg],'rg')['raw_p'])
        rg.hsq1.tot=0.1;rg._negative_hsq=False;rg.rg_se=float('nan')
        r=p.numeric_result([rg],'rg');self.assertEqual(r['status'],'NOT_ESTIMABLE');self.assertIsNone(r['raw_p'])

    def test_swallowed_method_failure_and_invalid_p_refused(self):
        for r in [None,[],[None],[None,None]]:
            with self.subTest(r=r),self.assertRaises(ValueError):p.numeric_result(r,'rg')
        rg=types.SimpleNamespace(rg_ratio=0.2,rg_se=0.1,z=2,p=1.01,_negative_hsq=False,
            hsq1=types.SimpleNamespace(tot=0.2),hsq2=types.SimpleNamespace(tot=0.3))
        with self.assertRaises(ValueError):p.numeric_result([rg],'rg')

    def test_negative_h2_diagnostic_retained_without_invented_p(self):
        x=types.SimpleNamespace(tot=-0.00012345678912345678,tot_se=0.03)
        r=p.numeric_result(x,'h2');self.assertEqual(r['values']['h2'],x.tot);self.assertIsNone(r['raw_p'])
        self.assertEqual(r['status'],'ESTIMATED')

    def test_complete_source_rows_gzip_magic_and_duplicate_snp_refused(self):
        import gzip
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'work';work.mkdir();source=root/'input-without-gzip-extension'
            raw=b'SNP\tA1\tA2\tN\tZ\nrs1\tA\tG\t10000\t1.2345678912345678\n'
            with gzip.open(source,'wb') as f:f.write(raw)
            path,receipt=p.plain_sumstats(source,work,0)
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(receipt['complete_munged_rows'],1)
            source=root/'duplicate';source.write_bytes(raw+b'rs1\tC\tT\t10000\t2\n')
            with self.assertRaisesRegex(ValueError,'unique munged'):p.plain_sumstats(source,work,1)

    def test_output_json_roundtrip_is_full_precision_no_overwrite_no_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json';v={'p':0.003883492874891234}
            p.publish_json(path,v);self.assertEqual(json.loads(path.read_bytes()),v)
            with self.assertRaises(FileExistsError):p.publish_json(path,v)
            with self.assertRaises(ValueError):p.publish_json(Path(tmp)/'bad.json',{'p':float('nan')})

if __name__=='__main__':unittest.main()
