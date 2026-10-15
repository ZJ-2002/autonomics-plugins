import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess

from tests.test_frozen_b_project import fixture,project
from tools import prove_locked_b_source_transport as proof


class LockedBTransportTests(unittest.TestCase):
    def test_only_no_fit_graph_shapes_are_constructed(self):
        source=proof.ROOT/'plugins/frozen-b-project'
        for family,nodes,edges in [(False,20,19),(True,5,4)]:
            job=proof.job_for(Path('/unused'),source,family=family)
            self.assertEqual(job['scope'],proof.SCOPE)
            self.assertEqual((len(job['nodes']),len(job['edges'])),(nodes,edges))
            self.assertTrue(all(node['kind'] in ['file_reference','frozen_b_legacy_intake','frozen_b_legacy_family'] for node in job['nodes']))
            self.assertEqual(job['additional_plugins'],[])
        job=proof.job_for(Path('/unused'),source,normalized=proof.ROOT/'plugins/bulk-limma-normalized',authorization=(Path('/unused/operator.json'),'a'*64))
        self.assertEqual((len(job['nodes']),len(job['edges'])),(29,64))
        self.assertEqual(job['scope'],proof.FULL_SCOPE)
        with self.assertRaises(RuntimeError):proof.job_for(Path('/unused'),source,normalized=proof.ROOT/'plugins/bulk-limma-normalized')

    def test_verifier_requires_successful_actual_current_byte_check(self):
        report=dict(actual_exit=0,script_sha256='1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073',
            runtime_manifest_sha256='1bf0699bffde16a419a308d66654610cdca3170aa3fab2b8b50d93656e80e2a5',g0_granted=False,
            actual_report=dict(passed=True,read_only=True,errors=[],hash_checks=46786,unique_file_hashes=23669,
                all_project_scientific_gates_passed=False,scientific_results_computed=False))
        proof.fresh_gate(report)
        for field,value in [('actual_exit',True),('g0_granted',True),('script_sha256','0'*64)]:
            changed=copy.deepcopy(report);changed[field]=value
            with self.assertRaises(RuntimeError):proof.fresh_gate(changed)
        changed=copy.deepcopy(report);changed['actual_report']['passed']=False
        with self.assertRaises(RuntimeError):proof.fresh_gate(changed)

    def test_source_inventory_requires_exact_nineteen_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths,lock=fixture(root)
            for name,path in paths.items():lock['files'][name]['relative_path']=path.name
            self.assertEqual(len(proof.preflight_sources(root,lock)),19)
            paths['config'].write_bytes(b'WRONG')
            with self.assertRaises(RuntimeError):proof.preflight_sources(root,lock)
            changed=copy.deepcopy(lock);changed['files'].pop('matrix')
            with self.assertRaises(RuntimeError):proof.preflight_sources(root,changed)

    def test_all_ten_ports_and_model_receipts_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths,lock=fixture(root);outputs=project.intake(paths,lock)
            destination=root/'outputs';destination.mkdir()
            for name,value in outputs.items():(destination/name).write_bytes(value)
            definition=dict(ports=dict(outputs=[dict(path=name) for name in project.OUTPUTS]))
            sources={name:project.identity(path.read_bytes()) for name,path in paths.items()}
            self.assertEqual(len(proof.validate_ports(destination,definition,lock,sources)['ports']),10)
            path=destination/'therapy_sensitivity-intake.json';original=path.read_bytes();value=json.loads(original);value['G0']=True
            path.write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):proof.validate_ports(destination,definition,lock,sources)
            path.write_bytes(original);(destination/'genes.tsv').unlink()
            with self.assertRaises(RuntimeError):proof.validate_ports(destination,definition,lock,sources)

    def test_runtime_owner_and_image_cannot_drift(self):
        expected=dict(label='Python',reference=proof.IMAGE,installed_manifest_sha256='sha256:exact',image_config_digest=proof.CONFIG,ordered_diff_ids=['sha256:one'])
        owner=dict(all_three_software_images_exactly_installed=True,installed=[expected])
        actual=dict(Digest='sha256:exact',Id=proof.CONFIG,RootFS=dict(Layers=['sha256:one']))
        proof.image_identity(owner,actual)
        for field,value in [('Digest','wrong'),('Id','wrong'),('RootFS',dict(Layers=['sha256:other']))]:
            changed=copy.deepcopy(actual);changed[field]=value
            with self.assertRaises(RuntimeError):proof.image_identity(owner,changed)

    def test_historical_family_without_official_adjustment_is_refusal_only(self):
        with tempfile.TemporaryDirectory() as directory:
            case=__import__('tests.test_frozen_b_project',fromlist=['FrozenProjectTests']).FrozenProjectTests()
            case.paths,case.lock=fixture(Path(directory));raw=case.family_inputs()
            audit=project.strict_json(raw['limma_audit']);audit.pop('family_adjustment')
            with self.assertRaises(ValueError):project.family({**raw,'limma_audit':project.canonical(audit)},case.lock)
            self.assertFalse(hasattr(project,'adjust'))

    def test_official_numeric_comparison_rejects_missing_ids_and_out_of_tolerance(self):
        row=dict(gene_id='gene-1',status='ESTIMATED',role='LEGACY_EXPLORATORY_PRIMARY_MODEL',
            beta='1',moderated_se='0.1',df='20',lo='0.8',hi='1.2',p_raw='0.002',q_BH='0.004',q_BY='0.008')
        result=proof.compare_reference_family([row],[row],1,'primary')
        self.assertEqual(set(result['max_absolute_errors'].values()),{0})
        for field,value in [('gene_id','other'),('status','NOT_ESTIMABLE'),('role','OTHER'),
                ('p_raw','NA'),('q_BH','NaN'),('beta','1.0001')]:
            changed={**row,field:value}
            with self.assertRaises(RuntimeError):proof.compare_reference_family([changed],[row],1,'primary')
        with self.assertRaises(RuntimeError):proof.compare_reference_family([],[],1,'primary')
        missing={**row,'beta':'NA'}
        proof.compare_reference_family([missing],[missing],1,'primary')

    def test_original_reference_block_is_unique_and_unmodified(self):
        block='  con<-gzfile(file.path(root,cfg$matrix_file));lines<-readLines(con);close(con)\n untouched <- TRUE'
        self.assertEqual(proof.original_reference_block('prefix\n'+block+'\n} else stop("no")'),block)
        for text in ['',block,block+'\n'+block+'\n} else stop("no")']:
            with self.assertRaises(RuntimeError):proof.original_reference_block(text)

    def test_repeated_kind_ports_bind_exact_actual_run_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'work';scratch=root/'scratch';scratch.mkdir();work.mkdir()
            live=scratch/'result.tsv';live.write_bytes(b'id\tvalue\n1\t2\n')
            definition=dict(artifact_prefix='/artifacts/samekind',ports=dict(outputs=[dict(path='result.tsv',format='tsv')]))
            for run in ['autonomics-container-command-1-10','autonomics-container-command-1-11']:
                path=work/'artifacts/samekind'/run;path.mkdir(parents=True);(path/'result.tsv').write_bytes(live.read_bytes())
            node=dict(execution=dict(run_name='autonomics-container-command-1-11'),port_assignments={'0':
                dict(path=str(live),format='tsv',fingerprint=dict(size=live.stat().st_size,content_hash=None))})
            ports=proof.actual_ports(work,definition,node,scratch)
            self.assertEqual(ports[0].parent.name,'autonomics-container-command-1-11')
            ports[0].write_bytes(b'wrong')
            with self.assertRaises(RuntimeError):proof.actual_ports(work,definition,node,scratch)

    def test_rds_leaf_validator_uses_elementwise_numeric_masks_and_attributes(self):
        result=subprocess.run(['Rscript','--vanilla','-e',proof.RDS_LEAF_VALIDATOR+proof.RDS_LEAF_SELFTEST],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['ELEMENTWISE_RDS_VALIDATOR_2_POSITIVE_5_REFUSALS_PASS'])

    def test_environment_failures_cannot_count_as_expected_source_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stderr=root/'stderr';stderr.write_text('BLOCKED: frozen source bytes differ')
            node=dict(status='failed',execution=dict(exit_code=2,image=proof.IMAGE,image_digest=proof.IMAGE.split('@')[1],
                stderr_log=dict(path=str(stderr))),error=dict(message=stderr.read_text()))
            proof.expected_refusal(node,proof.IMAGE,'frozen source bytes differ',root)
            for field,value in [('exit_code',137),('exit_code',True),('image','other'),('image_digest','sha256:wrong')]:
                changed=copy.deepcopy(node);changed['execution'][field]=value
                with self.assertRaises(RuntimeError):proof.expected_refusal(changed,proof.IMAGE,'frozen source bytes differ',root)
            changed=copy.deepcopy(node);changed['error']['message']='OOM'
            with self.assertRaises(RuntimeError):proof.expected_refusal(changed,proof.IMAGE,'frozen source bytes differ',root)
            stderr.write_text('container start failed')
            with self.assertRaises(RuntimeError):proof.expected_refusal(node,proof.IMAGE,'frozen source bytes differ',root)

    def test_runner_and_record_require_real_same_archive_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            archives=Path(directory);archive=archives/('a'*32);artifacts=archive/'artifacts';output=artifacts/'permanent/build'
            output.mkdir(parents=True);runner=output/'official_plugin_dag';runner.write_bytes(b'toy executable')
            record=output/'build-record.json';record.write_text(json.dumps(dict(actual_build_exit=0,
                parent_commit='4ceefbd821baab8deebb070645a2fb8b1fa8e1ba',engine_commit='toy',
                executables=dict(runner=dict(executable=runner.name,sha256=proof.digest(runner))))))
            manifest=artifacts/'MANIFEST.json';manifest.write_text(json.dumps(dict(session=archive.name,files={
                path.relative_to(artifacts).as_posix():dict(bytes=path.stat().st_size,sha256=proof.digest(path)) for path in [runner,record]})))
            seal=proof.digest(manifest);(archive/'SESSION.json').write_text(json.dumps(dict(session=archive.name,state='CLEANED',
                manifest_sha256=seal,worker_exit_status=0)))
            proof.build_membership(archives,runner,record,seal)
            fake=archive/'fake-record.json';fake.write_bytes(record.read_bytes())
            with self.assertRaises(RuntimeError):proof.build_membership(archives,runner,fake,seal)
            other=archives/'official_plugin_dag';other.write_bytes(runner.read_bytes())
            with self.assertRaises(RuntimeError):proof.build_membership(archives,other,record,seal)

    def test_failure_or_cancellation_cannot_count_as_upstream_skip(self):
        node=dict(status='skipped',execution=None,port_assignments={},skipped_because='intake')
        proof.expected_upstream_skip(node,'intake')
        for field,value in [('status','failed'),('status','cancelled'),('status','pending'),
                ('skipped_because',None),('skipped_because','other'),('port_assignments',{'0':{}}),('execution',{})]:
            changed={**node,field:value}
            with self.assertRaises(RuntimeError):proof.expected_upstream_skip(changed,'intake')


if __name__=='__main__':unittest.main()
