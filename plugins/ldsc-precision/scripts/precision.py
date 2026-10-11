"""Typed official LDSC results; no scientific authorization or rounded-log P.

Called only by distinct precision kinds. Original h2/rg log kinds stay intact.
The engine must independently admit protocol, sources, methods, gates and
result visibility; a frozen numeric recipe is not that authorization.
"""
import argparse
import contextlib
import csv
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import traceback
import warnings

SOURCE = Path('/opt/cachexia-official-ldsc')
LIMIT = 16*1024**2
KEYS = {'schema_version','status','protocol_version','module_id','analysis_id','family_id',
        'phenotype_ids','method','source_archive_sha256','input_origin','input_sha256',
        'parameters','prevalence','seed','official_runtime','pvalue_policy'}
ROLE = 'OFFICIAL_DEFAULT_RG_BOUNDS_NONPOSITIVE_H2_MISSINGNESS'


def need(ok, message):
    if not ok: raise ValueError('precise LDSC contract: '+message)


def unique(pairs):
    result={}
    for k,v in pairs:
        need(k not in result,'duplicate JSON key');result[k]=v
    return result


def read_json(path):
    with path.open('rb') as f: raw=f.read(LIMIT+1)
    need(0<len(raw)<=LIMIT,'bounded complete metadata required')
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: need(False,'nonfinite JSON metadata'))


def identity(path):
    h=hashlib.sha256();count=0
    with path.open('rb') as f:
        for raw in iter(lambda:f.read(1024**2),b''):h.update(raw);count+=len(raw)
    return {'sha256':h.hexdigest(),'bytes':count}


def identifier(value):
    need(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,160}',value),'bounded identifier required')


def check_config(config, method):
    count=1 if method=='h2' else 2
    need(set(config)==KEYS and type(config['schema_version']) is int and config['schema_version']==1,
         'complete exact configuration required')
    need(config['status']=='FROZEN' and config['protocol_version']=='4.3.2'
         and config['module_id']=='A_ARCH' and config['method']==method,'explicit matching frozen original architecture method required')
    need(config['input_origin'] in {'SYNTHETIC_TECHNICAL_ONLY','LEGACY_SEEN_NOT_NEW_EVIDENCE',
        'DECLARED_RESEARCH_INPUTS_REQUIRING_ENGINE_AUTHORIZATION'},'explicit input evidence identity required')
    identifier(config['analysis_id'])
    need(config['family_id']==('A_ARCH_GLOBAL' if method=='rg' else None),'diagnostics must not acquire an inferential family')
    need(isinstance(config['phenotype_ids'],list) and len(config['phenotype_ids'])==count
         and len(set(config['phenotype_ids']))==count,'distinct ordered phenotype identities required')
    for tid in config['phenotype_ids']:identifier(tid)
    need(isinstance(config['source_archive_sha256'],str) and re.fullmatch('[0-9a-f]{64}',config['source_archive_sha256']),
         'original archive content identity required')
    binding_keys=['sumstats_a']+(['sumstats_b'] if method=='rg' else [])+['panel_manifest']
    need(isinstance(config['input_sha256'],dict) and set(config['input_sha256'])==set(binding_keys)
         and all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in config['input_sha256'].values()),
         'all actual bound input digests required')
    need(type(config['seed']) is int and 0<=config['seed']<=4294967295,'explicit bounded reproducibility seed required')
    need(config['pvalue_policy']==ROLE,'declared official default result-validity policy required')
    params=config['parameters']
    need(isinstance(params,dict) and set(params)=={'n_blocks','chisq_max'}
         and type(params['n_blocks']) is int and params['n_blocks']>=2,'unconstrained official integer jackknife policy required')
    x=params['chisq_max']
    need(x is None or type(x) in (int,float) and math.isfinite(x) and x>0,'positive explicit outlier cutoff or official default required')
    prev=config['prevalence']
    need(isinstance(prev,list) and len(prev)==count,'complete original phenotype prevalence declarations required')
    # The official rg interface requires all traits on one declared scale.
    need(all(p is None for p in prev) or all(isinstance(p,dict) and set(p)=={'sample','population'}
        and all(type(v) in (int,float) and math.isfinite(v) and 0<v<1 for v in p.values()) for p in prev),
        'paired sample/population prevalence for every trait or explicit observed scale required')
    return binding_keys


