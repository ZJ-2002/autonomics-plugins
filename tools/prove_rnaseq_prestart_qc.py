"""Explicit managed, synthetic-only OCI qualification; no downloads or study data."""
import csv,hashlib,json,math,os,random,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IMAGE='ghcr.io/zj-2002/deseq2@sha256:5931c509f7f30d44177033877a96b062bf8532d16e5762daebfa20564278a59f'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(p):
 with p.open(newline='') as f:return list(csv.reader(f,delimiter='\t'))
def write_table(p,rows):
 with p.open('x',newline='') as f:csv.writer(f,delimiter='\t',lineterminator='\n').writerows(rows)
def main():
 out=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'rnaseq-prestart-qc';out.mkdir()
 (out/'driver.py').write_bytes(Path(__file__).read_bytes())
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
 source=ROOT/'plugins/rnaseq-qc';bindings={p.name:sha(p) for p in source.iterdir() if p.is_file()};(out/'SOURCE_BINDINGS.json').write_text(json.dumps(bindings,indent=2))
 podman=os.environ['AUTONOMICS_PODMAN_PROGRAM'];backend=json.loads(os.environ.get('QC_BACKEND_JSON','[]'))
 env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
 rng=random.Random(20261016);samples=['001','s2','s3','s4','s5','s6','s7','s8']
 rows=[['gene_id',*samples],['all_zero',*([0]*8)]]+[[f'g{i}',*[rng.randint(20,2000)*(j+1) for j in range(8)]] for i in range(1,101)]
 meta=[['sample_id','condition'],*[[s,'unused_a' if i<4 else 'unused_b'] for i,s in enumerate(samples)]]
 result={'accepted':False,'scope':'SYNTHETIC_PRESTART_QC_NO_DIFFERENTIAL_FIT','source_revision':revision,'scientific_authorization':False,'cases':[]};numeric_checks=0
 def run(case,counts,metadata,*,constant=False,collision=False,bad=False):
  path=out/case;path.mkdir();write_table(path/'counts.tsv',counts);write_table(path/'metadata.tsv',metadata)
  if collision:(path/'out0.tsv').write_text('foreign output\n')
  guard='library(DESeq2)\nfor(n in c("DESeq","estimateDispersions","nbinomWaldTest","nbinomLRT","results"))trace(n,where=asNamespace("DESeq2"),tracer=quote(stop("FORBIDDEN_DIFFERENTIAL_CALL")),print=FALSE)\nsys.source("/source/prestart_qc.R",envir=.GlobalEnv)\n'
  (path/'guard.R').write_text(guard)
  args=[podman,*backend,'run','--rm','--pull=never','--userns=keep-id','--user',f'{os.getuid()}:{os.getgid()}','--read-only','--network','none','--cap-drop=all','--security-opt=no-new-privileges','--cpus=1','--memory=4g','--pids-limit=128','--tmpfs','/tmp:size=512m,mode=1777','-v',str(source)+':/source:ro','-v',str(path)+':/work:rw','-e','AUTONOMICS_INPUT0=/work/counts.tsv','-e','AUTONOMICS_INPUT1=/work/metadata.tsv']
  outputs=['out0.tsv','out1.tsv','out2.tsv','out3.tsv','out4.tsv','out5.tsv','out6.json']
  for i,n in enumerate(outputs):args+=['-e',f'AUTONOMICS_OUTPUT{i}=/work/{n}']
  args+=['--entrypoint','/opt/autonomics/Rscript-vanilla',IMAGE,'/work/guard.R']
  before={n:sha(path/n) for n in ['counts.tsv','metadata.tsv']};start=time.monotonic();p=subprocess.run(args,env=env,capture_output=True,timeout=600)
  (path/'stdout.txt').write_bytes(p.stdout);(path/'stderr.txt').write_bytes(p.stderr)
  receipt=dict(command=args,exit=p.returncode,seconds=time.monotonic()-start,inputs_before=before,inputs_after={n:sha(path/n) for n in before},actual_fixture_binding=True,forbidden_differential_calls_trapped=True)
  (path/'execution.json').write_text(json.dumps(receipt,indent=2));assert receipt['inputs_before']==receipt['inputs_after']
  if bad or collision:
   assert p.returncode!=0,(case,p.stderr.decode());assert not any((path/n).exists() for n in outputs[1:] if collision) if collision else not any((path/n).exists() for n in outputs)
   if collision:assert (path/'out0.tsv').read_text()=='foreign output\n'
  else:
   assert p.returncode==0,(case,p.stderr.decode());assert all((path/n).is_file() for n in outputs)
   report=json.loads((path/'out6.json').read_text());assert report['genes']==len(counts)-1 and report['samples']==len(counts[0])-1
   assert report['gene_ids']==[r[0] for r in counts[1:]] and report['sample_ids']==counts[0][1:]
   assert not any(report[k] for k in ['differential_fit_performed','dispersion_fit_performed','differential_tests_performed','scientific_qc_pass_granted','feature_or_sample_removal'])
   assert report['inputs']==dict(counts_sha256=before['counts.tsv'],metadata_sha256=before['metadata.tsv'])
   assert report['engine']['DESeq2']=='1.50.2' and report['pca_status']==('NO_SAMPLE_VARIATION' if constant else 'AVAILABLE')
  result['cases'].append(dict(case=case,exit=p.returncode,expected_failure=bad or collision));return path
 try:
  forward=run('forward',rows,meta)
  shuffled=run('metadata-shuffled',rows,[meta[0],*reversed(meta[1:])])
  blinded=run('phenotype-changed',rows,[meta[0],*[[s,'different'] for s in samples]])
  for other in [shuffled,blinded]:
   for i in range(6):assert (other/f'out{i}.tsv').read_bytes()==(forward/f'out{i}.tsv').read_bytes()
  reference=r'''library(DESeq2)
options(digits=17)
x<-as.matrix(read.delim("/work/counts.tsv",row.names=1,check.names=FALSE));storage.mode(x)<-"integer"
sf<-DESeq2::estimateSizeFactorsForMatrix(x);n<-sweep(x,2,sf,"/");y<-log2(n+1);pc<-prcomp(t(y),center=TRUE,scale.=FALSE,rank.=min(ncol(x)-1,nrow(x)))
w<-function(x,p)write.table(x,p,sep="\t",quote=TRUE,row.names=FALSE)
w(data.frame(sample_id=colnames(x),size_factor=sf),"/work/reference_sf.tsv")
w(data.frame(gene_id=rownames(n),n,check.names=FALSE),"/work/reference_norm.tsv")
w(data.frame(gene_id=rownames(y),y,check.names=FALSE),"/work/reference_log.tsv")
w(data.frame(sample_id=colnames(x),as.matrix(dist(t(y))),check.names=FALSE),"/work/reference_dist.tsv")
w(data.frame(sample_id=colnames(x),pc$x %*% t(pc$x),check.names=FALSE),"/work/reference_pca_gram.tsv")
'''
  (forward/'reference.R').write_text(reference)
  cmd=[podman,*backend,'run','--rm','--pull=never','--userns=keep-id','--user',f'{os.getuid()}:{os.getgid()}','--read-only','--network','none','--cpus=1','--memory=4g','--tmpfs','/tmp:size=512m','-v',str(forward)+':/work:rw','--entrypoint','/opt/autonomics/Rscript-vanilla',IMAGE,'/work/reference.R']
  p=subprocess.run(cmd,env=env,capture_output=True,timeout=600);(forward/'reference.stderr.txt').write_bytes(p.stderr);(forward/'reference.execution.json').write_text(json.dumps(dict(command=cmd,exit=p.returncode)));assert p.returncode==0,p.stderr.decode()
  def close(a,b):
   nonlocal numeric_checks
   a=float(a);b=float(b);assert math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-9+1e-9*abs(b),(a,b);numeric_checks+=1
  for actual,expected in [('out0.tsv','reference_norm.tsv'),('out1.tsv','reference_log.tsv'),('out4.tsv','reference_dist.tsv')]:
   a=table(forward/actual);b=table(forward/expected);assert a[0]==b[0] and len(a)==len(b)
   for ra,rb in zip(a[1:],b[1:]):
    assert ra[0]==rb[0]
    for va,vb in zip(ra[1:],rb[1:]):close(va,vb)
  library=table(forward/'out5.tsv');sf=table(forward/'reference_sf.tsv');assert library[0][4]=='size_factor'
  for j,(a,b) in enumerate(zip(library[1:],sf[1:])):assert a[0]==b[0];close(a[4],b[1]);close(a[1],sum(float(r[j+1]) for r in rows[1:]))
  scores=table(forward/'out2.tsv');gram=table(forward/'reference_pca_gram.tsv')
  for i,a in enumerate(scores[1:]):
   assert a[0]==gram[i+1][0]
   for j,b in enumerate(scores[1:]):close(sum(float(x)*float(y) for x,y in zip(a[1:],b[1:])),gram[i+1][j+1])
  pca=table(forward/'out3.tsv');assert pca[0]==['component','variance','proportion','cumulative'];close(sum(float(r[2]) for r in pca[1:]),1)
  run('constant',[[*rows[0]],['zero',*([0]*8)],['same',*([10]*8)]],meta,constant=True)
  mutants={}
  def clone():return [r.copy() for r in rows]
  for case,value in [('negative',-1),('fractional','0.5'),('nonfinite','NaN'),('lossy-fraction','1.00000000000000001')]:
   c=clone();c[2][1]=value;mutants[case]=(c,meta)
  c=clone();c[2][0]=c[1][0];mutants['duplicate-gene']=(c,meta)
  c=clone();c[0][2]=c[0][1];mutants['duplicate-sample']=(c,meta)
  c=clone()
  for r in c[1:]:r[1]=0
  mutants['zero-library']=(c,meta)
  mutants['missing-metadata']=(rows,meta[:-1]);mutants['duplicate-metadata']=(rows,[*meta,meta[-1]])
  mutants['no-ratio-solution']=([['gene_id','a','b'],['g1',1,0],['g2',0,1]],[['sample_id'],['a'],['b']])
  for case,(c,m) in mutants.items():run(case,c,m,bad=True)
  run('foreign-output',rows,meta,collision=True)
  assert bindings=={p.name:sha(p) for p in source.iterdir() if p.is_file()}
  result.update(accepted=True,source_unchanged=True,genes=101,samples=8,numerical_checks=numeric_checks,tolerance='1e-9 absolute plus 1e-9 relative; PCA compared by sample Gram matrix, not arbitrary PC signs',same_dependency_environment_reference=True)
 finally:(out/'RESULT.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result))
if __name__=='__main__':main()
