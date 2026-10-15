import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools import prove_frozen_a_current_dag as proof


class FrozenACurrentDagTests(unittest.TestCase):
    def test_six_nodes_bind_all_five_inputs_in_order(self):
        job = proof.job_for(Path('/unused/toy'), proof.PLUGIN)
        self.assertEqual(len(job['nodes']), 6)
        self.assertEqual(len(job['edges']), 5)
        self.assertEqual(job['nodes'][-1], dict(id='analysis',kind=proof.KIND,spec={}))
        for index, edge in enumerate(job['edges']):
            self.assertEqual(edge, {'from':'input'+str(index),'to':'analysis','from_port':0,'to_port':index})
            self.assertEqual(job['nodes'][index]['spec']['path'], 'vfs:///'+proof.INPUTS[index])
        self.assertEqual(job['bundles'], [])
        self.assertEqual(job['additional_plugins'], [])

    def test_staged_input_requires_source_port_path_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); work = root / 'work'; work.mkdir()
            scratch = root / 'scratch'; stage = scratch / 'worker/.autonomics/inputs'; stage.mkdir(parents=True)
            bindings = []
            for index, name in enumerate(proof.INPUTS):
                (work / name).write_text('EXACT_TOY_BYTES_'+str(index))
                (stage / ('input-'+str(index)+Path(name).suffix)).write_bytes((work / name).read_bytes())
                bindings.append(dict(to_port=index,from_port=0,path='vfs:///'+name,
                    fingerprint=dict(size=(work / name).stat().st_size),**{'from':'input'+str(index)}))
            analysis = dict(inputs=bindings)
            self.assertEqual(len(proof.bound_inputs(work,analysis,scratch)),5)
            for field,value in [('from','other'),('from_port',1),('path','vfs:///foreign.tsv')]:
                changed = copy.deepcopy(analysis); changed['inputs'][0][field] = value
                with self.assertRaises(RuntimeError): proof.bound_inputs(work,changed,scratch)
            (stage / 'input-0.tsv').write_text('WRONG_BYTES')
            with self.assertRaises(RuntimeError): proof.bound_inputs(work,analysis,scratch)

    def test_dag_report_requires_all_success_nodes_and_current_identity(self):
        job = dict(plugin_manifest_sha256='toy-manifest')
        report = dict(first_run=dict(nodes=[dict(id='input'+str(index),status='success') for index in range(5)]+
            [dict(id='analysis',status='success')],errors=[]),engine_source_revision=proof.ENGINE,
            native_statistical_factories_registered=False,input_hashing='ContentRequired',max_concurrency=1,
            incremental=False,current_daemon_verified=False,original_manifest_sha256='toy-manifest',
            plugin_name='twosamplemr-v432-a',additional_plugin_identities=[],g0_granted=False)
        self.assertEqual(proof.checked_report(report,job,True)['status'],'success')
        for field,value in [('engine_source_revision','OLD'),('input_hashing','Metadata'),('g0_granted',True)]:
            changed=copy.deepcopy(report); changed[field]=value
            with self.assertRaises(RuntimeError): proof.checked_report(changed,job,True)
        changed=copy.deepcopy(report); changed['first_run']['nodes'][0]['status']='failed'
        with self.assertRaises(RuntimeError): proof.checked_report(changed,job,True)
        changed=copy.deepcopy(report); changed['first_run']['nodes'][-1]['status']='failed';changed['first_run']['errors']=['rejected']
        self.assertEqual(proof.checked_report(changed,job,False)['status'],'failed')
        with self.assertRaises(RuntimeError): proof.checked_report(report,job,False)

    def test_oracle_requires_all_six_exact_tsv_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); oracle=root/'oracle'; oracle.mkdir(); actual=[]
            for index in range(6):
                path=root/('actual'+str(index));path.write_text('SNP\tb\nrs1\t0.25\n');actual.append(path)
                (oracle/('output'+str(index))).write_bytes(path.read_bytes())
            self.assertEqual(len(proof.exact_tables(actual,oracle)),6)
            with self.assertRaises(RuntimeError):proof.exact_tables(actual[:5],oracle)
            actual[4].write_text('SNP\tb\nrs1\t0.2500000001\n')
            with self.assertRaises(RuntimeError):proof.exact_tables(actual,oracle)

    def test_provenance_comparison_ignores_only_adapter_path_identity(self):
        old=dict(adapter_sha256='beec8ef591d96180ac720c909288fd1090a7803e610c048e980b3de92636a53b',
            input_sha256=['1','2','3','4','5'],seed=432202610,scientific_authorization_granted=False)
        actual=copy.deepcopy(old);actual['adapter_sha256']='new-script'
        self.assertTrue(proof.compare_provenance(actual,old,'new-script')['all_other_fields_equal'])
        for field,value in [('seed',1),('input_sha256',['foreign']),('scientific_authorization_granted',True)]:
            changed=copy.deepcopy(actual);changed[field]=value
            with self.assertRaises(RuntimeError):proof.compare_provenance(changed,old,'new-script')
        with self.assertRaises(RuntimeError):proof.compare_provenance(actual,old,'wrong-source')


if __name__ == '__main__': unittest.main()