def runtime_identity():
    files={str(p.relative_to(SOURCE)):identity(p)['sha256'] for p in sorted(SOURCE.rglob('*.py'))}
    return {'python':sys.version.split()[0],'packages':{n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','bitarray']},
            'runtime_files':files}


def panel_identity(path):
    panel=read_json(path)
    need(isinstance(panel,dict) and set(panel)=={'schema_version','files'} and type(panel['schema_version']) is int
         and panel['schema_version']==1 and isinstance(panel['files'],dict),'complete panel manifest required')
    mandatory={f'ref_ld/LDscore.{chrom}.l2.{suffix}' for chrom in range(1,23) for suffix in ['ldscore.gz','M_5_50']}
    mandatory|={f'w_ld/weights.hm3_noMHC.{chrom}.l2.ldscore.gz' for chrom in range(1,23)}
    need(mandatory<=set(panel['files']),'all22 chromosomes of reference, M_5_50 and weight panels required')
    checked={}
    for name,expected in sorted(panel['files'].items()):
        relative=PurePosixPath(name)
        need(isinstance(name,str) and not relative.is_absolute() and '..' not in relative.parts and str(relative)==name
             and relative.parts[0] in {'ref_ld','w_ld'},'safe declared panel file required')
        file=Path('/panels')/name
        need(file.is_file() and not file.is_symlink() and not any(p.is_symlink() for p in file.parents),'regular nonsymlink panel source required')
        need(isinstance(expected,dict) and set(expected)=={'sha256','bytes'} and type(expected['bytes']) is int
             and expected['bytes']>0 and isinstance(expected['sha256'],str) and re.fullmatch('[0-9a-f]{64}',expected['sha256']),
             'complete panel file content identity required')
        actual=identity(file);need(actual==expected,'actual panel bytes differ: '+name);checked[name]=actual
    return checked


def plain_sumstats(path, work, position):
    need(path.is_file(),'actual sumstats input required')
    with path.open('rb') as f:compressed=f.read(2)==b'\x1f\x8b'
    if compressed:
        destination=work/f'input-{position}.tsv'
        with gzip.open(path,'rb') as src,destination.open('xb') as dst:shutil.copyfileobj(src,dst,1024**2)
    else:destination=path
    with destination.open('r') as f:
        reader=csv.DictReader(f,delimiter='\t')
        need(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames))
             and set(reader.fieldnames)=={'SNP','A1','A2','N','Z'},'exact complete LDSC SNP/allele/N/Z columns required')
        count=0;seen=set()
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()),'malformed full sumstats row')
            need(row['SNP'] and row['SNP'] not in seen,'complete unique munged SNP identifiers required')
            seen.add(row['SNP']);count+=1
            need(len(row['A1'])==len(row['A2'])==1 and row['A1'] in 'ACGT' and row['A2'] in 'ACGT'
                 and row['A1']!=row['A2'],'declared munged allele pair required')
            need(math.isfinite(float(row['Z'])) and math.isfinite(float(row['N'])) and float(row['N'])>0,
                 'finite signed statistic and positive sample size required')
        need(count>0,'empty sumstats input')
    return destination,{'original_transport':identity(path),'official_plain_input':identity(destination),'complete_munged_rows':count}


def number(value):
    if isinstance(value,(str,bool)) or value is None:return None
    try:v=float(value)
    except (ValueError,TypeError):return None
    return v if math.isfinite(v) else None


