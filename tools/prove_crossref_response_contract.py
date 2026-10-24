"""Prove the Crossref success-envelope and author-order regressions on exact source candidates."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.prove_biorxiv_response_contract import digest, listed_cases, source_map, write
from tools.prove_literature_blank_fields import test_summary


PATHS = ('crates/crossref/src/client.rs','crates/crossref/src/types.rs','crates/crossref/src/convert.rs',
         'crates/crossref/src/format.rs',
         'crates/crossref/tests/crossref_response_integrity.rs')
TARGET = 'crossref_response_integrity'
BASELINE_CASES = ('regression_missing_work_list_metadata_is_not_a_zero_result',
                  'regression_author_sequence_does_not_assert_corresponding')


def validate_execution(text,names,expected_failure=False):
    summary = test_summary(text)
    actual = re.findall(r'^test (\S+) \.\.\. (ok|FAILED|ignored)$',text,re.MULTILINE)
    if sorted(name for name,status in actual)!=sorted(names):
        raise ValueError('Actual test execution must equal the requested nonempty inventory')
    if any(status!=('FAILED' if expected_failure else 'ok') for name,status in actual):
        raise ValueError('Each regression must have its independently expected actual outcome')
    return dict(**summary,executed_tests=actual)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-repository',required=True,type=Path)
    parser.add_argument('--parent',required=True)
    parser.add_argument('--target',required=True,type=Path)
    arguments=parser.parse_args()
    permanent=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent or not re.fullmatch('[0-9a-f]{40}',arguments.parent):
        raise RuntimeError('Managed exact-commit build required')
    session_path=Path.home()/'.local/state/autonomics/validation-archives'/Path(permanent).parent.name/'SESSION.json'
    session=json.loads(session_path.read_text())
    if session['profile']!='build' or session['state']!='EXECUTING' or not arguments.target.is_dir():
        raise RuntimeError('Active admitted build profile and existing canonical build cache required')
    output=Path(permanent)/'crossref-response-contract'
    output.mkdir(mode=0o700)
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    workspace=Path(os.environ['TMPDIR'])/'crossref-source'
    workspace.mkdir()
    environment=dict(os.environ,GIT_INDEX_FILE=str(Path(os.environ['TMPDIR'])/'crossref-response.index'))

    def git(*parts):
        return subprocess.check_output(['git','-C',str(arguments.engine_repository),*parts],env=environment).decode().strip()

    overlays={path:digest(arguments.engine_repository/path) for path in PATHS}

    def candidate(label,paths):
        git('read-tree',arguments.parent)
        for path in paths:
            blob=git('hash-object','-w',str(arguments.engine_repository/path))
            git('update-index','--add','--cacheinfo','100644,'+blob+','+path)
        tree=git('write-tree')
        commit=git('commit-tree',tree,'-p',arguments.parent,'-m',label)
        changes=git('diff-tree','--no-commit-id','--name-only','-r',arguments.parent,commit).splitlines()
        if sorted(changes)!=sorted(paths):
            raise RuntimeError('Candidate source changed outside assigned Crossref paths')
        return commit,tree

    baseline_commit,baseline_tree=candidate('test(crossref): reproduce incomplete envelope and author-order corruption',[PATHS[-1]])
    commit,tree=candidate('fix(crossref): validate work response identity without inventing corresponding authors',PATHS)
    archive_path=Path(os.environ['TMPDIR'])/'committed-source.tar'
    subprocess.run(['git','-C',str(arguments.engine_repository),'archive','--format=tar','-o',str(archive_path),baseline_commit],check=True)
    with tarfile.open(archive_path) as archive:
        archive.extractall(workspace,filter='data')
    for label,command in [('rustc-version',['rustc','-vV']),('cargo-version',['cargo','-V'])]:
        result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=30)
        (output/(label+'.txt')).write_text(result.stdout)

    def execute(label,revision,selection=None,expected=0):
        destination=output/label
        destination.mkdir()
        child={name:value for name,value in os.environ.items()
               if not name.endswith(('_API_KEY','_TOKEN'))
               and not name.startswith(('ENDPOINT_','LITERATURE_','CROSSREF_'))}
        child.update(CARGO_TARGET_DIR=str(arguments.target),CARGO_BUILD_JOBS='2',CARGO_TERM_COLOR='never',
                     AUTONOMICS_SOURCE_REVISION=revision,CROSSREF_RESPONSE_EVIDENCE_ROOT=str(destination/'cases'))
        command=['cargo','test','--release','--locked','--offline','-j','2','-p','crossref',
                 '--test',TARGET,'--no-run','--message-format=json']
        write(destination/'build-command.json',command)
        with (destination/'build.stdout.jsonl').open('x') as stdout,(destination/'build.stderr.log').open('x') as stderr:
            build=subprocess.run(command,cwd=workspace,env=child,stdout=stdout,stderr=stderr,timeout=13500)
        write(destination/'build-exit.json',{'exit':build.returncode})
        if build.returncode:
            raise RuntimeError('Committed Crossref build failed: '+label)
        artifacts=[json.loads(line) for line in (destination/'build.stdout.jsonl').read_text().splitlines() if line.startswith('{')]
        executables={entry['executable'] for entry in artifacts if entry.get('reason')=='compiler-artifact'
                     and entry.get('executable') and entry.get('profile',{}).get('test')
                     and entry.get('target',{}).get('name')==TARGET}
        if len(executables)!=1:
            raise RuntimeError('One exact compiled integration executable required')
        executable=Path(executables.pop())
        durable=destination/'test-executable'
        shutil.copyfile(executable,durable)
        durable.chmod(0o700)
        executable_hash=digest(durable)
        listing=subprocess.run([str(durable),'--list'],cwd=workspace,env=child,capture_output=True,text=True,check=True)
        (destination/'test-list.txt').write_text(listing.stdout)
        names=listed_cases(listing.stdout)
        command=[str(durable),*([selection] if selection else []),'--test-threads=1']
        with (destination/'test.stdout.log').open('x') as stdout,(destination/'test.stderr.log').open('x') as stderr:
            result=subprocess.run(command,cwd=workspace,env=child,stdout=stdout,stderr=stderr,timeout=240)
        text=(destination/'test.stdout.log').read_text()
        selected=list(BASELINE_CASES) if selection else names
        checked=validate_execution(text,selected,expected_failure=bool(expected))
        if result.returncode!=expected or digest(durable)!=executable_hash:
            raise RuntimeError('Executable identity or exit differed from frozen expectation')
        record=dict(exit=result.returncode,expected_exit=expected,listed_tests=names,
                    executable_sha256=executable_hash,**checked)
        write(destination/'execution.json',record)
        return record

    baseline_map=source_map(workspace)
    baseline=execute('baseline',baseline_commit,'regression_',expected=101)
    text=(output/'baseline/test.stdout.log').read_text()
    if baseline['failed']!=2 or 'genuine zero-result list' not in text or 'invent corresponding-author evidence' not in text:
        raise RuntimeError('Both baseline failures must reproduce the intended independent regressions')
    if source_map(workspace)!=baseline_map:
        raise RuntimeError('Baseline source changed during reproduction')
    for path in PATHS[:-1]:
        (workspace/path).write_bytes((arguments.engine_repository/path).read_bytes())
    before=source_map(workspace)
    write(output/'committed-source-files.json',before)
    for path in PATHS:
        blob=subprocess.check_output(['git','-C',str(arguments.engine_repository),'show',commit+':'+path])
        if hashlib.sha256(blob).hexdigest()!=before[path]:
            raise RuntimeError('Materialized source differs from the committed candidate')
    repaired=execute('repaired',commit)
    if repaired['failed'] or source_map(workspace)!=before or overlays!={path:digest(arguments.engine_repository/path) for path in PATHS}:
        raise RuntimeError('Repaired proof failed or source identity drifted')
    records=list((output/'repaired/cases').glob('*/actual-sdk-result.json'))
    if len(records)!=31:
        raise RuntimeError('Every predeclared Crossref fixture domain must produce actual evidence')
    write(output/'verification.json',dict(status='CROSSREF_RESPONSE_AND_AUTHOR_ORDER_REGRESSIONS_REPRODUCED_AND_REPAIRED',
        parent=arguments.parent,baseline_commit=baseline_commit,baseline_tree=baseline_tree,
        engine_commit=commit,engine_tree=tree,changed_paths=PATHS,source_sha256=overlays,
        source_unchanged=True,source_files=len(before),baseline=baseline,repaired=repaired,
        actual_fixture_cases=len(records),all_cases_are_sdk_not_dag=True,
        absent_corresponding_assertion_is_not_confirmed_negative=True,
        live_source_complete_domain_qualified=False,deployed_daemon_verified=False,scientific_authorized=False,g0_granted=False))
    print('CROSSREF_RESPONSE_REPAIR_PROVEN; ALL_PROVIDER_DOMAINS=false; G0=false')


if __name__=='__main__':
    main()
