"""Real-image refusal and non-publication checks for the canonical H5AD node."""

import argparse
import json
import os
from pathlib import Path
import sys

import anndata as ad
import numpy as np
from scipy import sparse

from test_official import FAMILY, call, create, digest


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args(); arguments.evidence.mkdir()
    cases = [('no-X','materialized X'), ('zero-cells','materialized X'), ('zero-genes','materialized X'),
        ('nan-X','finite real'), ('inf-X','finite real'), ('complex-X','finite real'),
        ('integer-over-53','exactly representable'), ('unsigned-over-53','exactly representable'),
        ('duplicate-int-over-53','duplicate integer coordinates'), ('bad-sparse-index','sparse matrix structure'),
        ('duplicate-cell','axes must be unique'), ('duplicate-gene','axes must be unique'),
        ('empty-cell','lexical identifiers'), ('empty-gene','lexical identifiers'), ('tab-gene','lexical identifiers'),
        ('missing-gene-sets','strict nonempty JSON'), ('malformed-json','strict nonempty JSON'),
        ('empty-programs','strict nonempty JSON'), ('duplicate-json-key','duplicate JSON'),
        ('empty-signature','nonempty lexical gene'), ('numeric-member','nonempty lexical gene'),
        ('empty-name','signature names'), ('score-collision','overwrite obs'),
        ('ambiguous-sign','ambiguous signed'), ('no-overlap','at least one matching'),
        ('over-maxrank','effective maxRank'), ('undefined-official-score','official UCell failed'),
        ('h5ad-exists','refusing to overwrite'), ('report-exists','refusing to overwrite'),
        ('dangling-output','refusing to overwrite'), ('output-alias','distinct'), ('input-overwrite','distinct'),
        ('second-link-failure','injected second link'), ('R-failure','official UCell failed')]
    records = []
    for name, fragment in cases:
        directory = arguments.evidence/name; directory.mkdir()
        programs = create(directory, 'dense')
        data = ad.read_h5ad(directory/'input.h5ad')
        if name=='no-X': data.X = None
        elif name=='zero-cells': data = data[:0].copy()
        elif name=='zero-genes': data = data[:,:0].copy()
        elif name in ['nan-X','inf-X']: data.X[0,0] = np.nan if name=='nan-X' else np.inf
        elif name=='complex-X': data.X = data.X.astype(complex)+1j
        elif name in ['integer-over-53','unsigned-over-53']:
            data.X = data.X.astype(np.int64 if name=='integer-over-53' else np.uint64)
            data.X[0,0] = 2**53+1
        elif name=='duplicate-int-over-53':
            data.X = sparse.csr_matrix((np.array([2**53,1],dtype=np.int64),np.array([0,0]),
                np.array([0,2,*[2]*(data.n_obs-1)])),shape=data.shape)
        elif name=='bad-sparse-index':
            data.X = sparse.csr_matrix((np.array([1.]),np.array([data.n_vars+1]),
                np.array([0,1,*[1]*(data.n_obs-1)])),shape=data.shape)
        elif name=='duplicate-cell': data.obs_names = [data.obs_names[1],*data.obs_names[1:]]
        elif name=='duplicate-gene': data.var_names = [data.var_names[1],*data.var_names[1:]]
        elif name=='empty-cell': data.obs_names = ['',*data.obs_names[1:]]
        elif name in ['empty-gene','tab-gene']: data.var_names = ['' if name=='empty-gene' else 'A\tB',*data.var_names[1:]]
        elif name=='undefined-official-score': data = data[:,:1].copy(); programs={'one':['A']}
        if name=='empty-programs': programs={}
        elif name=='empty-signature': programs={'one':[]}
        elif name=='numeric-member': programs={'one':[1]}
        elif name=='empty-name': programs={'':['A']}
        elif name=='score-collision': programs={'donor':['A']}
        elif name=='ambiguous-sign': programs={'one':['A+','A-']}
        elif name=='no-overlap': programs={'one':['ABSENT']}
        elif name=='over-maxrank': programs={'one':['A',*[f'absent-{index}' for index in range(12)]]}
        data.write_h5ad(directory/'input.h5ad')
        variables=dict(os.environ,AUTONOMICS_INPUT0=str(directory/'input.h5ad'),
            AUTONOMICS_OUTPUT0=str(directory/'output.h5ad'),AUTONOMICS_OUTPUT1=str(directory/'report.json'),
            SC_P_JSON_GENE_SETS=json.dumps(programs))
        if name=='missing-gene-sets': variables.pop('SC_P_JSON_GENE_SETS')
        elif name=='malformed-json': variables['SC_P_JSON_GENE_SETS']='not JSON'
        elif name=='duplicate-json-key': variables['SC_P_JSON_GENE_SETS']='{"one":["A"],"one":["B"]}'
        sentinel=None
        if name in ['h5ad-exists','report-exists']:
            sentinel=directory/('output.h5ad' if name=='h5ad-exists' else 'report.json'); sentinel.write_bytes(b'old-output')
        elif name=='dangling-output': (directory/'output.h5ad').symlink_to('absent.h5ad')
        elif name=='output-alias': variables['AUTONOMICS_OUTPUT1']=variables['AUTONOMICS_OUTPUT0']
        elif name=='input-overwrite': variables['AUTONOMICS_OUTPUT0']=variables['AUTONOMICS_INPUT0']
        command=[sys.executable,str(FAMILY/'scripts/score.py')]
        if name=='second-link-failure':
            code="import os,runpy;original=os.link;calls=[]\ndef link(*args,**kwargs):\n calls.append(1)\n if len(calls)==2:raise OSError('injected second link failure')\n return original(*args,**kwargs)\nos.link=link\nrunpy.run_path("+repr(str(FAMILY/'scripts/score.py'))+",run_name='__main__')"
            command=[sys.executable,'-c',code]
        elif name=='R-failure':
            code="import subprocess,runpy\ndef refuse(command,**kwargs):return subprocess.CompletedProcess(command,2,b'',b'injected R failure')\nsubprocess.run=refuse\nrunpy.run_path("+repr(str(FAMILY/'scripts/score.py'))+",run_name='__main__')"
            command=[sys.executable,'-c',code]
        checksum=digest(directory/'input.h5ad')
        result=call(command,directory,'declared-node-script',variables)
        assert result.returncode!=0 and fragment in result.stderr.decode(),(name,result.stderr.decode())
        assert digest(directory/'input.h5ad')==checksum
        for path in [directory/'output.h5ad',directory/'report.json']:
            if path==sentinel: assert path.read_bytes()==b'old-output'
            else: assert not path.is_file()
        assert not list(directory.glob('.ucell-*'))
        records.append({'case':name,'specifically_refused':True,'normal_outputs_not_published':True,
                        'input_unchanged':True,'G0':False});print(name,'PASS',flush=True)
    (arguments.evidence/'SUMMARY.json').write_text(json.dumps({'cases':len(records),'records':records,
        'ordinary_second_publication_failure_injected':True,'crash_or_resume_claim':False,'G0':False},indent=2)+'\n')


if __name__=='__main__':main()
