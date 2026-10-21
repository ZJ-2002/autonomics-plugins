import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
RESTORED = ['README.md', 'dds_diagnostics.R', 'deseq2_runner.R', 'manifest.toml',
    'tests/method_evidence_convergence.R', 'tests/method_evidence_fixture.R',
    'tests/method_evidence_reference.R', 'tests/test_deseq2_boundaries.py', 'tests/test_method_evidence.py']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    source_archive = verify_archive(ARCHIVES, 'adb70758f2804596ba20f5b9973dbab3',
        '227ba306ceeeaf88c66e7003679d34a02d72ee2d2b1f1c676a0ba2c46dfad50a')
    require(source_archive['positive_worker_exit_verified'], 'Existing method source binding not successful')
    records = json.loads((Path(source_archive['artifact_root']) /
        'permanent/fixed120-current-post-response-repair/SOURCE_IDENTITIES_397.json').read_bytes())
    expected = {row['path']: row['observed'] for row in records}
    configuration = Path.home() / '.autonomics/plugins.toml'
    original = configuration.read_bytes()
    entries = {row['name']: row for row in tomllib.loads(original.decode())['plugin']}
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'deseq2-canonical-source-restoration'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    observations = []
    for family in ['bulk-rnaseq', 'deseq2']:
        source = Path(entries[family]['path'])
        identity = json.loads((source.parent / 'SOURCE_IDENTITY.json').read_bytes())
        require(source.parent.parent.parent == Path.home() / '.autonomics/plugins/snapshots'
                and source.name == 'tree' and source.parent.name.startswith('external-'), 'Expected sealed snapshot layout required')
        actual_names = {path.relative_to(source).as_posix() for path in source.rglob('*') if path.is_file()}
        require(actual_names == set(identity['files']), 'Snapshot inventory changed')
        for name, digest in identity['files'].items():
            path = source / name
            require(not path.is_symlink() and sha(path) == digest, 'Snapshot member identity changed')
        bound = []
        for path in source.rglob('*'):
            recorded_path = str(path)
            if family == 'bulk-rnaseq':
                require(identity['source'] == str(ROOT / 'plugins/bulk-rnaseq'), 'Unexpected bulk snapshot origin')
                recorded_path = str(Path(identity['source']) / path.relative_to(source))
            if recorded_path in expected:
                require(dict(bytes=path.stat().st_size, sha256=sha(path)) == expected[recorded_path], 'Qualified runtime identity changed')
                bound.append(path.relative_to(source).as_posix())
        require('manifest.toml' in bound, 'Existing snapshot lacks qualified manifest identity')
        canonical = ROOT / 'plugins' / family
        mismatches = [name for name, digest in identity['files'].items()
            if not (canonical / name).is_file() or sha(canonical / name) != digest]
        if family == 'deseq2':
            require(set(bound) >= {'manifest.toml', 'deseq2_runner.R', 'dds_diagnostics.R'}, 'All deployed DESeq2 runtime files must be qualified')
            require(not mismatches, 'Canonical source restoration is not exact')
            for name in RESTORED:
                (output / ('restored-' + name.replace('/', '__'))).write_bytes((canonical / name).read_bytes())
                published = subprocess.run(['git', '-C', str(ROOT), 'show',
                    '5e432fa7392d7ab18da9b1eb9121fc2b952c2e4a:plugins/deseq2/' + name], capture_output=True, timeout=30)
                require(published.returncode == 0 and published.stdout == (canonical / name).read_bytes(),
                        'Restoration must match the already published source, not invent another implementation')
            for name in ['tests/test_deseq2_boundaries.py', 'tests/test_method_evidence.py']:
                ast.parse((canonical / name).read_text(), filename=name)
        observations.append(dict(family=family, source_kind='IDENTITY_RECORDED_SEALED_EXTERNAL_SNAPSHOT_NOT_ORDINARY_MUTABLE_WORKTREE',
            original_source_commit=identity['commit'], snapshot_files_verified=len(identity['files']),
            qualified_runtime_files_reused=sorted(bound), canonical_snapshot_mismatches=mismatches,
            restored_file_sha256={name: identity['files'][name] for name in RESTORED} if family == 'deseq2' else {}))
    runner = (ROOT / 'plugins/deseq2/deseq2_runner.R').read_text()
    require('publication_file_identity <- function' in runner and 'publication_remove_owned_file <- function' in runner,
            'Existing publication ownership guards were lost')
    test = ROOT / 'tests/test_deseq2_source_restoration.py'
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'),
        '-p', test.name, '-v'], env=environment, capture_output=True, timeout=60)
    (output / 'tests.stdout').write_bytes(result.stdout)
    (output / 'tests.stderr').write_bytes(result.stderr)
    require(result.returncode == 0 and b'Ran 3 tests' in result.stderr and b'\nOK\n' in result.stderr,
            'Three restoration regressions must actually pass')
    require(configuration.read_bytes() == original, 'Production source configuration changed')
    report = dict(schema='DESEQ2_CANONICAL_SOURCE_RESTORATION_V1', pass_scoped_source_restoration=True,
        observations=observations, restored_files=len(RESTORED), actual_regression_tests_passed=3,
        regression_test_sha256=sha(test), restored_python_tests_parsed_without_execution=2,
        existing_publication_guards_preserved=True, production_configuration_changed=False,
        restored_files_already_present_in_published_revision='5e432fa7392d7ab18da9b1eb9121fc2b952c2e4a',
        prior_source_binding_failure_session='7596ce6680274ca7abcaa5a23e64d527',
        production_restart_performed=False, new_statistical_fits=0, new_software_admissions=0,
        scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(restored_files=len(RESTORED), regression_tests_passed=3,
        new_statistical_fits=0, production_configuration_changed=False)), flush=True)


if __name__ == '__main__':
    main()
