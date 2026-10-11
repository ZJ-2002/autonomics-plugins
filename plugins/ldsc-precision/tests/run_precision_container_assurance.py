"""Actual pinned method/full returned-state parity. Synthetic panels/GWAS only."""
import argparse
import copy
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import tomllib

ROOT=Path(__file__).resolve().parents[1]
IMAGE='localhost/cachexia-ldsc-official@sha256:febf11d5ec554b53e2e022f26e55033233cb4692f40eb7d81cdaa7fe11d70999'


def identity(path):return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}


def state_fields(value,path=()):
    if isinstance(value,dict) and value.get('kind')=='OBJECT':
        yield path+('__object_class',),'META',value['class']
        yield from state_fields(value['fields'],path)
    elif isinstance(value,dict) and value.get('kind')=='ARRAY':
        yield path+('__array_shape',),'META',json.dumps(value['shape'])
        yield path+('__array_dtype',),'META',value['dtype']
        def leaves(rows,index=()):
            if len(index)==len(value['shape']):yield from state_fields(rows,path+index)
            else:
                for i,v in enumerate(rows):yield from leaves(v,index+(i,))
        yield from leaves(value['values'])
    elif isinstance(value,dict) and value.get('kind')=='MISSING':yield path,value['reason'],None
    elif isinstance(value,dict):
        for k,v in sorted(value.items()):yield from state_fields(v,path+(k,))
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from state_fields(v,path+(i,))
    elif value is None:yield path,'NONE',None
    elif isinstance(value,bool):yield path,'BOOL',value
    elif isinstance(value,(int,float)):yield path,'NUMBER',float(value)
    elif isinstance(value,str):yield path,'TEXT',value
    else:raise ValueError('unknown actual returned-field encoding')


