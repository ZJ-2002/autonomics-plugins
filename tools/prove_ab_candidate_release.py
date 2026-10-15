"""Test an exact A/B-only Git candidate without publishing unrelated dirty work."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = 'ea0617675ed2e6d73b1d7942e13d9863631bd484'
EXPECTED_TESTS = 355
FAMILIES = ('twosamplemr-v432-a', 'bulk-limma-normalized', 'frozen-b-project', 'twosamplemr')
ADAPTERS = ('frozen-a-harmonisation', 'frozen-a-input-qualification')
EXTRA = ('tests/test_frozen_b_project.py', 'tests/test_frozen_a_current_dag.py',
         'tests/test_normalized_b_current_dag.py', 'tools/prove_frozen_b_family_transport.py',
         'tools/prove_frozen_a_current_dag.py', 'tools/prove_normalized_b_current_dag.py',
         'tools/prove_ab_candidate_release.py', 'tools/audit_opentargets_direct_files.py',
         'docs/ab-official-backend-repairs-20261015.md', 'evidence/ab-official-backend-repairs-20261015.json',
         'docs/frozen-a-io-current-dag-20261015.md', 'evidence/frozen-a-io-current-dag-20261015.json',
         'docs/normalized-b-io-official-adjustment-20261015.md',
         'evidence/normalized-b-io-official-adjustment-20261015.json', 'catalog/release-lock.json')
EXTRA += ('tests/test_frozen_b_intake_budget.py', 'tests/test_frozen_b_family_contract.py',
          'tools/prove_frozen_b_intake_budget.py', 'tests/prove_frozen_b_family_contract.py',
          'docs/frozen-b-source-family-closure-20261015.md',
          'docs/ab-candidate-cutover-20261015.md',
          'evidence/frozen-b-source-family-closure-20261015.json')
EXTRA += ('tools/prove_locked_b_source_transport.py', 'tools/build_locked_b_plugin_probe.py',
          'tools/probes/official_plugin_dag.rs', 'tools/reconcile_ab_evidence_index.py',
          'tests/test_locked_b_source_transport.py', 'tests/test_reconcile_ab_evidence_index.py',
          'docs/locked-b-replay-and-index-20261015.md',
          'evidence/locked-b-replay-and-index-20261015.json',
          'evidence/locked-b-replay-node-proof-20261015.tsv')
EXTRA += ('tools/prove_frozen_a_harmonisation.py', 'tools/prove_frozen_a_package_identity.py',
          'tests/test_frozen_a_harmonisation.py', 'docs/frozen-a-harmonisation-20261015.md',
          'evidence/frozen-a-harmonisation-20261015.json')
EXTRA += ('tools/acquire_frozen_a_python_runtime.py', 'tools/prove_frozen_a_plink_source.py',
          'tools/prove_frozen_a_harmonisation_dag.py', 'tests/test_frozen_a_harmonisation_dag.py',
          'tests/test_frozen_a_input_qualification.py', 'docs/frozen-a-upstream-source-20261015.md',
          'evidence/frozen-a-upstream-source-20261015.json')
EXTRA += ('tools/prove_frozen_a_input_qualification.py', 'tests/test_frozen_a_input_qualification_driver.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ids(suite):
    for value in suite:
        if isinstance(value, unittest.TestSuite):
            yield from test_ids(value)
        else:
            yield value.id()


def main():
    if not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') or not os.environ.get('TMPDIR'):
        raise RuntimeError('Managed source-proof session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ab-source-release'
    output.mkdir(mode=0o700)
    scratch = Path(os.environ['TMPDIR'])
    environment = dict(os.environ, GIT_INDEX_FILE=str(scratch / 'ab-release.index'))

    def git(*arguments, data=None):
        return subprocess.check_output(['git', '-C', str(ROOT), *arguments], env=environment, input=data).decode().strip()

    paths = set(EXTRA)
    for namespace, families in [('plugins', FAMILIES), ('research-adapters', ADAPTERS)]:
        for family in families:
            for path in (ROOT / namespace / family).rglob('*'):
                if path.is_symlink():
                    raise RuntimeError('Unreviewed source alias')
                if path.is_file() and '__pycache__' not in path.parts:
                    paths.add(path.relative_to(ROOT).as_posix())
    identities = {name: digest(ROOT / name) for name in sorted(paths)}
    original = json.loads(git('show', PARENT + ':quality/required-tests.json'))
    sys.path.insert(0, str(ROOT))
    additions = set()
    for name in ('tests.test_frozen_b_project', 'tests.test_frozen_a_current_dag', 'tests.test_normalized_b_current_dag',
                 'tests.test_frozen_b_intake_budget', 'tests.test_frozen_b_family_contract'):
        additions.update(test_ids(unittest.defaultTestLoader.loadTestsFromName(name)))
    for name in ('tests.test_locked_b_source_transport', 'tests.test_reconcile_ab_evidence_index',
                 'tests.test_frozen_a_harmonisation', 'tests.test_frozen_a_harmonisation_dag',
                 'tests.test_frozen_a_input_qualification', 'tests.test_frozen_a_input_qualification_driver'):
        additions.update(test_ids(unittest.defaultTestLoader.loadTestsFromName(name)))
    original['test_ids'].extend(sorted(additions - set(original['test_ids'])))
    if len(original['test_ids']) != EXPECTED_TESTS or len(set(original['test_ids'])) != EXPECTED_TESTS:
        raise RuntimeError('Exact A/B release test inventory differs')
    quality = (json.dumps(original, indent=2) + '\n').encode()
    expected_quality = json.loads((ROOT / 'plugins/frozen-b-project/source-lock.json').read_text())['files']['quality/required-tests.json']
    if expected_quality != dict(bytes=len(quality), sha256=hashlib.sha256(quality).hexdigest()):
        raise RuntimeError('Paired family source lock must bind this exact release test inventory')
    git('read-tree', PARENT)
    for name in sorted(paths):
        blob = git('hash-object', '-w', str(ROOT / name))
        mode = '100755' if (ROOT / name).stat().st_mode & 0o111 else '100644'
        git('update-index', '--add', '--cacheinfo', mode + ',' + blob + ',' + name)
    git('update-index', '--add', '--cacheinfo', '100644,' + git('hash-object', '-w', '--stdin', data=quality) + ',quality/required-tests.json')
    tree = git('write-tree')
    message = 'Add scoped official frozen A upstream qualification evidence and guards'
    code_commit = git('commit-tree', tree, '-p', PARENT, '-m', message)
    evolved_path = 'plugins/twosamplemr/manifest.toml'
    evolution = json.loads(git('show', PARENT + ':provenance/source-evolution.json'))
    evolution_bytes = (git('show', PARENT + ':provenance/source-evolution.json') + '\n').encode()
    evolution_commit = None
    commit = code_commit
    if git('rev-parse', PARENT + ':' + evolved_path) != git('rev-parse', code_commit + ':' + evolved_path):
        index = json.loads(git('show', PARENT + ':provenance/source-index.json'))
        origin = next(row for row in index['plugins'] if row['directory'] == 'plugins/twosamplemr')
        original = next(row for row in origin['files'] if row['path'] == 'manifest.toml')
        content = (ROOT / evolved_path).read_bytes()
        change = dict(path=evolved_path,
            original=dict(repository=origin['repository'], revision=origin['revision'],
                          **{key: original[key] for key in ['sha256', 'bytes', 'git_blob']}),
            current=dict(repository='https://github.com/ZJ-2002/autonomics-plugins.git', revision=code_commit,
                         path=evolved_path, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content),
                         git_blob=git('rev-parse', code_commit + ':' + evolved_path)))
        evolution['changes'] = [row for row in evolution['changes'] if row['path'] != evolved_path] + [change]
        evolution_bytes = (json.dumps(evolution, indent=2) + '\n').encode()
        git('update-index', '--add', '--cacheinfo', '100644,' +
            git('hash-object', '-w', '--stdin', data=evolution_bytes) + ',provenance/source-evolution.json')
        tree = git('write-tree')
        commit = git('commit-tree', tree, '-p', code_commit, '-m', 'Record exact imported action documentation source evolution')
        evolution_commit = code_commit
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', PARENT, commit).splitlines()
    if not set(changed) <= paths | {'quality/required-tests.json', 'provenance/source-evolution.json'} or not changed:
        raise RuntimeError('Unrelated source in A/B candidate')
    archive = scratch / 'ab-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '-o', str(archive), commit], check=True)
    source = scratch / 'source'
    source.mkdir()
    with tarfile.open(archive) as handle:
        handle.extractall(source, filter='data')
    subprocess.run(['git', '-C', str(source), 'init', '--quiet'], check=True)
    objects = git('rev-parse', '--path-format=absolute', '--git-path', 'objects')
    (source / '.git/objects/info/alternates').write_text(objects + '\n')
    subprocess.run(['git', '-C', str(source), 'update-ref', '--no-deref', 'HEAD', commit], check=True)
    for name, identity in identities.items():
        if digest(source / name) != identity:
            raise RuntimeError('Git export differs from actual proved source')
    with (output / 'tests.stdout.log').open('x') as stdout, (output / 'tests.stderr.log').open('x') as stderr:
        result = subprocess.run([sys.executable, '-B', str(source / 'tools/run_checks.py'),
            '--output', str(output / 'SOURCE_CHECKS.json')], cwd=source, stdout=stdout, stderr=stderr, timeout=180)
    report = json.loads((output / 'SOURCE_CHECKS.json').read_text())
    if (result.returncode or report['tests_run'] != EXPECTED_TESTS or not report['complete'] or not report['source_lock_matches']
            or report['failures'] or report['errors'] or report['skipped']):
        raise RuntimeError('Exact committed A/B release tests incomplete')
    if identities != {name: digest(ROOT / name) for name in paths}:
        raise RuntimeError('A/B source changed during release proof')
    record = dict(status='EXACT_AB_SOURCE_RELEASE_CHECKED_NOT_DEPLOYED', parent=PARENT, commit=commit, tree=tree,
        actual_commit_parent=git('rev-parse', commit + '^'), source_evolution_commit=evolution_commit,
        source_evolution_ledger_sha256=hashlib.sha256(evolution_bytes).hexdigest(),
        changed_paths=changed, source_sha256=identities, tests_run=report['tests_run'], source_lock_matches=True,
        no_unrelated_dirty_code_imported=True, production_configuration_changed=False, scientific_authorization_granted=False, g0_granted=False)
    (output / 'VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n')
    print(commit)


if __name__ == '__main__':
    main()
