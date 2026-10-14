"""Check generic-probe refusals and one already-qualified no-panel R transport."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports,digest,write


def sealed(archives,identity,expected,packet):
    artifacts=archives/identity/'artifacts'
    if digest(artifacts/'MANIFEST.json')!=expected: raise RuntimeError('Exact sealed fixture archive required')
    manifest=json.loads((artifacts/'MANIFEST.json').read_text())
    actual={path.relative_to(artifacts).as_posix() for path in artifacts.rglob('*') if path.is_file() and path.name!='MANIFEST.json'}
    if actual!=set(manifest['files']): raise RuntimeError('Complete fixture membership differs')
    for name,record in manifest['files'].items():
        path=artifacts/name
        if path.is_symlink() or path.stat().st_size!=record['bytes'] or digest(path)!=record['sha256']:
            raise RuntimeError('Sealed fixture changed')
    return artifacts/'permanent'/packet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner',required=True,type=Path)
    parser.add_argument('--build-record',required=True,type=Path)
    parser.add_argument('--archives',required=True,type=Path)
    arguments=parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ: raise RuntimeError('Managed validation required')
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'generic-plugin-guards'
    output.mkdir()
    shutil.copyfile(Path(__file__),output/'driver.py')
    build=json.loads(arguments.build_record.read_text())
    if build['actual_build_exit']!=0 or digest(arguments.runner)!=build['executable_sha256']:
        raise RuntimeError('Exact compiler artifact required')
    runner=Path(os.environ['TMPDIR'])/'official_plugin_dag'
    with arguments.runner.open('rb') as source,runner.open('xb') as destination: shutil.copyfileobj(source,destination)
    runner.chmod(0o700)
    if digest(runner)!=build['executable_sha256']: raise RuntimeError('Owned executable copy differs')
    reference=sealed(arguments.archives,'037b894e5ec94df0b41734bafc3aaaec','cfab74e29cf8bca58094c289d4a8ef892e079e51f7eaa814e091931a3420b14d','ldsc-precision-dag')
    base=json.loads((reference/'h2-observed/job.json').read_text())
    template=reference/'source'
    refusals=[]
    cases=[('manifest-hash','canonical manifest bytes differ'),('plugin-name','exact nonempty plugin identity required'),
           ('native-kind','undeclared node or native statistical fallback forbidden'),('engineering-collision','plugin cannot replace an engineering factory'),
           ('script-traversal','nonlocal script path forbidden'),('panel-mapping','declared panel mapping differs or is not explicitly synthetic')]
    for name,message in cases:
        work=output/name
        work.mkdir()
        family=work/'source'
        shutil.copytree(template,family)
        job=copy.deepcopy(base)
        job.update(run_root=str(work),plugin_manifest=str(family/'manifest.toml'))
        if name=='manifest-hash': job['plugin_manifest_sha256']='0'*64
        elif name=='plugin-name': job['expected_plugin_name']='WRONG'
        elif name=='native-kind': job['nodes'][-1]['kind']='linear_regression'
        elif name=='panel-mapping': job['panel_overrides'][0]['declared_bundle']='wrong/reference'
        else:
            path=family/'manifest.toml'
            text=path.read_text()
            if name=='engineering-collision': text=text.replace('kind = "ldsc_h2_frozen_precision"','kind = "file_reference"')
            else: text=text.replace('script_file = "scripts/precision.py"','script_file = "../outside.py"')
            path.write_text(text)
            job['plugin_manifest_sha256']=digest(path)
        write(work/'job.json',job)
        completed=subprocess.run([str(runner),str(work/'job.json')],capture_output=True,text=True,timeout=60)
        (work/'runner.stdout').write_text(completed.stdout)
        (work/'runner.stderr').write_text(completed.stderr)
        if completed.returncode!=1 or message not in completed.stderr or (work/'dag-report.json').exists() or (work/'artifacts').exists():
            raise RuntimeError('Exact generic guard was not enforced: '+name)
        refusals.append(dict(case=name,exit_code=completed.returncode,exact_guard_message=message,DAG_execution_not_entered=True))
    previous=sealed(arguments.archives,'5b167d8b53824d3aaae9585b9addb53f','581d816aeb53bedcd4eac71835a3f6875bf11f1cf7d2e624d8d1cad689c2fc92','current-official-r-stats-dag')
    original=previous/'adjust-BH'
    work=output/'no-panel-adjust-BH'
    work.mkdir()
    source=work/'source'
    shutil.copytree(previous/'source',source)
    for name in ['input0.tsv','input1.tsv']: shutil.copyfile(original/name,work/name)
    job=json.loads((original/'job.json').read_text())
    job.update(scope='TECHNICAL_PLUGIN_DAG_NOT_G0',expected_plugin_name='cachexia-r-stats',run_root=str(work),plugin_manifest=str(source/'manifest.toml'),
               plugin_manifest_sha256=digest(source/'manifest.toml'),script_sha256={'scripts/statistics.R':digest(source/'scripts/statistics.R')},
               panel_overrides=[],bundles=[],panel_manifest_sha256={})
    write(work/'job.json',job)
    completed=subprocess.run([str(runner),str(work/'job.json')],capture_output=True,text=True,timeout=120)
    (work/'runner.stdout').write_text(completed.stdout)
    (work/'runner.stderr').write_text(completed.stderr)
    if completed.returncode: raise RuntimeError('Actual no-panel transport failed')
    report=json.loads((work/'dag-report.json').read_text())
    first=report['first_run']
    if (report['engine_source_revision']!=build['engine_commit'] or report['native_statistical_factories_registered'] is not False
            or first['errors'] or len(first['nodes'])!=8 or any(item['status']!='success' for item in first['nodes'])):
        raise RuntimeError('Actual complete no-panel graph failed')
    analysis=next(item for item in first['nodes'] if item['id']=='analysis')
    import tomllib
    manifest=tomllib.loads((source/'manifest.toml').read_text())
    definition=next(item for item in manifest['nodes'] if item['kind']=='cachexia_r_p_adjust')
    scratch=Path(os.environ['TMPDIR'])/'official-plugin-container-workspaces'/work.name
    ports=check_ports(work,definition,analysis,scratch)
    if (work/'materialized.tsv').read_bytes()!=(original/'materialized.tsv').read_bytes():
        raise RuntimeError('No-panel typed materialized table differs from sealed reference')
    write(output/'verification.json',dict(status='GENERIC_ENGINE_GUARDS_AND_ONE_NO_PANEL_TRANSPORT_PROVEN_SCOPED',engine_commit=build['engine_commit'],
          executable_sha256=build['executable_sha256'],refusals=refusals,no_panel_transport=dict(case='adjust-BH',nodes=8,edges=7,published_ports=len(ports),
          complete_typed_table_byte_equal=True,new_R_method_certificates=0),all_plugins_or_versions_qualified=False,daemon_or_study_qualified=False,g0_granted=False))
    print(json.dumps(dict(refusals=len(refusals),no_panel_DAGs=1,g0_granted=False)))


if __name__=='__main__': main()
