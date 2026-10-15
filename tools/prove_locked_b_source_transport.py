"""Private user-authorized locked B replay and separate no-fit transport controls."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_opentargets_direct_files import sealed_archive
from tools.prove_bulk_current_chain import plugin_spec
from tools.prove_current_ldsc import digest, write

REVISION = 'efb691f43a47037a3b9fff48a6cb08dff472426e'
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')
DELIVERY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/results/v4.3.2/B_LOCKED_RERUN_20261014')
HISTORICAL = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/results/v4.3.2/B_LEGACY_TUI/limma/autonomics-container-command-154916-1791977653199707884/results.tsv')
HISTORICAL_SHA = '1c0debba15aff22e0de0a27e1bb59ccae1f4f29fb9d2a587306fabea45f75573'
OWNER = Path('/home/zj-normal/.autonomics/containers-overlay/SOFTWARE_INSTALLATION_OWNER.json')
OWNER_SHA = '7d88bee121dbbdc974787b64cbcccc1e5304a09e805303d897d3ea28ef7d2bbc'
FRESH = 'd585c6c7ef5f49b7bc3845d722572eec'
FRESH_SEAL = 'ae4bdb186263789615ad6123376b2c9a090f850e2f0920528eb79f53a9b81bf7'
IMAGE = 'docker.io/library/python@sha256:a66d3a463d0be3cc537c269b0d3418746dda512417a975559a0eaa8a6406baaf'
CONFIG = 'sha256:82cd6bca489be723b62b192752c133eb7c6acbcecaeca797628725d994998c5b'
SCOPE = 'LOCKED_LEGACY_SOURCE_TRANSPORT_NO_FIT_NOT_G0'
FULL_SCOPE = 'LOCKED_LEGACY_B_THREE_MODEL_REPLAY_NOT_G0'
AUTHORIZATION = Path('/home/zj-normal/Work/autonomics/results/cachexia-v4.3.2/B_ISOLATED_REPLAY_AUTHORIZATION_20261015.json')
AUTHORIZATION_SHA = 'fd8d56a7dd76eea82bab82d4a07c94d4e1e2f9040d69881e02810cf84e916299'
NORMALIZED_IMAGE = 'localhost/autonomics/frozen-b-normalized@sha256:723904dd46c9148d75716555e2f641604d98c22909bc333d5fac832f33ebffed'
NORMALIZED_PINS = {'manifest.toml':'d643744bb9c96c31f3e0f86b8782ff61a66ec4281ca3b0c45bbc041dbcda09f2',
    'scripts/run-design.R':'ed9ab1fd7b4c5f4533a7fac14d50ded9c829a840e849d974486945534648d707',
    'scripts/run-limma.R':'a300208080b1cf6c8d3361fe4f0dbea50977a45f7e76fed00bfe49dc7def738c'}
INPUTS = ['config','manifest','samples','features','scope','design_certificate','software_lock','r_dependencies',
    'r_session','scientific_code','scientific_rules','scope_decision','matrix','source_metadata','g0_certificate',
    'family_lock','restore_acceptance','runtime_manifest','byte_verifier']
PINS = {'manifest.toml':'939a180cafbdeb45899ea216fe71db7e0a2a77a6fc360d09258e14532dbfbcef',
    'scripts/run-intake.py':'6d6f6aac6c57c873886864fb700db6628a974bc370b18c21dbb1e04e47217ac1',
    'scripts/run-family.py':'fd934edefd44aeecb50bafd6a9d832e71618c18409762c585e7838bded144b0b'}
MODELS = {'primary':('~group+age+sex',4,'LEGACY_EXPLORATORY_PRIMARY_MODEL'),
    'unadjusted':('~group',2,'PRESPECIFIED_SENSITIVITY_ONLY'),
    'therapy_sensitivity':('~group+age+sex+treatment',5,'PRESPECIFIED_SENSITIVITY_ONLY')}
RDS_LEAF_VALIDATOR = '''leaf_equal<-function(actual,reference) {
 stopifnot(identical(typeof(actual),typeof(reference)),identical(class(actual),class(reference)),
  identical(length(actual),length(reference)))
 if(is.list(actual)) {
  for(i in seq_along(actual)) leaf_equal(actual[[i]],reference[[i]])
 } else if(is.numeric(actual)) {
  stopifnot(identical(is.na(actual),is.na(reference)),identical(is.nan(actual),is.nan(reference)),
   identical(is.infinite(actual),is.infinite(reference)))
  infinities<-is.infinite(actual)
  stopifnot(identical(actual[infinities],reference[infinities]))
  finite<-is.finite(actual)
  stopifnot(all(abs(actual[finite]-reference[finite])<=1e-12+1e-11*abs(reference[finite])))
 } else stopifnot(identical(actual,reference))
 left<-attributes(actual);right<-attributes(reference)
 stopifnot(identical(names(left),names(right)))
 if(length(left)) for(i in seq_along(left)) leaf_equal(left[[i]],right[[i]])
 invisible(TRUE)
}
'''
RDS_LEAF_SELFTEST = '''valid<-list(a=c(1,1e12,NA_real_,NaN,Inf,-Inf),b=matrix(c(1,2,3,4),2))
leaf_equal(valid,valid)
leaf_equal(c(1+1e-12,1e12+1),c(1,1e12))
stopifnot(isTRUE(all.equal(c(1,1e12),c(1.1,1e12+1),tolerance=1e-11)))
for(pair in list(list(c(1,1e12),c(1.1,1e12+1)),list(c(NA_real_),c(NaN)),
 list(c(Inf),c(-Inf)),list(1L,1),list(setNames(1,"a"),setNames(1,"b")))) {
 stopifnot(inherits(tryCatch({leaf_equal(pair[[1L]],pair[[2L]]);NULL},error=identity),"error"))
}
cat("ELEMENTWISE_RDS_VALIDATOR_2_POSITIVE_5_REFUSALS_PASS\\n")
'''


def require(ok,message):
    if not ok: raise RuntimeError(message)


def fresh_gate(value):
    report=value.get('actual_report',{})
    require(type(value.get('actual_exit')) is int and value['actual_exit']==0 and
        value.get('script_sha256')=='1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073' and
        value.get('runtime_manifest_sha256')=='1bf0699bffde16a419a308d66654610cdca3170aa3fab2b8b50d93656e80e2a5' and
        report.get('passed') is True and report.get('read_only') is True and report.get('errors')==[] and
        type(report.get('hash_checks')) is int and report['hash_checks']==46786 and
        type(report.get('unique_file_hashes')) is int and report['unique_file_hashes']==23669 and
        report.get('all_project_scientific_gates_passed') is False and
        report.get('scientific_results_computed') is False and value.get('g0_granted') is False,
        'Actual fresh original whole-project verification required, without scientific release')


def regular(path):
    path=Path(path).absolute()
    require(path.resolve()==path and not any(p.is_symlink() for p in [path,*path.parents]) and
        stat.S_ISREG(path.lstat().st_mode),'Unaliased regular source required')
    return path


def preflight_sources(study,lock):
    require(set(lock['files'])==set(INPUTS),'Exact nineteen-source lock required')
    records={};total=0
    for name in INPUTS:
        relative=Path(lock['files'][name]['relative_path'])
        require(not relative.is_absolute() and '..' not in relative.parts,'Frozen source path must remain inside the root')
        path=regular(study/relative);size=path.stat().st_size;total+=size
        require(0<size<=64*1024**2 and total<=64*1024**2,'Bounded aggregate source budget required')
        actual=digest(path)
        require(actual==lock['files'][name]['sha256'],'Actual frozen source bytes differ: '+name)
        records[name]=dict(sha256=actual,bytes=size)
    return records


def resource_preflight(output,name):
    available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    free=shutil.disk_usage(output).free
    write(output/(name+'-resources.json'),dict(mem_available_bytes=available,disk_free_bytes=free,
        task_memory_budget_bytes=1024**3,required_system_reserve_bytes=4*1024**3,no_concurrent_method_execution=True))
    require(available>=5*1024**3 and free>=2*1024**3,'Current one-GiB task plus four-GiB system reserve and bounded disk space required')
    return available


def table(path):
    with path.open(newline='') as handle:
        reader=csv.DictReader(handle,delimiter='\t',strict=True);rows=list(reader)
    require(reader.fieldnames is not None and len(reader.fieldnames)==len(set(reader.fieldnames)) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows),'Complete table required')
    return reader.fieldnames,rows


def validate_ports(directory,definition,lock,sources):
    names=[port['path'] for port in definition['ports']['outputs']]
    require(len(names)==10 and len(set(names))==10 and all((directory/name).is_file() and
        not (directory/name).is_symlink() and (directory/name).stat().st_size>0 for name in names),'All ten declared ports required')
    header,expression=table(directory/'expression.tsv');_,genes=table(directory/'genes.tsv');_,samples=table(directory/'samples.tsv')
    require(len(expression)==len(genes)==lock['gene_count'] and len(samples)==lock['primary_samples'] and
        header==['gene_id',*[row['sample_id'] for row in samples]] and
        [row['gene_id'] for row in expression]==[row['gene_id'] for row in genes],'Complete ordered gene/sample axes required')
    derived={name:digest(directory/(name+'.tsv')) for name in ['expression','genes','samples','decisions']}
    for model,(formula,rank,role) in MODELS.items():
        prefix='' if model=='primary' else model+'-'
        config_path=directory/(prefix+'config.json'); receipt=json.loads((directory/(prefix+'intake.json')).read_text())
        config=json.loads(config_path.read_text())
        require(receipt['scope']=='FROZEN_V432_B_LEGACY_SOURCE_INTAKE_NOT_QUALIFICATION' and
            receipt['source_files']==sources and receipt['input_sha256']==derived and receipt['config_sha256']==digest(config_path) and
            receipt['model_id']==model and receipt['model_formula']==formula and receipt['rank']==rank and
            receipt['residual_df']==lock['primary_samples']-rank and receipt['family_role']==role and
            receipt['result_exposure']=='SEEN' and receipt['primary_samples']==header[1:] and
            receipt['independent_unit_ids']==[row['independent_unit_id'] for row in samples] and
            config['input_sha256']==derived and config['software_lock']==lock['software_lock'] and
            config['method']=='LIMMA_EBAYES' and config['expression_scale']=='log2_normalized' and
            config['method_parameters']==dict(trend=True,robust=True,allowed_warning_messages=[]) and
            all(receipt[name] is False for name in ['frozen_scientific_code_executed','original_full_project_byte_verifier_executed',
                'original_full_project_byte_audit_verified','scientific_authorization','formal_authorized','G0']),
            'Every model must retain exact source, method, role and false-authority receipts')
    return dict(ports=[dict(port=index,name=name,bytes=(directory/name).stat().st_size,sha256=digest(directory/name))
        for index,name in enumerate(names)],genes=len(genes),selected_samples=len(samples),models=list(MODELS))


def image_identity(owner,actual):
    require(owner['all_three_software_images_exactly_installed'] is True,'Reviewed software backend required')
    expected=next(item for item in owner['installed'] if item['label']=='Python')
    require(expected['reference']==IMAGE and actual['Digest']==expected['installed_manifest_sha256'] and
        'sha256:'+actual['Id'].removeprefix('sha256:')==CONFIG==expected['image_config_digest'] and
        actual['RootFS']['Layers']==expected['ordered_diff_ids'],'Fresh exact Python image/config/layers required')


def job_for(work,source,*,family=False,propagate=False,normalized=None,authorization=None):
    require(not (family and propagate),'Separate no-fit graph cases required')
    names=['historical-results.tsv','genes.tsv','intake.json','historical-audit.json'] if family else [name+'.input' for name in INPUTS]
    nodes=[dict(id='input'+str(index),kind='file_reference',spec=dict(path='vfs:///'+name,format='file',hash_content=True)) for index,name in enumerate(names)]
    method='family' if family else 'intake'
    nodes.append(dict(id=method,kind='frozen_b_legacy_'+method,spec={}))
    edges=[{'from':'input'+str(index),'to':method,'from_port':0,'to_port':index} for index in range(len(names))]
    if propagate:
        nodes.append(dict(id='blocked_family',kind='frozen_b_legacy_family',spec={}))
        edges.append({'from':'intake','to':'blocked_family','from_port':2,'to_port':1})
    job=dict(scope=SCOPE,run_root=str(work),**plugin_spec(source),bundles=[],panel_manifest_sha256={},additional_plugins=[],nodes=nodes,edges=edges)
    if normalized is not None:
        require(not family and not propagate and authorization is not None,'Full replay requires separate explicit authorization')
        job.update(scope=FULL_SCOPE,additional_plugins=[plugin_spec(normalized)],
            operator_authorization_file=str(authorization[0]),operator_authorization_sha256=authorization[1])
        for model,config_port,receipt_port in [('primary',0,5),('unadjusted',6,7),('therapy_sensitivity',8,9)]:
            design,limma,endpoint=(model+'_'+stage for stage in ['design','limma','family'])
            nodes.extend([dict(id=design,kind='bulk_normalized_design',spec={}),dict(id=limma,kind='bulk_normalized_limma',spec={}),
                          dict(id=endpoint,kind='frozen_b_legacy_family',spec={})])
            for target in [design,limma]:
                edges.append({'from':'intake','to':target,'from_port':config_port,'to_port':0})
                edges.extend({'from':'intake','to':target,'from_port':index,'to_port':index} for index in range(1,5))
            edges.append({'from':design,'to':limma,'from_port':0,'to_port':5})
            edges.extend([{'from':limma,'to':endpoint,'from_port':0,'to_port':0},
                {'from':'intake','to':endpoint,'from_port':2,'to_port':1},
                {'from':'intake','to':endpoint,'from_port':receipt_port,'to_port':2},
                {'from':limma,'to':endpoint,'from_port':1,'to_port':3}])
    return job


def inspect_backend(output):
    require(digest(regular(OWNER))==OWNER_SHA,'Exact existing software owner required')
    owner=json.loads(OWNER.read_text());backend=owner['runtime_backend']
    for key in ['storage','runroot']:
        value=owner[key];current=Path(value['path']).stat()
        require((current.st_dev,current.st_ino,current.st_uid,current.st_gid)==
            (value['device'],value['inode'],value['uid'],value['gid']),'Software backend identity drift')
    shim=Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    require("'--tmpdir'" in shim.read_text(),'Qualified backend ownership shim required')
    command=[str(shim),*backend,'image','inspect',IMAGE]
    result=subprocess.run(command,capture_output=True,text=True,check=True,timeout=60)
    (output/'image-inspect.json').write_text(result.stdout);image_identity(owner,json.loads(result.stdout)[0])
    write(output/'runtime-identity.json',dict(owner_sha256=OWNER_SHA,backend=backend,shim_sha256=digest(shim),
        image=IMAGE,config=CONFIG,no_build_or_pull=True,no_production_restart=True))
    return [str(shim),*backend]


def independent_projection(directory,study,lock):
    _,features=table(study/lock['files']['features']['relative_path'])
    _,samples=table(study/lock['files']['samples']['relative_path'])
    ids=[row['sample_id'] for row in samples]
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter='\t',lineterminator='\n');writer.writerow(['gene_id',*ids])
    count=0
    with gzip.open(study/lock['files']['matrix']['relative_path'],'rt',newline='') as matrix:
        for line in matrix:
            if line.rstrip('\r\n')=='!series_matrix_table_begin':break
        reader=csv.reader(matrix,delimiter='\t',strict=True);header=next(reader);positions=[header.index(name) for name in ids]
        for row in reader:
            if row==['!series_matrix_table_end']:break
            require(count<len(features) and row[0]==features[count]['source_probe_id'] and len(row)==len(header),'Independent original-source matrix axis differs')
            writer.writerow([features[count]['feature_id'],*[row[index] for index in positions]]);count+=1
    expected=stream.getvalue().encode()
    require(count==lock['gene_count'] and (directory/'expression.tsv').read_bytes()==expected and
        (directory/'samples.tsv').read_bytes()==(study/lock['files']['samples']['relative_path']).read_bytes(),
        'All selected expression decimals or original sample metadata changed')
    return dict(original_source_rows=count,selected_columns=len(ids),all_expression_decimals_byte_equal=True,
        expression_sha256=hashlib.sha256(expected).hexdigest(),no_statistical_fit=True)


def direct(prefix,source,output,study,lock,definition,*,bad=False):
    work=Path(os.environ['TMPDIR'])/('direct-bad' if bad else 'direct-good');work.mkdir()
    command=[*prefix,'run','--rm','--pull=never','--network=none','--read-only','--security-opt=no-new-privileges',
        '--cpus=1','--memory=1g','--pids-limit=64','--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),
        '-v',str(study)+':/study:ro','-v',str(source)+':/source:ro','-v',str(work)+':/outputs:rw',
        '-e','PYTHONDONTWRITEBYTECODE=1']
    bad_config=Path(os.environ['TMPDIR'])/'bad-config.input'
    if bad:
        bad_config.write_bytes((study/lock['files']['config']['relative_path']).read_bytes()+b'\n')
        command+=['-v',str(bad_config)+':/bad-config.input:ro']
    for index,name in enumerate(INPUTS):
        value='/bad-config.input' if bad and index==0 else '/study/'+lock['files'][name]['relative_path']
        command+=['-e','AUTONOMICS_INPUT'+str(index)+'='+value]
    for index,port in enumerate(definition['ports']['outputs']):command+=['-e','AUTONOMICS_OUTPUT'+str(index)+'=/outputs/'+port['path']]
    command+=['--entrypoint=python3',IMAGE,'-I','-S','-B','/source/scripts/run-intake.py']
    write(output/'command.json',command)
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    (output/'stdout.log').write_text(result.stdout);(output/'stderr.log').write_text(result.stderr)
    require(type(result.returncode) is int and (result.returncode==2 if bad else result.returncode==0),'Actual declared-port Python intake execution failed')
    if bad:
        require('frozen source bytes differ' in result.stderr and not list(work.iterdir()),'Wrong source must fail before publishing any result')
    else:
        for port in definition['ports']['outputs']:shutil.copyfile(work/port['path'],output/port['path'])
    return dict(exit=result.returncode,inputs=19,declared_outputs=10,wrong_source_refused=bad,normal_outputs=0 if bad else 10)


def authorize():
    require(digest(regular(AUTHORIZATION))==AUTHORIZATION_SHA and stat.S_IMODE(AUTHORIZATION.stat().st_mode)==0o600,
        'Exact private bounded user authorization required')
    value=json.loads(AUTHORIZATION.read_text())
    require(value['schema']=='USER_AUTHORIZED_BOUNDED_LEGACY_TECHNICAL_REPLAY_V1' and value['authorized_scope']==FULL_SCOPE and
        value['user_reply']=='允许隔离技术复现' and value['plugin_code_revision']==REVISION and
        value['cohort']==dict(source_samples=46,primary_samples=22,case_n=17,control_n=5,gene_count=23786) and
        value['models']==list(MODELS) and value['fresh_original_byte_verifier_session']==FRESH and
        value['fresh_original_byte_verifier_manifest_sha256']==FRESH_SEAL and
        value['execution_constraints']['independent_official_reference_comparison_allowed'] is True and
        value['execution_constraints']['production_restart_allowed'] is False and
        value['execution_constraints']['frozen_configuration_changes_allowed'] is False and value['g0_granted'] is False,
        'Bounded technical authorization cannot be extended to other inputs, models, restart or G0')


def copy_sources(work,study,lock,*,bad=False):
    for name in INPUTS:
        original=study/lock['files'][name]['relative_path'];target=work/(name+'.input')
        shutil.copyfile(original,target)
        require(digest(target)==lock['files'][name]['sha256'],'Private source copy identity differs')
    if bad:
        filename=work/'config.input';filename.write_bytes(filename.read_bytes()+b'\n')


def dispatched_bindings(work,analysis,nodes,edges,scratch):
    expected=[edge for edge in edges if edge['to']==analysis['id']]
    bindings=analysis['inputs']
    require(len(bindings)==len(expected),'Complete actual method edge inventory required')
    if analysis['port_assignments']:
        workspace=Path(next(iter(analysis['port_assignments'].values()))['path']).parent
        candidates=workspace/'.autonomics/inputs'
    else:candidates=scratch
    records=[]
    for edge in expected:
        binding=next((item for item in bindings if item['to_port']==edge['to_port']),None)
        require(binding is not None and binding['from']==edge['from'] and binding['from_port']==edge['from_port'],
            'Actual graph input edge differs')
        original=nodes[edge['from']]['port_assignments'][str(edge['from_port'])]['path']
        original=work/original.removeprefix('vfs:///') if original.startswith('vfs:///') else Path(original)
        matches=list(candidates.rglob('input-'+str(edge['to_port'])+'.*'))
        matches=[filename for filename in matches if filename.parent.name=='inputs' and filename.parent.parent.name=='.autonomics']
        require(len(matches)==1 and not matches[0].is_symlink() and matches[0].resolve().is_relative_to(scratch.resolve()) and
            digest(matches[0])==digest(original) and binding['fingerprint']['size']==original.stat().st_size,
            'Actual staged file bytes or ownership differs')
        records.append(dict(from_node=edge['from'],from_port=edge['from_port'],to_port=edge['to_port'],
            source_sha256=digest(original),staged_sha256=digest(matches[0])))
    return records


def actual_ports(work,definition,analysis,scratch):
    assignments=analysis['port_assignments'];run_name=analysis['execution']['run_name']
    require(isinstance(run_name,str) and re.fullmatch('autonomics-container-command-[0-9]+-[0-9]+',run_name) and
        set(assignments)=={str(index) for index in range(len(definition['ports']['outputs']))},'Exact actual run and complete port inventory required')
    published_root=work/definition['artifact_prefix'].removeprefix('/')/run_name
    result=[]
    for index,port in enumerate(definition['ports']['outputs']):
        value=assignments[str(index)];live=regular(Path(value['path']));published=regular(published_root/port['path'])
        require(live.resolve().is_relative_to(scratch.resolve()) and published.resolve().is_relative_to(work.resolve()) and
            live.name==port['path'] and live.stat().st_size>0 and value['format']==port['format'] and
            value['fingerprint']['size']==live.stat().st_size and digest(live)==digest(published),
            'Exact actual-run owned live/published port differs')
        recorded=value['fingerprint'].get('content_hash')
        require(recorded is None or recorded.removeprefix('sha256:')==digest(live),'Recorded actual output hash differs')
        result.append(published)
    return result


def expected_refusal(node,image,marker,scratch):
    execution=node.get('execution')
    require(node['status']=='failed' and isinstance(execution,dict) and type(execution.get('exit_code')) is int and
        execution['exit_code']==2 and execution.get('image')==image and execution.get('image_digest')==image.split('@',1)[1],
        'Expected method refusal must not be an environment/container failure')
    stderr=regular(Path(execution['stderr_log']['path']))
    require(stderr.resolve().is_relative_to(scratch.resolve()) and marker in stderr.read_text() and
        marker in node['error']['message'],'Actual frozen source/receipt refusal diagnostic required')
    return stderr


def expected_upstream_skip(node,failed):
    require(node['status']=='skipped' and node.get('execution') is None and not node['port_assignments'] and
        node.get('skipped_because')==failed,'Failed upstream must produce attributable skipped nodes, not failed/cancelled work')


def graph(runner,build,work,job,definitions,*,failure=None):
    write(work/'job.json',job)
    admission=subprocess.run([str(runner),'--validate-job',str(work/'job.json')],capture_output=True,text=True,timeout=60)
    (work/'admission.stdout').write_text(admission.stdout);(work/'admission.stderr').write_text(admission.stderr)
    require(admission.returncode==0,'Actual guarded job preflight failed; computation not started')
    admitted=json.loads(admission.stdout)
    require(admitted['scope']==job['scope'] and admitted['job_validated_without_execution'] is True and
        admitted['containers_started'] is False and admitted['scientific_results_computed'] is False and
        admitted['g0_granted'] is False,'Actual guarded no-execution admission receipt differs')
    run=subprocess.run([str(runner),str(work/'job.json')],capture_output=True,text=True,timeout=900)
    (work/'runner.stdout').write_text(run.stdout);(work/'runner.stderr').write_text(run.stderr)
    require(run.returncode==0,'Isolated bounded graph runner failed before reporting the DAG')
    report=json.loads((work/'dag-report.json').read_text());nodes={node['id']:node for node in report['first_run']['nodes']}
    require(len(nodes)==len(job['nodes']) and set(nodes)=={node['id'] for node in job['nodes']} and
        report['engine_source_revision']==build['engine_commit'] and report['input_hashing']=='ContentRequired' and
        report['max_concurrency']==1 and report['incremental'] is False and report['native_statistical_factories_registered'] is False and
        report['original_manifest_sha256']==job['plugin_manifest_sha256'] and report['g0_granted'] is False,
        'Exact bounded isolated graph identity required')
    require(report['scope']==('REAL_LOCKED_LEGACY_THREE_MODEL_TECHNICAL_REPLAY' if job['scope']==FULL_SCOPE else
        'REAL_LOCKED_LEGACY_TRANSPORT_NO_FIT') and report['current_daemon_verified'] is False and
        report['explicit_replay_scope_allows_fit'] is (job['scope']==FULL_SCOPE), 'Actual guarded replay scope differs')
    expected_extras=[dict(plugin_name=extra['expected_plugin_name'],original_manifest_sha256=extra['plugin_manifest_sha256'],
        script_sha256=extra['script_sha256'],panels=[])
        for extra in job['additional_plugins']]
    require(report['additional_plugin_identities']==expected_extras,'Actual additional official plugin identity differs')
    scratch=Path(os.environ['TMPDIR'])/'official-plugin-container-workspaces'/work.name
    ports={};bindings={};readbacks={}
    for record in job['nodes']:
        node=nodes[record['id']]
        if record['kind']=='file_reference':
            require(node['status']=='success','All reference nodes must succeed')
            continue
        if failure is None:
            require(node['status']=='success' and node['execution']['exit_code']==0,'Actual complete production-kind graph failed')
            definition=definitions[record['kind']]
            require(node['execution']['image']==definition['expected_image'] and
                node['execution']['image_digest']==definition['expected_image'].split('@',1)[1],'Actual production-kind image differs')
            ports[record['id']]=actual_ports(work,definition,node,scratch)
            bindings[record['id']]=dispatched_bindings(work,node,nodes,job['edges'],scratch)
            readbacks[record['id']]=[]
            for filename in ports[record['id']]:
                if filename.suffix=='.json':
                    parsed=json.loads(filename.read_text());readbacks[record['id']].append(dict(path=filename.name,json_keys=sorted(parsed)))
                elif filename.suffix=='.tsv':
                    header,rows=table(filename);readbacks[record['id']].append(dict(path=filename.name,columns=len(header),rows=len(rows)))
                else:readbacks[record['id']].append(dict(path=filename.name,sha256=digest(filename),RDS_object_comparison_required=True))
        elif record['id']==failure:
            marker='frozen source bytes differ' if failure=='intake' else 'actual complete official limma method receipt without scientific authority required'
            stderr=expected_refusal(node,definitions[record['kind']]['expected_image'],marker,scratch)
            shutil.copyfile(stderr,work/'expected-refusal.stderr')
            bindings[record['id']]=dispatched_bindings(work,node,nodes,job['edges'],scratch)
        else:
            expected_upstream_skip(node,failure)
    if failure:
        require(report['first_run']['errors'] and not list((work/'artifacts').rglob('family.tsv')) and
            not list((work/'artifacts').rglob('results.tsv')) and not list((work/'artifacts').rglob('config.json')),
            'Refusal must not publish normal result artifacts')
    else:require(not report['first_run']['errors'],'Positive graph reported errors')
    write(work/'transport-verification.json',dict(nodes=len(nodes),edges=len(job['edges']),bindings=bindings,readbacks=readbacks,
        published_ports=sum(len(value) for value in ports.values()),expected_failure=failure,g0_granted=False))
    return ports


def original_reference_block(text):
    start='  con<-gzfile(file.path(root,cfg$matrix_file));lines<-readLines(con);close(con)'
    require(text.count(start)==1,'Unique complete original run-B source/numerical block required')
    begin=text.index(start);end=text.find('\n} else stop(',begin)
    require(end>begin,'Complete original run-B block terminator required')
    return text[begin:end]


def official_reference(prefix,output,study,lock):
    frozen=study/lock['files']['scientific_code']['relative_path']
    require(digest(frozen)=='f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd','Exact frozen scientific program required')
    block=original_reference_block(frozen.read_text())
    reference=output/'official-reference';reference.mkdir()
    (reference/'frozen-scientific-source.R').write_bytes(frozen.read_bytes())
    (reference/'unaltered-run-B-source-numeric-block.R').write_text(block)
    program='''options(stringsAsFactors=FALSE,warn=1)
Sys.setenv(OMP_NUM_THREADS=1,OPENBLAS_NUM_THREADS=1,MKL_NUM_THREADS=1)
set.seed(432202610)
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("limma"))=="3.68.5",as.character(packageVersion("stats"))=="4.6.1")
root<-"/study";out<-file.path(root,"03_AUDIT/G0_v4.3.2_2026-10-11");dest<-"/reference"
cfg<-jsonlite::read_json(file.path(out,"B_ANALYSIS_CONFIG.json"),simplifyVector=TRUE)
read_tsv<-function(name) read.delim(file.path(out,name),check.names=FALSE,colClasses="character")
adjust_full<-function(p,method="BH") p.adjust(ifelse(is.finite(p),p,1),method=method)
original_write<-utils::write.table
write.table<-function(x,file,...) {
 original_write(x,file,...)
 saveRDS(list(fit=fit,variable_gene_ids=rownames(expr)[variable],full_gene_ids=rownames(expr)),file.path(dest,paste0(model,"-fit.rds")))
}
'''+block+'\n'
    (reference/'run-reference.R').write_text(program)
    command=[*prefix,'run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=1g',
        '--pids-limit=64','--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),'--tmpfs=/tmp:rw,size=64m',
        '-v',str(study)+':/study:ro','-v',str(reference)+':/reference:rw','--entrypoint=/opt/b-bulk/bin/Rscript-vanilla',
        NORMALIZED_IMAGE,'/reference/run-reference.R']
    write(reference/'command.json',command)
    result=subprocess.run(command,capture_output=True,text=True,timeout=600)
    (reference/'stdout.log').write_text(result.stdout);(reference/'stderr.log').write_text(result.stderr)
    require(result.returncode==0,'Independent original full run-B numerical/reference process failed')
    return reference


def compare_reference_family(actual,expected,gene_count,model):
    numeric=['beta','moderated_se','df','lo','hi','p_raw','q_BH','q_BY']
    require(len(actual)==len(expected)==gene_count,'All full-family rows required')
    maximum={name:0. for name in numeric}
    for left,right in zip(actual,expected,strict=True):
        require(all(left[name]==right[name] for name in ['gene_id','status','role']),'Original full gene IDs/status/role differ')
        for name in numeric:
            if left[name]=='NA' or right[name]=='NA':require(left[name]==right[name],'Exact original missing mask differs')
            else:
                value,target=float(left[name]),float(right[name]);difference=abs(value-target)
                require(math.isfinite(value) and math.isfinite(target) and difference<=1e-12+1e-11*abs(target),
                    'Original complete official numeric field differs: '+model+'/'+name)
                maximum[name]=max(maximum[name],difference)
    return dict(model=model,rows=len(actual),numeric_fields=numeric,max_absolute_errors=maximum,atol=1e-12,rtol=1e-11)


def full_comparison(prefix,output,ports,reference,lock):
    records=[]
    for model in MODELS:
        _,actual=table(ports[model+'_family'][0]);_,expected=table(reference/('FULL_TRANSCRIPTOME_'+model+'.tsv'))
        records.append(compare_reference_family(actual,expected,lock['gene_count'],model))
    program=RDS_LEAF_VALIDATOR+'''root<-commandArgs(TRUE)[1]
jobs<-jsonlite::fromJSON(file.path(root,"RDS-comparison-input.json"),simplifyVector=FALSE)
for(job in jobs) {
 actual<-readRDS(job$actual);reference<-readRDS(job$reference)
 stopifnot(identical(names(actual),names(reference)),identical(actual$full_gene_ids,reference$full_gene_ids),
  identical(actual$variable_gene_ids,reference$variable_gene_ids),length(actual$full_gene_ids)==23786L,
  isTRUE(all.equal(actual,reference,tolerance=1e-11,check.attributes=TRUE)))
 leaf_equal(actual,reference)
 cat(job$model,"COMPLETE_RDS_OBJECT_EQUAL\n")
}
'''
    jobs=[]
    for model in MODELS:
        current=output/(model+'-actual.rds');shutil.copyfile(ports[model+'_limma'][2],current)
        jobs.append(dict(model=model,actual='/work/'+current.name,reference='/work/official-reference/'+model+'-fit.rds'))
    write(output/'RDS-comparison-input.json',jobs);(output/'RDS-comparison.R').write_text(program)
    command=[*prefix,'run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=1g',
        '--pids-limit=64','--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),'--tmpfs=/tmp:rw,size=64m',
        '-v',str(output)+':/work:ro','--entrypoint=/opt/b-bulk/bin/Rscript-vanilla',NORMALIZED_IMAGE,'/work/RDS-comparison.R','/work']
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    (output/'RDS-comparison.stdout').write_text(result.stdout);(output/'RDS-comparison.stderr').write_text(result.stderr)
    require(result.returncode==0 and result.stdout.splitlines()==[model+' COMPLETE_RDS_OBJECT_EQUAL' for model in MODELS],
        'Complete official RDS object readback/comparison failed')
    return records


def validator_preflight(prefix,output):
    program=output/'RDS-validator-selftest.R';program.write_text(RDS_LEAF_VALIDATOR+RDS_LEAF_SELFTEST)
    command=[*prefix,'run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=256m',
        '--pids-limit=64','--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),'--tmpfs=/tmp:rw,size=16m',
        '-v',str(program)+':/selftest.R:ro','--entrypoint=/opt/b-bulk/bin/Rscript-vanilla',NORMALIZED_IMAGE,'/selftest.R']
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (output/'RDS-validator.stdout').write_text(result.stdout);(output/'RDS-validator.stderr').write_text(result.stderr)
    require(result.returncode==0 and result.stdout.splitlines()==['ELEMENTWISE_RDS_VALIDATOR_2_POSITIVE_5_REFUSALS_PASS'],
        'Actual non-fitting RDS elementwise validator preflight failed')
    write(output/'RDS-validator-preflight.json',dict(command=command,actual_exit=result.returncode,
        program_sha256=digest(program),positive_cases=2,refusal_cases=5,no_statistical_fit=True))


def build_membership(archives,runner,record,seal):
    runner=regular(runner);record=regular(record)
    archive=next((parent for parent in record.parents if re.fullmatch('[0-9a-f]{32}',parent.name) and parent.parent==archives),None)
    require(archive is not None,'Sealed new explicit-replay runner archive required')
    checked=sealed_archive(archive,seal,successful=True);artifacts=archive/'artifacts'
    require(runner.parent==record.parent and runner.is_relative_to(artifacts) and record.is_relative_to(artifacts) and
        runner.relative_to(artifacts).as_posix() in checked['manifest']['files'] and
        record.relative_to(artifacts).as_posix() in checked['manifest']['files'],
        'Runner and build record must be exact members of the same sealed successful archive')
    build=json.loads(record.read_text());built=build['executables']['runner']
    require(type(build['actual_build_exit']) is int and build['actual_build_exit']==0 and digest(runner)==built['sha256'] and
        built['executable']=='official_plugin_dag' and runner.name==built['executable'] and
        build['parent_commit']=='4ceefbd821baab8deebb070645a2fb8b1fa8e1ba',
        'Exact successful compiled no-fit/full-replay guard runner required')
    return archive,{**build,'executable_sha256':built['sha256']}


def post_verifier(output,study,lock):
    script=regular(study/lock['files']['byte_verifier']['relative_path'])
    require(digest(script)==lock['files']['byte_verifier']['sha256'],'Original whole-byte verifier changed')
    command=['/usr/bin/python3','-I','-B',str(script)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=600)
    (output/'post-verifier.stdout.json').write_text(result.stdout);(output/'post-verifier.stderr.log').write_text(result.stderr)
    record=dict(actual_exit=result.returncode,script_sha256=digest(script),
        runtime_manifest_sha256=lock['files']['runtime_manifest']['sha256'],actual_report=json.loads(result.stdout),g0_granted=False)
    fresh_gate(record);write(output/'post-verifier.json',record)
    return dict(actual_exit=result.returncode,passed=True,hash_checks=record['actual_report']['hash_checks'],
        unique_file_hashes=record['actual_report']['unique_file_hashes'],scientific_release=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner',type=Path);parser.add_argument('--build-record',type=Path)
    parser.add_argument('--build-seal');parser.add_argument('--direct-only',action='store_true');args=parser.parse_args()
    require(args.direct_only or all([args.runner,args.build_record,args.build_seal]),'Full graph proof requires final guarded runner identity')
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),'Managed validation required')
    archives=Path.home()/'.local/state/autonomics/validation-archives'
    verified=sealed_archive(archives/FRESH,FRESH_SEAL,successful=True)
    gate=json.loads((archives/FRESH/'artifacts/permanent/frozen-project-readonly-byte-audit/VERIFICATION.json').read_text());fresh_gate(gate)
    authorize()
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'locked-b-source-transport';output.mkdir(mode=0o700)
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    source=output/'source';(source/'scripts').mkdir(parents=True)
    for name,pin in PINS.items():
        value=subprocess.check_output(['git','-C',str(ROOT),'show',REVISION+':plugins/frozen-b-project/'+name])
        require(hashlib.sha256(value).hexdigest()==pin,'Exact unmodified published production method required')
        (source/name).write_bytes(value)
    lock=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',REVISION+':plugins/frozen-b-project/project-lock.json']))
    normalized=output/'normalized-source';(normalized/'scripts').mkdir(parents=True)
    for name,pin in NORMALIZED_PINS.items():
        value=subprocess.check_output(['git','-C',str(ROOT),'show',REVISION+':plugins/bulk-limma-normalized/'+name])
        require(hashlib.sha256(value).hexdigest()==pin,'Exact unmodified published official R transport required')
        (normalized/name).write_bytes(value)
    manifest=tomllib.loads((source/'manifest.toml').read_text());definition=next(node for node in manifest['nodes'] if node['kind']=='frozen_b_legacy_intake')
    sources=preflight_sources(STUDY,lock)
    available=resource_preflight(output,'initial')
    write(output/'preflight.json',dict(scope='REAL_LOCKED_LEGACY_SOURCE_TRANSPORT_NO_FIT',source_revision=REVISION,
        source_identities=sources,fresh_verifier_session=FRESH,fresh_verifier_manifest_sha256=FRESH_SEAL,
        fresh_verifier_archive_members_rehashed=len(verified['manifest']['files']),mem_available_bytes=available,
        no_production_restart=True,statistical_fit_performed_during_preflight=False,private_artifacts_not_for_publication=True))
    prefix=inspect_backend(output)
    owner=json.loads(OWNER.read_text());expected=next(item for item in owner['installed'] if item['label']=='B')
    inspection=subprocess.run([*prefix,'image','inspect',NORMALIZED_IMAGE],capture_output=True,text=True,check=True,timeout=60)
    (output/'R-image-inspect.json').write_text(inspection.stdout);actual=json.loads(inspection.stdout)[0]
    require(actual['Digest']==expected['installed_manifest_sha256'] and 'sha256:'+actual['Id'].removeprefix('sha256:')==expected['image_config_digest'] and
        actual['RootFS']['Layers']==expected['ordered_diff_ids'],'Fresh exact official R image identity required')
    good=output/'direct-good';good.mkdir();good_result=direct(prefix,source,good,STUDY,lock,definition)
    readback=validate_ports(good,definition,lock,sources);projection=independent_projection(good,STUDY,lock)
    bad=output/'direct-bad';bad.mkdir();bad_result=direct(prefix,source,bad,STUDY,lock,definition,bad=True)
    if args.direct_only:
        require(preflight_sources(STUDY,lock)==sources,'Canonical nineteen-source input identities changed')
        sealed_archive(archives/FRESH,FRESH_SEAL,successful=True)
        require(digest(OWNER)==OWNER_SHA and digest(AUTHORIZATION)==AUTHORIZATION_SHA,'Owner or user authorization changed')
        write(output/'verification.json',dict(status='DIRECT_REAL_LOCKED_19_SOURCE_10_PORT_TRANSPORT_ONLY_NOT_DAG_OR_FIT',
            direct_positive=good_result,wrong_sha_refusal=bad_result,readback=readback,independent_projection=projection,
            source_revision=REVISION,source_pins=PINS,canonical_sources_unchanged=True,statistical_fit_executed=False,
            actual_production_kind_DAG_executed=False,resident_production_deployment_qualified=False,g0_granted=False))
        return
    build_archive,build=build_membership(archives,args.runner,args.build_record,args.build_seal)
    runner=Path(os.environ['TMPDIR'])/'locked-b-plugin-dag';shutil.copyfile(args.runner,runner);runner.chmod(0o700)
    require(digest(runner)==build['executable_sha256'],'Owned explicit-replay runner copy differs')
    shutil.copyfile(args.build_record,output/'build-record.json')
    proxy=Path(os.environ['TMPDIR'])/'podman-proxy';proxy.mkdir();launcher=proxy/'podman'
    launcher.write_text('#!/usr/bin/python3\nimport os,sys\nos.execv('+repr(prefix[0])+','+repr(prefix)+'+sys.argv[1:])\n');launcher.chmod(0o700)
    os.environ['PATH']=str(proxy)+os.pathsep+os.environ['PATH']
    normalized_manifest=tomllib.loads((normalized/'manifest.toml').read_text())
    definitions={node['kind']:{**node,'expected_image':data['image']['reference']}
        for data in [manifest,normalized_manifest] for node in data['nodes']}
    transport=output/'intake-positive';transport.mkdir();copy_sources(transport,STUDY,lock)
    transport_ports=graph(runner,build,transport,job_for(transport,source),definitions)
    require(all(digest(filename)==digest(good/filename.name) for filename in transport_ports['intake']),
        'Actual production-kind intake DAG differs from direct same-source execution')
    intake_directory=transport_ports['intake'][0].parent
    validate_ports(intake_directory,definition,lock,sources)
    historical=output/'historical-family-refusal';historical.mkdir()
    require(digest(regular(HISTORICAL))==HISTORICAL_SHA,'Exact original real 23-column result required')
    old_audit=DELIVERY/'LIMMA_AUDIT_primary.json';old=json.loads(old_audit.read_text());receipt=json.loads((good/'intake.json').read_text())
    old_header,_=table(HISTORICAL)
    require(len(old_header)==23 and 'q_BH' not in old_header and 'family_adjustment' not in old and
        old['plugin_transport_output_sha256']['results']==HISTORICAL_SHA and old['input_sha256']==receipt['input_sha256'] and
        old['config_sha256']==receipt['config_sha256'],'Historical refusal must use actual unadjusted official results, not old Python q')
    for original,name in [(HISTORICAL,'historical-results.tsv'),(good/'genes.tsv','genes.tsv'),(good/'intake.json','intake.json'),(old_audit,'historical-audit.json')]:
        shutil.copyfile(original,historical/name)
    graph(runner,build,historical,job_for(historical,source,family=True),definitions,failure='family')
    validator_preflight(prefix,output)
    resource_preflight(output,'before-full-DAG')
    full=output/'full-positive';full.mkdir();copy_sources(full,STUDY,lock)
    full_job=job_for(full,source,normalized=normalized,authorization=(AUTHORIZATION,AUTHORIZATION_SHA))
    full_ports=graph(runner,build,full,full_job,definitions)
    require(sum(len(value) for value in full_ports.values())==28,'All 28 declared processing output ports required')
    validate_ports(full_ports['intake'][0].parent,definition,lock,sources)
    bad_full=output/'full-bad-source';bad_full.mkdir();copy_sources(bad_full,STUDY,lock,bad=True)
    graph(runner,build,bad_full,job_for(bad_full,source,normalized=normalized,authorization=(AUTHORIZATION,AUTHORIZATION_SHA)),definitions,failure='intake')
    resource_preflight(output,'before-independent-reference')
    reference=official_reference(prefix,output,STUDY,lock)
    comparisons=full_comparison(prefix,output,full_ports,reference,lock)
    post_check=post_verifier(output,STUDY,lock)
    require(preflight_sources(STUDY,lock)==sources,'Canonical nineteen-source input identities changed')
    sealed_archive(archives/FRESH,FRESH_SEAL,successful=True)
    sealed_archive(build_archive,args.build_seal,successful=True)
    require(digest(OWNER)==OWNER_SHA and digest(AUTHORIZATION)==AUTHORIZATION_SHA,'Reviewed software owner or user authorization changed')
    write(output/'verification.json',dict(status='USER_AUTHORIZED_B_FULL_ISOLATED_TECHNICAL_REPLAY_PROVEN_NOT_DEPLOYED',direct_positive=good_result,
        wrong_sha_refusal=bad_result,readback=readback,independent_projection=projection,
        exact_production_kind='frozen_b_legacy_intake',source_revision=REVISION,source_pins=PINS,
        canonical_sources_unchanged=True,official_R_and_authorized_real_model_fit_executed=True,
        production_kind_intake_positive_DAG=dict(nodes=20,edges=19,published_ports=10),
        historical_family_refusal_DAG=dict(nodes=5,edges=4,normal_outputs=0,old_Python_q_used_as_official=False),
        full_positive_DAG=dict(nodes=29,edges=64,published_processing_ports=28,official_models=3),
        full_wrong_source_DAG=dict(nodes=29,edges=64,method_failure='intake',downstream_methods_not_executed=9),
        official_reference=dict(unaltered_original_run_B_source_and_numeric_block=True,independent_R_process=True,
            all_23786_rows_per_model=True,complete_RDS_objects_compared=True,comparisons=comparisons,
            original_whole_R_program_guards_executed=False),
        explicit_user_authorization_sha256=AUTHORIZATION_SHA,original_full_verifier_evidence_unchanged=True,
        actual_original_whole_root_post_verification=post_check,
        resident_production_deployment_qualified=False,scientific_authorization_granted=False,g0_granted=False))


if __name__=='__main__':
    try:
        main()
    except BaseException:
        location=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
        if location:
            output=Path(location)/'locked-b-source-transport'
            if output.is_dir():
                try:
                    lock=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',REVISION+':plugins/frozen-b-project/project-lock.json']))
                    write(output/'failure-source-postcheck.json',dict(canonical_sources=preflight_sources(STUDY,lock),
                        canonical_sources_unchanged=True,method_success_inferred=False))
                except Exception as error:
                    write(output/'failure-source-postcheck-error.json',dict(error=str(error),method_success_inferred=False))
        raise
