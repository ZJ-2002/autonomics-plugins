"""Managed synthetic I/O refusals and injected publication/rollback boundaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

from generate_toy import generate, sha


HERE=Path(__file__).resolve().parent
PLUGIN=HERE.parent
BASELINE_SESSION='bf7c68c3d99a4f7c8eef4c94a60cfa6f'
BASELINE_SEAL='4a1df063e40beefeb23567137afdbefc74851af4489cae46ef2c8a1ec86ca25a'
INPUT_NAMES=['input.tsv','config.json','certificate.json','lock.tsv','proof.json']
NONTHROWING=['postlink_current_early','postlink_current_last','postlink_previous','postlink_log_last']
CASES=['input_log_alias','output_duplicate','existing_log','existing_result','dangling_output',
    'output_symlink_input','output_hardlink_input','parent_alias_input','late_provenance_directory',
    'invalid_qualified_row','method_failure','stage_write_failure','publish_conflict',
    'rollback_replaced_inode','rollback_modified_content','input_change_after_method',*NONTHROWING,
    'staging_directory_replaced','staged_log_directory_replaced']


def record(path):
    if path.is_symlink():
        return dict(kind='symlink',target=os.readlink(path))
    if path.is_file():
        info=path.stat()
        return dict(kind='file',bytes=info.st_size,sha256=sha(path),device=info.st_dev,inode=info.st_ino)
    if path.is_dir():
        return dict(kind='directory')
    return dict(kind='missing')


def refresh(inputs):
    config=json.loads((inputs/'config.json').read_text());config['program_sha256']=sha(inputs/'input.tsv')
    (inputs/'config.json').write_text(json.dumps(config))
    proof=json.loads((inputs/'proof.json').read_text());proof['input_sha256']=[sha(inputs/name) for name in INPUT_NAMES[:4]]
    (inputs/'proof.json').write_text(json.dumps(proof))


def scientific_block(text):
    start='methods <- c("mr_ivw", "mr_egger_regression", "mr_weighted_median")\n'
    end='tables <- list(ans, heterogeneity, intercept, loo, sensitivities, h)'
    if text.count(start)!=1 or text.count(end)!=1:
        raise RuntimeError('Unique original method block boundaries required')
    return text.split(start)[1].split(end)[0]


def main():
    baseline=sys.argv[1:]==['--reproduce-postlink-baseline']
    if sys.argv[1:] and not baseline:raise RuntimeError('Unknown technical proof arguments')
    permanent=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent:
        raise RuntimeError('Managed technical session required')
    output=Path(permanent)/('v432-a-postlink-baseline' if baseline else 'v432-a-io-fixed');output.mkdir()
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    (output/'generate_toy.py').write_bytes((HERE/'generate_toy.py').read_bytes())
    script=output/'fixed-mr.R';script.write_bytes((PLUGIN/'scripts/mr.R').read_bytes())
    if baseline and sha(script)!='beec8ef591d96180ac720c909288fd1090a7803e610c048e980b3de92636a53b':
        raise RuntimeError('Post-link baseline requires the exact previously proven candidate')
    archives=Path.home()/'.local/state/autonomics/validation-archives'
    baseline_archive=archives/BASELINE_SESSION
    sys.path.insert(0,str(PLUGIN.parents[1]))
    from tools.audit_opentargets_direct_files import sealed_archive
    sealed_archive(baseline_archive,BASELINE_SEAL,successful=True)
    old=baseline_archive/'artifacts/permanent/v432-a-io-baseline/original-mr.R'
    if scientific_block(old.read_text())!=scientific_block(script.read_text()):
        raise RuntimeError('Frozen RNG/method expression block changed')
    image=tomllib.loads((PLUGIN/'manifest.toml').read_text())['image']['reference']
    results={}
    for name in NONTHROWING if baseline else CASES:
        destination=output/name;destination.mkdir()
        directory=Path(os.environ['TMPDIR'])/('v432-a-io-'+name);inputs=directory/'inputs';generate(inputs,.001)
        outputs=directory/'outputs';outputs.mkdir()
        paths=[f'/work/outputs/output{position}' for position in range(9)]
        driver='source("/fixed-mr.R")\n'
        if name=='input_log_alias':paths[7]='/work/inputs/input.tsv'
        elif name=='output_duplicate':paths[1]=paths[0]
        elif name in ['existing_log','existing_result']:(outputs/('output7' if name=='existing_log' else 'output0')).write_text('OLD_SENTINEL\n')
        elif name=='dangling_output':(outputs/'output2').symlink_to('missing-target')
        elif name=='output_symlink_input':(outputs/'output0').symlink_to('../inputs/input.tsv')
        elif name=='output_hardlink_input':os.link(inputs/'input.tsv',outputs/'output0')
        elif name=='parent_alias_input':
            (directory/'input-alias').symlink_to('inputs',target_is_directory=True);paths[7]='/work/input-alias/input.tsv'
        elif name=='late_provenance_directory':(outputs/'output8').mkdir()
        elif name=='invalid_qualified_row':
            (inputs/'input.tsv').write_text((inputs/'input.tsv').read_text().replace('QUALIFIED','NOT_QUALIFIED',1));refresh(inputs)
        elif name=='method_failure':
            driver='trace("mr_heterogeneity",where=asNamespace("TwoSampleMR"),tracer=quote(stop("INJECTED_OFFICIAL_METHOD_FAILURE")),print=FALSE)\n'+driver
        elif name=='stage_write_failure':
            driver='trace("write_json",where=asNamespace("jsonlite"),tracer=quote(stop("INJECTED_LATE_STAGE_FAILURE")),print=FALSE)\n'+driver
        elif name in ['publish_conflict','rollback_replaced_inode','rollback_modified_content']:
            mutation=''
            if name=='rollback_replaced_inode':mutation='temporary <- paste0(first,".foreign"); writeLines("FOREIGN_REPLACEMENT",temporary); stopifnot(file.rename(temporary,first))\n'
            if name=='rollback_modified_content':mutation='writeLines("FOREIGN_MODIFIED_SAME_INODE",first)\n'
            driver='''original_link <- base::file.link
counter <- 0L
first <- NULL
file.link <- function(from,to) {
 counter <<- counter+1L
 if(counter==3L) {
  before <- system2("stat",c("-c","%d:%i","--",shQuote(first)),stdout=TRUE)
''' + mutation + '''
  after <- system2("stat",c("-c","%d:%i","--",shQuote(first)),stdout=TRUE)
  writeLines(c(before,after),"/work/fault-identity.txt")
  writeLines("FOREIGN_PUBLICATION_CONFLICT",to)
  return(FALSE)
 }
 result <- original_link(from,to)
 if(counter==2L) first <<- to
 result
}
source("/fixed-mr.R")
'''
        elif name=='input_change_after_method':
            driver='''lines <- readLines("/fixed-mr.R",warn=FALSE)
boundary <- which(lines=="execute_frozen_a <- function() {")
stopifnot(length(boundary)==1L)
injection <- c("original_method <- run_frozen_a", "run_frozen_a <- function(inputs,paths) { original_method(inputs,paths); cat(rawToChar(as.raw(10)),file=inputs[1],append=TRUE) }")
source(textConnection(c(lines[seq_len(boundary-1L)],injection,lines[boundary:length(lines)])))
'''.replace('\\"','"')
        elif name in NONTHROWING:
            counter=2 if name=='postlink_current_early' else 3 if name=='postlink_previous' else 9
            destination_r='first' if name=='postlink_previous' else 'log' if name=='postlink_log_last' else 'to'
            driver='''original_link <- base::file.link
counter <- 0L
first <- NULL
log <- NULL
file.link <- function(from,to) {
 counter <<- counter+1L
 result <- original_link(from,to)
 if(counter==1L) log <<- to
 if(counter==2L) first <<- to
 if(counter==COUNTER) {
  target <- DESTINATION
  before <- system2("stat",c("-c","%d:%i","--",shQuote(target)),stdout=TRUE)
  temporary <- paste0(target,".foreign")
  writeLines("FOREIGN_NONTHROWING_REPLACEMENT",temporary)
  stopifnot(file.rename(temporary,target))
  after <- system2("stat",c("-c","%d:%i","--",shQuote(target)),stdout=TRUE)
  writeLines(c(before,after),"/work/fault-identity.txt")
 }
 result
}
source("/fixed-mr.R")
'''.replace('COUNTER',str(counter)).replace('DESTINATION',destination_r)
        elif name in ['staging_directory_replaced','staged_log_directory_replaced']:
            target='dirname(from)' if name=='staging_directory_replaced' else 'dirname(log)'
            sentinel='FOREIGN_STAGE_DIRECTORY' if name=='staging_directory_replaced' else 'output7'
            driver='''original_link <- base::file.link
counter <- 0L
log <- NULL
file.link <- function(from,to) {
 counter <<- counter+1L
 if(counter==1L) log <<- from
 if(counter==3L) {
  target <- TARGET
  before <- system2("stat",c("-c","%d:%i","--",shQuote(target)),stdout=TRUE)
  stopifnot(file.rename(target,paste0(target,".moved-fixture")),dir.create(target))
  writeLines("FOREIGN_STAGE_SENTINEL",file.path(target,"STAGED_FILENAME"))
  after <- system2("stat",c("-c","%d:%i","--",shQuote(target)),stdout=TRUE)
  writeLines(c(before,after),"/work/fault-identity.txt")
  writeLines(target,"/work/foreign-stage.txt")
  return(FALSE)
 }
 original_link(from,to)
}
source("/fixed-mr.R")
'''.replace('TARGET',target).replace('STAGED_FILENAME',sentinel)
        (directory/'fault-driver.R').write_text(driver)
        before={filename:sha(inputs/filename) for filename in INPUT_NAMES}
        ports_before=[record(directory/path.removeprefix('/work/')) for path in paths]
        command=['podman','run','--rm','--pull=never','--network=none','--read-only',
            '--userns=keep-id',f'--user={os.getuid()}:{os.getgid()}',
            '--security-opt=no-new-privileges','--cpus=2','--memory=2g',
            '-v',str(directory)+':/work:rw','-v',str(script)+':/fixed-mr.R:ro']
        for position,filename in enumerate(INPUT_NAMES):command+=['-e',f'AUTONOMICS_INPUT{position}=/work/inputs/{filename}']
        for position,path in enumerate(paths):command+=['-e',f'AUTONOMICS_OUTPUT{position}={path}']
        command+=['--entrypoint=Rscript',image,'--vanilla','/work/fault-driver.R']
        (destination/'command.json').write_text(json.dumps(command,indent=2)+'\n')
        result=subprocess.run(command,capture_output=True,text=True,timeout=300)
        (destination/'stdout.log').write_text(result.stdout);(destination/'stderr.log').write_text(result.stderr)
        after={filename:sha(inputs/filename) for filename in INPUT_NAMES}
        ports_after=[record(directory/path.removeprefix('/work/')) for path in paths]
        if baseline:
            if result.returncode!=0:raise RuntimeError('Original nonthrowing counterexample did not reproduce: '+name)
        elif result.returncode==0:raise RuntimeError('Fault/refusal unexpectedly succeeded: '+name)
        if name=='input_change_after_method':
            if before['input.tsv']==after['input.tsv']:raise RuntimeError('Planned input-mutation injection did not execute')
        elif before!=after:raise RuntimeError('Adapter changed a protected toy input: '+name)
        for position,previous in enumerate(ports_before):
            if previous['kind']!='missing' and previous!=ports_after[position]:
                raise RuntimeError('Preexisting output/alias changed: '+name)
        preserved={1} if name=='publish_conflict' else {0,1} if name in ['rollback_replaced_inode','rollback_modified_content'] else {0} if name in ['postlink_current_early','postlink_previous'] else {8} if name=='postlink_current_last' else set()
        for position in range(9):
            if position==7 or ports_before[position]['kind']!='missing':continue
            if position in preserved:
                path=outputs/f'output{position}'
                if not path.read_text().startswith('FOREIGN'):raise RuntimeError('Foreign publication was not preserved')
            elif not baseline and ports_after[position]['kind']!='missing':raise RuntimeError('Partial scientific artifact remained: '+name)
        identities=(directory/'fault-identity.txt').read_text().splitlines() if (directory/'fault-identity.txt').exists() else []
        if name=='rollback_replaced_inode' and (len(identities)!=2 or identities[0]==identities[1]):raise RuntimeError('Distinct-inode replacement injection not proven')
        if name=='rollback_modified_content' and (len(identities)!=2 or identities[0]!=identities[1]):raise RuntimeError('Same-inode content mutation injection not proven')
        if name in NONTHROWING and (len(identities)!=2 or identities[0]==identities[1]):raise RuntimeError('Nonthrowing distinct-inode replacement not proven')
        if name=='postlink_log_last' and not (outputs/'output7').read_text().startswith('FOREIGN'):raise RuntimeError('Foreign log not preserved')
        leftovers=list(outputs.glob('.twosamplemr-v432-a-stage-*'))
        if name in ['staging_directory_replaced','staged_log_directory_replaced']:
            target=directory/(directory/'foreign-stage.txt').read_text().strip().removeprefix('/work/')
            if set(leftovers)!={target,Path(str(target)+'.moved-fixture')}:raise RuntimeError('Replaced staging-directory identity was not preserved')
            sentinel=target/('FOREIGN_STAGE_DIRECTORY' if name=='staging_directory_replaced' else 'output7')
            if sentinel.read_text()!='FOREIGN_STAGE_SENTINEL\n':raise RuntimeError('Foreign staged file was deleted or appended')
            if len(identities)!=2 or identities[0]==identities[1]:raise RuntimeError('Distinct staging-directory identities required')
        elif leftovers:raise RuntimeError('Owned staging directories not cleaned')
        for root,folders,files in os.walk(directory,followlinks=False):
            for filename in files:
                source=Path(root)/filename
                if source.is_symlink():continue
                target=destination/'artifacts'/source.relative_to(directory);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
                if sha(source)!=sha(target):raise RuntimeError('Technical artifact copy identity differs')
        results[name]=dict(exit=result.returncode,input_sha256_before=before,input_sha256_after=after,
            ports_before=ports_before,ports_after=ports_after,fault_identities=identities,
            scientific_data_used=False,g0_granted=False)
        (destination/'verification.json').write_text(json.dumps(results[name],indent=2)+'\n')
    if (PLUGIN/'scripts/mr.R').read_bytes()!=script.read_bytes():raise RuntimeError('Adapter source changed during I/O proof')
    (output/'verification.json').write_text(json.dumps(dict(status='FOUR_NONTHROWING_PUBLICATION_DEFECTS_REPRODUCED' if baseline else 'TWENTY_TWO_SYNTHETIC_IO_BOUNDARIES_PASSED_NOT_DEPLOYED',
        cases=results,image=image,fixed_script_sha256=sha(script),original_script_sha256=sha(old),
        frozen_rng_and_official_call_expression_block_unchanged=True,
        original_failure_evidence_unchanged=True,active_study_or_daemon_modified=False,g0_granted=False),indent=2)+'\n')
    print(('4_NONTHROWING_DEFECTS_REPRODUCED' if baseline else '22_SYNTHETIC_IO_CASES_PASSED')+'; NO_STUDY_EXECUTION; G0=false')


if __name__=='__main__':main()