def numeric_result(result, method):
    if method=='h2':
        values={k:number(getattr(result,attr,None)) for k,attr in {'h2':'tot','h2_se':'tot_se','intercept':'intercept',
            'intercept_se':'intercept_se','mean_chisq':'mean_chisq','lambda_gc':'lambda_gc','ratio':'ratio','ratio_se':'ratio_se'}.items()}
        need(values['h2'] is not None and values['h2_se'] is not None and values['h2_se']>=0,
             'official diagnostic estimate missing/nonfinite')
        return {'status':'ESTIMATED','reason':'OFFICIAL_OBSERVED_H2_DIAGNOSTIC','raw_p':None,'values':values}
    need(isinstance(result,list) and len(result)==1 and result[0] is not None,'official swallowed pair failure; no fallback result')
    rg=result[0]
    values={k:number(getattr(rg,attr,None)) for k,attr in {'rg':'rg_ratio','rg_se':'rg_se','z':'z','official_p':'p'}.items()}
    values['h2_a']=number(rg.hsq1.tot);values['h2_b']=number(rg.hsq2.tot)
    reason='OFFICIAL_UNCONSTRAINED_RG'
    if any(v is None for v in [values['h2_a'],values['h2_b']]) or getattr(rg,'_negative_hsq',False) or min(values['h2_a'],values['h2_b'])<=0:
        reason='OFFICIAL_NONPOSITIVE_H2'
    elif values['rg'] is not None and abs(values['rg'])>1.2:reason='OFFICIAL_DEFAULT_RG_OUT_OF_BOUNDS'
    elif any(values[k] is None for k in ['rg','rg_se','z','official_p']) or values['rg_se']<=0:
        reason='OFFICIAL_MISSING_OR_NONFINITE_RG'
    else:need(0<=values['official_p']<=1,'official P outside probability range')
    estimated=reason=='OFFICIAL_UNCONSTRAINED_RG'
    return {'status':'ESTIMATED' if estimated else 'NOT_ESTIMABLE','reason':reason,
            'raw_p':values['official_p'] if estimated else None,'values':values}


def encode_state(value, count=None, active=None):
    """Preserve all official object fields without inventing finite replacements."""
    import numpy as np
    count=[0] if count is None else count;active=set() if active is None else active
    count[0]+=1;need(count[0]<=1000000,'complete returned state exceeds admitted budget; no truncation')
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,(np.bool_,np.integer)):return value.item()
    if isinstance(value,(float,np.floating)):
        v=float(value)
        return v if math.isfinite(v) else {'kind':'MISSING','reason':'NAN' if math.isnan(v) else 'POSINF' if v>0 else 'NEGINF','value':None}
    need(id(value) not in active,'cyclic returned state unsupported');active.add(id(value))
    try:
        if isinstance(value,np.ndarray):return {'kind':'ARRAY','shape':list(value.shape),'dtype':str(value.dtype),'values':encode_state(value.tolist(),count,active)}
        if isinstance(value,(list,tuple)):return [encode_state(v,count,active) for v in value]
        if isinstance(value,dict):
            need(all(isinstance(k,str) for k in value),'unsupported returned dictionary keys')
            return {k:encode_state(v,count,active) for k,v in sorted(value.items())}
        need(type(value).__module__.startswith('ldscore.') and hasattr(value,'__dict__'),'unsupported official returned object')
        return {'kind':'OBJECT','class':type(value).__module__+'.'+type(value).__name__,
            'fields':encode_state(vars(value),count,active)}
    finally:active.remove(id(value))


