"""Build the exact locked A/B technical probe and execute its self-contained Rust guards."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

PARENT = '4ceefbd821baab8deebb070645a2fb8b1fa8e1ba'
EXAMPLE = 'official_plugin_dag'
SOURCE_PATH = 'crates/container-plugin/examples/'+EXAMPLE+'.rs'
GUARDS = {
    'transport_tests::original_synthetic_scope_remains_available',
    'transport_tests::synthetic_scope_cannot_relabel_fixed_real_frozen_b_plugin',
    'transport_tests::exact_transport_job_is_accepted_without_executing_it',
    'transport_tests::fit_sql_conversion_and_unknown_kinds_are_rejected',
    'transport_tests::plugin_identity_panels_and_additional_plugins_cannot_be_substituted',
    'transport_tests::unsafe_paths_specs_and_unknown_scope_are_rejected',
    'transport_tests::source_report_requires_actual_readonly_success_without_scientific_authority',
    'transport_tests::source_capsule_checks_seal_membership_and_each_file_hash',
    'transport_tests::source_capsule_rejects_extra_members_symlinks_and_missing_evidence',
    'transport_tests::full_replay_requires_exact_typed_29_node_64_edge_topology',
    'transport_tests::full_replay_cannot_change_source_images_methods_or_authorization_identity',
    'transport_tests::full_replay_does_not_relax_no_fit_mode',
    'transport_tests::a_harmonisation_requires_exact_six_sources_and_one_method',
    'transport_tests::a_harmonisation_rejects_fit_sql_other_plugins_and_source_substitution',
    'transport_tests::a_harmonisation_requires_all_six_unique_input_bindings',
    'transport_tests::a_harmonisation_cannot_be_relabelled_synthetic',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-repository', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    arguments = parser.parse_args()
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session_id = permanent.parent.name
    archive = Path.home()/'.local/state/autonomics/validation-archives'/session_id
    session = json.loads((archive/'SESSION.json').read_text())
    if session['profile'] != 'build' or session['state'] != 'EXECUTING' or session['workspace'] != str(permanent.parent):
        raise RuntimeError('Active admitted build-profile worker required')
    target = Path.home()/'.cache/localdeploy-target'
    if arguments.target != target or target.is_symlink() or not target.is_dir():
        raise RuntimeError('Existing canonical target required; no sandbox or environment copy')
    output = permanent/'locked-b-probe-build'
    output.mkdir()
    shutil.copyfile(Path(__file__), output/'driver.py')
    source_file = Path(__file__).parent/'probes/official_plugin_dag.rs'
    source_sha = digest(source_file)
    shutil.copyfile(source_file, output/'probe.rs')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    write(output/'resource-preflight.json', dict(memory_available_bytes=available,
          free_bytes=shutil.disk_usage(target).free, canonical_target=str(target),
          no_environment_copy=True, production_restarted=False))
    if available < 6*1024**3 or shutil.disk_usage(target).free < 8*1024**3:
        raise RuntimeError('HOLD: bounded build resources unavailable')
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(os.environ['TMPDIR'])/'locked-b-probe.index'))
    def git(*parts):
        return subprocess.check_output(['git','-C',str(arguments.engine_repository),*parts], env=environment).decode().strip()
    git('read-tree', PARENT)
    blob = git('hash-object','-w',str(source_file))
    git('update-index','--add','--cacheinfo','100644,'+blob+','+SOURCE_PATH)
    tree = git('write-tree')
    commit = git('commit-tree',tree,'-p',PARENT,'-m','Add scope-locked A qualification and B technical transport replay probe')
    changed = git('diff-tree','--no-commit-id','--name-only','-r',PARENT,commit).splitlines()
    if changed != [SOURCE_PATH]:
        raise RuntimeError('Only the reviewed technical probe may differ from the exact parent')
    write(output/'candidate.json',dict(engine_commit=commit,parent_commit=PARENT,git_tree=tree,
          changed_paths=changed,probe_sha256=source_sha,remote_pushed=False,scientific_authorized=False,g0_granted=False))
    source_archive = Path(os.environ['TMPDIR'])/'locked-b-source.tar'
    subprocess.run(['git','-C',str(arguments.engine_repository),'archive','--format=tar','-o',str(source_archive),commit],check=True)
    source = Path(os.environ['TMPDIR'])/'locked-b-source'
    source.mkdir()
    with tarfile.open(source_archive) as stream:
        stream.extractall(source, filter='data')
    before = {path.relative_to(source).as_posix():digest(path) for path in source.rglob('*') if path.is_file() and not path.is_symlink()}
    write(output/'committed-source-files.json',before)
    if digest(source/SOURCE_PATH) != source_sha:
        raise RuntimeError('Exact exported probe identity required')
    build_env = dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_BUILD_JOBS='2',
                     CARGO_TERM_COLOR='never',AUTONOMICS_SOURCE_REVISION=commit)
    results = {}
    for phase, operation, extra in [('runner','build',[]),('guards','test',['--no-run'])]:
        command = ['cargo',operation,'--release','--locked','--offline','-j','2','-p','container-plugin',
                   '--example',EXAMPLE,*extra,'--message-format=json']
        write(output/(phase+'-command.json'),command)
        with (output/(phase+'-cargo.stdout.jsonl')).open('x') as stdout, (output/(phase+'-cargo.stderr.log')).open('x') as stderr:
            result = subprocess.run(command,cwd=source,env=build_env,stdout=stdout,stderr=stderr,timeout=13500)
        write(output/(phase+'-build-exit.json'),dict(exit=result.returncode))
        if result.returncode:
            raise RuntimeError('Actual exact probe build failed; no old executable fallback')
        messages = [json.loads(line) for line in (output/(phase+'-cargo.stdout.jsonl')).read_text().splitlines() if line.startswith('{')]
        artifacts = [Path(message['executable']) for message in messages if message.get('reason')=='compiler-artifact'
                     and message.get('executable') and message.get('target',{}).get('name')==EXAMPLE]
        if len(artifacts) != 1:
            raise RuntimeError('One actual compiler executable required')
        executable = output/('official_plugin_dag' if phase=='runner' else 'guard-tests')
        shutil.copyfile(artifacts[0],executable)
        executable.chmod(0o700)
        results[phase] = dict(executable=executable.name,sha256=digest(executable),compiler_messages=len(messages))
        if phase=='guards':
            with (output/'guards.stdout.log').open('x') as stdout, (output/'guards.stderr.log').open('x') as stderr:
                tested = subprocess.run([str(executable),'--test-threads=1','--color=never'],cwd=source,env=build_env,
                                        stdout=stdout,stderr=stderr,timeout=180)
            text = (output/'guards.stdout.log').read_text()
            observed = re.findall(r'^test (\S+) \.\.\. ok$', text, re.M)
            write(output/'guards-execution.json',dict(exit=tested.returncode,stdout_sha256=digest(output/'guards.stdout.log'),
                  required_tests=sorted(GUARDS),observed_passed_tests=observed))
            if (tested.returncode or len(observed)!=16 or set(observed)!=GUARDS
                    or 'test result: ok. 16 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' not in text):
                raise RuntimeError('All sixteen exact Rust guards must actually pass without ignored or filtered tests')
    after = {path.relative_to(source).as_posix():digest(path) for path in source.rglob('*') if path.is_file() and not path.is_symlink()}
    if before != after or digest(source_file) != source_sha:
        raise RuntimeError('Source changed during exact compilation')
    write(output/'build-record.json',dict(engine_commit=commit,parent_commit=PARENT,git_tree=tree,
          probe_sha256=source_sha,changed_paths=changed,source_unchanged=True,committed_source_files=len(before),
          actual_build_exit=0,executables=results,canonical_target=str(target),remote_pushed=False,
          containers_started=False,real_study_fitted=False,production_restarted=False,scientific_authorized=False,g0_granted=False))
    print(json.dumps(dict(engine_commit=commit,probe_sha256=source_sha,executables=results,scientific_authorized=False,g0_granted=False)))


if __name__ == '__main__':
    main()
