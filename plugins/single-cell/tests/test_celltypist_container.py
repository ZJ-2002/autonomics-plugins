"""Both trusted official models, author calls, voting and expression branches."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import anndata as ad
import scanpy as sc

from celltypist_compare import compare
from celltypist_fixtures import fixture


FAMILY=Path(__file__).resolve().parents[1]


def execute(command,directory,label,variables):
    started=time.monotonic()
    result=subprocess.run(command,env=variables,capture_output=True,timeout=900)
    (directory/(label+'.stdout.txt')).write_bytes(result.stdout)
    (directory/(label+'.stderr.txt')).write_bytes(result.stderr)
    (directory/(label+'.execution.json')).write_text(json.dumps({'command':command,'exit':result.returncode,
        'seconds':time.monotonic()-started,'G0':False},indent=2)+'\n')
    return result


def environment(directory,request,models_directory):
    return dict(os.environ,AUTONOMICS_INPUT0=str(directory/'input.h5ad'),AUTONOMICS_OUTPUT0=str(directory/'output.h5ad'),
        AUTONOMICS_OUTPUT1=str(directory/'report.json'),SC_MODEL_DIR=str(models_directory),SC_MODEL_FILE=request['model_file'],
        SC_P_STR_MODEL_FILE=request['model_file'],SC_P_BOOL_MAJORITY_VOTING=str(request['majority_voting']).lower())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('evidence',type=Path)
    parser.add_argument('--reference-library',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--pbmc3k-file',type=Path)
    arguments=parser.parse_args()
    arguments.evidence.mkdir()
    cases=[(filename[:-4]+'-'+str(int(vote)),'dense',filename,vote,80)
           for filename in ['Immune_All_Low.pkl','Immune_All_High.pkl'] for vote in [False,True]]
    cases += [(variant,variant,'Immune_All_Low.pkl',True,80) for variant in
        ['csr','csc','float32','reordered','partial-genes','raw-fallback','raw-valid-X-valid',
         'overwrite-annotation-columns','auto-existing-graph','auto-existing-pca','auto-no-graph','moderate-score-voting']]
    cases += [('cells-'+str(count),'dense','Immune_All_Low.pkl',True,count) for count in [49,50,51]]
    cases += [('small-preexisting-annotations','small-preexisting-annotations','Immune_All_Low.pkl',True,49)]
    if arguments.pbmc3k_file:
        cases += [('official-pbmc3k-'+str(int(vote)),'pbmc3k','Immune_All_Low.pkl',vote,2700) for vote in [False,True]]
    records=[]
    changed_confidence_cases=0
    for name,variant,filename,voting,cells in cases:
        directory=arguments.evidence/name
        directory.mkdir()
        if variant=='pbmc3k':
            data=ad.read_h5ad(arguments.pbmc3k_file)
            sc.pp.normalize_total(data,target_sum=1e4)
            sc.pp.log1p(data)
            data.obs['leiden']=['all']*data.n_obs
            data.write_h5ad(directory/'input.h5ad')
        else:
            fixture(directory,arguments.models/filename,variant,cells)
        request={'model_file':filename,'majority_voting':voting}
        (directory/'request.json').write_text(json.dumps(request,indent=2)+'\n')
        author=execute([sys.executable,str(FAMILY/'tests/celltypist_reference.py'),str(directory),str(arguments.models)],
            directory,'fresh-author',dict(os.environ,PYTHONPATH=str(arguments.reference_library)))
        node=execute([sys.executable,str(FAMILY/'scripts/celltypist_annotate.py')],directory,'declared-node-script',
            environment(directory,request,arguments.models))
        if author.returncode or node.returncode:
            raise AssertionError(author.stderr.decode()+node.stderr.decode())
        checked=compare(directory)
        details=json.loads((directory/'fresh-author.json').read_text())
        changed_confidence_cases+=int(details['voting_confidence_differs_from_best_match'])
        (directory/'CHECKS.json').write_text(json.dumps(checked,indent=2)+'\n')
        records.append({'case':name,**checked})
        print(name,'PASS',flush=True)
    assert changed_confidence_cases>0,'Voting confidence mismatch branch was not exercised'
    (arguments.evidence/'SUMMARY.json').write_text(json.dumps({'cases':len(records),'records':records,
        'voted_label_differs_and_aligned_confidence_cases':changed_confidence_cases,
        'official_small_cell_voting_skip_tested':True,'both_official_models_tested':True,
        'auto_graph_and_auto_PCA_paths_tested':True,'G0':False},indent=2)+'\n')


if __name__=='__main__':
    main()
