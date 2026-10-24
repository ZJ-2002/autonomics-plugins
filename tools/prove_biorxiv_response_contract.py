"""Reproduce bioRxiv HTTP-to-absence corruption, then prove the repaired connected DAG."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.prove_literature_blank_fields import test_summary


PATHS = ('crates/bib-base/src/query.rs', 'crates/bib-base/tests/biorxiv_response_integrity_dag.rs')
TARGET = 'biorxiv_response_integrity_dag'
BASELINE_CASE = 'http_429_must_not_be_replaced_by_another_server_hit'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def baseline_with_explicit_transport_seam(original, repaired):
    signature = '    async fn fetch_from_server(&self, server: &str, doi: &str) -> Result<Option<Article>> {'
    if original.count(signature) != 1 or repaired.count(signature) != 1:
        raise ValueError('Unique original transport method boundary required')
    old_url = 'format!("https://api.biorxiv.org/details/{server}/{doi}")'
    prefix, suffix = original.split(signature)
    if suffix.count(old_url) != 1:
        raise ValueError('Exact original production URL required')
    fixed_prefix = repaired.split(signature)[0]
    if 'pub fn with_endpoint(' not in fixed_prefix or 'endpoint: String' not in fixed_prefix:
        raise ValueError('Explicit constructor-only fixture seam required')
    return fixed_prefix + signature + suffix.replace(old_url, 'format!("{}/{server}/{doi}", self.endpoint)')


def listed_cases(text):
    names = re.findall(r'^(\S+): test$', text, re.MULTILINE)
    summaries = re.findall(r'^(\d+) tests?, (\d+) benchmarks?$', text, re.MULTILINE)
    if not names or len(set(names)) != len(names) or summaries != [(str(len(names)), '0')]:
        raise ValueError('Actual nonempty unique test inventory required')
    return names


def source_map(source):
    return {str(path.relative_to(source)): digest(path) for path in source.rglob('*')
            if path.is_file() and not path.is_symlink()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-repository', required=True, type=Path)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--target', required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent or not re.fullmatch('[0-9a-f]{40}', arguments.parent):
        raise RuntimeError('Managed exact-commit build required')
    session_path = Path.home() / '.local/state/autonomics/validation-archives' / Path(permanent).parent.name / 'SESSION.json'
    session = json.loads(session_path.read_text())
    if session['profile'] != 'build' or session['state'] != 'EXECUTING' or not arguments.target.is_dir():
        raise RuntimeError('Active admitted build profile and existing canonical build cache required')
    output = Path(permanent) / 'biorxiv-response-contract'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    workspace = Path(os.environ['TMPDIR']) / 'biorxiv-source'
    workspace.mkdir()
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(os.environ['TMPDIR']) / 'biorxiv.index'))

    def git(*parts):
        return subprocess.check_output(['git', '-C', str(arguments.engine_repository), *parts], env=environment).decode().strip()

    overlays = {path: digest(arguments.engine_repository / path) for path in PATHS}
    original = subprocess.check_output(['git', '-C', str(arguments.engine_repository), 'show', arguments.parent + ':' + PATHS[0]]).decode()
    repaired = (arguments.engine_repository / PATHS[0]).read_text()
    seam = baseline_with_explicit_transport_seam(original, repaired)
    seam_file = Path(os.environ['TMPDIR']) / 'baseline-query.rs'
    seam_file.write_text(seam)

    def candidate(label, query):
        git('read-tree', arguments.parent)
        for path, content in [(PATHS[0], query), (PATHS[1], arguments.engine_repository / PATHS[1])]:
            blob = git('hash-object', '-w', str(content))
            git('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path)
        tree = git('write-tree')
        commit = git('commit-tree', tree, '-p', arguments.parent, '-m', label)
        changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', arguments.parent, commit).splitlines()
        if sorted(changes) != sorted(PATHS):
            raise RuntimeError('Candidate source changed outside assigned bioRxiv paths')
        return commit, tree

    baseline_commit, baseline_tree = candidate('test(biorxiv): preserve original response handling with explicit local transport seam', seam_file)
    commit, tree = candidate('fix(biorxiv): separate backend failures, validated absence and ambiguous versions', arguments.engine_repository / PATHS[0])
    archive_path = Path(os.environ['TMPDIR']) / 'committed-source.tar'
    subprocess.run(['git', '-C', str(arguments.engine_repository), 'archive', '--format=tar', '-o', str(archive_path), baseline_commit], check=True)
    with tarfile.open(archive_path) as archive:
        archive.extractall(workspace, filter='data')
    for label, command in [('rustc-version',['rustc','-vV']),('cargo-version',['cargo','-V'])]:
        result = subprocess.run(command,check=True,capture_output=True,text=True,timeout=30)
        (output/(label+'.txt')).write_text(result.stdout)

    def execute(label, revision, selection=None, expected=0):
        destination = output / label
        destination.mkdir()
        child = {name: value for name, value in os.environ.items()
                 if not name.endswith(('_API_KEY', '_TOKEN'))
                 and not name.startswith(('ENDPOINT_', 'LITERATURE_', 'BIORXIV_'))}
        child.update(CARGO_TARGET_DIR=str(arguments.target), CARGO_BUILD_JOBS='2', CARGO_TERM_COLOR='never',
                     AUTONOMICS_SOURCE_REVISION=revision, BIORXIV_RESPONSE_EVIDENCE_ROOT=str(destination / 'dags'))
        command = ['cargo', 'test', '--release', '--locked', '--offline', '-j', '2', '-p', 'bib-base',
                   '--test', TARGET, '--no-run', '--message-format=json']
        write(destination / 'build-command.json', command)
        with (destination / 'build.stdout.jsonl').open('x') as stdout, (destination / 'build.stderr.log').open('x') as stderr:
            build = subprocess.run(command, cwd=workspace, env=child, stdout=stdout, stderr=stderr, timeout=13500)
        write(destination / 'build-exit.json', {'exit': build.returncode})
        if build.returncode:
            raise RuntimeError('Committed bioRxiv build failed: ' + label)
        artifacts = [json.loads(line) for line in (destination / 'build.stdout.jsonl').read_text().splitlines() if line.startswith('{')]
        executables = {entry['executable'] for entry in artifacts if entry.get('reason') == 'compiler-artifact'
                       and entry.get('executable') and entry.get('profile', {}).get('test')
                       and entry.get('target', {}).get('name') == TARGET}
        if len(executables) != 1:
            raise RuntimeError('One exact compiled integration executable required')
        executable = Path(executables.pop())
        durable = destination / 'test-executable'
        shutil.copyfile(executable, durable)
        durable.chmod(0o700)
        executable_hash = digest(durable)
        listing = subprocess.run([str(durable), '--list'], cwd=workspace, env=child, capture_output=True, text=True, check=True)
        (destination / 'test-list.txt').write_text(listing.stdout)
        names = listed_cases(listing.stdout)
        command = [str(durable), *([selection, '--exact'] if selection else []), '--test-threads=1']
        with (destination / 'test.stdout.log').open('x') as stdout, (destination / 'test.stderr.log').open('x') as stderr:
            result = subprocess.run(command, cwd=workspace, env=child, stdout=stdout, stderr=stderr, timeout=240)
        text = (destination / 'test.stdout.log').read_text()
        summary = test_summary(text)
        actual = re.findall(r'^test (\S+) \.\.\. (ok|FAILED|ignored)$', text, re.MULTILINE)
        expected_names = [selection] if selection else names
        if sorted(name for name, status in actual) != sorted(expected_names) or result.returncode != expected:
            raise RuntimeError('Actual executed test inventory or exit differs from frozen expectation')
        if digest(durable) != executable_hash:
            raise RuntimeError('Test executable changed during execution')
        record = dict(exit=result.returncode, expected_exit=expected, listed_tests=names,
                      executed_tests=actual, executable_sha256=executable_hash, **summary)
        write(destination / 'execution.json', record)
        return record

    baseline_map = source_map(workspace)
    baseline = execute('baseline', baseline_commit, BASELINE_CASE, expected=101)
    if baseline['failed'] != 1 or 'HTTP 429 must not become absence' not in (output / 'baseline/test.stdout.log').read_text():
        raise RuntimeError('Baseline did not reproduce the intended corruption')
    if source_map(workspace) != baseline_map:
        raise RuntimeError('Baseline source changed during reproduction')
    (workspace / PATHS[0]).write_bytes((arguments.engine_repository / PATHS[0]).read_bytes())
    before = source_map(workspace)
    write(output / 'committed-source-files.json', before)
    for path in PATHS:
        expected_hash = before[path]
        blob = subprocess.check_output(['git', '-C', str(arguments.engine_repository), 'show', commit + ':' + path])
        if hashlib.sha256(blob).hexdigest() != expected_hash:
            raise RuntimeError('Materialized source does not match committed candidate')
    fixed = execute('repaired', commit)
    if fixed['failed'] or source_map(workspace) != before or overlays != {path: digest(arguments.engine_repository / path) for path in PATHS}:
        raise RuntimeError('Repaired proof failed or source identity drifted')
    reports = list((output / 'repaired/dags').glob('*/run-report.json'))
    if len(reports) != 27 or sum(json.loads(path.read_text())['ok'] for path in reports) != 2:
        raise RuntimeError('All 27 predeclared connected DAG controls must be present, with exactly two successful hits')
    for path in reports:
        graph = json.loads(path.with_name('dag.json').read_text())
        report = json.loads(path.read_text())
        if len(graph['nodes']) != 2 or graph['edges'] != [dict(from_port=0,to_port=0,**{'from':'source','to':'merge'})]:
            raise RuntimeError('Actual connected DAG differs from the predeclared two-node graph')
        if {node['id'] for node in report['nodes']} != {'source','merge'}:
            raise RuntimeError('Runtime node identity differs from graph')
    write(output / 'verification.json', dict(status='BIORXIV_BACKEND_FAILURE_REGRESSION_REPRODUCED_AND_REPAIRED',
        parent=arguments.parent, baseline_commit=baseline_commit, baseline_tree=baseline_tree,
        baseline_constructor_seam_only=True, engine_commit=commit, engine_tree=tree,
        source_sha256=overlays, changed_paths=PATHS, source_unchanged=True, source_files=len(before),
        baseline=baseline, repaired=fixed, actual_connected_dags=len(reports),
        actual_successful_dags=2, actual_failure_dags=25, multiple_versions_require_explicit_adjudication=True,
        live_source_complete_domain_qualified=False, deployed_daemon_verified=False, scientific_authorized=False, g0_granted=False))
    print('BIORXIV_RESPONSE_REPAIR_PROVEN; ALL_PROVIDER_DOMAINS=false; G0=false')


if __name__ == '__main__':
    main()
