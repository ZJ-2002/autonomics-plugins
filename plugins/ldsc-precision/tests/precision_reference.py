"""Independent direct official API and full returned-field oracle, TEST only."""
import csv
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import sys
import numpy as np
sys.path.insert(0,'/opt/cachexia-official-ldsc')
import ldsc


def flatten(value,path=()):
    if isinstance(value,np.ndarray):
        yield path+('__array_shape',),'META',json.dumps(list(value.shape))
        yield path+('__array_dtype',),'META',str(value.dtype)
        for index in np.ndindex(value.shape):yield from flatten(value[index],path+tuple(index))
    elif isinstance(value,dict):
        for key,v in sorted(value.items()):yield from flatten(v,path+(key,))
    elif isinstance(value,(list,tuple)):
        for i,v in enumerate(value):yield from flatten(v,path+(i,))
    elif value is None:yield path,'NONE',None
    elif isinstance(value,(bool,np.bool_)):yield path,'BOOL',bool(value)
    elif isinstance(value,(int,float,np.integer,np.floating)):
        v=float(value)
        yield path,('NUMBER' if math.isfinite(v) else 'NAN' if math.isnan(v) else 'POSINF' if v>0 else 'NEGINF'),v if math.isfinite(v) else None
    elif isinstance(value,str):yield path,'TEXT',value
    else:
        yield path+('__object_class',),'META',type(value).__module__+'.'+type(value).__name__
        yield from flatten(vars(value),path)


def main():
    config=json.loads(Path('/work/config.json').read_text());method=config['method']
    inputs=[]
    for i in range(1 if method=='h2' else 2):
        path=Path('/work/input-'+str(i))
        with path.open('rb') as f:gz=f.read(2)==b'\x1f\x8b'
        actual=Path('/work/reference-input-'+str(i)+'.tsv')
        if gz:
            with gzip.open(path,'rb') as src:actual.write_bytes(src.read())
        else:actual.write_bytes(path.read_bytes())
        inputs.append(str(actual))
    # Exact original parser options; never import or reuse the precision node.
    args=['--'+method,inputs[0] if method=='h2' else ','.join(inputs),
        '--ref-ld-chr','/panels/ref_ld/LDscore.','--w-ld-chr','/panels/w_ld/weights.hm3_noMHC.',
        '--n-blocks',str(config['parameters']['n_blocks']),'--out','/work/direct-official']
    if config['parameters']['chisq_max'] is not None:args+=['--chisq-max',str(config['parameters']['chisq_max'])]
    if config['prevalence'][0] is not None:
        args+=['--samp-prev',','.join(str(p['sample']) for p in config['prevalence']),
               '--pop-prev',','.join(str(p['population']) for p in config['prevalence'])]
    parsed=ldsc.parser.parse_args(args);logger=ldsc.Logger('/work/direct-official.log')
    random.seed(config['seed']);np.random.seed(config['seed'])
    result=ldsc.sumstats.estimate_h2(parsed,logger) if method=='h2' else ldsc.sumstats.estimate_rg(parsed,logger)
    if method=='h2':
        scalars={name:float(getattr(result,attr)) for name,attr in {'h2':'tot','h2_se':'tot_se','intercept':'intercept',
            'intercept_se':'intercept_se','mean_chisq':'mean_chisq','lambda_gc':'lambda_gc','ratio':'ratio','ratio_se':'ratio_se'}.items()}
    else:
        obj=result[0]
        scalars={name:float(getattr(obj,attr)) if not isinstance(getattr(obj,attr),str) else None
                 for name,attr in {'rg':'rg_ratio','rg_se':'rg_se','z':'z','official_p':'p'}.items()}
        scalars.update(h2_a=float(obj.hsq1.tot),h2_b=float(obj.hsq2.tot))
    report={'direct_official_scalars':scalars,'complete_returned_fields':list(flatten(result))}
    if method=='h2' and config['prevalence'][0] is not None:
        p=config['prevalence'][0];factor=ldsc.sumstats.reg.h2_obs_to_liab(1,p['sample'],p['population'])
        report['liability_diagnostic']={'official_scale_factor':float(factor),'h2':float(factor*result.tot),'h2_se':float(factor*result.tot_se)}
    Path('/work/direct-reference.json').write_text(json.dumps(report,allow_nan=False))

if __name__=='__main__':main()
