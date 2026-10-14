import copy
import hashlib
import json
from pathlib import Path
import tomllib
import unittest
from tools import b_normalized_contract_binding as binding

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT/'research-adapters/b-bulk-normalized-contract'
def raw(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def fixture():
    contract=json.loads((ADAPTER/'runtime-contract.json').read_bytes())
    common=dict(protocol_version='4.3.2',method='LIMMA_EBAYES',expression_scale='log2_normalized',contrast_id='SYN_CONTRAST',
      resource_id='SYN_MICROARRAY',design={'numerator':'case','denominator':'control','covariates':[], 'family_min_units':3,'qr_tolerance':1e-7},
      software_lock=contract['software_lock'],method_parameters={'trend':True,'robust':True,'allowed_warning_messages':[]},
      limits={'max_expression_elements':1000,'max_input_file_bytes':1024*1024})
    request=dict(schema_version=1,**common,source_resource_id='SYN_SOURCE',accession='SYN_ACCESSION',condition_mapping={'case':'case','control':'control'},endpoint_column='SYN_WEIGHT_LOSS',result_exposure='SEEN')
    template=dict(schema_version=1,**common,status='FROZEN',source_archive_sha256=contract['source_design_sha256'],input_sha256=dict.fromkeys(['expression','genes','samples','decisions']))
    genes=b'matrix_row\tgene_id\tanalysis_id\tfamily_id\tcontrast_id\testimand_id\n1\tSYN_G1\tSYN_CONTRAST:SYN_G1\tB_TRANSCRIPTOME\tSYN_CONTRAST\tE_B_DIS\n2\tSYN_G2\tSYN_CONTRAST:SYN_G2\tB_TRANSCRIPTOME\tSYN_CONTRAST\tE_B_DIS\n'
    assay=dict(schema_version=1,scope='EXPLICIT_FROZEN_SOURCE_ASSAY_DECLARATION_NOT_QUALIFICATION',assay_type='GENE_LEVEL_MICROARRAY_RMA_LOG2',
      normalization='SOURCE_RMA_LOG2_NOT_RENORMALIZED',request_identity=binding.identity(raw(request)),gene_registry_identity=binding.identity(genes),
      feature_registry_identity={'sha256':'b'*64,'bytes':55},source_metadata_identity={'sha256':'c'*64,'bytes':66},
      contrast_id=common['contrast_id'],resource_id=common['resource_id'],accession=request['accession'])
    return request,template,genes,assay

class BindingTests(unittest.TestCase):
    def test_full_abi_exact_source_and_723_candidate_does_not_authorize(self):
        r,t,g,a=fixture(); b=binding.compile_unsigned_binding(raw(r),raw(t),g,raw(a))
        self.assertEqual(b['request'],binding.identity(raw(r)));self.assertEqual(b['gene_registry'],binding.identity(g));self.assertEqual(b['gene_count'],2)
        for key in ['execution_ready','method_acceptance_verified','source_qualified','formal_authorized','scientific_authorization','G0']:self.assertIs(b[key],False)
        self.assertIn('EXACT_VARIANT_METHOD_ACCEPTANCE',b['missing_execution_contracts']);self.assertEqual(b['binding_compiler_source'],binding.identity(Path(binding.__file__).read_bytes()))
        manifest=tomllib.loads((ADAPTER/'manifest.toml').read_text());self.assertEqual(manifest['image']['reference'],b['image_reference'])
        self.assertEqual([len(n['ports']['inputs']) for n in manifest['nodes']],[5,6])
        self.assertEqual([p['path'] for p in manifest['nodes'][1]['ports']['outputs']],['results.tsv','audit.json','official.rds'])
        self.assertEqual([n['kind'] for n in manifest['nodes']],[b['design_kind'],b['limma_kind']])
    def test_embedded_method_verbatim_no_legacy_alias_or_transport_audit(self):
        original=ROOT/'research-adapters/b-bulk-limma-contract/scripts'
        self.assertEqual((ADAPTER/'scripts/bulk-limma.R').read_bytes(),(original/'bulk-limma.R').read_bytes())
        for name in ['run-design.R','run-limma.R']:
            old=(original/name).read_bytes();new=(ADAPTER/'scripts'/name).read_bytes()
            self.assertEqual(old.splitlines()[2],new.splitlines()[2])
            self.assertIn(b'"AUTONOMICS_INPUT0"',new);self.assertIn(b'"AUTONOMICS_OUTPUT0"',new)
            self.assertNotIn(b'plugin_transport_output_sha256',new)
    def test_scope_scale_versions_and_all_linked_metadata_refuse(self):
        for case in ['counts','TPM','voom','DESeq2','normalized_RNA','renormalized','stale_gene','stale_request','wrong_version','wrong_template','unfrozen']:
            with self.subTest(case=case):
                r,t,g,a=fixture()
                if case in ['counts','TPM']:r['expression_scale']=t['expression_scale']=case
                elif case in ['voom','DESeq2']:r['method']=t['method']=case
                elif case=='normalized_RNA':a['assay_type']='RNA_LOG2'
                elif case=='renormalized':a['normalization']='RENORMALIZED'
                elif case=='stale_gene':g+=b'x'
                elif case=='stale_request':a['request_identity']['sha256']='0'*64
                elif case=='wrong_version':r['software_lock']=copy.deepcopy(r['software_lock']);r['software_lock']['limma']='3.66.0'
                elif case=='wrong_template':t['design']=copy.deepcopy(t['design']);t['design']['numerator']='other'
                elif case=='unfrozen':t['status']='DRAFT'
                with self.assertRaises(ValueError):binding.compile_unsigned_binding(raw(r),raw(t),g,raw(a))
    def test_gene_universe_identity_schema_order_duplicates_refuse(self):
        for change in [lambda g:g.replace(b'SYN_G2',b'SYN_G1'),lambda g:g.replace(b'2\t',b'3\t'),lambda g:g.replace(b'B_TRANSCRIPTOME',b'OTHER'),lambda g:b'not a table']:
            r,t,g,a=fixture();g=change(g);a['gene_registry_identity']=binding.identity(g)
            with self.assertRaises(ValueError):binding.compile_unsigned_binding(raw(r),raw(t),g,raw(a))

    def test_duplicate_and_caller_approval_fields_cannot_be_a_gate(self):
        r,t,g,a=fixture()
        with self.assertRaises(ValueError):binding.compile_unsigned_binding(b'{"schema_version":1,"schema_version":1}',raw(t),g,raw(a))
        a['method_acceptance_verified']=True
        with self.assertRaises(ValueError):binding.compile_unsigned_binding(raw(r),raw(t),g,raw(a))

if __name__=='__main__':unittest.main()
