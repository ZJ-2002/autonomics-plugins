import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.prove_normalized_b_current_dag import compare_tables, failed_chain, job_for, sealed


class NormalizedCurrentDagTests(unittest.TestCase):
    def test_three_models_seven_nodes_eleven_edges(self):
        root = Path(__file__).resolve().parents[1]
        for model in ['primary', 'unadjusted', 'therapy_sensitivity']:
            job = job_for(Path('/owned')/model, root/'plugins/bulk-limma-normalized')
            self.assertEqual(len(job['nodes']), 7)
            self.assertEqual(len(job['edges']), 11)
            self.assertEqual([(edge['from'],edge['from_port'],edge['to_port']) for edge in job['edges'] if edge['to']=='limma'],
                             [*[(f'input{index}',0,index) for index in range(5)],('design',0,5)])

    def test_mixed_full_table_rejects_missing_or_identity_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = ['gene_id','status','raw_p','log2_expression_difference','standard_error','moderated_df','ci_lower','ci_upper','q_BH','q_BY']
            row = ['SYN_G0','ESTIMATED','.1','1','.2','10','.6','1.4','.2','.3']
            def table(name, columns, values):
                with (root/name).open('w',newline='') as stream:
                    writer=csv.writer(stream,delimiter='\t');writer.writerow(columns);writer.writerow(values)
            table('actual',header,row); table('old',header,row)
            table('frozen',['gene_id','beta','moderated_se','df','lo','hi','p_raw','q_BH','q_BY'],[row[0],*row[3:8],row[2],*row[8:]])
            self.assertEqual(compare_tables(root/'actual',root/'old',root/'frozen')['rows'],1)
            for index,value in [(0,'OTHER'),(2,'NA'),(3,'5')]:
                changed=row.copy();changed[index]=value;table('actual',header,changed)
                with self.assertRaises(RuntimeError): compare_tables(root/'actual',root/'old',root/'frozen')

    def test_fixed_oracle_rejects_membership_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);artifacts=root/'archive/artifacts';artifacts.mkdir(parents=True)
            payload=artifacts/'payload';payload.write_bytes(b'fixed')
            manifest=artifacts/'MANIFEST.json'
            manifest.write_text(json.dumps({'files':{'payload':{'bytes':5,'sha256':hashlib.sha256(b'fixed').hexdigest()}}}))
            identity=hashlib.sha256(manifest.read_bytes()).hexdigest()
            sealed(root,'archive',identity)
            (artifacts/'extra').write_bytes(b'bad')
            with self.assertRaises(RuntimeError): sealed(root,'archive',identity)

    def test_upstream_failure_requires_skip_and_no_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            report={'first_run':{'errors':['expected'],'nodes':[
                {'id':'design','status':'failed','port_assignments':{}},
                {'id':'limma','status':'skipped','port_assignments':{}}]}}
            failed_chain(report,Path(temporary))
            changed=copy.deepcopy(report);changed['first_run']['nodes'][1]['status']='success'
            with self.assertRaises(RuntimeError): failed_chain(changed,Path(temporary))


if __name__ == '__main__':
    unittest.main()
