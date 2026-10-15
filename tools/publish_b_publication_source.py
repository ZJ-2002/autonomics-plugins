"""Prepare exact B publication-repair source; only explicit --publish permits own-main FF."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import publish_frozen_a_family_source as shared

require = shared.require
strict_json = shared.strict_json
identity = shared.identity
content_identity = shared.content_identity
json_bytes = shared.json_bytes
write = shared.write
inventory = shared.inventory
execute = shared.execute
PARENT = 'd91be9dad535e79c97fb3566b07fe1f68d0954ba'
REMOTE = 'https://github.com/ZJ-2002/autonomics-plugins.git'
SHARED_SHA = '47704da4548ccb64db5e41ded0105d3ce58783eed52d4bb9530c171a8a5047f6'
BASE_TESTS = 585
EXPECTED_TESTS = 639
QUALITY = 'quality/required-tests.json'
B_SOURCE_LOCK = 'plugins/frozen-b-project/source-lock.json'
CATALOG = 'catalog/release-lock.json'
EVOLUTION = 'provenance/source-evolution.json'
SOURCE_INDEX = 'provenance/source-index.json'
DIRECT_SESSION = '3916f488e09e4ded99b39890cfc4cf68'
DIRECT_SEAL = '001806a1bd052088aefe6e663624c6b859d6252b8b839779e45569f332f568ef'
TOY_SESSION = '90cd8c2be137412595dd47ebec644dae'
TOY_SEAL = 'c054a3f2975e894ed61e0cd23b74286d7911bf5e4053164d669e05f376b4eddc'
IMPORTED_PINS = {
    'plugins/pseudobulk/scripts/pseudobulk_counts.py':
        (21097, 'd1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109'),
    'plugins/single-cell/scripts/score_genes.py':
        (12674, 'dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774'),
    'plugins/single-cell/tests/test_score_genes_contract.py':
        (2130, '43fb66628521a85cbc05131367907488d65fc447224adedd8b6977a2e77ee857'),
}
NEW_TEST_MODULES = {
    'tests.test_pseudobulk_publication_ownership': 12,
    'tests.test_score_genes_publication': 28,
    'tests.test_b_publication_dag': 14,
}
TOOL_PATHS = (
    'tools/prove_pseudobulk_publication_ownership.py',
    'tools/check_pseudobulk_publication_runtime.py',
    'tools/check_score_genes_publication_runtime.py',
    'tools/prove_b_publication_runtime.py',
    'tools/prove_b_publication_dag.py',
    'tools/publish_b_publication_source.py',
)
ASSOCIATED_A_SOURCE_PATHS = (
    'tools/probes/frozen_a_family_dag.rs',
    'tools/build_frozen_a_family_probe.py',
    'tools/prove_frozen_a_family_dag.py',
    'tests/test_frozen_a_family_probe_build.py',
)
DOCUMENT_PATHS = (
    'docs/b-publication-ownership-20261015.md',
    'evidence/b-publication-ownership-20261015.json',
)
METADATA_PATHS = (QUALITY, B_SOURCE_LOCK, CATALOG, EVOLUTION)
SELECTED_PATHS = tuple(IMPORTED_PINS) + tuple(module.replace('.', '/') + '.py' for module in NEW_TEST_MODULES) + TOOL_PATHS + DOCUMENT_PATHS + ASSOCIATED_A_SOURCE_PATHS
NESTED_NAMES = {
    'test_current_ten_nodes_keep_other_nine_definitions_unchanged',
    'test_injected_script_and_ports', 'test_proved_script_bytes',
    'test_seed_domain', 'test_retained_image_and_family_panel',
}
NESTED = '''import importlib.util,json,sys,unittest
path=sys.argv[1]
spec=importlib.util.spec_from_file_location('score_contract',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Observed(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.executed=[]
    def startTest(self,test):
        self.executed.append(test.id())
        super().startTest(test)
suite=unittest.defaultTestLoader.loadTestsFromTestCase(module.ScoringContractTests)
result=unittest.TextTestRunner(stream=sys.stderr,verbosity=2,resultclass=Observed).run(suite)
json.dump(dict(tests_run=result.testsRun,executed_test_ids=result.executed,failures=len(result.failures),
    errors=len(result.errors),skipped=len(result.skipped)),sys.stdout)
sys.stdout.write('\\n')
sys.exit(0 if result.wasSuccessful() and not result.skipped and result.testsRun==5 else 1)
'''


def verified_archive(session_id, seal, expected_members):
    archive = Path.home() / '.local/state/autonomics/validation-archives' / session_id
    session = strict_json((archive / 'SESSION.json').read_bytes())
    require(session['session'] == session_id and session['state'] == 'CLEANED' and
        type(session['worker_exit_status']) is int and session['worker_exit_status'] == 0 and
        type(session['launcher_exit_status']) is int and session['launcher_exit_status'] == 0 and
        session['manifest_sha256'] == seal, 'Exact successful technical archive required')
    artifacts = archive / 'artifacts'
    require(content_identity(artifacts / 'MANIFEST.json')['sha256'] == seal, 'Technical archive seal differs')
    manifest = strict_json((artifacts / 'MANIFEST.json').read_bytes())
    require(manifest['session'] == session_id and len(manifest['files']) == expected_members, 'Exact archive membership count required')
    for name, fact in manifest['files'].items():
        require(isinstance(name, str) and not Path(name).is_absolute() and
            all(part not in ['', '.', '..'] for part in name.split('/')), 'Safe ordinary archive member required')
        require(content_identity(artifacts / name) == fact, 'Archived evidence bytes differ')
    require(set(inventory(artifacts)) == set(manifest['files']) | {'MANIFEST.json'}, 'Archive has missing or extra files')
    return artifacts


def checked_evidence():
    artifacts = verified_archive(DIRECT_SESSION, DIRECT_SEAL, 473)
    proof = strict_json((artifacts / 'permanent/b-publication-runtime/verification.json').read_bytes())
    require(proof['actual_method_containers'] == proof['owned_container_intents_verified'] == 2 and
        proof['containers_remaining'] == 0 and proof['actual_DAG_executed'] is False and
        proof['scientific_authorization_granted'] is False and proof['g0_granted'] is False,
        'Bounded successful direct methods, not invented DAG authority, required')
    require(proof['pseudobulk']['actual_child_processes'] == 82 and
        proof['score_genes']['actual_scientific_suite_cases'] == 14 and
        len(proof['score_genes']['publication_cases']) == 6 and
        proof['score_genes']['descriptor_h5ad_compatibility']['actual_official_AnnData_write_h5ad_and_readback'] is True,
        'Complete original/fixed actual runtime inventory required')
    for name, (size, sha) in list(IMPORTED_PINS.items())[:2]:
        require({key: proof['sources'][name][key] for key in ['bytes', 'sha256']} == dict(bytes=size, sha256=sha),
            'B method source differs from actual direct-runtime evidence')
    toy = verified_archive(TOY_SESSION, TOY_SEAL, 9)
    counter = strict_json((toy / 'permanent/pseudobulk-publication-ownership/verification.json').read_bytes())
    require(counter['current_sha256'] == IMPORTED_PINS['plugins/pseudobulk/scripts/pseudobulk_counts.py'][1] and
        counter['versions'] == 2 and counter['controls_per_version'] == 9 and
        counter['numerical_aggregation_executed'] is False and counter['actual_node_run_executed'] is False,
        'Exact eighteen publication observations required without method overclaim')
    return dict(direct_session=DIRECT_SESSION, direct_seal=DIRECT_SEAL, direct_members=473,
        publication_toy_session=TOY_SESSION, publication_toy_seal=TOY_SEAL, publication_toy_members=9,
        all_members_rehashed=True, original_direct_DAG_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepare-only', action='store_true', help='Default: prepare and prove source without network or push')
    modes.add_argument('--publish', action='store_true', help='After proof, permit ordinary fast-forward push to own exact-parent main')
    arguments = parser.parse_args()
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed source-proof session required')
    require(content_identity(Path(shared.__file__).resolve())['sha256'] == SHARED_SHA, 'Reviewed shared source-release helper required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session_id = permanent.parent.name
    require(permanent.is_absolute() and permanent.name == 'permanent' and re.fullmatch('[0-9a-f]{32}', session_id), 'Exact managed permanent path required')
    session = strict_json((Path.home() / '.local/state/autonomics/validation-archives' / session_id / 'SESSION.json').read_bytes())
    require(session.get('schema') == 'TECHNICAL_VALIDATION_SESSION_V1' and session.get('session') == session_id and
        session.get('state') == 'EXECUTING' and session.get('profile') == 'light' and
        session.get('unit') == 'autonomics-validation-' + session_id + '.service' and
        session.get('workspace') == str(permanent.parent), 'Active owned light session required')
    cgroups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    require(len(cgroups) == 1 and cgroups[0].endswith('/' + session['unit'] + '/worker-native'), 'Recorded worker service cgroup required')
    scratch = Path(os.environ['TMPDIR'])
    require(scratch.is_absolute() and scratch.resolve(strict=True).is_relative_to(permanent.parent.resolve(strict=True)), 'Owned TMPDIR required')
    output = permanent / 'b-publication-source-release'
    output.mkdir(mode=0o700)
    environment = dict(os.environ, GIT_INDEX_FILE=str(scratch / 'b-publication-private.index'),
        GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')
    subprocess_environment = {key: value for key, value in environment.items() if key != 'GIT_INDEX_FILE'}

    def git(*parts, payload=None):
        return subprocess.check_output(['git', '-C', str(ROOT), *parts], env=environment, input=payload)

    def canonical_git_path(name):
        path = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--git-path', name],
            env=subprocess_environment).decode().strip())
        return path if path.is_absolute() else ROOT / path

    def repository_state():
        return dict(head_oid=git('rev-parse', 'HEAD').decode().strip(),
            head=identity(canonical_git_path('HEAD')), index=identity(canonical_git_path('index')))

    before = repository_state()
    write(output / 'repository-before.json', before)
    require(git('cat-file', '-t', PARENT).strip() == b'commit', 'Exact published parent object required')
    require(git('show', PARENT + ':tools/publish_frozen_a_family_source.py') == Path(shared.__file__).read_bytes(),
        'Shared helper must equal the exact parent Git source')
    original_quality = strict_json(git('show', PARENT + ':' + QUALITY))
    require(set(original_quality) == {'scope', 'test_ids'} and
        original_quality['scope'] == 'CATALOG_TESTS_NOT_SCIENTIFIC_CERTIFICATES' and
        len(original_quality['test_ids']) == len(set(original_quality['test_ids'])) == BASE_TESTS,
        'Complete original 585-test Git inventory required; mutable local inventory is not authoritative')
    original_lock = strict_json(git('show', PARENT + ':' + B_SOURCE_LOCK))
    original_catalog = strict_json(git('show', PARENT + ':' + CATALOG))
    original_evolution = strict_json(git('show', PARENT + ':' + EVOLUTION))
    source_index = strict_json(git('show', PARENT + ':' + SOURCE_INDEX))
    selected_before = {name: identity(ROOT / name) for name in SELECTED_PATHS}
    for name, (size, sha) in IMPORTED_PINS.items():
        require(content_identity(ROOT / name) == dict(bytes=size, sha256=sha), 'Reviewed B source identity differs')
    write(output / 'selected-source-before.json', selected_before)
    write(output / 'direct-runtime-verified.json', checked_evidence())
    public_evidence = strict_json((ROOT / DOCUMENT_PATHS[1]).read_bytes())
    require(public_evidence['direct_runtime']['session'] == DIRECT_SESSION and
        public_evidence['direct_runtime']['manifest_sha256'] == DIRECT_SEAL and
        public_evidence['scientific_authorization_granted'] is False and public_evidence['g0_granted'] is False,
        'Public scope must retain exact direct evidence and false scientific authority')
    parent_tar = scratch / 'parent-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '-o', str(parent_tar), PARENT], env=environment, check=True)
    prepared = scratch / 'prepared-source'
    prepared.mkdir()
    with tarfile.open(parent_tar) as handle:
        handle.extractall(prepared, filter='data')
    for name in SELECTED_PATHS:
        destination = prepared / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        destination.chmod(0o755 if selected_before[name]['executable'] else 0o644)
        require(content_identity(destination) == {key: selected_before[name][key] for key in ['bytes', 'sha256']},
            'Selected source overlay differs')
    discovered = strict_json(execute([sys.executable, '-B', '-c', shared.DISCOVER, str(prepared)],
        directory=prepared, environment=subprocess_environment, output=output, label='discover-tests'))
    require(isinstance(discovered, list) and len(discovered) == len(set(discovered)) == EXPECTED_TESTS and
        set(original_quality['test_ids']) <= set(discovered), 'Exact 639-test discovery must preserve every original 585 ID')
    additions = set(discovered) - set(original_quality['test_ids'])
    require(len(additions) == 54 and all(sum(name.startswith(module + '.') for name in additions) == count
        for module, count in NEW_TEST_MODULES.items()) and all(any(name.startswith(module + '.')
        for module in NEW_TEST_MODULES) for name in additions), 'Only exact PB12, scoring28 and B-DAG14 IDs may be added')
    quality = copy.deepcopy(original_quality)
    quality['test_ids'].extend(sorted(additions))
    (prepared / QUALITY).write_bytes(json_bytes(quality))
    updated_lock = copy.deepcopy(original_lock)
    require(QUALITY in updated_lock['files'], 'Existing frozen-B release metadata must contain quality identity')
    updated_lock['files'][QUALITY] = content_identity(prepared / QUALITY)
    (prepared / B_SOURCE_LOCK).write_bytes(json_bytes(updated_lock))
    execute([sys.executable, '-B', str(prepared / 'tools/catalog.py'), 'refresh', '--root', str(prepared)],
        directory=prepared, environment=subprocess_environment, output=output, label='refresh-catalog')
    refreshed = strict_json((prepared / CATALOG).read_bytes())
    expected_catalog = copy.deepcopy(original_catalog)
    catalog_paths = set(IMPORTED_PINS) | {B_SOURCE_LOCK}
    touched = set()
    for family in expected_catalog['families']:
        for member in family['files']:
            name = family['directory'] + '/' + member['path']
            if name in catalog_paths:
                member.update(content_identity(prepared / name))
                member['executable'] = bool((prepared / name).stat().st_mode & 0o111)
                touched.add(name)
    require(touched == catalog_paths and refreshed == expected_catalog and
        refreshed['canonical_families'] == 36 and refreshed['canonical_kinds'] == 69,
        'Catalog may change only the exact three imported members and existing frozen-B metadata')
    git('read-tree', PARENT)
    code_paths = SELECTED_PATHS + (QUALITY, B_SOURCE_LOCK, CATALOG)

    def stage(name):
        path = prepared / name
        blob = git('hash-object', '-w', str(path)).decode().strip()
        git('update-index', '--add', '--cacheinfo', ('100755' if path.stat().st_mode & 0o111 else '100644') + ',' + blob + ',' + name)
        return blob

    for name in code_paths:
        stage(name)
    code_tree = git('write-tree').decode().strip()
    code_commit = git('commit-tree', code_tree, '-p', PARENT, '-m',
        'Add bounded B publication ownership repairs and associated A guard-fixture source').decode().strip()
    evolution = copy.deepcopy(original_evolution)
    expected_evolution_paths = set(IMPORTED_PINS)
    changed_evolution = []
    for name, (size, sha) in IMPORTED_PINS.items():
        matches = [(source, member) for source in source_index['plugins'] + source_index['research_adapters']
            for member in source['files'] if source['directory'] + '/' + member['path'] == name]
        require(len(matches) == 1, 'Each changed imported path must have its unique first-import identity')
        origin, member = matches[0]
        first_import = dict(repository=origin['repository'], revision=origin['revision'],
            **{key: member[key] for key in ['sha256', 'bytes', 'git_blob']})
        blob = git('rev-parse', code_commit + ':' + name).decode().strip()
        change = dict(path=name, original=first_import, current=dict(repository=REMOTE,
            revision=code_commit, path=name, sha256=sha, bytes=size, git_blob=blob))
        locations = [index for index, entry in enumerate(evolution['changes']) if entry['path'] == name]
        require(len(locations) <= 1, 'Duplicate prior source-evolution record')
        if locations:
            require(evolution['changes'][locations[0]]['original'] == first_import,
                'Existing first-import origin must never be replaced with an intermediate revision')
            evolution['changes'][locations[0]] = change
        else:
            evolution['changes'].append(change)
        require(git('show', code_commit + ':' + name) == (prepared / name).read_bytes(), 'Code revision must contain exact evolved bytes')
        changed_evolution.append(change)
    unchanged_before = [entry for entry in original_evolution['changes'] if entry['path'] not in expected_evolution_paths]
    unchanged_after = [entry for entry in evolution['changes'] if entry['path'] not in expected_evolution_paths]
    require(unchanged_after == unchanged_before, 'Unrelated source-evolution entries changed')
    (prepared / EVOLUTION).write_bytes(json_bytes(evolution))
    stage(EVOLUTION)
    tree = git('write-tree').decode().strip()
    candidate = git('commit-tree', tree, '-p', code_commit, '-m',
        'Preserve first-import origins and bind three B repair files to exact Git source').decode().strip()
    require(git('diff-tree', '--no-commit-id', '--name-only', '-r', code_commit, candidate).decode().splitlines() == [EVOLUTION],
        'Source-evolution child may change only its explicit ledger')
    selected_paths = SELECTED_PATHS + METADATA_PATHS
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', PARENT, candidate).decode().splitlines()
    require(changed and set(changed) <= set(selected_paths) and set(METADATA_PATHS) <= set(changed), 'Unrelated or incomplete source release delta')
    for name in selected_paths:
        require(git('show', candidate + ':' + name) == (prepared / name).read_bytes(), 'Candidate committed bytes differ from prepared export')
    for label, revision in [('code', code_commit), ('candidate', candidate)]:
        payload = git('cat-file', 'commit', revision)
        require(hashlib.sha1(b'commit ' + str(len(payload)).encode() + b'\0' + payload).hexdigest() == revision,
            'Raw Git commit object identity differs')
        with (output / (label + '.commit')).open('xb') as handle:
            handle.write(payload)
    candidate_tar = scratch / 'candidate-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '-o', str(candidate_tar), candidate], env=environment, check=True)
    committed = scratch / 'committed-source'
    committed.mkdir()
    with tarfile.open(candidate_tar) as handle:
        handle.extractall(committed, filter='data')
    for name in selected_paths:
        require((committed / name).read_bytes() == (prepared / name).read_bytes(), 'Fresh final Git export differs')
    subprocess.run(['git', '-C', str(committed), 'init', '--quiet'], env=subprocess_environment, check=True)
    objects = git('rev-parse', '--path-format=absolute', '--git-path', 'objects').decode().strip()
    (committed / '.git/objects/info/alternates').write_text(objects + '\n')
    subprocess.run(['git', '-C', str(committed), 'update-ref', '--no-deref', 'HEAD', candidate], env=subprocess_environment, check=True)
    source_before = inventory(committed)
    write(output / 'committed-source-files.json', source_before)
    execute([sys.executable, '-B', str(committed / 'tools/run_checks.py'), '--output', str(output / 'SOURCE_CHECKS.json')],
        directory=committed, environment=subprocess_environment, output=output, label='source-checks')
    checks = strict_json((output / 'SOURCE_CHECKS.json').read_bytes())
    require(type(checks.get('tests_run')) is int and checks['tests_run'] == EXPECTED_TESTS and
        checks.get('complete') is True and checks.get('source_lock_matches') is True and
        all(type(checks.get(name)) is int and checks[name] == 0 for name in ['failures', 'errors', 'skipped']) and
        checks.get('required_test_ids') == quality['test_ids'] and len(checks['executed_test_ids']) == EXPECTED_TESTS and
        set(checks['executed_test_ids']) == set(quality['test_ids']), 'All 639 exact committed tests must actually run without skips')
    nested = strict_json(execute([sys.executable, '-B', '-c', NESTED,
        str(committed / 'plugins/single-cell/tests/test_score_genes_contract.py')],
        directory=committed, environment=subprocess_environment, output=output, label='nested-score-contract'))
    require(nested.get('tests_run') == 5 and len(nested['executed_test_ids']) == 5 and
        {name.rsplit('.', 1)[-1] for name in nested['executed_test_ids']} == NESTED_NAMES and
        all(type(nested.get(name)) is int and nested[name] == 0 for name in ['failures', 'errors', 'skipped']),
        'All five separate nested contract tests must actually run; they are not extra top-level required IDs')
    imports = strict_json(execute([sys.executable, '-B', str(committed / 'tools/catalog.py'), 'verify-import', '--root', str(committed)],
        directory=committed, environment=subprocess_environment, output=output, label='verify-import'))
    require(type(imports.get('imported_files_verified')) is int and imports['imported_files_verified'] > 0 and
        imports.get('current_source_inventory_matches_release_lock') is True, 'Actual imported-source Git-object proof required')
    require(inventory(committed) == source_before, 'Final committed export changed during verification')
    require(selected_before == {name: identity(ROOT / name) for name in SELECTED_PATHS}, 'Selected canonical source changed during preparation')
    require(repository_state() == before, 'Canonical working HEAD or index changed')
    for name in selected_paths:
        destination = output / 'selected-source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(committed / name, destination)
    verification = dict(schema='B_PUBLICATION_EXACT_SOURCE_RELEASE_V1',
        status='SOURCE_ONLY_CHECKED_DIRECT_RUNTIME_PROVEN_DAG_AND_DEPLOYMENT_CLAIMS_SEPARATE',
        parent=PARENT, code_commit=code_commit, candidate=candidate, git_tree=tree,
        changed_paths=changed, allowed_paths=list(selected_paths), actual_top_level_tests=EXPECTED_TESTS,
        original_tests_preserved=BASE_TESTS, new_test_ids=sorted(additions), actual_nested_tests=5,
        evolved_imported_files=changed_evolution, original_import_index_unchanged=True,
        selected_source_identities=selected_before, associated_A_source_only_paths=list(ASSOCIATED_A_SOURCE_PATHS),
        A_guard_build_or_method_claim_created=False, source_lock_matches=True, canonical_families=36,
        canonical_kinds=69, imported_source_verification=imports, source_release_runs_DAG=False,
        production_configuration_changed=False, production_restarted=False, scientific_authorization_granted=False,
        g0_granted=False, published=False, remote_not_queried_without_publish=True,
        repository_before=before, repository_after=repository_state())
    write(output / 'PREPARED.json', verification)
    if arguments.publish:
        remote_before = execute(['git', '-C', str(ROOT), 'ls-remote', '--exit-code', REMOTE, 'refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='remote-before').decode().split()
        require(remote_before == [PARENT, 'refs/heads/main'], 'Remote main changed; no force, reset or rebase permitted')
        execute(['git', '-C', str(ROOT), 'push', REMOTE, candidate + ':refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='push')
        remote_after = execute(['git', '-C', str(ROOT), 'ls-remote', '--exit-code', REMOTE, 'refs/heads/main'],
            directory=ROOT, environment=subprocess_environment, output=output, label='remote-after').decode().split()
        require(remote_after == [candidate, 'refs/heads/main'], 'Published remote identity differs from proved final child')
        require(repository_state() == before, 'Publication changed working HEAD or index')
        verification.update(published=True, remote_main=candidate, remote_not_queried_without_publish=False)
    write(output / 'VERIFICATION.json', verification)
    write(output / 'repository-after.json', repository_state())
    print(json.dumps(dict(candidate=candidate, code_commit=code_commit, tests=EXPECTED_TESTS,
        nested_tests=5, published=verification['published'], G0=False)))


if __name__ == '__main__':
    main()
