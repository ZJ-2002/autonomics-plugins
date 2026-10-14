"""Replay all sealed full-precision LDSC cases through the reusable plugin DAG."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports, digest, normalize_engine_log, panels, write
from tools.prove_ldsc_entrypoints import checked_reference

ROOT=Path(__file__).resolve().parents[1]
REFERENCE="80cfad43df464152bc4c7561829a4b7c"
COMPARATOR=ROOT/'plugins/ldsc-precision/tests/run_precision_container_assurance.py'
spec=importlib.util.spec_from_file_location('sealed_precision_comparator',COMPARATOR)
comparison=importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def compare_state(actual,reference):
    fields=[[list(path),kind,value] for path,kind,value in comparison.state_fields(actual)]
    if fields!=reference:
        raise RuntimeError("Complete official returned fields, metadata or missingness differ")
    return dict(fields=len(fields),finite_fields=sum(kind=='NUMBER' for _,kind,_ in fields))


def check_inputs(work,originals,analysis,scratch):
    if len(analysis['inputs'])!=len(originals):
        raise RuntimeError("Complete precision input-port inventory required")
    records=[]
    for index,original in enumerate(originals):
        source=work/original.name
        suffix=''.join(original.suffixes)
        found=[path for path in scratch.rglob(f'input-{index}{suffix}') if path.parent.name=='inputs' and path.parent.parent.name=='.autonomics']
        bound=next((item for item in analysis['inputs'] if item['to_port']==index),None)
        if (len(found)!=1 or bound is None or bound['from']!='input'+str(index)
                or bound['path']!='vfs:///'+original.name or bound['fingerprint']['size']!=source.stat().st_size
                or not (found[0].resolve().is_relative_to(scratch) or found[0].resolve()==source.resolve())
                or digest(found[0])!=digest(original) or digest(source)!=digest(original)):
            raise RuntimeError("Exact staged configuration/data/panel input bytes required")
        records.append(dict(port=index,sha256=digest(found[0]),bytes=found[0].stat().st_size))
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner',required=True,type=Path)
    parser.add_argument('--build-record',required=True,type=Path)
    parser.add_argument('--archives',required=True,type=Path)
    arguments=parser.parse_args()
    permanent=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent:
        raise RuntimeError('Managed validation required')
    build=json.loads(arguments.build_record.read_text())
    if build['actual_build_exit']!=0 or digest(arguments.runner)!=build['executable_sha256']:
        raise RuntimeError('Exact successful generic probe compiler artifact required')
    runner=Path(os.environ['TMPDIR'])/'official_plugin_dag'
    with arguments.runner.open('rb') as source,runner.open('xb') as destination:
        shutil.copyfileobj(source,destination)
    runner.chmod(0o700)
    if digest(runner)!=build['executable_sha256']:
        raise RuntimeError('Owned executable copy differs')
    reference=checked_reference(arguments.archives/REFERENCE)
    reference_report=json.loads((reference/'RESULT.json').read_text())
    family=ROOT/'plugins/ldsc-precision'
    if digest(family/'scripts/precision.py')!=reference_report['method_script']['sha256']:
        raise RuntimeError('Current method differs from the independent qualified reference')
    if digest(family/'manifest.toml')!=reference_report['manifest']['sha256']:
        raise RuntimeError('Current precision manifest differs from the qualified reference')
    output=Path(permanent)/'ldsc-precision-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__),output/'driver.py')
    shutil.copyfile(COMPARATOR,output/'state-comparator.py')
    shutil.copyfile(arguments.build_record,output/'build-record.json')
    source=output/'source'
    (source/'scripts').mkdir(parents=True)
    shutil.copyfile(family/'manifest.toml',source/'manifest.toml')
    shutil.copyfile(family/'scripts/precision.py',source/'scripts/precision.py')
    manifest=tomllib.loads((source/'manifest.toml').read_text())
    if manifest['plugin_name']!='ldsc-precision' or manifest['image']['reference']!=reference_report['image']:
        raise RuntimeError('Exact declared precision plugin identity required')
    cases=[(item['method']+'-'+item['scale'],item['method'],False) for item in reference_report['cases']]
    cases.extend(('negative-'+item['defect'],'rg',True) for item in reference_report['negative_cases'])
    records=[]
    for name,method,negative in cases:
        original=reference/name
        work=output/name
        work.mkdir()
        bundles,panel_hashes=panels(work,reference/'panels')
        originals=[original/'config.json',original/'input-0']+([original/'input-1'] if method=='rg' else [])+[original/'panel-manifest.json']
        nodes=[]
        edges=[]
        for index,path in enumerate(originals):
            shutil.copyfile(path,work/path.name)
            nodes.append(dict(id='input'+str(index),kind='file_reference',spec=dict(path='vfs:///'+path.name,format='json' if path.suffix=='.json' else 'tsv')))
            edges.append(dict(from_port=0,to_port=index,**{'from':'input'+str(index),'to':'analysis'}))
        kind='ldsc_'+method+'_frozen_precision'
        definition=next(item for item in manifest['nodes'] if item['kind']==kind)
        nodes.append(dict(id='analysis',kind=kind,spec={}))
        overrides=[dict(binding=panel['binding'],declared_bundle=panel['bundle'],mount=panel['mount'],
                        synthetic_bundle=next(bundle['ident'] for bundle in bundles if bundle['source']=='/synthetic-panels/'+panel['binding'])) for panel in manifest['panels']]
        job=dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0',expected_plugin_name='ldsc-precision',run_root=str(work),plugin_manifest=str(source/'manifest.toml'),
                 plugin_manifest_sha256=digest(source/'manifest.toml'),script_sha256={'scripts/precision.py':digest(source/'scripts/precision.py')},
                 panel_overrides=overrides,bundles=bundles,panel_manifest_sha256=panel_hashes,nodes=nodes,edges=edges)
        write(work/'job.json',job)
        with (work/'runner.stdout').open('wb') as stdout,(work/'runner.stderr').open('wb') as stderr:
            completed=subprocess.run([str(runner),str(work/'job.json')],stdout=stdout,stderr=stderr,timeout=300)
        if completed.returncode:
            raise RuntimeError('Actual generic DAG runner failed: '+name)
        report=json.loads((work/'dag-report.json').read_text())
        if (report['engine_source_revision']!=build['engine_commit'] or report['scope']!=job['scope'] or report['plugin_name']!='ldsc-precision'
                or report['input_hashing']!='ContentRequired' or report['max_concurrency']!=1 or report['incremental'] is not False
                or report['original_manifest_sha256']!=job['plugin_manifest_sha256'] or report['g0_granted'] is not False
                or report['native_statistical_factories_registered'] is not False):
            raise RuntimeError('Actual generic probe source identity or scope differs')
        first=report['first_run']
        if {item['id'] for item in first['nodes']}!={node['id'] for node in nodes}:
            raise RuntimeError('Complete actual graph inventory required')
        analysis=next(item for item in first['nodes'] if item['id']=='analysis')
        if analysis['execution']['image']!=manifest['image']['reference']:
            raise RuntimeError('Actual precision image differs')
        scratch=Path(os.environ['TMPDIR'])/'official-plugin-container-workspaces'/name
        input_checks=check_inputs(work,originals,analysis,scratch)
        execution=work/'execution-evidence'
        execution.mkdir()
        for key in ['task_manifest','stdout_log','stderr_log']:
            item=analysis['execution'].get(key)
            if item is None:
                if key=='task_manifest': raise RuntimeError('Actual task evidence missing')
                continue
            path=Path(item['path'])
            if path.is_symlink(): raise RuntimeError('Execution evidence is symlinked')
            shutil.copyfile(path,execution/path.name)
            if digest(path)!=digest(execution/path.name): raise RuntimeError('Execution evidence changed')
        result=dict(case=name,kind=kind,nodes=len(nodes),edges=len(edges),input_bindings=input_checks,negative=negative)
        if negative:
            if not first['errors'] or analysis['status']!='failed' or analysis['execution']['exit_code']!=2 or list((work/'artifacts').rglob('result.json')):
                raise RuntimeError('Invalid method became a successful output')
            audits=list(scratch.rglob('audit.json'))
            if len(audits)!=1 or audits[0].is_symlink(): raise RuntimeError('Unique owned failure audit required')
            audit=json.loads(audits[0].read_text())
            expected=json.loads((original/'audit.json').read_text())
            if audit['status']!='BLOCKED' or audit['error']!=expected['error']:
                raise RuntimeError('Exact predeclared refusal reason differs')
            if any(list(scratch.rglob(name)) for name in ['result.json','bound_config.json','official_state.json']):
                raise RuntimeError('Refused method left normal analytical state')
            shutil.copyfile(audits[0],work/'preserved-failure-audit.json')
            result.update(outcome='EXACT_METHOD_REFUSAL_PRESERVED',published_ports=0,fields=0,finite_fields=0)
        else:
            if first['errors'] or any(item['status']!='success' for item in first['nodes']): raise RuntimeError('Positive DAG failed: '+name)
            ports=check_ports(work,definition,analysis,scratch)
            values={port['path']:path for port,path in zip(definition['ports']['outputs'],ports)}
            expected=json.loads((original/'result.json').read_text())
            if json.loads(values['result.json'].read_text())!=expected or json.loads(values['bound_config.json'].read_text())!=json.loads((original/'bound_config.json').read_text()):
                raise RuntimeError('Complete unrounded result or frozen configuration differs')
            state=compare_state(json.loads(values['official_state.json'].read_text()),json.loads((original/'direct-reference.json').read_text())['complete_returned_fields'])
            audit=json.loads(values['audit.json'].read_text())
            previous=json.loads((original/'audit.json').read_text())
            for key in ['warnings','complete_munged_source_receipts','panel_file_identities','official_runtime','result_status','config_identity','input_identities']:
                if audit[key]!=previous[key]: raise RuntimeError('Complete audit identity/semantics differ: '+key)
            substitutions=[]
            for index in range(1,len(originals)-1):
                substitutions.extend([(f'/work/.autonomics/inputs/input-{index}',f'<INPUT{index-1}>'),(f'/work/input-{index-1}',f'<INPUT{index-1}>')])
            actual_arguments=dict(audit['official_arguments'])
            expected_arguments=dict(previous['official_arguments'])
            for arguments in [actual_arguments,expected_arguments]:
                for key in ['h2','rg']:
                    if isinstance(arguments.get(key),str):
                        for before,after in substitutions:
                            arguments[key]=arguments[key].replace(before,after)
            if actual_arguments!=expected_arguments:
                raise RuntimeError('Complete dispatched official arguments differ')
            if normalize_engine_log(values['official.log'].read_text(),substitutions)!=normalize_engine_log((original/'official.log').read_text(),substitutions):
                raise RuntimeError('Complete official precision log differs')
            result.update(state,outcome='COMPLETE_AUTHOR_STATE_RESULT_AND_AUDIT_MATCHED',published_ports=len(ports))
        records.append(result)
        (output/'completed-cases.json').write_text(json.dumps(records,indent=2)+'\n')
    write(output/'verification.json',dict(status='PRECISION_PLUGIN_DAG_PROVEN_FIXED_SYNTHETIC_CASES',engine_commit=build['engine_commit'],executable_sha256=build['executable_sha256'],
          cases=records,independent_reference_recomputed=False,source_manifest_sha256=digest(source/'manifest.toml'),method_sha256=digest(source/'scripts/precision.py'),
          actual_research_panels_qualified=False,daemon_deployed=False,formal_authorized=False,g0_granted=False))
    print(json.dumps(dict(cases=len(records),positive=sum(not row['negative'] for row in records),g0_granted=False)))


if __name__=='__main__':
    main()
