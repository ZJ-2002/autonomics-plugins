"""Reproduce and repair blank Crossref queries in exact committed SDK and DAG sources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


PATHS = (
    'crates/crossref/src/query.rs',
    'crates/crossref/tests/structured_search_field_contract.rs',
    'crates/bib-base/tests/literature_provider_field_dag.rs',
)


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def test_summary(text):
    matches = re.findall(r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;', text)
    if len(matches) != 1:
        raise RuntimeError('One actual test summary required')
    status, passed, failed, ignored = matches[0]
    passed, failed, ignored = int(passed), int(failed), int(ignored)
    if passed + failed < 1 or ignored or (status == 'ok') != (failed == 0):
        raise RuntimeError('Missing, empty, inconsistent or skipped actual test execution')
    return dict(passed=passed, failed=failed, ignored=ignored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-repository', type=Path, required=True)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--target', type=Path, required=True)
    arguments = parser.parse_args()
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent or not re.fullmatch('[0-9a-f]{40}', arguments.parent):
        raise RuntimeError('Managed exact-commit build required')
    output = Path(permanent) / 'literature-blank-field-proof'
    output.mkdir(mode=0o700)
    session = json.loads((Path.home() / '.local/state/autonomics/validation-archives'
                          / Path(permanent).parent.name / 'SESSION.json').read_text())
    if session['profile'] != 'build' or session['state'] != 'EXECUTING':
        raise RuntimeError('Active managed build-profile admission required')
    if not arguments.target.is_dir():
        raise RuntimeError('Existing canonical build cache required')
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(os.environ['TMPDIR']) / 'candidate.index'))

    def git(*parts):
        return subprocess.check_output(['git', '-C', str(arguments.engine_repository), *parts],
                                       env=environment).decode().strip()

    overlays = {path: digest(arguments.engine_repository / path) for path in PATHS}

    def candidate(label, paths):
        git('read-tree', arguments.parent)
        for path in paths:
            blob = git('hash-object', '-w', str(arguments.engine_repository / path))
            git('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path)
        tree = git('write-tree')
        commit = git('commit-tree', tree, '-p', arguments.parent, '-m', label)
        changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', arguments.parent, commit).splitlines()
        if sorted(changes) != sorted(paths):
            raise RuntimeError('Unexpected source changes')
        archive_path = Path(os.environ['TMPDIR']) / (label + '.tar')
        subprocess.run(['git', '-C', str(arguments.engine_repository), 'archive', '--format=tar',
                        '-o', str(archive_path), commit], check=True)
        source = Path(os.environ['TMPDIR']) / label
        source.mkdir()
        with tarfile.open(archive_path) as archive:
            archive.extractall(source, filter='data')
        return commit, tree, source

    def compile_and_run(label, source, commit, package, target, selection=None, expected=0):
        directory = output / label
        directory.mkdir()
        build_environment = dict(os.environ, CARGO_TARGET_DIR=str(arguments.target),
                                 CARGO_BUILD_JOBS='2', CARGO_TERM_COLOR='never',
                                 AUTONOMICS_SOURCE_REVISION=commit)
        command = ['cargo', 'test', '--release', '--locked', '--offline', '-j', '2',
                   '-p', package, *target, '--no-run', '--message-format=json']
        write(directory / 'build-command.json', command)
        with (directory / 'cargo.stdout.jsonl').open('x') as stdout, (directory / 'cargo.stderr.log').open('x') as stderr:
            build = subprocess.run(command, cwd=source, env=build_environment,
                                   stdout=stdout, stderr=stderr, timeout=13500)
        write(directory / 'build-exit.json', {'exit': build.returncode})
        if build.returncode:
            raise RuntimeError('Exact source build failed: ' + label)
        artifacts = [json.loads(line) for line in (directory / 'cargo.stdout.jsonl').read_text().splitlines()
                     if line.startswith('{')]
        executables = {entry['executable'] for entry in artifacts
                       if entry.get('reason') == 'compiler-artifact' and entry.get('executable')
                       and entry.get('profile', {}).get('test')}
        if len(executables) != 1:
            raise RuntimeError('Ambiguous actual test executable')
        executable = Path(executables.pop())
        executable_hash = digest(executable)
        durable = directory / 'test-executable'
        shutil.copyfile(executable, durable)
        durable.chmod(0o700)
        command = [str(durable), *([selection] if selection else []), '--test-threads=1']
        execution_environment = dict(build_environment,
            LITERATURE_PROVIDER_FIELD_EVIDENCE_ROOT=str(directory / 'dags'))
        with (directory / 'test.stdout.log').open('x') as stdout, (directory / 'test.stderr.log').open('x') as stderr:
            result = subprocess.run(command, cwd=source, env=execution_environment,
                                    stdout=stdout, stderr=stderr, timeout=180)
        text = (directory / 'test.stdout.log').read_text()
        summary = test_summary(text)
        record = dict(exit=result.returncode, expected_exit=expected, executable_sha256=executable_hash,
                      **summary)
        write(directory / 'execution.json', record)
        if result.returncode != expected or digest(durable) != executable_hash:
            raise RuntimeError('Unexpected execution outcome or changed binary')
        return record

    before_commit, before_tree, before = candidate('reproduce-crossref-blank-query', [PATHS[1]])
    baseline = compile_and_run('baseline', before, before_commit, 'crossref',
                              ['--test', 'structured_search_field_contract'],
                              'every_combination_of_blank_fields_is_rejected', expected=101)
    if baseline['failed'] != 1 or 'blank structured fields must not request' not in (output / 'baseline/test.stdout.log').read_text():
        raise RuntimeError('Baseline failure is not the intended regression')
    commit, tree, source = candidate('fix-crossref-blank-query', PATHS)
    source_before = {str(path.relative_to(source)): digest(path) for path in source.rglob('*')
                     if path.is_file() and not path.is_symlink()}
    write(output / 'committed-source-files.json', source_before)
    results = {}
    results['sdk_query'] = compile_and_run('sdk-query', source, commit, 'crossref', ['--lib'], 'query::tests::')
    results['sdk_contract'] = compile_and_run('sdk-contract', source, commit, 'crossref',
                                            ['--test', 'structured_search_field_contract'])
    results['dag_contract'] = compile_and_run('dag-contract', source, commit, 'bib-base',
                                            ['--test', 'literature_provider_field_dag'])
    source_after = {str(path.relative_to(source)): digest(path) for path in source.rglob('*')
                    if path.is_file() and not path.is_symlink()}
    if source_before != source_after or overlays != {path: digest(arguments.engine_repository / path) for path in PATHS}:
        raise RuntimeError('Source identity changed during proof')
    reports = list((output / 'dag-contract/dags').glob('*/run-report.json'))
    if len(reports) != 15 or any(json.loads(path.read_text())['ok'] for path in reports):
        raise RuntimeError('All fifteen expected rejection DAGs must actually fail')
    write(output / 'verification.json', dict(status='BLANK_QUERY_REGRESSION_REPRODUCED_AND_REPAIRED',
        parent=arguments.parent, baseline_commit=before_commit, baseline_tree=before_tree,
        engine_commit=commit, engine_tree=tree, changed_paths=PATHS, source_sha256=overlays,
        source_unchanged=True, source_files=len(source_before), baseline=baseline, results=results,
        actual_rejection_dags=len(reports), live_provider_or_all_supported_fields_qualified=False,
        deployed_daemon_verified=False, scientific_authorized=False, g0_granted=False))
    print('BLANK_QUERY_REPAIR_PROVEN; OFFICIAL_HTTP_OR_ALL_PROVIDER_CERTIFICATE=false; G0=false')


if __name__ == '__main__':
    main()
