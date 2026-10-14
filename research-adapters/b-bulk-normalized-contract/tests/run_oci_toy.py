"""25-gene SYN full-B ABI check in cached723; no image creation or study input."""
import ast, copy, csv, hashlib, importlib.util, io, json, math, os, runpy, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADAPTER=ROOT/'research-adapters/b-bulk-normalized-contract'
OLD=ROOT/'research-adapters/b-bulk-limma-contract'
CONTRACT=json.loads((ADAPTER/'runtime-contract.json').read_bytes())
IMAGE=CONTRACT['image_reference']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(x,msg):
 if not x:raise RuntimeError(msg)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def load(p):return json.loads(Path(p).read_bytes())
permanent=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']); evidence=permanent/'full-b-normalized-abi-toy';evidence.mkdir()
need(os.environ.get('AUTONOMICS_PODMAN_PROGRAM'),'use managed python-script entry and its owned Podman shim')
state=Path.home()/'.autonomics';overlay=state/'containers-overlay';runroot=overlay/'run'
PODMAN=['podman','--root',str(overlay/'storage'),'--runroot',str(runroot),'--tmpdir',str(runroot/'libpod-tmp'),'--storage-driver','overlay']
commands=[]
def execute(extra):
 p=subprocess.run([*PODMAN,*extra],capture_output=True,text=True)
 commands.append({'operation':extra[0],'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr.encode()).hexdigest()})
 return p
metadata=execute(['image','inspect',IMAGE]);need(metadata.returncode==0,'cached exact image unavailable')
inspected=json.loads(metadata.stdout);need(len(inspected)==1 and (inspected[0].get('Digest')==IMAGE.split('@')[1] or IMAGE in inspected[0].get('RepoDigests',[])),'cached platform image identity differs')
with tempfile.TemporaryDirectory(prefix='b-normalized-abi-syn-',dir=os.environ['TMPDIR']) as temporary:
 syn=Path(temporary)
 def container(script,inputs=None,target=None,expected=0,expression=None,reference=False):
  command=['run','--rm','--pull=never','--network=none','--read-only','--memory=512m','--cpus=1','--pids-limit=64',
   '--tmpfs','/tmp:rw,size=64m','-v',str(syn)+':/syn:rw','-v',str(ADAPTER)+':/adapter:ro','-v',str(OLD)+':/reference:ro',
   '--entrypoint',CONTRACT['interpreter']]
  if inputs is not None:
   target.mkdir()
   names=['audit.json'] if script=='run-design.R' else ['results.tsv','audit.json','official.rds']
   for i,p in enumerate(inputs):command+=['-e','AUTONOMICS_INPUT'+str(i)+'=/syn/'+str(p.relative_to(syn))]
   for i,n in enumerate(names):command+=['-e','AUTONOMICS_OUTPUT'+str(i)+'=/syn/'+str(target.relative_to(syn))+'/'+n]
  command.append(IMAGE)
  if expression is not None:command+=['-e',expression]
  else:command.append(('/reference' if reference else '/adapter')+'/scripts/'+script)
  p=execute(command);need(p.returncode==expected,'SYN container status differs: '+p.stderr[-1200:]);return p
 measured=container(None,expression='cat(jsonlite::toJSON(c(list(R=as.character(getRversion())),setNames(lapply(c("limma","statmod","jsonlite","digest","stats"),function(p)as.character(packageVersion(p))),c("limma","statmod","jsonlite","digest","stats"))),auto_unbox=TRUE))')
 need(json.loads(measured.stdout)==CONTRACT['software_lock'],'actual complete package lock differs')
 # Reuse only the fixed Python fixture-generation statements, before any R,
 # method invocation or frozen data read in the existing25-gene SYN driver.
 fixture_source=ROOT/'plugins/bulk-limma-normalized/tests/run_method_toy.py'
 module=runpy.run_path(str(fixture_source),run_name='SYN_fixture_helpers')
 tree=ast.parse(fixture_source.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
 selected=[];collect=False
 for n in function.body:
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ids' for t in n.targets):collect=True
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='project_dir' for t in n.targets):break
  if collect:selected.append(n)
 need(selected,'fixed SYN generator statement set missing')
 context={**module,'output':syn};exec(compile(ast.Module(body=selected,type_ignores=[]),str(fixture_source),'exec'),context)
 project=ROOT/'plugins/frozen-b-project';spec=importlib.util.spec_from_file_location('SYN_project_config',project/'scripts/project.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
 lock=load(project/'project-lock.json');lock.update(gene_count=25,primary_samples=8,case_n=4,control_n=4,residual_df=4,contrast_id='SYN_CONTRAST')
 hashes={n:sha(syn/(n+'.tsv')) for n in ['expression','genes','samples','decisions']}
 cfg=p.method_config(lock,hashes,'primary');cfg['source_archive_sha256']=CONTRACT['source_design_sha256']
 config=syn/'config.json';config.write_bytes(canonical(cfg));inputs=[config,*[syn/(n+'.tsv') for n in ['expression','genes','samples','decisions']]]
 source_sha={str(f.relative_to(ROOT)):sha(f) for f in [Path(__file__),fixture_source,project/'scripts/project.py',project/'project-lock.json',ADAPTER/'manifest.toml',ADAPTER/'runtime-contract.json',*sorted((ADAPTER/'scripts').glob('*.R'))]}
 need([sha(f) for f in [ADAPTER/'scripts/bulk-limma.R',OLD/'scripts/bulk-limma.R']][0]==sha(OLD/'scripts/bulk-limma.R'),'numeric source differs')
 design=syn/'design';container('run-design.R',inputs,design)
 fit=syn/'fit';container('run-limma.R',[*inputs,design/'audit.json'],fit)
 old_design=syn/'reference-design';container('run-design.R',inputs,old_design,reference=True)
 old_fit=syn/'reference-fit';container('run-limma.R',[*inputs,old_design/'audit.json'],old_fit,reference=True)
 need((design/'audit.json').read_bytes()==(old_design/'audit.json').read_bytes(),'standard DESIGN audit ABI differs')
 need((fit/'audit.json').read_bytes()==(old_fit/'audit.json').read_bytes(),'standard LIMMA audit ABI differs')
 need((fit/'results.tsv').read_bytes()==(old_fit/'results.tsv').read_bytes(),'legacy adapter numerical source wrapper parity differs')
 rows=list(csv.DictReader((fit/'results.tsv').open(),delimiter='\t'));need(len(rows)==25 and rows[-1]['raw_p']=='NA' and rows[-1]['family_p']=='NA','full gene/constant row differs')
 sample_rows=list(csv.DictReader((syn/'samples.tsv').open(),delimiter='\t'));matrix=[[1.,float(r['group']=='case'),float(r['age']),float(r['sex']=='M')] for r in sample_rows]
 xtx=[[sum(r[i]*r[j] for r in matrix) for j in range(4)] for i in range(4)]
 expr=list(csv.DictReader((syn/'expression.tsv').open(),delimiter='\t'));ids=context['ids']
 for e,r in zip(expr[:-1],rows[:-1],strict=True):
  y=[float(e[k]) for k in ids]; beta=module['solve'](xtx,[sum(a[j]*v for a,v in zip(matrix,y,strict=True)) for j in range(4)])[1]
  need(math.isclose(float(r['log2_expression_difference']),beta,rel_tol=1e-10,abs_tol=1e-11),'independent Python OLS coefficient differs')
 # Read actual opaque RDS fields through official R; not an inferred filename check.
 oracle='x<-readRDS("/syn/fit/official.rds");y<-readRDS("/syn/reference-fit/official.rds");stopifnot(identical(x,y),length(x$full_gene_ids)==25L,length(x$variable_gene_ids)==24L,nrow(x$fit$coefficients)==24L);cat("RDS_FIELDS_AND_REFERENCE_IDENTICAL")'
 need(container(None,expression=oracle).stdout.strip()=='RDS_FIELDS_AND_REFERENCE_IDENTICAL','official RDS proof differs')
 rejects=[]
 for name,change in [('raw-counts',{'expression_scale':'raw_integer_counts'}),('wrong-software',{'software_lock':{**cfg['software_lock'],'limma':'3.66.0'}}),('wrong-input-sha',{'input_sha256':{**hashes,'genes':'0'*64}})]:
  bad=syn/(name+'.json');bad.write_bytes(canonical({**cfg,**change}));target=syn/('reject-'+name)
  container('run-design.R',[bad,*inputs[1:]],target,expected=2);need(not (target/'audit.json').exists(),'rejection published design');rejects.append(name)
 bad=syn/'stale-design.json';bad.write_bytes(canonical({**load(design/'audit.json'),'config_sha256':'0'*64}));target=syn/'reject-stale-design'
 container('run-limma.R',[*inputs,bad],target,expected=2);need(not (target/'results.tsv').exists(),'stale receipt published fit');rejects.append('stale-design')
 # Preserve only small mandatory SYN method outputs/config identities, not a new environment.
 for stage in ['design','fit']:
  target=evidence/stage;target.mkdir()
  for f in (syn/stage).iterdir():
   if f.is_file() and not f.name.startswith('.'): (target/f.name).write_bytes(f.read_bytes())
 proof={'scope':'ACTUAL_CACHED723_SYN_FULL_B_NORMALIZED_ABI_REVIEW_NOT_METHOD_OR_SCIENTIFIC_AUTHORIZATION','image_reference':IMAGE,
  'actual_image_config':inspected[0]['Id'],'actual_software_lock':json.loads(measured.stdout),'source_sha256':source_sha,
  'fixture_input_sha256':{f.name:sha(f) for f in inputs},'genes':25,'estimated_rows':24,'constant_na_rows':1,
  'same_standard_design_limma_audit_schema':True,'reference_wrapper_same_image_exact_numerical_bytes':True,
  'independent_python_ols_coefficients_verified':True,'official_rds_fields_read_and_identical':True,'rejected_cases':rejects,
  'method_acceptance_verified':False,'source_qualified':False,'full_family_worker_qualified':False,'formal_authorized':False,'scientific_authorization':False,'G0':False,
  'no_image_build_pull_export_or_environment_copy':True,'commands':commands,'preserved_syn_outputs':{str(f.relative_to(evidence)):sha(f) for f in evidence.rglob('*') if f.is_file()}}
 (evidence/'RESULT.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'scope':proof['scope'],'gene_count':25,'source_sha256':source_sha,'rejections':rejects,'scientific_authorization':False}))