def publish_json(path,value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    need(len(raw)<=LIMIT,'complete precision output exceeds metadata budget; no truncation')
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def execute(outputs, audit):
    method=os.environ['ARCH_LDSC_METHOD'];need(method in {'h2','rg'},'unknown fixed method')
    count=3 if method=='h2' else 4
    need(os.environ.get('AUTONOMICS_INPUT_COUNT')==str(count),'exact complete input port count required')
    inputs=[Path(os.environ['AUTONOMICS_INPUT'+str(i)]) for i in range(count)]
    config=read_json(inputs[0]);binding_keys=check_config(config,method)
    bound={k:identity(path) for k,path in zip(binding_keys,inputs[1:])}
    need(all(v['sha256']==config['input_sha256'][k] for k,v in bound.items()),'actual frozen input binding differs')
    audit.update(config=config,config_identity=identity(inputs[0]),input_identities=bound)
    need(runtime_identity()==config['official_runtime'],'complete pinned runtime source/packages differ')
    panels=panel_identity(inputs[-1]);audit['panel_file_identities']=panels
    work=Path(os.environ['AUTONOMICS_WORKDIR'])/'.autonomics'/'precision';work.mkdir(parents=True,exist_ok=False)
    parsed_inputs=[];source_receipts=[]
    for i,path in enumerate(inputs[1:-1]):
        actual,receipt=plain_sumstats(path,work,i);parsed_inputs.append(actual);source_receipts.append(receipt)
    sys.path.insert(0,str(SOURCE))
    import ldsc
    import numpy as np
    import random
    need(Path(ldsc.__file__).resolve()==SOURCE/'ldsc.py' and Path(ldsc.sumstats.__file__).resolve()==SOURCE/'ldscore/sumstats.py',
         'official namespace resolves outside pinned source')
    args=['--'+method,str(parsed_inputs[0]) if method=='h2' else ','.join(map(str,parsed_inputs)),
        '--ref-ld-chr','/panels/ref_ld/LDscore.','--w-ld-chr','/panels/w_ld/weights.hm3_noMHC.',
        '--n-blocks',str(config['parameters']['n_blocks']),'--out',str(work/'official')]
    if config['parameters']['chisq_max'] is not None:args+=['--chisq-max',str(config['parameters']['chisq_max'])]
    if config['prevalence'][0] is not None:
        args+=['--samp-prev',','.join(str(p['sample']) for p in config['prevalence']),
               '--pop-prev',','.join(str(p['population']) for p in config['prevalence'])]
    parsed=ldsc.parser.parse_args(args)
    need(parsed.intercept_h2 is None and parsed.intercept_gencov is None and not parsed.no_intercept,
         'unconstrained official intercepts required')
    random.seed(config['seed']);np.random.seed(config['seed'])
    logger=ldsc.Logger(str(work/'official.log'))
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            result=ldsc.sumstats.estimate_h2(parsed,logger) if method=='h2' else ldsc.sumstats.estimate_rg(parsed,logger)
        typed=numeric_result(result,method);state=encode_state(result)
    finally:
        logger.log_fh.flush()
        logger.log_fh.close()
    shutil.copyfile(work/'official.log',outputs[1])
    # Every actual input/runtime/panel identity is revalidated after computation.
    need({k:identity(path) for k,path in zip(binding_keys,inputs[1:])}==bound
         and identity(inputs[0])==audit['config_identity'] and panel_identity(inputs[-1])==panels
         and runtime_identity()==config['official_runtime'],'consumed input/environment changed during calculation')
    record={k:config[k] for k in ['schema_version','protocol_version','module_id','analysis_id','family_id','phenotype_ids','method',
        'source_archive_sha256','input_origin','parameters','prevalence','pvalue_policy']}
    record.update(typed,config_identity=audit['config_identity'],input_identities=bound,
        scale='OBSERVED' if config['prevalence'][0] is None else 'OBSERVED_OBJECT_WITH_DECLARED_LIABILITY_SUMMARY',
        scientific_qualification_granted=False,formal_authorization_granted=False)
    if method=='h2' and config['prevalence'][0] is not None:
        p=config['prevalence'][0];factor=float(ldsc.sumstats.reg.h2_obs_to_liab(1,p['sample'],p['population']))
        record['liability_diagnostic']={'official_scale_factor':factor,'h2':factor*typed['values']['h2'],'h2_se':factor*typed['values']['h2_se']}
    output_ids={'result':publish_json(outputs[0],record),'state':publish_json(outputs[4],state),
                'bound_config':publish_json(outputs[3],config),'official_log':identity(outputs[1])}
    audit.update(status='TECHNICAL_PRECISION_PASS_NOT_SCIENTIFIC',official_arguments=vars(parsed),
        complete_munged_source_receipts=source_receipts,warnings=[{'type':type(w.message).__name__,'message':str(w.message)} for w in captured],
        output_identities=output_ids,official_runtime=config['official_runtime'],result_status=typed['status'])
    return audit


def main():
    outputs=[Path(os.environ['AUTONOMICS_OUTPUT'+str(i)]) for i in range(5)]
    need(len(set(outputs))==5 and not any(p.exists() for p in outputs),'five distinct never-overwritten outputs required')
    audit={'status':'RUNNING','scientific_qualification_granted':False,'formal_authorization_granted':False}
    try:
        audit=execute(outputs,audit)
    except BaseException as e:
        for i in [0,3,4]:outputs[i].unlink(missing_ok=True)
        audit.update(status='BLOCKED',error=type(e).__name__+': '+str(e));traceback.print_exc()
    publish_json(outputs[2],audit)
    return 0 if audit['status']=='TECHNICAL_PRECISION_PASS_NOT_SCIENTIFIC' else 2

if __name__=='__main__':sys.exit(main())
