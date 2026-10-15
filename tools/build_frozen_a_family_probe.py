"""Build the dedicated complete-A-family probe with all thirty-seven exact guards."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

PARENT = '11f061589473cb8e4fa57d364ad7107108245de1'
PROBE_SHA = 'aa26a2e25925acf9ea1cc0137b5374947b8b4719b0a63caf0da7dac3f9959555'
KERNEL_SOURCE_PINS = {
    'crates/dag-core/src/resource.rs': '21c32eb20d1a4b22573b1032048329ee7c5f29217066123b718cbbb2b8d75e06',
    'crates/dag-core/src/resource_tests.rs': '9a80098c52b5242b8d3f34734052d0ee26a5ddac021d4ac3e90578c63697a1d7',
    'crates/dag-core/src/dag/execution/local.rs': 'da748075d402c0c1cefebe3a8a1a364f17f3eef6a085599628bc6302979765eb',
}
EXAMPLE = 'frozen_a_family_dag'
SOURCE_PATH = 'crates/container-plugin/examples/'+EXAMPLE+'.rs'
GUARDS = {
    'family_tests::actual_manifest_family_kind_and_immutable_image_are_checked',
    'family_tests::dedicated_families_and_loaded_kinds_cannot_use_other_scopes',
    'family_tests::exact_thirteen_nodes_twenty_two_edges_accept_all_three_cases',
    'family_tests::fit_sql_parameters_extra_and_duplicate_nodes_are_rejected',
    'family_tests::family_sources_require_managed_temporary_root_not_permanent_evidence',
    'family_tests::missing_duplicate_and_rewired_edges_are_rejected',
    'family_tests::panels_bundles_and_extra_authority_are_rejected',
    'family_tests::other_scopes_do_not_gain_temporary_fixture_root_permission',
    'family_tests::pending_identity_never_authorizes_a_family',
    'family_tests::plugin_manifest_script_name_and_additional_family_are_pinned',
    'family_tests::request_incomplete_ids_invalid_probabilities_and_scientific_scope_are_rejected',
    'family_tests::request_schema_missing_duplicate_and_unknown_fields_are_rejected',
    'family_tests::source_reference_path_format_and_content_hash_are_exact',
    'family_tests::technical_requests_accept_literal_complete_synthetic_or_empty_ledger_only',
    'transport_tests::a_harmonisation_cannot_be_relabelled_synthetic',
    'transport_tests::a_harmonisation_rejects_fit_sql_other_plugins_and_source_substitution',
    'transport_tests::a_harmonisation_requires_all_six_unique_input_bindings',
    'transport_tests::a_harmonisation_requires_exact_six_sources_and_one_method',
    'transport_tests::a_raw_cannot_be_relabelled_synthetic_or_other_no_fit_scope',
    'transport_tests::a_raw_rejects_changed_panel_source_digest_manifest_and_plugins',
    'transport_tests::a_raw_requires_all_nine_unique_input_bindings',
    'transport_tests::a_raw_requires_exact_nine_sources_and_one_no_mr_method',
    'transport_tests::a_raw_sources_require_exact_canonical_readonly_mount_and_port_roles',
    'transport_tests::exact_transport_job_is_accepted_without_executing_it',
    'transport_tests::fit_sql_conversion_and_unknown_kinds_are_rejected',
    'transport_tests::full_replay_cannot_change_source_images_methods_or_authorization_identity',
    'transport_tests::full_replay_does_not_relax_no_fit_mode',
    'transport_tests::full_replay_requires_exact_typed_29_node_64_edge_topology',
    'transport_tests::original_synthetic_scope_remains_available',
    'transport_tests::plugin_identity_panels_and_additional_plugins_cannot_be_substituted',
    'transport_tests::source_capsule_checks_seal_membership_and_each_file_hash',
    'transport_tests::source_capsule_rejects_extra_members_symlinks_and_missing_evidence',
    'transport_tests::source_report_requires_actual_readonly_success_without_scientific_authority',
    'transport_tests::synthetic_manifest_kinds_cannot_hide_locked_nodes_by_renaming',
    'transport_tests::synthetic_scope_cannot_relabel_fixed_real_frozen_b_plugin',
    'transport_tests::synthetic_scope_rejects_renamed_families_with_locked_kinds',
    'transport_tests::unsafe_paths_specs_and_unknown_scope_are_rejected',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def checked_probe_source(path):
    if path.is_symlink() or not path.is_file() or digest(path) != PROBE_SHA:
        raise RuntimeError('Exact reviewed thirty-seven-guard probe source required')
    return PROBE_SHA


def snapshot_kernel_sources(repository, exported, destination):
    records = {}
    for name, expected in KERNEL_SOURCE_PINS.items():
        payload = subprocess.check_output(['git', '-C', str(repository), 'show', PARENT + ':' + name])
        path = exported / name
        if (hashlib.sha256(payload).hexdigest() != expected or path.is_symlink() or not path.is_file()
                or path.read_bytes() != payload):
            raise RuntimeError('Committed and exported native memory source must match the pinned fixed engine: ' + name)
        snapshot = destination / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open('xb') as handle:
            handle.write(payload)
        if digest(snapshot) != expected:
            raise RuntimeError('Native memory source snapshot differs: ' + name)
        records[name] = dict(sha256=expected, bytes=len(payload))
    return records


def repository_identity(repository):
    head = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD']).decode().strip()
    index = Path(subprocess.check_output(['git', '-C', str(repository), 'rev-parse', '--git-path', 'index']).decode().strip())
    if not index.is_absolute():
        index = repository / index
    if index.is_symlink() or (index.exists() and not index.is_file()):
        raise RuntimeError('Ordinary active Git index required')
    return dict(head=head, index_path=str(index), index_sha256=digest(index) if index.exists() else None)


def private_git_environment(temporary):
    return dict(os.environ, GIT_INDEX_FILE=str(temporary / 'frozen-a-family-probe.index'))


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
    output = permanent/'frozen-a-family-probe-build'
    output.mkdir()
    shutil.copyfile(Path(__file__), output/'driver.py')
    source_file = Path(__file__).parent/'probes/frozen_a_family_dag.rs'
    source_sha = checked_probe_source(source_file)
    shutil.copyfile(source_file, output/'probe.rs')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    write(output/'resource-preflight.json', dict(memory_available_bytes=available,
          free_bytes=shutil.disk_usage(target).free, canonical_target=str(target),
          no_environment_copy=True, production_restarted=False))
    if available < 6*1024**3 or shutil.disk_usage(target).free < 8*1024**3:
        raise RuntimeError('HOLD: bounded build resources unavailable')
    active_before = repository_identity(arguments.engine_repository)
    environment = private_git_environment(Path(os.environ['TMPDIR']))
    def git(*parts):
        return subprocess.check_output(['git','-C',str(arguments.engine_repository),*parts], env=environment).decode().strip()
    git('read-tree', PARENT)
    blob = git('hash-object','-w',str(source_file))
    git('update-index','--add','--cacheinfo','100644,'+blob+','+SOURCE_PATH)
    tree = git('write-tree')
    commit = git('commit-tree',tree,'-p',PARENT,'-m','Add scope-locked complete A family technical replay probe')
    changed = git('diff-tree','--no-commit-id','--name-only','-r',PARENT,commit).splitlines()
    if changed != [SOURCE_PATH]:
        raise RuntimeError('Only the reviewed technical probe may differ from the exact parent')
    if repository_identity(arguments.engine_repository) != active_before:
        raise RuntimeError('Active Git HEAD or index changed while preparing isolated candidate')
    raw_commit = subprocess.check_output(['git', '-C', str(arguments.engine_repository), 'cat-file', 'commit', commit], env=environment)
    if hashlib.sha1(b'commit ' + str(len(raw_commit)).encode() + b'\0' + raw_commit).hexdigest() != commit:
        raise RuntimeError('Exact raw candidate Git commit identity required')
    (output/'candidate.commit').write_bytes(raw_commit)
    write(output/'candidate.json',dict(engine_commit=commit,parent_commit=PARENT,git_tree=tree,
          changed_paths=changed,probe_sha256=source_sha,kernel_source_pins=KERNEL_SOURCE_PINS,
          remote_pushed=False,scientific_authorized=False,g0_granted=False))
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
    kernel_sources = snapshot_kernel_sources(arguments.engine_repository, source, output/'kernel-source')
    write(output/'kernel-source-pins.json', dict(parent_commit=PARENT, files=kernel_sources,
          exported_sources_equal_committed_parent=True, old_sdk_fallback_allowed=False))
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
        executable = output/(EXAMPLE if phase=='runner' else 'guard-tests')
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
            if (tested.returncode or len(observed)!=37 or set(observed)!=GUARDS
                    or 'test result: ok. 37 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' not in text):
                raise RuntimeError('All thirty-seven exact Rust guards must actually pass without ignored or filtered tests')
    after = {path.relative_to(source).as_posix():digest(path) for path in source.rglob('*') if path.is_file() and not path.is_symlink()}
    if before != after or digest(source_file) != source_sha:
        raise RuntimeError('Source changed during exact compilation')
    active_after = repository_identity(arguments.engine_repository)
    if active_before != active_after:
        raise RuntimeError('Active Git HEAD or index changed during isolated build')
    write(output/'active-git-preservation.json', dict(before=active_before, after=active_after,
          active_head_and_index_unchanged=True, private_index=environment['GIT_INDEX_FILE']))
    write(output/'build-record.json',dict(engine_commit=commit,parent_commit=PARENT,git_tree=tree,
          probe_sha256=source_sha,changed_paths=changed,source_unchanged=True,committed_source_files=len(before),
          kernel_source_pins=kernel_sources,old_sdk_fallback_allowed=False,
          actual_build_exit=0,executables=results,canonical_target=str(target),remote_pushed=False,
          containers_started=False,real_study_fitted=False,production_restarted=False,scientific_authorized=False,g0_granted=False))
    print(json.dumps(dict(engine_commit=commit,probe_sha256=source_sha,executables=results,scientific_authorized=False,g0_granted=False)))


if __name__ == '__main__':
    main()
