import copy
import csv
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('precise_export', ROOT / 'research-adapters/a-carrier-concordance-v1/export_precise.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FIXTURE = '''args <- commandArgs(trailingOnly=TRUE)
values <- data.frame(id.exposure="TOY_X", id.outcome="TOY_M", outcome="toy outcome",
 exposure="toy exposure", method=c("Inverse variance weighted", "MR Egger"),
 nsnp=c(10,10), b=c(0.10000000000000002,-0.20000000000000004), se=c(0.03,0.04),
 pval=c(0.12345678901234566,1e-200), role="EXPLORATORY_OVERLAP_UNRESOLVED",
 p_primary=NA, p_for_family=1, p_raw_exploratory=c(0.12345678901234566,1e-200))
if (args[3] == "finite-primary") values$p_primary <- 0.05
if (args[3] == "different-p") values$p_raw_exploratory[1] <- 0.5
if (args[3] == "bad-role") values$role <- "PRIMARY"
if (args[3] == "nonfinite") values$b[1] <- Inf
saveRDS(list(mr=values,contract=list(R="4.6.1",TwoSampleMR="0.7.11")),args[1])
write.table(values,args[2],sep="\\t",quote=FALSE,row.names=FALSE,na="NA")
'''


class PreciseCarrierExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rds = self.root / 'original.rds'
        self.tsv = self.root / 'original.tsv'
        (self.root / 'fixture.R').write_text(FIXTURE)
        self.fixture('normal')

    def fixture(self, mode):
        subprocess.run(['/usr/bin/Rscript', '--vanilla', str(self.root / 'fixture.R'), str(self.rds), str(self.tsv), mode],
            check=True, capture_output=True)
        self.request = dict(schema=MODULE.SCHEMA, scope='LOSSLESS_CARRIER_CONVERSION_NOT_PRIMARY_AUTHORITY',
            tsv_sha256=MODULE.sha(self.tsv.read_bytes()), rds_sha256=MODULE.sha(self.rds.read_bytes()),
            selectors=[{'id.exposure':'TOY_X', 'id.outcome':'TOY_M', 'method':name}
                for name in ['Inverse variance weighted', 'MR Egger']])

    def test_real_binary64_values_not_rounded_original_are_exported(self):
        before = [self.tsv.read_bytes(), self.rds.read_bytes()]
        payload, receipt = MODULE.extract(self.tsv, self.rds, self.request)
        old = list(csv.DictReader(io.StringIO(before[0].decode()), delimiter='\t'))
        new = list(csv.DictReader(io.StringIO(payload.decode()), delimiter='\t'))
        self.assertNotEqual(float(old[0]['pval']), float(new[0]['pval']))
        self.assertEqual(float(new[0]['pval']), 0.12345678901234566)
        self.assertEqual(float(new[1]['pval']), 1e-200)
        self.assertEqual(float(new[0]['b']), 0.10000000000000002)
        self.assertEqual(receipt['numeric_cells_binary64_exact'], 12)
        self.assertTrue(receipt['derived_carrier_not_historical_restoration'])
        self.assertFalse(receipt['primary_authority_granted'])
        self.assertEqual([self.tsv.read_bytes(), self.rds.read_bytes()], before)

    def test_wrong_input_hash_and_exact_method_mapping_are_rejected(self):
        for change in ['hash', 'method']:
            request = copy.deepcopy(self.request)
            if change == 'hash': request['rds_sha256'] = '0' * 64
            else: request['selectors'][0]['method'] = 'OTHER'
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODULE.extract(self.tsv, self.rds, request)

    def test_incomplete_duplicate_and_promoted_scope_requests_are_rejected(self):
        for change in ['short', 'duplicate', 'scope']:
            request = copy.deepcopy(self.request)
            if change == 'short': request['selectors'] = request['selectors'][:1]
            elif change == 'duplicate': request['selectors'][1] = request['selectors'][0]
            else: request['scope'] = 'PRIMARY_APPROVED'
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODULE.extract(self.tsv, self.rds, request)

    def test_inconsistent_or_promoted_objects_are_rejected(self):
        for mode in ['finite-primary', 'different-p', 'bad-role', 'nonfinite']:
            self.fixture(mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                MODULE.extract(self.tsv, self.rds, self.request)

    def test_matched_hashes_cannot_hide_altered_tsv(self):
        self.tsv.write_bytes(self.tsv.read_bytes().replace(b'toy outcome', b'other label'))
        self.request['tsv_sha256'] = MODULE.sha(self.tsv.read_bytes())
        with self.assertRaises(ValueError):
            MODULE.extract(self.tsv, self.rds, self.request)

    def test_symlink_sources_are_rejected(self):
        alias = self.root / 'alias.rds'
        alias.symlink_to(self.rds)
        with self.assertRaises(ValueError):
            MODULE.extract(self.tsv, alias, self.request)
