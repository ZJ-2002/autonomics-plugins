"""Native cases require exact host R/stats4.6.1; no CI/native qualification claim."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'research-adapters/cachexia-contracts-v432/scripts/guards.py'
guards = types.ModuleType('official_family_guard_source')
guards.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_bytes(), str(SCRIPT), 'exec'), guards.__dict__)


def exact_r_available():
    binary = shutil.which('Rscript')
    if not binary:
        return False
    try:
        result = subprocess.run([binary, '--vanilla', '-e',
            'quit(status=if(as.character(getRversion())=="4.6.1" && as.character(utils::packageVersion("stats"))=="4.6.1") 0L else 1L)'],
            capture_output=True, timeout=10, check=False)
        return result.returncode == 0 and result.stdout == result.stderr == b''
    except (OSError, subprocess.SubprocessError):
        return False


HAS_EXACT_R = exact_r_available()
REQUIRES_R = 'requires actual R/stats 4.6.1; this native test is not stdlib-only'


def vector_bytes(values):
    return ''.join(('0' if p == 0 else format(p, '.17g')) + '\n' for p in values).encode('ascii')


def reference(values, method):
    # A separate direct official call, not the guard's subprocess program.
    program = ('p<-scan(file("stdin"),quiet=TRUE); '
        'q<-stats::p.adjust(p,method=commandArgs(TRUE)[1],n=length(p)); '
        'cat(paste(sprintf("%.17g",q),collapse="\\n"),"\\n",sep="")')
    result = subprocess.run([shutil.which('Rscript'),'--vanilla','-e',program,method],
        input=vector_bytes(values),capture_output=True,timeout=15,check=True)
    if result.stderr:
        raise AssertionError('direct official reference emitted stderr')
    return [float(p) for p in result.stdout.splitlines()], result.stdout


class OfficialRTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HAS_EXACT_R, REQUIRES_R)

    def test_real_r_edges_ties_tiny_p_na_placeholders_and_exact_receipts(self):
        identifiers = ['zero','minus-zero','tiny','tie-1','tie-2','one','not-estimable','not-run']
        records = [dict(test_id=k,raw_p=p,status='ESTIMATED',q=0.0)
            for k,p in zip(identifiers[:6],[0.0,-0.0,1e-300,0.01,0.01,1.0])]
        records += [dict(test_id='not-estimable',raw_p=None,status='NOT_ESTIMABLE')]
        vector = [0.0,0.0,1e-300,0.01,0.01,1.0,1.0,1.0]
        for method in ('BH','BY'):
            receipts = []
            rows = guards.complete_family(identifiers,records,method=method,receipts=receipts)
            expected, raw_q = reference(vector,method)
            self.assertEqual([r['q'] for r in rows],expected)
            self.assertEqual([r['test_id'] for r in rows],identifiers)
            self.assertTrue(all(r['family_size']==8 and r['family_status']=='INCOMPLETE' for r in rows))
            self.assertEqual(rows[-1]['status'],'NOT_RUN')
            self.assertIsNone(rows[-2]['raw_p'])
            receipt = receipts[0]
            self.assertEqual(receipt['n'],8)
            self.assertEqual(receipt['input_vector_sha256'],hashlib.sha256(vector_bytes(vector)).hexdigest())
            self.assertEqual(receipt['input_vector_bytes'],len(vector_bytes(vector)))
            self.assertEqual(receipt['q_vector_sha256'],hashlib.sha256(raw_q).hexdigest())
            self.assertEqual(receipt['q_values_sha256'],hashlib.sha256(guards._canonical(expected)).hexdigest())
            self.assertEqual(receipt['ordered_test_ids_sha256'],hashlib.sha256(guards._canonical(identifiers)).hexdigest())
            self.assertEqual(receipt['program_sha256'],hashlib.sha256(guards.R_ADJUST_PROGRAM.encode()).hexdigest())
            self.assertEqual(receipt['Rscript_sha256'],guards._file_sha(Path(shutil.which('Rscript')).resolve()))
            self.assertEqual((receipt['R_version'],receipt['stats_version']),('4.6.1','4.6.1'))
            self.assertIs(receipt['scientific_G0_granted'],False)

    def test_ordered_ids_restore_original_row_order_without_prior_q_input(self):
        ids=['z','b','a','d']
        records=[dict(test_id=k,raw_p=p,status='ESTIMATED',q_bh=0.0,q_by=0.0)
                 for k,p in [('a',0.01),('z',0.1),('d',0.01),('b',0.5)]]
        for method in ('BH','BY'):
            rows=guards.complete_family(ids,records,method=method)
            expected,_=reference([0.1,0.5,0.01,0.01],method)
            self.assertEqual([r['test_id'] for r in rows],ids)
            self.assertEqual([r['q'] for r in rows],expected)
            self.assertTrue(all(r['family_status']=='COMPLETE' for r in rows))

    def test_distinct_complete_b_family_vectors_do_not_concatenate_model_q(self):
        families=[('B_TRANSCRIPTOME',6,[0.001,0.03]),('B_PRIMARY_STATES',9,[0.2,0.4,0.01])]
        for family,n,values in families:
            ids=[family+'-'+str(i) for i in range(n)]
            records=[dict(test_id=ids[i],raw_p=p,status='ESTIMATED',q_bh=0.0,q_by=0.0) for i,p in enumerate(values)]
            for method in ('BH','BY'):
                receipts=[]
                rows=guards.complete_family(ids,records,method=method,receipts=receipts)
                expected,_=reference(values+[1.]*(n-len(values)),method)
                self.assertEqual([r['q'] for r in rows],expected)
                self.assertEqual(receipts[0]['n'],n)

    def test_paths_use_two_full_registered_vectors_and_preserve_component_states(self):
        edges=[dict(test_id='XM',exposure_id='X',outcome_id='M',raw_p=0.01,status='ESTIMATED'),
            dict(test_id='MY',exposure_id='M',outcome_id='Y',raw_p=0.02,status='ESTIMATED'),
            dict(test_id='MY-unrun',exposure_id='M',outcome_id='Y',raw_p=None,status='NOT_RUN')]
        paths=[]
        for family,count in [('A_PRIMARY_PATHS',2),('A_EXPANDED_PATHS',3)]:
            for i in range(count):
                paths.append(dict(path_id=family+str(i),family=family,xm_edge_id='XM',my_edge_id='MY-unrun' if i==0 else 'MY',x_id='X',m_id='M',y_id='Y'))
        receipts=[]
        rows=guards.path_rows(paths,edges,{'planned_counts':{'A_PRIMARY_PATHS':2,'A_EXPANDED_PATHS':3}},receipts=receipts)
        self.assertEqual([(r['family'],r['method'],r['n']) for r in receipts],[('A_PRIMARY_PATHS','BY',2),('A_EXPANDED_PATHS','BY',3)])
        for family,count in [('A_PRIMARY_PATHS',2),('A_EXPANDED_PATHS',3)]:
            chosen=[r for r in rows if r['family']==family]
            expected,_=reference([1.0]+[0.02]*(count-1),'BY')
            self.assertEqual([r['q_by'] for r in chosen],expected)
            self.assertEqual(chosen[0]['status'],'NOT_RUN')
            self.assertTrue(all(r['family_status']=='INCOMPLETE' and r['family_size']==count for r in chosen))


class CorrectionTransportTests(unittest.TestCase):
    def test_missing_r_and_invalid_rows_never_fall_back(self):
        with mock.patch.object(guards.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'no correction fallback'):
                guards.complete_family(['a'],[dict(test_id='a',raw_p=0.1,status='ESTIMATED')],method='BH')
        for values in [[True],[float('nan')],[float('inf')],[-0.1],[1.1],[]]:
            with self.subTest(values=values),self.assertRaises(ValueError):guards.official_adjust(values,'BH')
        with mock.patch.object(guards,'official_adjust') as adjust:
            with self.assertRaises(ValueError):guards.complete_family(['a'],[dict(test_id='a',raw_p=0.1,status='FAILED')],method='BH')
            adjust.assert_not_called()

    def test_timeout_and_nonzero_exit_are_refusals(self):
        for error in [subprocess.TimeoutExpired('Rscript',45),OSError('SYNTHETIC failure')]:
            with mock.patch.object(guards.shutil,'which',return_value='/usr/bin/python3'),mock.patch.object(guards.subprocess,'run',side_effect=error):
                with self.assertRaises(ValueError):guards.official_adjust([0.1],'BH')
        def failed(command,**kwargs):return subprocess.CompletedProcess(command,17)
        with mock.patch.object(guards.shutil,'which',return_value='/usr/bin/python3'),mock.patch.object(guards.subprocess,'run',side_effect=failed):
            with self.assertRaisesRegex(ValueError,'process failed'):guards.official_adjust([0.1],'BH')

    def test_exact_stdout_header_count_numeric_domain_and_stderr_are_checked(self):
        header=b'AUTONOMICS_R_STATS_PADJUST_V1\t4.6.1\t4.6.1\tBH\t1\n'
        for payload,error in [(header.replace(b'4.6.1',b'4.5.0')+b'0.1\n',b''),(header+b'NaN\n',b''),(header+b'1.1\n',b''),(header+b'0.1\n0.2\n',b''),(header+b'0.1',b''),(header+b'0.1\n',b'warning'),(b'x'*600,b'')]:
            def fake(command,payload=payload,error=error,**kwargs):
                kwargs['stdout'].write(payload);kwargs['stderr'].write(error)
                return subprocess.CompletedProcess(command,0)
            with mock.patch.object(guards.shutil,'which',return_value='/usr/bin/python3'),mock.patch.object(guards.subprocess,'run',side_effect=fake):
                with self.assertRaises(ValueError):guards.official_adjust([0.1],'BH')


if __name__=='__main__':unittest.main(verbosity=2)
