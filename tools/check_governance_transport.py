"""Validate opt-in B/C source transport and exact normalized ABI; no execution."""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
from tools.catalog import ROOT, contained_file, inventory, read_verified_import

SOURCE_COMMIT='073fa0b888828a661a73fa87ee562adbbe571c32'
FAMILIES=('b-bulk-inputs-contract','b-donor-contract','b-donor-method','b-state-contract','b-state-method',
    'pseudobulk-contract','singscore-contract','c-network-contract','c-network-source-contract','c-safety-contract')
NORMALIZED='b-bulk-limma-contract'
IMAGE='localhost/autonomics/b-bulk-limma@sha256:6932fcead69397d2d6dc941c45aca1e74e84c11a098bd0a510f73ec7fd4301c2'
CURRENT_LEGACY_PLUGINS={'bulk-limma-normalized':{'bulk_normalized_design','bulk_normalized_limma'},
    'frozen-b-project':{'frozen_b_legacy_intake','frozen_b_legacy_family'}}
OPTIONAL_CURRENT_LEGACY_PLUGINS={'twosamplemr-v432-a':{'twosamplemr_v432_a_exploratory'}}
CURRENT_OFFICIAL_METHOD_ADDITIONS={'r-stats-lm':{'r_stats_lm'}}
CURRENT_TECHNICAL_ADDITIONS={'frozen-project-verifier':{'frozen_v432_readonly_full_verify'}}
IMAGE_SHA={
 '/opt/b-bulk-build/SOURCE_LOCK.json':'5e12f6c8573004c40bd0724c66733152f3a394a530b30d8d283476aaeebcd9c2',
 '/opt/b-bulk-build/install-source.R':'1e014a6cd11c9768910ec6fc11334ef706b85f71d845b010fde07e7ae64487b7',
 '/opt/b-bulk-build/package-lock.tsv':'b0ad611f7c33ae7812c1665d6d4831adc9dbe56f50671c77a6eceb54c5c36204',
 '/opt/b-bulk-build/probe-toolchain.R':'010005ae937d1546937830bcfc885662e20c18b787010557a3e51afdbb86b31a',
 '/opt/b-bulk/bin/Rscript-vanilla':'7ae0fab26e28de0bdd8ce15dc3d694dd64c383ca002867e76c63db9f4596d8c6',
 '/opt/b-bulk/bulk-limma.R':'c5d0a5f4fe179dd79ea49ea954f439b1e08af312102ac7ba3c570a82d10f010a',
 '/opt/b-bulk/run-design.R':'b1f7cc7b2d8e8a94244b148ea651fa4a4b286f2a69da093b05c4541a82a73a2e',
 '/opt/b-bulk/run-limma.R':'cddc93770a8ceafa4ffe4f98c0f1584463666b6f1601acae342ca0988f5dbc99'}

def require(ok,msg):
    if not ok:raise ValueError(msg)

def identity(raw):return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def regular(directory,name):return contained_file(directory,name).read_bytes()

def check_family(directory,*,normalized=False):
    directory=Path(directory);lock=json.loads(regular(directory,'component-source.json'));manifest=tomllib.loads(regular(directory,'manifest.toml').decode())
    require(lock['source_commit']==SOURCE_COMMIT and lock['status']=='ENGINEERING_CANDIDATE','exact core source/candidate identity differs')
    require(lock['scientific_authorization'] is False and lock['method_acceptance_verified'] is False
        and lock['loaded_worker_registration_verified'] is False and lock['auto_enable'] is False,'source transport promoted to admission')
    for name,ref in lock['imported_files'].items():
        raw=regular(directory,name)
        if (identity(raw)!={k:ref[k] for k in ['sha256','bytes']} or
                hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=ref['git_blob']):
            # Only the fixed repository layout can consume actual verified Git
            # evolution. Standalone original-byte fixtures retain the old path.
            require(directory.parent.name=='research-adapters','evolved source requires actual repository layout')
            verified=read_verified_import(directory.parent.parent,'research-adapters/'+directory.name+'/'+name)
            require(raw==verified,'imported source changed after Git evolution replay')
    if normalized:
        require(manifest['image']['reference']==IMAGE and lock['image_reference']==IMAGE,'exact6932 image differs')
        require({path:ref['sha256'] for path,ref in lock['image_sources'].items()}==IMAGE_SHA,'all8 frozen image source hashes required')
        for image_path,ref in lock['image_sources'].items():require(identity(regular(directory,ref['local_path']))=={k:ref[k] for k in ['sha256','bytes']},'measured image-source bytes differ')
        require(lock['source_distribution_provenance_qualified'] is False and lock['full_method_qualification_verified'] is False,'engineering image promoted to method/source acceptance')
        nodes=manifest['nodes'];require([n['kind'] for n in nodes]==['b_bulk_frozen_design','b_bulk_frozen_limma'],'two exact normalized kinds/order required')
        for node,stage,n_inputs,outputs in zip(nodes,['DESIGN','LIMMA'],[5,6],[['audit.json'],['results.tsv','audit.json','official.rds']],strict=True):
            require(node['command']=={'interpreter':'/opt/b-bulk/bin/Rscript-vanilla','script_file':'scripts/run-'+stage.lower()+'.R'},'fixed vanilla command/entry differs')
            require(node['stage_in_mode']=='copy' and node['timeout_secs']==1200,'fixed stage/timeout differs')
            require(node['resources']=={'network':'isolated','read_only_rootfs':True,'pull_policy':'never','cpus':1.0,'memory':'1Gi','pids_limit':64},'offline read-only fixed resources differ')
            require(node['ports']['inputs']==[{'type':'file'}]*n_inputs and node['ports']['outputs']==[{'path':name,'format':('json' if name.endswith('.json') else 'r_rds' if name.endswith('.rds') else 'tsv')} for name in outputs],'actual input/output port order or format differs')
            wrapper=regular(directory,node['command']['script_file']).decode()
            encoded=wrapper.split('eval(parse(text=',1)[1].split('),envir=bulk)',1)[0]
            require(json.loads(encoded).encode()==regular(directory,'scripts/bulk-limma.R'),'full embedded unchanged limma component differs')
            require('inputs<-vapply(seq_len('+str(n_inputs)+'L)-1L' in wrapper and 'outputs<-vapply(seq_len('+str(len(outputs))+'L)-1L' in wrapper
                and 'names<-c('+','.join(json.dumps(n) for n in outputs)+')' in wrapper,'generated actual port ABI differs')
            require(regular(directory,node['command']['script_file'])==regular(directory,'image-source/run-'+stage.lower()+'.R'),'adapter entry differs from measured installed image')
        require(regular(directory,'scripts/bulk-limma.R')==regular(directory,'image-source/bulk-limma.R'),'adapter core differs from measured installed image')
    return {'directory':directory.name,'kinds':[n['kind'] for n in manifest['nodes']],'source_file_count':len(lock['imported_files']),
        'normalized_eight_source_hashes_checked':normalized,'scientific_authorization':False,'auto_enable':False}

