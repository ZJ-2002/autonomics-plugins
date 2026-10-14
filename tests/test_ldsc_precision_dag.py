import copy
import gzip
import json
import hashlib
from pathlib import Path
import tempfile
import subprocess
import unittest

from tools import prove_ldsc_precision_dag as proof


class PrecisionDagTests(unittest.TestCase):
    def state(self):
        return dict(kind='OBJECT',**{'class':'official.Fit'},fields=dict(estimate=1.2345,missing=dict(kind='MISSING',reason='NAN'),
                values=dict(kind='ARRAY',shape=[2],dtype='float64',values=[1.0,2.0])))

    def test_complete_state_includes_classes_shapes_missing_reasons_and_values(self):
        evidence=json.loads((proof.ROOT/'evidence/ldsc-precision-current-dag-20261015.json').read_text())
        for name,expected in evidence['source_sha256'].items():
            if name == 'tools/probes/official_plugin_dag.rs':
                original=subprocess.check_output(['git','-C',str(proof.ROOT),'show',evidence['probe_source_publication_revision']+':'+name])
                self.assertEqual(hashlib.sha256(original).hexdigest(),expected,name)
            else:
                self.assertEqual(proof.digest(proof.ROOT/name),expected,name)
        self.assertEqual(evidence['complete_returned_fields_compared'],2235)
        self.assertEqual(evidence['expected_nonestimable_results'],1)
        self.assertFalse(evidence['actual_research_panels_or_GWAS_qualified'])
        self.assertFalse(evidence['g0_granted'])
        value=self.state()
        reference=[[list(path),kind,number] for path,kind,number in proof.comparison.state_fields(value)]
        result=proof.compare_state(value,reference)
        self.assertEqual(result['finite_fields'],3)
        for mutation in ['estimate','class','shape','missing']:
            changed=copy.deepcopy(value)
            if mutation=='estimate': changed['fields']['estimate']=1.2346
            elif mutation=='class': changed['class']='other.Fit'
            elif mutation=='shape': changed['fields']['values']['dtype']='float32'
            else: changed['fields']['missing']['reason']='NONE'
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):
                proof.compare_state(changed,reference)

    def test_all_metadata_and_extensionless_inputs_require_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'config.json'
            original.write_bytes(b'{"frozen":"exact"}')
            work=root/'work'
            work.mkdir()
            (work/original.name).write_bytes(original.read_bytes())
            scratch=root/'scratch'
            staged=scratch/'.autonomics/inputs/input-0.json'
            staged.parent.mkdir(parents=True)
            staged.write_bytes(original.read_bytes())
            analysis=dict(inputs=[dict(to_port=0,**{'from':'input0'},path='vfs:///config.json',fingerprint=dict(size=original.stat().st_size))])
            self.assertEqual(len(proof.check_inputs(work,[original],analysis,scratch)),1)
            transport=root/'input-0'
            transport.write_bytes(gzip.compress(b'SYNTHETIC PLAINTEXT',mtime=0))
            (work/transport.name).write_bytes(transport.read_bytes())
            (staged.parent/'input-1').write_bytes(transport.read_bytes())
            analysis['inputs'].append(dict(to_port=1,**{'from':'input1'},path='vfs:///input-0',fingerprint=dict(size=transport.stat().st_size)))
            self.assertEqual(len(proof.check_inputs(work,[original,transport],analysis,scratch)),2)
            staged.write_bytes(b'{"frozen":"other"}')
            with self.assertRaises(RuntimeError):
                proof.check_inputs(work,[original,transport],analysis,scratch)


if __name__=='__main__':
    unittest.main()
