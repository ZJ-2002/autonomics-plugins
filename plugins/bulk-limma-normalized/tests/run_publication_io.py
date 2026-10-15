"""Managed R entry-publication fault controls; numerical fitting is tested separately."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


PLUGIN=Path(__file__).resolve().parents[1]
DRIVER=r'''
arguments<-commandArgs(TRUE)
cfg<-jsonlite::fromJSON(arguments[2L],simplifyVector=FALSE)
expressions<-parse(arguments[1L])
stopifnot(length(expressions)==4L)
for(expression in expressions[-length(expressions)]) eval(expression,envir=.GlobalEnv)
inputs<-unlist(cfg$inputs,use.names=FALSE)
outputs<-unlist(cfg$outputs,use.names=FALSE)
for(i in seq_along(inputs)) do.call(Sys.setenv,setNames(list(inputs[i]),paste0("AUTONOMICS_INPUT",i-1L)))
for(i in seq_along(outputs)) do.call(Sys.setenv,setNames(list(outputs[i]),paste0("AUTONOMICS_OUTPUT",i-1L)))
bulk$bulk_main<-function(args) {
  bundle<-tail(args,1L)
  stopifnot(dir.create(bundle))
  jsonlite::write_json(list(synthetic=TRUE),file.path(bundle,"audit.json"),auto_unbox=TRUE)
  if(identical(args[1L],"LIMMA")) {
    result<-data.frame(gene_id=c("SYN_G1","SYN_G2","SYN_G3"),status=c("ESTIMATED","NOT_ESTIMABLE","ESTIMATED"),
      raw_p=c("0.01","NA","0.2"),family_p=c("0.01","NA","0.2"),check.names=FALSE)
    write.table(result,file.path(bundle,"results.tsv"),sep="\t",quote=FALSE,row.names=FALSE,na="NA")
    saveRDS(list(synthetic=TRUE),file.path(bundle,"official.rds"))
  }
}
original_link<-base::file.link
calls<-0L
edited_identity<-NULL
edit_same_inode<-function(target) {
  before<-system2("stat",c("-c","%d:%i:%u","--",shQuote(target)),stdout=TRUE)
  writeBin(readBin(cfg$foreign,"raw",n=file.info(cfg$foreign)$size),target)
  after<-system2("stat",c("-c","%d:%i:%u","--",shQuote(target)),stdout=TRUE)
  stopifnot(identical(before,after))
  edited_identity<<-list(before=before,after=after)
}
file.link<-function(from,to) {
  calls<<-calls+1L
  if(cfg$case=="sameinode-edit-late-failure" && calls==2L) {
    edit_same_inode(outputs[1L]);stop("SYNTHETIC_LATE_PUBLISH_FAILURE")
  }
  if(cfg$case %in% c("foreign-replacement-late-failure","owned-late-failure") && calls==2L) {
    if(cfg$case=="foreign-replacement-late-failure") {
      stopifnot(unlink(outputs[1L])==0L,file.copy(cfg$foreign,outputs[1L]))
    }
    stop("SYNTHETIC_LATE_PUBLISH_FAILURE")
  }
  linked<-original_link(from,to)
  if(cfg$case=="foreign-replacement-after-link" && calls==1L && isTRUE(linked)) {
    stopifnot(unlink(to)==0L,file.copy(cfg$foreign,to))
  }
  if(isTRUE(linked)) {
    if(cfg$case=="sameinode-edit-after-link" && calls==1L) edit_same_inode(to)
    if(cfg$case=="sameinode-edit-final-after-link" && calls==length(outputs)) edit_same_inode(to)
    if(cfg$case=="sameinode-edit-prior-at-final" && calls==length(outputs)) edit_same_inode(outputs[1L])
  }
  linked
}
status<-tryCatch({entry_main();0L},error=function(error) {
  cat("BLOCKED:",conditionMessage(error),"\n",file=stderr());2L
})
cat(jsonlite::toJSON(list(synthetic_publication_case=cfg$case,exit_status=status,file_link_calls=calls,edited_identity=edited_identity),auto_unbox=TRUE),"\n")
quit(save="no",status=status)
'''


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def run_case(root,stage,case,library):
    root.mkdir()
    inputs=[]
    for index in range(5 if stage=='design' else 6):
        path=root/f'input{index}.txt'
        path.write_text('SYNTHETIC INPUT '+str(index)+'\n')
        inputs.append(path)
    before={path.name:sha(path) for path in inputs}
    directory=root/'output'
    directory.mkdir()
    names=['audit.json'] if stage=='design' else ['results.tsv','audit.json','official.rds']
    outputs=[directory/name for name in names]
    foreign=root/'foreign.txt'
    foreign.write_bytes(b'FOREIGN_REPLACEMENT_MUST_SURVIVE\n')
    if case=='preexisting-output':
        outputs[-1].write_bytes(foreign.read_bytes())
    if case=='dangling-output':
        outputs[0].symlink_to(root/'nonexistent-target')
    if case=='input-as-output':
        inputs[0]=outputs[0]
        inputs[0].write_bytes(b'ORIGINAL_INPUT_MUST_SURVIVE\n')
        before={str(path):sha(path) for path in inputs}
    config=dict(case=case,inputs=list(map(str,inputs)),outputs=list(map(str,outputs)),foreign=str(foreign))
    config_path=root/'case.json'
    config_path.write_text(json.dumps(config))
    driver=root/'driver.R'
    driver.write_text(DRIVER)
    environment={**os.environ,'R_LIBS_USER':str(library),'R_PROFILE_USER':'/dev/null','R_ENVIRON_USER':'/dev/null'}
    process=subprocess.run(['Rscript','--vanilla',str(driver),str(PLUGIN/'scripts'/f'run-{stage}.R'),str(config_path)],
                           env=environment,capture_output=True,text=True,timeout=60)
    (root/'stdout.txt').write_text(process.stdout)
    (root/'stderr.txt').write_text(process.stderr)
    observed=json.loads(process.stdout.strip())
    after={str(path) if case=='input-as-output' else path.name:sha(path) for path in inputs}
    result=dict(stage=stage,case=case,exit=process.returncode,observed=observed,input_hashes_before=before,input_hashes_after=after,
        foreign_sha256=sha(foreign),outputs=[dict(name=path.name,regular=path.is_file(),symlink=path.is_symlink(),
        sha256=sha(path) if path.is_file() else None) for path in outputs])
    assert before==after,'input bytes changed during output publication'
    return result


def validate(result):
    case=result['case']
    outputs=result['outputs']
    if case=='normal':
        assert result['exit']==0 and all(item['regular'] and not item['symlink'] for item in outputs)
    else:
        assert result['exit']==2,'publication refusal/fault must not return success'
        if case.startswith('sameinode-edit'):
            index=len(outputs)-1 if case=='sameinode-edit-final-after-link' else 0
            assert outputs[index]['sha256']==result['foreign_sha256'],'rollback deleted a same-inode edited output'
            assert result['observed']['edited_identity']['before']==result['observed']['edited_identity']['after']
            assert not any(item['regular'] for position,item in enumerate(outputs) if position!=index),'partial result ports escaped failed publication'
        elif case.startswith('foreign-replacement'):
            assert outputs[0]['sha256']==result['foreign_sha256'],'rollback deleted or accepted a foreign replacement'
            assert not any(item['regular'] for item in outputs[1:]),'partial result ports escaped failed publication'
        elif case=='preexisting-output':
            assert outputs[-1]['sha256']==result['foreign_sha256'],'preexisting output changed'
        elif case=='owned-late-failure':
            assert not any(item['regular'] for item in outputs),'owned partial output was not rolled back'
        elif case=='dangling-output':
            assert outputs[0]['symlink'],'existing dangling symlink was removed'
        elif case=='input-as-output':
            assert outputs[0]['regular'],'input alias was removed'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',required=True,type=Path)
    parser.add_argument('--phase',required=True,choices=['baseline','identity-baseline','repaired'])
    args=parser.parse_args()
    permanent=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent:
        parser.error('run this acceptance through the managed session')
    output=Path(permanent)/('normalized-b-publication-'+args.phase)
    output.mkdir()
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    before={name:sha(PLUGIN/'scripts'/name) for name in ['run-design.R','run-limma.R']}
    if args.phase=='baseline':
        cases=[('limma','foreign-replacement-late-failure')]
    elif args.phase=='identity-baseline':
        cases=[(stage,case) for stage in ['design','limma'] for case in ['sameinode-edit-after-link','sameinode-edit-final-after-link']]
        cases += [('limma','sameinode-edit-prior-at-final'),('limma','sameinode-edit-late-failure')]
    else:
        cases=[(stage,case) for stage in ['design','limma'] for case in ['normal','preexisting-output','dangling-output','input-as-output']]
        cases += [('limma','foreign-replacement-late-failure'),('limma','owned-late-failure'),
                  ('limma','foreign-replacement-after-link'),('design','foreign-replacement-after-link')]
        cases += [(stage,case) for stage in ['design','limma'] for case in ['sameinode-edit-after-link','sameinode-edit-final-after-link']]
        cases += [('limma','sameinode-edit-prior-at-final'),('limma','sameinode-edit-late-failure')]
    results=[]
    with tempfile.TemporaryDirectory(prefix='normalized-b-publication-',dir=os.environ['TMPDIR']) as scratch:
        for stage,case in cases:
            root=Path(scratch)/(stage+'-'+case)
            result=run_case(root,stage,case,args.library.resolve(strict=True))
            target=output/root.name
            target.mkdir()
            for name in ['case.json','driver.R','stdout.txt','stderr.txt']:
                (target/name).write_bytes((root/name).read_bytes())
            (target/'observed.json').write_text(json.dumps(result,indent=2)+'\n')
            if args.phase=='baseline':
                assert result['exit']==2 and not result['outputs'][0]['regular']
                assert 'SYNTHETIC_LATE_PUBLISH_FAILURE' in (root/'stderr.txt').read_text()
                try:
                    validate(result)
                except AssertionError as error:
                    assert str(error)=='rollback deleted or accepted a foreign replacement'
                    result['expected_regression_assertion']=str(error)
                else:
                    raise AssertionError('Original rollback corruption was not reproduced')
            elif args.phase=='identity-baseline':
                assert result['observed']['edited_identity']['before']==result['observed']['edited_identity']['after']
                if case=='sameinode-edit-late-failure':
                    assert result['exit']==2 and not result['outputs'][0]['regular']
                else:
                    index=len(result['outputs'])-1 if case=='sameinode-edit-final-after-link' else 0
                    assert result['exit']==0 and result['outputs'][index]['sha256']==result['foreign_sha256']
                try:
                    validate(result)
                except AssertionError as error:
                    result['expected_regression_assertion']=str(error)
                else:
                    raise AssertionError('Same-inode publication corruption was not reproduced')
            else:
                validate(result)
            results.append(result)
    assert before=={name:sha(PLUGIN/'scripts'/name) for name in before},'wrapper source changed during proof'
    record=dict(scope='R_ENTRY_PUBLICATION_CONTROL_WITH_STUB_METHOD_NOT_NUMERICAL_OR_SCIENTIFIC_ACCEPTANCE',
        phase=args.phase,source_sha256=before,cases=results,case_count=len(results),
        baseline_regression_reproduced=args.phase.endswith('baseline'),official_method_numeric_test_run=False,
        containers_started=False,independently_managed_workers_started=False,scientific_authorization=False,G0=False)
    (output/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print('NORMALIZED_B_PUBLICATION_'+args.phase.upper()+'_CONTROL_COMPLETED; NUMERICAL_QUALIFICATION=false; G0=false')


if __name__=='__main__':
    main()