def check(root=ROOT):
    root=Path(root);index=json.loads((root/'provenance/p0-load-source-imports-20261012.json').read_bytes())
    require(index['source_commit']==SOURCE_COMMIT and index['original_source_index_rewritten'] is False,'additional source index identity differs')
    require({r['directory'] for r in index['research_adapters']}=={'research-adapters/'+n for n in [*FAMILIES,NORMALIZED]},'exact11 selected transport families required')
    for row in index['research_adapters']:
        lock=json.loads((root/row['directory']/'component-source.json').read_bytes())
        require(row['source_commit']==lock['source_commit'] and row['files']==lock['imported_files'],'additional source index and family lock differ')
    results=[check_family(root/'research-adapters'/n,normalized=n==NORMALIZED) for n in [*FAMILIES,NORMALIZED]]
    proposed={k for row in results for k in row['kinds']};require(len(proposed)==18,'exact18 new unique kinds required')
    for namespace in ['plugins','research-adapters']:
        for path in (root/namespace).glob('*/manifest.toml'):
            if namespace=='research-adapters' and path.parent.name in [*FAMILIES,NORMALIZED]:continue
            kinds={n['kind'] for n in tomllib.loads(path.read_text())['nodes']};require(not (kinds&proposed),'new transport kind collides with existing canonical/opt-in family')
    catalog=inventory(root)
    allowed={**CURRENT_LEGACY_PLUGINS,**OPTIONAL_CURRENT_LEGACY_PLUGINS,**CURRENT_OFFICIAL_METHOD_ADDITIONS,**CURRENT_TECHNICAL_ADDITIONS}
    additions=[r for r in catalog['families'] if r['directory'].startswith('plugins/') and r['plugin_name'] in allowed]
    actual={r['plugin_name']:set(r['kinds']) for r in additions}
    require(all(actual.get(name)==kinds for name,kinds in CURRENT_LEGACY_PLUGINS.items()) and
        all(allowed[name]==kinds for name,kinds in actual.items()),'exact current independent LEGACY A/B plugin additions required')
    require(catalog['canonical_families']-len(additions)==31 and
        catalog['canonical_kinds']-sum(len(r['kinds']) for r in additions)==62,'original canonical import source scope changed')
    return {'scope':'OFFLINE_MANIFEST_SOURCE_AND_PORT_ABI_TRANSPORT_NOT_NATIVE_LOADER_IMAGE_WORKER_OR_SCIENCE_ACCEPTANCE',
        'selected_families':results,'new_unique_kinds':18,'canonical_families':31,'canonical_kinds':62,
        'current_canonical_families':catalog['canonical_families'],'current_canonical_kinds':catalog['canonical_kinds'],
        'current_legacy_additions':sorted(set(actual)-set(CURRENT_OFFICIAL_METHOD_ADDITIONS)-set(CURRENT_TECHNICAL_ADDITIONS)),
        'current_official_method_additions':sorted(set(actual)&set(CURRENT_OFFICIAL_METHOD_ADDITIONS)),
        'current_technical_additions':sorted(set(actual)&set(CURRENT_TECHNICAL_ADDITIONS)),
        'native_loader_construct_verified':False,'loaded_worker_registration_verified':False,'scientific_authorization':False,'auto_enable':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();print(json.dumps(check(a.root),sort_keys=True))