def run(output,shared,runtime_path):
    output=output.resolve();output.mkdir(mode=0o700)
    manifest=tomllib.loads((ROOT/'manifest.toml').read_text())
    if manifest['image']['reference']!=IMAGE:raise ValueError('explicit image identity changed')
    runtime=json.loads(runtime_path.read_text());runtime_snapshot=output/'declared-runtime.json';runtime_snapshot.write_bytes(runtime_path.read_bytes())
    podman=['podman','--root',str(output/'storage'),'--runroot',str(output/'runroot'),
        '--storage-opt','additionalimagestore='+str(shared.resolve())]
    inspected=subprocess.run(podman+['image','inspect',IMAGE],capture_output=True,text=True,check=True)
    (output/'image-inspect.json').write_text(inspected.stdout)
    if json.loads(inspected.stdout)[0]['Digest']!=IMAGE.split('@')[1]:raise ValueError('actual image identity changed')
    panels=output/'panels';ref=panels/'ref_ld';weight=panels/'w_ld';ref.mkdir(parents=True);weight.mkdir()
    rng=random.Random(20261012);trait=[[],[]]
    for chrom in range(1,23):
        panel=[]
        for i in range(100):
            snp='rs'+str((chrom-1)*100+i+1);L=5+rng.random()*15;g=rng.gauss(0,1);ind=rng.gauss(0,1)
            z1=rng.gauss(0,1)+math.sqrt(0.2*10000/2200*L)*g
            z2=rng.gauss(0,1)+math.sqrt(0.25*12000/2200*L)*(0.5*g+math.sqrt(0.75)*ind)
            panel.append([chrom,snp,i+1,format(L,'.17g')])
            trait[0].append([snp,'A','G',10000,format(z1,'.17g')]);trait[1].append([snp,'A','G',12000,format(z2,'.17g')])
        text=io.StringIO();w=csv.writer(text,delimiter='\t',lineterminator='\n');w.writerow(['CHR','SNP','BP','L2']);w.writerows(panel)
        for path in [ref/f'LDscore.{chrom}.l2.ldscore.gz',weight/f'weights.hm3_noMHC.{chrom}.l2.ldscore.gz']:
            with gzip.open(path,'wb') as f:f.write(text.getvalue().encode())
        for suffix in ['M','M_5_50']:(ref/f'LDscore.{chrom}.l2.{suffix}').write_text('100\n')
    panel_value={'schema_version':1,'files':{str(p.relative_to(panels)):identity(p) for p in sorted(panels.rglob('*')) if p.is_file()}}
    panel_manifest=output/'panel-manifest.json';panel_manifest.write_text(json.dumps(panel_value,sort_keys=True,separators=(',',':')))
    source=[]
    for rows in trait:
        text=io.StringIO();w=csv.writer(text,delimiter='\t',lineterminator='\n');w.writerow(['SNP','A1','A2','N','Z']);w.writerows(rows);source.append(text.getvalue().encode())
    checks=[]
    for method,scale,compression in [('h2','observed',False),('h2','liability',True),('rg','observed',False),('rg','liability',True),('rg','nonpositive_h2',False)]:
        case=output/(method+'-'+scale);case.mkdir(mode=0o700)
        count=1 if method=='h2' else 2
        for i in range(count):
            if compression:
                with gzip.open(case/f'input-{i}','wb') as f:f.write(source[i])
            else:
                raw=source[i]
                if scale=='nonpositive_h2' and i==0:
                    rows=list(csv.DictReader(io.StringIO(raw.decode()),delimiter='\t'))
                    # A deterministic decreasing chi-square/LD relationship.
                    ld={}
                    for file in sorted(ref.glob('*.ldscore.gz')):
                        with gzip.open(file,'rt') as f:
                            for r in csv.DictReader(f,delimiter='\t'):ld[r['SNP']]=float(r['L2'])
                    for r in rows:r['Z']=format(1/math.sqrt(ld[r['SNP']]),'.17g')
                    text=io.StringIO();w=csv.DictWriter(text,fieldnames=['SNP','A1','A2','N','Z'],delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows);raw=text.getvalue().encode()
                (case/f'input-{i}').write_bytes(raw)
        shutil.copyfile(panel_manifest,case/'panel-manifest.json')
        binding={'sumstats_a':identity(case/'input-0')['sha256'],**({'sumstats_b':identity(case/'input-1')['sha256']} if method=='rg' else {}),
            'panel_manifest':identity(case/'panel-manifest.json')['sha256']}
        config={'schema_version':1,'status':'FROZEN','protocol_version':'4.3.2','module_id':'A_ARCH',
            'analysis_id':'SYNTHETIC-ARCH-'+method+'-'+scale,'family_id':'A_ARCH_GLOBAL' if method=='rg' else None,
            'phenotype_ids':['SYNTHETIC-A','SYNTHETIC-B'] if method=='rg' else ['SYNTHETIC-A'],
            'method':method,'source_archive_sha256':'a'*64,'input_origin':'SYNTHETIC_TECHNICAL_ONLY','input_sha256':binding,
            'parameters':{'n_blocks':20,'chisq_max':None},'prevalence':[{'sample':0.2,'population':0.1} for _ in range(count)] if scale=='liability' else [None]*count,
            'seed':20261012,'official_runtime':runtime,'pvalue_policy':'OFFICIAL_DEFAULT_RG_BOUNDS_NONPOSITIVE_H2_MISSINGNESS'}
        (case/'config.json').write_text(json.dumps(config,sort_keys=True,separators=(',',':')))
        variables={'ARCH_LDSC_METHOD':method,'AUTONOMICS_INPUT_COUNT':str(count+2),'AUTONOMICS_INPUT0':'/work/config.json',
            'AUTONOMICS_WORKDIR':'/work','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
        for i in range(count):variables['AUTONOMICS_INPUT'+str(i+1)]='/work/input-'+str(i)
        variables['AUTONOMICS_INPUT'+str(count+1)]='/work/panel-manifest.json'
        for i,name in enumerate(['result.json','official.log','audit.json','bound_config.json','official_state.json']):variables['AUTONOMICS_OUTPUT'+str(i)]='/work/'+name
        base=podman+['run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=2g','--pids-limit=128',
            '--security-opt=no-new-privileges','--tmpfs','/tmp:rw,size=64m','-v',str(case)+':/work:rw',
            '-v',str(panels)+':/panels:ro','-v',str(ROOT/'scripts/precision.py')+':/precision.py:ro',
            '-v',str(ROOT/'tests/precision_reference.py')+':/reference.py:ro','--entrypoint','python']
        for k,v in variables.items():base+=['-e',k+'='+v]
        actual=subprocess.run(base+[IMAGE,'/precision.py'],capture_output=True,text=True,timeout=180)
        (case/'actual-command.json').write_text(json.dumps(base+[IMAGE,'/precision.py']));(case/'actual.stdout').write_text(actual.stdout);(case/'actual.stderr').write_text(actual.stderr)
        if actual.returncode:raise RuntimeError(method+' actual typed method failed: '+actual.stderr+'; '+(case/'audit.json').read_text())
        direct=subprocess.run(base+[IMAGE,'/reference.py'],capture_output=True,text=True,timeout=180)
        (case/'reference-command.json').write_text(json.dumps(base+[IMAGE,'/reference.py']));(case/'reference.stdout').write_text(direct.stdout);(case/'reference.stderr').write_text(direct.stderr)
        if direct.returncode:raise RuntimeError(method+' direct official reference failed: '+direct.stderr)
        result=json.loads((case/'result.json').read_text());oracle=json.loads((case/'direct-reference.json').read_text());audit=json.loads((case/'audit.json').read_text())
        if result['values']!=oracle['direct_official_scalars']:raise ValueError('official scalar output mismatch')
        if scale=='liability' and method=='h2' and result['liability_diagnostic']!=oracle['liability_diagnostic']:raise ValueError('official liability scale conversion mismatch')
        expected={json.dumps(path):(kind,value) for path,kind,value in oracle['complete_returned_fields']}
        returned={json.dumps(path):(kind,value) for path,kind,value in state_fields(json.loads((case/'official_state.json').read_text()))}
        if returned!=expected:raise ValueError('complete official returned object fields differ; '+str(set(returned)^set(expected)))
        for name,file in [('result','result.json'),('state','official_state.json'),('bound_config','bound_config.json'),('official_log','official.log')]:
            if audit['output_identities'][name]!=identity(case/file):raise ValueError('output hash/size receipt mismatch')
        if audit['status']!='TECHNICAL_PRECISION_PASS_NOT_SCIENTIFIC' or result['status']!=('NOT_ESTIMABLE' if scale=='nonpositive_h2' else 'ESTIMATED'):raise ValueError('actual scientific/technical status differs')
        if method=='rg' and result['status']=='ESTIMATED' and (result['raw_p']!=oracle['direct_official_scalars']['official_p'] or result['raw_p']==float(format(result['raw_p'],'.4g'))):raise ValueError('rounded-log P substituted')
        if result['formal_authorization_granted'] or result['scientific_qualification_granted']:raise ValueError('synthetic method claimed research permission')
        checks.append({'method':method,'scale':scale,'gzip_without_extension':compression,'original_munged_rows':2200,
            'full_returned_fields_compared':len(expected),'finite_numeric_fields_compared':sum(k=='NUMBER' for k,v in expected.values()),
            'all_returned_fields_exact':True,'all_scalars_exact':True,'official_family_P_exact':True if method=='rg' else None,'outputs_content_bound':True,'result_status':result['status'],
            'missing_raw_p_retained':result['raw_p'] is None if scale=='nonpositive_h2' else None})
    negative_checks=[]
    original_case=output/'rg-observed'
    for defect in ['source_digest','panel_missing_chr22','runtime_identity','duplicate_config_key']:
        case=output/('negative-'+defect);case.mkdir(mode=0o700)
        for name in ['input-0','input-1','panel-manifest.json','config.json']:shutil.copyfile(original_case/name,case/name)
        config=json.loads((case/'config.json').read_text())
        if defect=='source_digest':config['input_sha256']['sumstats_a']='0'*64
        elif defect=='panel_missing_chr22':
            value=json.loads((case/'panel-manifest.json').read_text());value['files'].pop('ref_ld/LDscore.22.l2.M_5_50')
            (case/'panel-manifest.json').write_text(json.dumps(value));config['input_sha256']['panel_manifest']=identity(case/'panel-manifest.json')['sha256']
        elif defect=='runtime_identity':config['official_runtime']['runtime_files']['ldscore/sumstats.py']='0'*64
        raw=json.dumps(config,sort_keys=True,separators=(',',':'))
        if defect=='duplicate_config_key':raw=raw[:-1]+',"schema_version":1}'
        (case/'config.json').write_text(raw)
        original_command=json.loads((original_case/'actual-command.json').read_text())
        command=[part.replace(str(original_case)+':/work:rw',str(case)+':/work:rw') for part in original_command]
        result=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (case/'actual-command.json').write_text(json.dumps(command));(case/'actual.stdout').write_text(result.stdout);(case/'actual.stderr').write_text(result.stderr)
        audit=json.loads((case/'audit.json').read_text())
        if result.returncode!=2 or audit['status']!='BLOCKED' or any((case/name).exists() for name in ['result.json','bound_config.json','official_state.json']):raise ValueError('actual negative probe did not block '+defect)
        negative_checks.append({'defect':defect,'actual_container_exit':result.returncode,'audit_status':audit['status'],'normal_numeric_state_config_outputs_absent':True})
    report={'status':'PASS','scope':'PINNED_OFFICIAL_METHOD_FULL_OBJECT_PRECISION_PARITY_SYNTHETIC_ONLY','image':IMAGE,
        'cases':checks,'negative_cases':negative_checks,'method_script':identity(ROOT/'scripts/precision.py'),'reference_script':identity(ROOT/'tests/precision_reference.py'),
        'manifest':identity(ROOT/'manifest.toml'),'original_panel_files':len(panel_value['files']),
        'actual_real_panel_qualification':False,'complete_architecture_family_qualification':False,'native_lineage_qualification':False,
        'scientific_qualification':False,'formal_authorization':False}
    with (output/'RESULT.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--shared-image-store',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
    a=p.parse_args();run(a.output,a.shared_image_store,a.runtime)
