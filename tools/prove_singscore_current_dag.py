"""Replay the complete frozen singscore counterexample inventory on the current probe."""

import argparse
import ast
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports,digest,write
from tools.prove_ldsc_precision_dag import check_inputs

ROOT=Path(__file__).resolve().parents[1]
REFERENCE_SEAL='bc29100f60061395cd96ae3b03effd988e9d763e64dd242af9f2c1e65b00b224'
EXISTING='test_preexisting_score_is_not_overwritten'


def reference(root):
    if digest(root/'SEALED_FILES.json')!=REFERENCE_SEAL:
        raise RuntimeError('Exact unchanged singscore reference seal required')
    records=json.loads((root/'SEALED_FILES.json').read_text())
    actual={path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() and path.name!='SEALED_FILES.json'}
    if actual!={record['path'] for record in records}:
        raise RuntimeError('Complete frozen reference membership required')
    for record in records:
        path=root/record['path']
        if path.is_symlink() or path.stat().st_size!=record['bytes'] or digest(path)!=record['sha256']:
            raise RuntimeError('Frozen singscore reference artifact differs')
    evidence=json.loads((ROOT/'evidence/canonical-singscore-20261011.json').read_text())
    if digest(root/'official-singscore_1.32.0.tar.gz')!=evidence['official_implementation']['reference_archive_sha256']:
        raise RuntimeError('Independent official package source differs')
    for name in ['plugins/singscore/manifest.toml','plugins/singscore/scripts/singscore.sh','plugins/singscore/tests/test_contract.py','plugins/singscore/tests/verify_outputs.R']:
        if digest(ROOT/name)!=evidence['source_tree_sha256'][name]:
            raise RuntimeError('Current method/test contract differs from qualified reference')
    methods={node.name for node in ast.walk(ast.parse((ROOT/'plugins/singscore/tests/test_contract.py').read_text())) if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')}
    cases={path.name for path in (root/'after').iterdir() if path.is_dir()}
    if len(methods)!=31 or cases!=methods:
        raise RuntimeError('Complete fixed 31-case inventory required')
    return evidence,sorted(cases)


def expected_error(case):
    lines=[line for line in (case/'node.stderr.txt').read_text().splitlines() if line.startswith('ERROR: ')]
    if len(lines)!=1:
        raise RuntimeError('Exact frozen method refusal diagnostic required')
    return lines[0]


def job_for(work,source):
    inputs=['matrix.tsv','signature.tsv','samples.tsv']
    nodes=[dict(id='input'+str(index),kind='file_reference',spec=dict(path='vfs:///'+name,format='tsv')) for index,name in enumerate(inputs)]
    nodes.append(dict(id='analysis',kind='singscore_bspec',spec={}))
    edges=[dict(from_port=0,to_port=index,**{'from':'input'+str(index),'to':'analysis'}) for index in range(3)]
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0',expected_plugin_name='singscore',run_root=str(work),plugin_manifest=str(source/'manifest.toml'),
                plugin_manifest_sha256=digest(source/'manifest.toml'),script_sha256={'scripts/singscore.sh':digest(source/'scripts/singscore.sh')},
                panel_overrides=[],bundles=[],panel_manifest_sha256={},nodes=nodes,edges=edges)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner',required=True,type=Path)
    parser.add_argument('--build-record',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path)
    arguments=parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    evidence,cases=reference(arguments.reference)
    build=json.loads(arguments.build_record.read_text())
    if build['actual_build_exit']!=0 or digest(arguments.runner)!=build['executable_sha256']:
        raise RuntimeError('Exact verified generic probe required')
    runner=Path(os.environ['TMPDIR'])/'official_plugin_dag'
    with arguments.runner.open('rb') as source,runner.open('xb') as destination: shutil.copyfileobj(source,destination)
    runner.chmod(0o700)
    if digest(runner)!=build['executable_sha256']: raise RuntimeError('Owned executable copy differs')
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'singscore-current-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__),output/'driver.py')
    shutil.copyfile(arguments.build_record,output/'build-record.json')
    source=output/'source'
    (source/'scripts').mkdir(parents=True)
    for name in ['manifest.toml','scripts/singscore.sh','tests/verify_outputs.R']:
        destination=source/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'plugins/singscore'/name,destination)
    manifest=tomllib.loads((source/'manifest.toml').read_text())
    definition=manifest['nodes'][0]
    image=manifest['image']['reference']
    inventory=[(name,arguments.reference/'after'/name) for name in cases if name!=EXISTING]
    inventory.append(('official-author-example',arguments.reference/'after-official-example-dag-final'))
    checks=[]
    readback=[]
    for name,original in inventory:
        work=output/name
        work.mkdir()
        originals=[original/filename for filename in ['matrix.tsv','signature.tsv','samples.tsv']]
        for path in originals: shutil.copyfile(path,work/path.name)
        job=job_for(work,source)
        write(work/'job.json',job)
        with (work/'runner.stdout').open('wb') as stdout,(work/'runner.stderr').open('wb') as stderr:
            process=subprocess.run([str(runner),str(work/'job.json')],stdout=stdout,stderr=stderr,timeout=180)
        if process.returncode: raise RuntimeError('Current singscore DAG runner failed: '+name)
        report=json.loads((work/'dag-report.json').read_text())
        if (report['engine_source_revision']!=build['engine_commit'] or report['scope']!=job['scope'] or report['plugin_name']!='singscore'
                or report['input_hashing']!='ContentRequired' or report['incremental'] is not False or report['max_concurrency']!=1
                or report['original_manifest_sha256']!=job['plugin_manifest_sha256'] or report['g0_granted'] is not False):
            raise RuntimeError('Actual engine identity or scope differs')
        first=report['first_run']
        if len(first['nodes'])!=4 or {node['id'] for node in first['nodes']}!={'input0','input1','input2','analysis'}:
            raise RuntimeError('Actual four-node graph inventory differs')
        analysis=next(node for node in first['nodes'] if node['id']=='analysis')
        scratch=Path(os.environ['TMPDIR'])/'official-plugin-container-workspaces'/name
        inputs=check_inputs(work,originals,analysis,scratch)
        success=name=='official-author-example' or json.loads((original/'node.execution.json').read_text())['returncode']==0
        record=dict(case=name,positive=success,nodes=4,edges=3,input_bindings=inputs)
        if analysis['execution']['image']!=image: raise RuntimeError('Actual singscore image differs')
        if success:
            if first['errors'] or any(node['status']!='success' for node in first['nodes']):
                raise RuntimeError('Valid scoring case failed: '+name)
            ports=check_ports(work,definition,analysis,scratch)
            expected=arguments.reference/'official-example-fixture/official_reference.RDS' if name=='official-author-example' else original/'official_reference.RDS'
            shutil.copyfile(expected,work/'sealed-official-reference.RDS')
            readback.append(dict(case=name,actual_rds='/work/'+str(ports[1].relative_to(output)),reference_rds='/work/'+str((work/'sealed-official-reference.RDS').relative_to(output)),
                                 scores_tsv='/work/'+str(ports[0].relative_to(output)),metadata_tsv='/work/'+str((work/'samples.tsv').relative_to(output))))
            record.update(published_ports=3,outcome='SCORES_AND_FULL_RDS_PENDING_BATCH_REFERENCE_READBACK')
        else:
            if not first['errors'] or analysis['status']!='failed' or analysis['execution']['exit_code']!=1 or list((work/'artifacts').rglob('singscore_scores.tsv')):
                raise RuntimeError('Invalid score case became a successful result')
            logs=list(scratch.rglob('singscore.log'))
            if len(logs)!=1 or logs[0].is_symlink() or expected_error(original) not in logs[0].read_text():
                raise RuntimeError('Exact scoring refusal reason was not retained')
            if any(list(scratch.rglob(filename)) for filename in ['singscore_scores.tsv','singscore.RDS']):
                raise RuntimeError('Failed scoring case left normal results')
            shutil.copyfile(logs[0],work/'preserved-failure.log')
            record.update(published_ports=0,outcome='EXACT_METHOD_REFUSAL_PRESERVED')
        checks.append(record)
        (output/'completed-cases.json').write_text(json.dumps(checks,indent=2)+'\n')
    pairs=output/'readback-pairs.tsv'
    with pairs.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(readback[0]),delimiter='\t',lineterminator='\n');writer.writeheader();writer.writerows(readback)
    command=['podman','run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=1g','--tmpfs=/tmp:rw,size=32m',
             '-v',str(output)+':/work:ro','--entrypoint=Rscript',image,'--vanilla','/work/source/tests/verify_outputs.R','/work/readback-pairs.tsv']
    with (output/'full-RDS-readback.stdout').open('wb') as stdout,(output/'full-RDS-readback.stderr').open('wb') as stderr:
        compared=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=180)
    if compared.returncode or ('VERIFIED_PAIRS '+str(len(readback))) not in (output/'full-RDS-readback.stdout').read_text():
        raise RuntimeError('Complete official rank/score/dispersion RDS comparison failed')
    for record in checks:
        if record['positive']: record['outcome']='COMPLETE_OFFICIAL_RANK_SIMPLE_RDS_AND_TSV_MATCHED'
    original=arguments.reference/'after'/EXISTING
    work=output/EXISTING
    work.mkdir()
    for name in ['matrix.tsv','signature.tsv','samples.tsv']: shutil.copyfile(original/name,work/name)
    outputs=[work/port['path'] for port in definition['ports']['outputs']]
    outputs[0].write_bytes((original/'output/scores.tsv').read_bytes())
    sentinel=digest(outputs[0])
    direct=['podman','run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=1g','--tmpfs=/tmp:rw,size=32m',
            '-v',str(work)+':/work:rw','-v',str(source/'scripts/singscore.sh')+':/program.R:ro','--entrypoint=Rscript']
    for index,name in enumerate(['matrix.tsv','signature.tsv','samples.tsv']): direct+=['-e',f'AUTONOMICS_INPUT{index}=/work/{name}']
    for index,port in enumerate(definition['ports']['outputs']): direct+=['-e',f'AUTONOMICS_OUTPUT{index}=/work/'+port['path']]
    completed=subprocess.run(direct+[image,'--vanilla','/program.R'],capture_output=True,text=True,timeout=90)
    (work/'direct.stdout').write_text(completed.stdout);(work/'direct.stderr').write_text(completed.stderr)
    if completed.returncode!=1 or digest(outputs[0])!=sentinel or outputs[1].exists() or expected_error(original) not in outputs[2].read_text():
        raise RuntimeError('Direct preexisting-output guard failed or changed the sentinel')
    write(output/'verification.json',dict(status='CURRENT_SINGSCORE_DAG_AND_FULL_AUTHOR_OBJECTS_PROVEN_SCOPED',engine_commit=build['engine_commit'],executable_sha256=build['executable_sha256'],
          fixed_original_cases=31,DAG_cases=checks,author_example_additional=True,full_RDS_readbacks=len(readback),
          direct_no_clobber=dict(case=EXISTING,exit_code=1,sentinel_sha256=sentinel,unchanged=True,not_claimed_as_a_DAG_case=True),
          original_reference_seal=REFERENCE_SEAL,independent_reference_recomputed=False,method_sha256=digest(source/'scripts/singscore.sh'),
          study_background_coverage_donor_or_platform_eligibility_qualified=False,daemon_deployed=False,formal_authorized=False,g0_granted=False))
    print(json.dumps(dict(DAGs=len(checks),positive=sum(item['positive'] for item in checks),direct_no_clobber=1,g0_granted=False)))


if __name__=='__main__': main()
