"""Explicit scoped original-input/argv parity in the pinned canonical image.
Synthetic GWAS only, no LD-panel/h2/rg or scientific authorization claim.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/zj-2002/ldsc@sha256:93b2542386a08df10402045b8036ff4da6733bea65324d50e326d035579d247a'


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output, shared_store):
    output=output.resolve();output.mkdir(mode=0o700)
    manifest=tomllib.loads((ROOT/'manifest.toml').read_text())
    if manifest['image']['reference']!=IMAGE:raise ValueError('explicit reviewed image identity changed')
    command=['podman','--root',str(output/'storage'),'--runroot',str(output/'runroot'),
        '--storage-opt','additionalimagestore='+str(shared_store.resolve())]
    inspection=subprocess.run(command+['image','inspect',IMAGE],capture_output=True,text=True,check=True)
    (output/'image-inspect.json').write_text(inspection.stdout)
    ident=json.loads(inspection.stdout)[0]
    if ident['Digest']!=IMAGE.split('@')[1]:raise ValueError('actual image digest differs')
    env={'LDSC_MUNGE_SNP':'original_variant','LDSC_MUNGE_N_COL':'original_sample_size',
        'LDSC_MUNGE_A1':'original_effect_allele','LDSC_MUNGE_A2':'original_other_allele',
        'LDSC_MUNGE_P':'original_P','LDSC_MUNGE_FRQ':'original_MAF',
        'LDSC_MUNGE_INFO':'original_INFO','LDSC_MUNGE_SIGNED_SUMSTATS':'original_signed_Z,0',
        'LDSC_MUNGE_INFO_MIN':'0.9','LDSC_MUNGE_MAF_MIN':'0.01','LDSC_MUNGE_N_MIN':'5000'}
    checks=[]
    for suffix in ['tsv','tsv.gz']:
        case=output/('gzip' if suffix.endswith('.gz') else 'plain');case.mkdir(mode=0o700)
        source=case/('original GWAS.'+suffix)
        raw=io.StringIO();writer=csv.writer(raw,delimiter='\t',lineterminator='\n')
        writer.writerow(['original_variant','original_effect_allele','original_other_allele','original_sample_size',
            'original_P','original_MAF','original_INFO','original_signed_Z'])
        for i in range(1000):
            z=(-1 if i%2 else 1)*(0.5+(i%70)/10)
            writer.writerow(['rs'+str(i+1),'A','G',10000,format(math.erfc(abs(z)/math.sqrt(2)),'.17g'),0.2,1,z])
        plain=raw.getvalue().encode()
        if suffix.endswith('.gz'):
            with gzip.open(source,'wb') as f:f.write(plain)
        else:source.write_bytes(plain)
        variables={**env,'AUTONOMICS_INPUT0':'/work/'+source.name,'AUTONOMICS_WORKDIR':'/work',
            'AUTONOMICS_OUTPUT0':'/work/wrapper.sumstats.gz','AUTONOMICS_OUTPUT1':'/work/wrapper.log'}
        base=command+['run','--rm','--pull=never','--network=none','--read-only','--cpus=2','--memory=1g',
            '--pids-limit=128','--security-opt=no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=64m',
            '-v',str(ROOT/'scripts/munge.sh')+':/entrypoint.sh:ro','-v',str(case)+':/work:rw',
            '--entrypoint','/bin/sh']
        for k,v in variables.items():base+=['-e',k+'='+v]
        result=subprocess.run(base+[IMAGE,'/entrypoint.sh'],capture_output=True,text=True,timeout=120)
        (case/'container.stdout').write_text(result.stdout);(case/'container.stderr').write_text(result.stderr)
        (case/'wrapper-command.json').write_text(json.dumps(base+[IMAGE,'/entrypoint.sh']))
        if result.returncode:raise RuntimeError('actual wrapper failed: '+result.stderr+'; '+(case/'wrapper.log').read_text())
        # Independent original CLI invocation uses a plain original source and
        # explicitly spelled parser options; it does not reuse wrapper argv.
        (case/'reference-original.tsv').write_bytes(plain)
        direct=['munge_sumstats','--sumstats','/work/reference-original.tsv','--out','/work/direct',
            '--snp','original_variant','--N-col','original_sample_size','--a1','original_effect_allele',
            '--a2','original_other_allele','--p','original_P','--frq','original_MAF','--info','original_INFO',
            '--signed-sumstats','original_signed_Z,0','--info-min','0.9','--maf-min','0.01','--n-min','5000']
        ref_command=command+['run','--rm','--pull=never','--network=none','--read-only','--cpus=2','--memory=1g',
            '--pids-limit=128','--security-opt=no-new-privileges','--tmpfs','/tmp:rw,size=64m','-v',str(case)+':/work:rw',
            '--entrypoint','munge_sumstats',IMAGE]+direct[1:]
        ref=subprocess.run(ref_command,capture_output=True,text=True,timeout=120)
        (case/'reference.stdout').write_text(ref.stdout);(case/'reference.stderr').write_text(ref.stderr)
        (case/'reference-command.json').write_text(json.dumps(ref_command))
        if ref.returncode:raise RuntimeError('actual direct official CLI failed: '+ref.stderr)
        with gzip.open(case/'wrapper.sumstats.gz','rb') as f:wrapped=f.read()
        with gzip.open(case/'direct.sumstats.gz','rb') as f:original=f.read()
        if wrapped!=original:raise ValueError('entire munged source table differs from direct original CLI')
        rows=list(csv.DictReader(io.StringIO(wrapped.decode()),delimiter='\t'))
        if len(rows)!=1000 or {r['SNP'] for r in rows}!={'rs'+str(i+1) for i in range(1000)}:raise ValueError('complete original SNP universe changed')
        if any(float(r['N'])!=10000 for r in rows):raise ValueError('sample size changed')
        for i,r in enumerate(rows):
            expected=(-1 if i%2 else 1)*(0.5+(i%70)/10)
            if abs(float(r['Z'])-expected)>0.002:raise ValueError('original_signed_Z convention changed')
        if (case/'wrapper.log').read_text().count('Writing summary statistics for 1000 SNPs')!=1:
            raise ValueError('method summary missing or duplicated')
        checks.append({'input_transport':suffix,'original_rows':1000,'all_SNP_IDs_preserved':True,
            'whole_decompressed_table_equals_direct_original_CLI':True,'N_preserved':True,'signed_Z_preserved':True,
            'single_method_summary':True,'source_sha256':digest(source),'wrapper_sha256':digest(ROOT/'scripts/munge.sh'),
            'output_decompressed_sha256':hashlib.sha256(wrapped).hexdigest()})
    report={'status':'PASS','scope':'CANONICAL_MUNGE_ORIGINAL_INPUT_AND_ARGV_PARITY_ONLY',
        'image_id':ident['Id'],'image_digest':ident['Digest'],'checks':checks,
        'input_origin':'SYNTHETIC_TECHNICAL_ONLY','h2_qualified':False,'rg_qualified':False,'scientific_qualification':False,
        'formal_authorized':False,'plugin_manifest_sha256':digest(ROOT/'manifest.toml')}
    with (output/'RESULT.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--shared-image-store',type=Path,required=True)
    a=p.parse_args();run(a.output,a.shared_image_store)
