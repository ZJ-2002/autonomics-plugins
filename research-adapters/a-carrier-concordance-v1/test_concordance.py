import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('carrier_concordance', BASE/'concordance.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FIXTURE = r'''
args <- commandArgs(trailingOnly=TRUE)
mr <- data.frame(id.exposure="TOY_X", id.outcome="TOY_M", outcome="toy outcome",
                 exposure="toy exposure", method=c("Inverse variance weighted", "MR Egger"),
                 nsnp=c(10,10), b=c(0.1,0.2), se=c(0.03,0.04), pval=c(0.01,0.02),
                 role="EXPLORATORY_OVERLAP_UNRESOLVED", p_primary=NA,
                 p_for_family=1, p_raw_exploratory=c(0.01,0.02))
saveRDS(list(mr=mr,contract=list(R="4.6.1",TwoSampleMR="0.7.11")),args[1])
write.table(mr,args[2],sep="\t",quote=FALSE,row.names=FALSE,na="NA")
'''


class ConcordanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        cls.base = Path(cls.temporary.name)
        cls.rds = cls.base/'toy.rds'
        cls.tsv = cls.base/'toy.tsv'
        fixture = cls.base/'fixture.R'
        fixture.write_text(FIXTURE)
        subprocess.run(['/usr/bin/Rscript', '--vanilla', str(fixture), str(cls.rds), str(cls.tsv)], check=True, capture_output=True)
        cls.request = {'schema':MODULE.SCHEMA, 'scope':'CARRIER_CONCORDANCE_ONLY_NOT_PRIMARY_AUTHORITY',
                       'tsv_sha256':MODULE.sha(cls.tsv.read_bytes()), 'rds_sha256':MODULE.sha(cls.rds.read_bytes()),
                       'selectors':[{'id.exposure':'TOY_X','id.outcome':'TOY_M','method':method} for method in ['Inverse variance weighted','MR Egger']]}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_serialization_without_authority(self):
        result = MODULE.verify(self.tsv, self.rds, copy.deepcopy(self.request))
        self.assertEqual(result['rows'], 2)
        self.assertFalse(result['primary_authority_granted'])
        self.assertFalse(result['binary64_equality_of_TSV_and_RDS_claimed'])

    def test_identity_and_method_mismatches(self):
        for field, value in [('id.exposure','OTHER'),('id.outcome','OTHER'),('method','OTHER')]:
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                request['selectors'][0][field] = value
                with self.assertRaisesRegex(ValueError, 'exactly one'):
                    MODULE.verify(self.tsv, self.rds, request)

    def test_duplicate_and_shortened_selectors(self):
        for selectors in [[self.request['selectors'][0]]*2,self.request['selectors'][:1]]:
            with self.subTest(selectors=selectors):
                request = copy.deepcopy(self.request)
                request['selectors'] = selectors
                with self.assertRaises(ValueError):
                    MODULE.verify(self.tsv, self.rds, request)

    def test_rehashed_numeric_missing_and_column_changes(self):
        payload = self.tsv.read_bytes()
        for label, changed in [('numeric',payload.replace(b'0.1\t',b'0.9\t',1)),
                               ('missing',payload.replace(b'\tNA\t',b'\t0\t',1)),
                               ('column',payload.replace(b'pval\t',b'other_p\t',1))]:
            with self.subTest(label=label):
                self.assertNotEqual(changed,payload)
                source = self.base/(label+'.tsv')
                source.write_bytes(changed)
                request = copy.deepcopy(self.request)
                request['tsv_sha256'] = MODULE.sha(changed)
                with self.assertRaisesRegex(ValueError, 'serialization differs'):
                    MODULE.verify(source, self.rds, request)

    def test_hash_scope_and_authority_overrides(self):
        for key, value in [('rds_sha256','0'*64),('scope','PRIMARY_APPROVED'),('approved',True)]:
            with self.subTest(key=key):
                request = copy.deepcopy(self.request)
                request[key] = value
                with self.assertRaises(ValueError):
                    MODULE.verify(self.tsv, self.rds, request)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            json.loads('{"schema":1,"schema":2}', object_pairs_hook=MODULE.unique_object)


if __name__ == '__main__':
    unittest.main()
