"""Mandatory actual-image refusals, including pre-unpickle confinement."""

import argparse
import json
from pathlib import Path
import shutil
import sys

import anndata as ad
import numpy as np

from celltypist_compare import digest
from celltypist_fixtures import fixture
from test_celltypist_container import FAMILY,environment,execute


def main():
    parser=argparse.ArgumentParser();parser.add_argument('evidence',type=Path);parser.add_argument('--models',type=Path,required=True)
    arguments=parser.parse_args();arguments.evidence.mkdir()
    cases=[('negative-X','invalid X'),('nan-X','finite log1p'),('infinite-X','invalid X'),('no-X','nonempty X'),
        ('late-negative-X','finite log1p'),('late-nan-X','finite log1p'),('raw-invalid','finite log1p'),
        ('duplicate-cell','unique'),('duplicate-gene','unique'),('empty-cell','nonempty'),('empty-gene','nonempty'),
        ('no-model-overlap','no gene symbols'),('missing-vote-label','cover every cell'),
        ('model-traversal','verified named model'),('model-absolute','verified named model'),
        ('model-binding-mismatch','bindings disagree'),('model-corrupt','model SHA256'),
        ('model-symlink-outside','stay inside'),('undeclared-input1','undeclared model'),
        ('boolean-invalid','true or false'),('h5ad-exists','refusing to overwrite'),('report-exists','refusing to overwrite'),
        ('dangling-output','refusing to overwrite'),('output-alias','distinct'),('input-overwrite','distinct'),
        ('second-link-failure','injected second link failure')]
    records=[]
    for name,fragment in cases:
        directory=arguments.evidence/name;directory.mkdir()
        settings={'model_file':'Immune_All_Low.pkl','majority_voting':True}
        fixture(directory,arguments.models/'Immune_All_Low.pkl','dense',1101 if name.startswith('late-') else 80)
        data=ad.read_h5ad(directory/'input.h5ad')
        if name in ['negative-X','nan-X','infinite-X','late-negative-X','late-nan-X']:
            data.X[1100 if name.startswith('late-') else 0,0]=np.nan if 'nan' in name else np.inf if 'infinite' in name else -1
        elif name=='no-X':data.X=None
        elif name=='raw-invalid':
            raw=data.copy();raw.X[0,0]=-1;data.raw=raw;data.X=data.X-7
        elif name=='duplicate-cell':data.obs_names=[data.obs_names[1],*data.obs_names[1:]]
        elif name=='duplicate-gene':data.var_names=[data.var_names[1],*data.var_names[1:]]
        elif name=='empty-cell':data.obs_names=['',*data.obs_names[1:]]
        elif name=='empty-gene':data.var_names=['',*data.var_names[1:]]
        elif name=='no-model-overlap':data.var_names=[f'NOT_A_SYMBOL_{index}' for index in range(data.n_vars)]
        elif name=='missing-vote-label':data.obs.loc[data.obs_names[0],'leiden']=np.nan
        data.write_h5ad(directory/'input.h5ad')
        variables=environment(directory,settings,arguments.models)
        if name=='model-traversal':variables.update(SC_MODEL_FILE='../Immune_All_Low.pkl',SC_P_STR_MODEL_FILE='../Immune_All_Low.pkl')
        elif name=='model-absolute':variables.update(SC_MODEL_FILE='/tmp/Immune_All_Low.pkl',SC_P_STR_MODEL_FILE='/tmp/Immune_All_Low.pkl')
        elif name=='model-binding-mismatch':variables['SC_P_STR_MODEL_FILE']='Immune_All_High.pkl'
        elif name in ['model-corrupt','model-symlink-outside']:
            models_directory=directory/'model';models_directory.mkdir()
            target=models_directory/'Immune_All_Low.pkl'
            if name=='model-corrupt':target.write_bytes(b'not a trusted pickle;must be refused before loading')
            else:target.symlink_to(arguments.models/'Immune_All_Low.pkl')
            variables['SC_MODEL_DIR']=str(models_directory)
        elif name=='undeclared-input1':variables['AUTONOMICS_INPUT1']=str(arguments.models/'Immune_All_Low.pkl')
        elif name=='boolean-invalid':variables['SC_P_BOOL_MAJORITY_VOTING']='not-boolean'
        sentinel=None
        if name in ['h5ad-exists','report-exists']:
            sentinel=directory/('output.h5ad' if name=='h5ad-exists' else 'report.json');sentinel.write_bytes(b'old-output')
        elif name=='dangling-output':(directory/'output.h5ad').symlink_to('absent.h5ad')
        elif name=='output-alias':variables['AUTONOMICS_OUTPUT1']=variables['AUTONOMICS_OUTPUT0']
        elif name=='input-overwrite':variables['AUTONOMICS_OUTPUT0']=variables['AUTONOMICS_INPUT0']
        checksum=digest(directory/'input.h5ad')
        command=[sys.executable,str(FAMILY/'scripts/celltypist_annotate.py')]
        if name=='second-link-failure':
            code="import os,runpy; original=os.link; calls=[]\ndef link(*args,**kwargs):\n calls.append(1)\n if len(calls)==2: raise OSError('injected second link failure')\n return original(*args,**kwargs)\nos.link=link\nrunpy.run_path("+repr(str(FAMILY/'scripts/celltypist_annotate.py'))+",run_name='__main__')"
            command=[sys.executable,'-c',code]
        result=execute(command,directory,'declared-node-script',variables)
        assert result.returncode!=0 and fragment in result.stderr.decode(),result.stderr.decode()
        assert digest(directory/'input.h5ad')==checksum
        for path in [directory/'output.h5ad',directory/'report.json']:
            if path==sentinel:assert path.read_bytes()==b'old-output'
            else:assert not path.is_file()
        assert not list(directory.glob('.celltypist-*'))
        records.append({'case':name,'specifically_refused':True,'normal_outputs_not_published':True,'input_unchanged':True,'G0':False})
        print(name,'PASS',flush=True)
    (arguments.evidence/'SUMMARY.json').write_text(json.dumps({'cases':len(records),'records':records,
        'trusted_model_boundary_before_unpickle':True,'no_malicious_pickle_deserialized':True,'crash_or_resume_claim':False,'G0':False},indent=2)+'\n')


if __name__=='__main__':main()
