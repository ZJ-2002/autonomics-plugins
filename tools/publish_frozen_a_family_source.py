"""Prepare an exact source-only family release; publication requires explicit --publish."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PARENT = 'cb594425a40bb0df267d0230397efaea32333b80'
REMOTE = 'https://github.com/ZJ-2002/autonomics-plugins.git'
BASE_TESTS = 493
EXPECTED_TESTS = 585
DIRECT_SESSION = '1dd93528d56d4cbe8a18e63247b0c2ee'
DIRECT_SEAL = '93fdedb6434a3ab570cec95e400909ef8b12408819be1acc33732b01dfbf0ccb'
QUALITY = 'quality/required-tests.json'
B_SOURCE_LOCK = 'plugins/frozen-b-project/source-lock.json'
CATALOG = 'catalog/release-lock.json'
FAMILY_PINS = {
    'research-adapters/frozen-a-family-assembly/README.md':
        (2119, 'bb25f9a2ac385cdf0e6acdcdc9ae72c53cfae5c3466423f1c288564fce48b9fc'),
    'research-adapters/frozen-a-family-assembly/contracts/source-lock.json':
        (2991, '6f9b3653a65834a602a0bdf977f570e9527298136421523c34c80831f9fac43c'),
    'research-adapters/frozen-a-family-assembly/manifest.toml':
        (2770, 'a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf'),
    'research-adapters/frozen-a-family-assembly/scripts/family.py':
        (26707, '3370bf9a604de0c3e6acab9e1e7617f7caba579c6630e96f17e0d2f4c002d1ba'),
    'research-adapters/frozen-a-family-adjustment/README.md':
        (2176, 'c0ebd9055f707dfa020fef70ecce3cf3fcc754af9ec48c629476acc406abe632'),
    'research-adapters/frozen-a-family-adjustment/manifest.toml':
        (1636, '55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da'),
    'research-adapters/frozen-a-family-adjustment/scripts/adjust.R':
        (21205, 'debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412'),
}
NEW_TEST_MODULES = {
    'tests.test_frozen_a_family_assembly': 31,
    'tests.test_frozen_a_family_adjustment': 14,
    'tests.test_frozen_a_family_runtime': 13,
    'tests.test_frozen_a_family_probe_build': 10,
    'tests.test_frozen_a_family_dag': 24,
}
TOOL_PATHS = (
    'tools/prove_frozen_a_family_runtime.py',
    'tools/build_frozen_a_family_probe.py',
    'tools/prove_frozen_a_family_dag.py',
    'tools/probes/frozen_a_family_dag.rs',
    'tools/publish_frozen_a_family_source.py',
)
DOCUMENT_PATHS = (
    'docs/frozen-a-complete-family-20261015.md',
    'evidence/frozen-a-complete-family-20261015.json',
)
METADATA_PATHS = (QUALITY, B_SOURCE_LOCK, CATALOG)
SELECTED_PATHS = tuple(FAMILY_PINS) + tuple(name.replace('.', '/') + '.py' for name in NEW_TEST_MODULES) + TOOL_PATHS + DOCUMENT_PATHS
DISCOVER = '''import json,sys,unittest
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root))
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py',top_level_dir=str(root))
def identifiers(value):
    if isinstance(value,unittest.TestSuite):
        return [name for member in value for name in identifiers(member)]
    return [value.id()]
print(json.dumps(identifiers(suite)))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def strict_json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError('Nonfinite JSON constant: ' + value)))


def identity(path):
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in [path, *path.parents]), 'Unaliased ordinary source required')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'Ordinary file required')
    payload = path.read_bytes()
    after = path.lstat()
    fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(fields(before) == fields(after) and len(payload) == before.st_size, 'File changed during identity check')
    return dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
        executable=bool(before.st_mode & 0o111), device=before.st_dev, inode=before.st_ino,
        mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)


def content_identity(path):
    observed = identity(path)
    return {name: observed[name] for name in ['bytes', 'sha256']}


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def write(path, value):
    with path.open('xb') as handle:
        handle.write(json_bytes(value))


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if '.git' in relative.parts or '__pycache__' in relative.parts:
            continue
        require(not path.is_symlink(), 'Unreviewed source link in exported tree')
        if path.is_file():
            result[relative.as_posix()] = content_identity(path)
    return result


def execute(command, *, directory, environment, output, label):
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, timeout=300)
    with (output / (label + '.stdout')).open('xb') as handle:
        handle.write(result.stdout)
    with (output / (label + '.stderr')).open('xb') as handle:
        handle.write(result.stderr)
    write(output / (label + '-execution.json'), dict(command=command, actual_exit=result.returncode))
    require(type(result.returncode) is int and result.returncode == 0, 'Command failed: ' + label)
    return result.stdout


def verified_direct_archive():
    archive = Path.home() / '.local/state/autonomics/validation-archives' / DIRECT_SESSION
    session = strict_json((archive / 'SESSION.json').read_bytes())
    require(session['session'] == DIRECT_SESSION and session['state'] == 'CLEANED' and
        type(session['worker_exit_status']) is int and session['worker_exit_status'] == 0 and
        type(session['launcher_exit_status']) is int and session['launcher_exit_status'] == 0 and
        session['manifest_sha256'] == DIRECT_SEAL, 'Actual successful direct runtime archive required')
    artifacts = archive / 'artifacts'
    require(content_identity(artifacts / 'MANIFEST.json')['sha256'] == DIRECT_SEAL, 'Direct archive seal differs')
    manifest = strict_json((artifacts / 'MANIFEST.json').read_bytes())
    require(manifest['session'] == DIRECT_SESSION and len(manifest['files']) == 183, 'Exact direct evidence inventory required')
    for name, fact in manifest['files'].items():
        require(isinstance(name, str) and not Path(name).is_absolute() and
            all(part not in ['', '.', '..'] for part in name.split('/')), 'Safe archive member required')
        require(content_identity(artifacts / name) == fact, 'Direct archive member differs')
    require(set(inventory(artifacts)) == set(manifest['files']) | {'MANIFEST.json'}, 'Direct archive membership differs')
    proof = strict_json((artifacts / 'permanent/frozen-a-family-runtime/verification.json').read_bytes())
    require(proof['actual_DAG_executed'] is False and proof['full_q_equal'] == 2520 and
        proof['full_official_RDS_vectors_read_back'] == 18 and proof['full_official_RDS_values_exact'] == 2520 and
        proof['scientific_authorization_granted'] is False and proof['g0_granted'] is False,
        'Exact bounded direct-runtime claims required')
    for name, (size, sha) in FAMILY_PINS.items():
        require({key: proof['code_identities'][name][key] for key in ['bytes', 'sha256']} ==
            dict(bytes=size, sha256=sha), 'Direct-runtime family source identity differs')
    return dict(session=DIRECT_SESSION, manifest_sha256=DIRECT_SEAL, members=183,
        all_members_rehashed=True, actual_DAG_executed=False, scientific_authorization_granted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepare-only', action='store_true', help='Prepare and test without network or publication (default)')
    modes.add_argument('--publish', action='store_true', help='After all proof checks, permit ordinary fast-forward publication to own main')
    arguments = parser.parse_args()
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed source-proof session required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session_id = permanent.parent.name
    require(permanent.is_absolute() and permanent.name == 'permanent' and re.fullmatch('[0-9a-f]{32}', session_id), 'Exact permanent path required')
    session = strict_json((Path.home() / '.local/state/autonomics/validation-archives' / session_id / 'SESSION.json').read_bytes())
    require(session.get('schema') == 'TECHNICAL_VALIDATION_SESSION_V1' and session.get('session') == session_id and
        session.get('state') == 'EXECUTING' and session.get('profile') == 'light' and
        session.get('unit') == 'autonomics-validation-' + session_id + '.service' and
        session.get('workspace') == str(permanent.parent), 'Active owned light session required')
    cgroups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    require(len(cgroups) == 1 and cgroups[0].endswith('/' + session['unit'] + '/worker-native'), 'Recorded worker cgroup required')
    scratch = Path(os.environ['TMPDIR'])
    require(scratch.is_absolute() and scratch.resolve(strict=True).is_relative_to(permanent.parent.resolve(strict=True)), 'Owned TMPDIR required')
    output = permanent / 'frozen-a-family-source-release'
    output.mkdir(mode=0o700)
    environment = dict(os.environ, GIT_INDEX_FILE=str(scratch / 'frozen-a-family-source.index'), GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')
    subprocess_environment = {name: value for name, value in environment.items() if name != 'GIT_INDEX_FILE'}

    def git(*parts, payload=None):
        return subprocess.check_output(['git', '-C', str(ROOT), *parts], env=environment, input=payload)

    def canonical_git_path(name):
        path = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--git-path', name], env=subprocess_environment).decode().strip())
        return path if path.is_absolute() else ROOT / path

    def repository_state():
        return dict(head_oid=git('rev-parse', 'HEAD').decode().strip(),
            head=identity(canonical_git_path('HEAD')), index=identity(canonical_git_path('index')))

    before = repository_state()
    write(output / 'repository-before.json', before)
    require(git('cat-file', '-t', PARENT).strip() == b'commit', 'Exact published parent object required')
    quality = strict_json(git('show', PARENT + ':' + QUALITY))
    require(set(quality) == {'scope', 'test_ids'} and quality['scope'] == 'CATALOG_TESTS_NOT_SCIENTIFIC_CERTIFICATES' and
        len(quality['test_ids']) == len(set(quality['test_ids'])) == BASE_TESTS, 'Original 493-test Git inventory required')
    original_tests = list(quality['test_ids'])
    source_lock = strict_json(git('show', PARENT + ':' + B_SOURCE_LOCK))
    original_catalog = strict_json(git('show', PARENT + ':' + CATALOG))
    selected_before = {name: identity(ROOT / name) for name in SELECTED_PATHS}
    for name, (size, sha) in FAMILY_PINS.items():
        require(content_identity(ROOT / name) == dict(bytes=size, sha256=sha), 'Family source differs from actual direct runtime')
    for family in ['frozen-a-family-assembly', 'frozen-a-family-adjustment']:
        directory = ROOT / 'research-adapters' / family
        actual = {path.relative_to(ROOT).as_posix() for path in directory.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts}
        require(actual == {name for name in FAMILY_PINS if name.startswith('research-adapters/' + family + '/')}, 'Unexpected family source member')
        require(not any(path.is_symlink() for path in directory.rglob('*')), 'Family source aliases forbidden')
    write(output / 'direct-runtime-verified.json', verified_direct_archive())
    public_evidence = strict_json((ROOT / DOCUMENT_PATHS[1]).read_bytes())
    require(public_evidence.get('status') == 'DRAFT_DIRECT_RUNTIME_PROVEN_ISOLATED_DAG_PENDING_NOT_DEPLOYED' and
        public_evidence['direct_runtime']['session'] == DIRECT_SESSION and
        public_evidence['direct_runtime']['manifest_sha256'] == DIRECT_SEAL and
        public_evidence['pending']['isolated_current_source_DAG'] == 'PENDING' and
        public_evidence['production_deployed_for_new_family'] is False and public_evidence['g0_granted'] is False,
        'Only direct-proven/DAG-pending draft may enter this source release')
    write(output / 'selected-source-before.json', selected_before)
    parent_archive = scratch / 'parent-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '-o', str(parent_archive), PARENT], env=environment, check=True)
    prepared = scratch / 'prepared-source'
    prepared.mkdir()
    with tarfile.open(parent_archive) as handle:
        handle.extractall(prepared, filter='data')
    for name in SELECTED_PATHS:
        destination = prepared / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        destination.chmod(0o755 if selected_before[name]['executable'] else 0o644)
        require(content_identity(destination) == {key: selected_before[name][key] for key in ['bytes', 'sha256']}, 'Overlay differs from selected source')
    discovered = strict_json(execute([sys.executable, '-B', '-c', DISCOVER, str(prepared)], directory=prepared,
        environment=subprocess_environment, output=output, label='discover-tests'))
    require(isinstance(discovered, list) and len(discovered) == len(set(discovered)) == EXPECTED_TESTS and
        set(original_tests) <= set(discovered), 'Exact 585-test discovery must preserve every original test')
    additions = set(discovered) - set(original_tests)
    require(len(additions) == sum(NEW_TEST_MODULES.values()) and all(
        sum(name.startswith(module + '.') for name in additions) == count for module, count in NEW_TEST_MODULES.items()) and
        all(any(name.startswith(module + '.') for module in NEW_TEST_MODULES) for name in additions), 'Only the exact five new module inventories may be added')
    quality['test_ids'].extend(sorted(additions))
    (prepared / QUALITY).write_bytes(json_bytes(quality))
    updated_lock = copy.deepcopy(source_lock)
    require(QUALITY in updated_lock['files'], 'Existing frozen-B release metadata must include quality identity')
    updated_lock['files'][QUALITY] = content_identity(prepared / QUALITY)
    (prepared / B_SOURCE_LOCK).write_bytes(json_bytes(updated_lock))
    execute([sys.executable, '-B', str(prepared / 'tools/catalog.py'), 'refresh', '--root', str(prepared)],
        directory=prepared, environment=subprocess_environment, output=output, label='refresh-catalog')
    refreshed = strict_json((prepared / CATALOG).read_bytes())
    expected_catalog = copy.deepcopy(original_catalog)
    additions_by_directory = {'research-adapters/frozen-a-family-assembly', 'research-adapters/frozen-a-family-adjustment'}
    new_rows = [row for row in refreshed['families'] if row['directory'] in additions_by_directory]
    require(len(new_rows) == 2 and {row['directory'] for row in new_rows} == additions_by_directory and
        all(row['source_inventory_only'] is True and row['scientific_certified'] is False and row['auto_enable'] is False for row in new_rows), 'Only two unapproved adapter catalog entries may be added')
    b_family = [row for row in expected_catalog['families'] if row['directory'] == 'plugins/frozen-b-project']
    require(len(b_family) == 1, 'One existing frozen-B catalog row required')
    b_member = [row for row in b_family[0]['files'] if row['path'] == 'source-lock.json']
    require(len(b_member) == 1, 'One existing frozen-B source-lock catalog member required')
    b_member[0].update(content_identity(prepared / B_SOURCE_LOCK))
    expected_catalog['families'].extend(new_rows)
    expected_catalog['families'].sort(key=lambda row: (0 if row['directory'].startswith('plugins/') else 1, row['directory']))
    require(refreshed == expected_catalog and refreshed['canonical_families'] == 36 and refreshed['canonical_kinds'] == 69,
        'Catalog changed beyond two research rows and existing release-metadata hash')
    git('read-tree', PARENT)
    selected_paths = SELECTED_PATHS + METADATA_PATHS
    for name in selected_paths:
        path = prepared / name
        blob = git('hash-object', '-w', str(path)).decode().strip()
        git('update-index', '--add', '--cacheinfo', ('100755' if path.stat().st_mode & 0o111 else '100644') + ',' + blob + ',' + name)
    tree = git('write-tree').decode().strip()
    candidate = git('commit-tree', tree, '-p', PARENT, '-m', 'Record direct-proven frozen A complete-family candidate; DAG and deployment pending').decode().strip()
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', PARENT, candidate).decode().splitlines()
    require(changed and set(changed) <= set(selected_paths) and set(METADATA_PATHS) <= set(changed), 'Unreviewed or incomplete release delta')
    for name in selected_paths:
        require(git('show', candidate + ':' + name) == (prepared / name).read_bytes(), 'Candidate Git bytes differ from prepared export')
    raw_commit = git('cat-file', 'commit', candidate)
    require(hashlib.sha1(b'commit ' + str(len(raw_commit)).encode() + b'\0' + raw_commit).hexdigest() == candidate, 'Candidate raw commit identity differs')
    with (output / 'candidate.commit').open('xb') as handle:
        handle.write(raw_commit)
    candidate_archive = scratch / 'candidate-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '-o', str(candidate_archive), candidate], env=environment, check=True)
    committed = scratch / 'committed-source'
    committed.mkdir()
    with tarfile.open(candidate_archive) as handle:
        handle.extractall(committed, filter='data')
    for name in selected_paths:
        require((committed / name).read_bytes() == (prepared / name).read_bytes(), 'Fresh committed export differs')
    subprocess.run(['git', '-C', str(committed), 'init', '--quiet'], env=subprocess_environment, check=True)
    objects = git('rev-parse', '--path-format=absolute', '--git-path', 'objects').decode().strip()
    (committed / '.git/objects/info/alternates').write_text(objects + '\n')
    subprocess.run(['git', '-C', str(committed), 'update-ref', '--no-deref', 'HEAD', candidate], env=subprocess_environment, check=True)
    source_before = inventory(committed)
    write(output / 'committed-source-files.json', source_before)
    execute([sys.executable, '-B', str(committed / 'tools/run_checks.py'), '--output', str(output / 'SOURCE_CHECKS.json')],
        directory=committed, environment=subprocess_environment, output=output, label='source-checks')
    checks = strict_json((output / 'SOURCE_CHECKS.json').read_bytes())
    require(type(checks.get('tests_run')) is int and checks['tests_run'] == EXPECTED_TESTS and checks.get('complete') is True and
        checks.get('source_lock_matches') is True and all(type(checks.get(name)) is int and checks[name] == 0 for name in ['failures', 'errors', 'skipped']) and
        checks.get('required_test_ids') == quality['test_ids'] and len(checks['executed_test_ids']) == EXPECTED_TESTS and
        set(checks['executed_test_ids']) == set(quality['test_ids']), 'Complete exact committed source tests required')
    imports = strict_json(execute([sys.executable, '-B', str(committed / 'tools/catalog.py'), 'verify-import', '--root', str(committed)],
        directory=committed, environment=subprocess_environment, output=output, label='verify-import'))
    require(type(imports.get('imported_files_verified')) is int and imports['imported_files_verified'] > 0 and
        imports.get('current_source_inventory_matches_release_lock') is True, 'Actual imported Git source verification required')
    require(inventory(committed) == source_before, 'Committed export changed during checks')
    require(selected_before == {name: identity(ROOT / name) for name in SELECTED_PATHS}, 'Selected canonical source changed')
    require(repository_state() == before, 'Canonical HEAD or index changed')
    for name in selected_paths:
        destination = output / 'selected-source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(committed / name, destination)
    verification = dict(schema='FROZEN_A_FAMILY_SOURCE_ONLY_RELEASE_V1',
        status='EXACT_SOURCE_CHECKED_DIRECT_PROVEN_DAG_PENDING_NOT_DEPLOYED', parent=PARENT, candidate=candidate,
        git_tree=tree, changed_paths=changed, allowed_paths=list(selected_paths), actual_tests=EXPECTED_TESTS,
        original_tests_preserved=BASE_TESTS, new_test_ids=sorted(additions), selected_source_identities=selected_before,
        candidate_raw_commit_sha256=hashlib.sha256(raw_commit).hexdigest(), imported_source_verification=imports,
        source_lock_matches=True, new_family_source_lock_unchanged=True, canonical_families=36, canonical_kinds=69,
        research_adapter_catalog_rows_added=2, production_configuration_changed=False, production_restarted=False,
        new_family_deployed=False, actual_DAG_executed=False, scientific_authorization_granted=False, g0_granted=False,
        published=False, remote_not_queried_without_publish=True, repository_before=before, repository_after=repository_state())
    write(output / 'PREPARED.json', verification)
    if arguments.publish:
        remote_before = execute(['git', '-C', str(ROOT), 'ls-remote', '--exit-code', REMOTE, 'refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='remote-before').decode().split()
        require(remote_before == [PARENT, 'refs/heads/main'], 'Remote main differs from exact parent; no force, reset or rebase permitted')
        execute(['git', '-C', str(ROOT), 'push', REMOTE, candidate + ':refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='push')
        remote_after = execute(['git', '-C', str(ROOT), 'ls-remote', '--exit-code', REMOTE, 'refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='remote-after').decode().split()
        require(remote_after == [candidate, 'refs/heads/main'], 'Published remote main differs from proved candidate')
        require(repository_state() == before, 'Publication changed canonical HEAD or index')
        verification.update(published=True, remote_main=candidate, remote_not_queried_without_publish=False)
    write(output / 'VERIFICATION.json', verification)
    write(output / 'repository-after.json', repository_state())
    print(json.dumps(dict(candidate=candidate, tests=EXPECTED_TESTS, published=verification['published'], status=verification['status'], G0=False)))


if __name__ == '__main__':
    main()
