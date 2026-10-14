"""Verify missing-input and unknown-parameter controls using a qualified score fixture."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest,write
from tools.prove_generic_plugin_guards import sealed


def missing_metadata_cause(messages):
    return ('PortDisconnected { node: "analysis", port: 2 }' in messages
            or 'All three declared input and output ports are required' in messages)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner',required=True,type=Path)
    parser.add_argument('--build-record',required=True,type=Path)
    parser.add_argument('--archives',required=True,type=Path)
    arguments=parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ: raise RuntimeError('Managed validation required')
    reference=sealed(arguments.archives,'50e4b946d8f14e38bf34c7c3e16f0980','d8992bc43f98a69a71aaa5d580d190bd46f236716a03c18a79a36c099bc2eb5c','singscore-current-dag')
    build=json.loads(arguments.build_record.read_text())
    if build['actual_build_exit']!=0 or digest(arguments.runner)!=build['executable_sha256']: raise RuntimeError('Exact verified probe required')
    runner=Path(os.environ['TMPDIR'])/'official_plugin_dag'
    with arguments.runner.open('rb') as source,runner.open('xb') as destination: shutil.copyfileobj(source,destination)
    runner.chmod(0o700)
    if digest(runner)!=build['executable_sha256']: raise RuntimeError('Owned executable differs')
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'singscore-graph-controls'
    output.mkdir()
    shutil.copyfile(Path(__file__),output/'driver.py')
    source=output/'source'
    shutil.copytree(reference/'source',source)
    original=reference/'test_bidirectional_official_rank_and_all_scores'
    template=json.loads((original/'job.json').read_text())
    results=[]
    for name in ['unknown-parameter','missing-metadata-edge']:
        work=output/name
        work.mkdir()
        for filename in ['matrix.tsv','signature.tsv','samples.tsv']: shutil.copyfile(original/filename,work/filename)
        job=copy.deepcopy(template)
        job.update(run_root=str(work),plugin_manifest=str(source/'manifest.toml'))
        if name=='unknown-parameter':
            job['nodes'][-1]['spec']={'unexpected_free_parameter':1}
        else:
            job['edges']=[edge for edge in job['edges'] if edge['to_port']!=2]
        write(work/'job.json',job)
        completed=subprocess.run([str(runner),str(work/'job.json')],capture_output=True,text=True,timeout=120)
        (work/'runner.stdout').write_text(completed.stdout)
        (work/'runner.stderr').write_text(completed.stderr)
        report_path=work/'dag-report.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else None
        if list((work/'artifacts').rglob('singscore_scores.tsv')):
            raise RuntimeError('Invalid control published a normal scoring result: '+name)
        messages=completed.stderr
        if report is not None:
            if not report['first_run']['errors']: raise RuntimeError('Invalid graph control succeeded')
            messages+='\n'+json.dumps(report['first_run']['errors'])
        elif completed.returncode!=1:
            raise RuntimeError('Expected explicit graph construction failure missing')
        if name=='unknown-parameter':
            if 'unexpected_free_parameter' not in messages:
                raise RuntimeError('Exact unknown-parameter diagnostic missing')
        elif not missing_metadata_cause(messages):
            raise RuntimeError('Exact missing metadata-input cause missing')
        results.append(dict(case=name,runner_exit=completed.returncode,report_written=report is not None,normal_result_absent=True,exact_cause_verified=True))
    write(output/'verification.json',dict(status='CURRENT_SINGSCORE_GRAPH_CONTROLS_ENFORCED',engine_commit=build['engine_commit'],cases=results,
          frozen_parameters_or_methods_changed=False,scientific_or_daemon_qualified=False,g0_granted=False))
    print(json.dumps(dict(controls=len(results),g0_granted=False)))


if __name__=='__main__': main()
