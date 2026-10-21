import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
REVISION = 'ab7c254e02c8e010e13cabe69e16060d8de05c7a'
REMOTE = 'https://github.com/ZJ-2002/autonomics-plugins.git'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    verified = verify_archive(ARCHIVES, 'fa2e9cc31575455e8a7e04e4f38ae93d',
        'bf2579c7b532fca909e515bee935347fecd5e18e3465aa0774ad5e8d76b5a1dc')
    require(verified['positive_worker_exit_verified'], 'Fixed node selection not verified')
    matrix = json.loads((Path(verified['artifact_root']) / 'permanent/fixed120-verified-observations/NODE_PROOF_120.json').read_bytes())
    families = {address.split('/')[0] for row in matrix['rows'] for address in row['selected_addresses']}
    prior = verify_archive(ARCHIVES, 'adb70758f2804596ba20f5b9973dbab3',
        '227ba306ceeeaf88c66e7003679d34a02d72ee2d2b1f1c676a0ba2c46dfad50a')
    require(prior['positive_worker_exit_verified'], 'Earlier source identities not verified')
    identities = json.loads((Path(prior['artifact_root']) / 'permanent/fixed120-current-post-response-repair/SOURCE_IDENTITIES_397.json').read_bytes())
    expected = {}
    for row in identities:
        require(row['path'] not in expected or expected[row['path']] == row['observed'], 'Conflicting prior source identity')
        expected[row['path']] = row['observed']
    configuration = Path.home() / '.autonomics/plugins.toml'
    original = configuration.read_bytes()
    parsed = tomllib.loads(original.decode())
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'selected-mutable-source-audit'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')
    for key in ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES']:
        environment.pop(key, None)

    def git(*arguments):
        result = subprocess.run(['git', '-C', str(ROOT), *arguments], env=environment, capture_output=True, timeout=120)
        require(result.returncode == 0, 'Source inspection failed: ' + arguments[0])
        return result.stdout

    require(git('ls-remote', REMOTE, 'refs/heads/main').decode().split()[0] == REVISION,
            'Published revision changed; do not silently select another')
    rows = []
    for entry in parsed['plugin']:
        if 'path' not in entry or entry['name'] not in families:
            continue
        source = Path(entry['path'])
        if not source.is_relative_to(ROOT) or source.resolve() != source:
            rows.append(dict(family=entry['name'], status='NONCANONICAL_OR_ALIASED_SOURCE_REQUIRES_SEPARATE_REVIEW',
                private_source_path_recorded=False))
            continue
        subdir = source.relative_to(ROOT).as_posix()
        require(subdir.startswith('plugins/') and len(source.relative_to(ROOT).parts) == 2,
                'Do not migrate study-specific or unknown source layouts')
        tree = git('ls-tree', '-r', '-z', REVISION, '--', subdir)
        require(tree and tree.endswith(b'\0'), 'Published family tree absent')
        files = []
        mismatches = []
        observed = []
        for record in tree.split(b'\0')[:-1]:
            metadata, raw_name = record.split(b'\t', 1)
            mode, kind, identity = metadata.decode().split()
            filename = raw_name.decode()
            require(filename.startswith(subdir + '/') and kind == 'blob' and mode in {'100644', '100755'},
                    'Unreviewed published source kind')
            published = git('cat-file', 'blob', identity)
            path = ROOT / filename
            valid = path.is_file() and not path.is_symlink() and path.read_bytes() == published
            fact = dict(path=filename, bytes=len(published), sha256=hashlib.sha256(published).hexdigest())
            files.append(fact)
            if not valid:
                mismatches.append(filename)
            if str(path) in expected:
                require(expected[str(path)] == dict(bytes=fact['bytes'], sha256=fact['sha256']),
                        'Published selected method differs from verified source snapshot')
                observed.append(filename)
        manifest = (source / 'manifest.toml').read_bytes()
        require(str(source / 'manifest.toml') in expected, 'Selected family manifest lacks prior source identity')
        manifest_parsed = tomllib.loads(manifest.decode())
        runtime = Path.home() / '.autonomics/plugins/runtime' / entry['name']
        runtime_matches = runtime.is_symlink() and runtime.resolve() == source
        rows.append(dict(family=entry['name'], subdir=subdir, published_revision=REVISION,
            status='BYTE_IDENTICAL_PIN_CANDIDATE' if not mismatches and runtime_matches else 'SOURCE_OR_RUNTIME_LINK_MISMATCH',
            tracked_files=files, prior_snapshot_files_reused=observed,
            published_worktree_mismatches=mismatches, runtime_link_matches=runtime_matches,
            manifest_sha256=hashlib.sha256(manifest).hexdigest(), image=manifest_parsed['image']['reference']))
    require(configuration.read_bytes() == original, 'Plugin configuration changed during inspection')
    report = dict(schema='SELECTED_MUTABLE_PLUGIN_SOURCE_AUDIT_V1', published_revision=REVISION,
        selected_mutable_families=len(rows), rows=rows,
        pin_candidates=sum(row['status'] == 'BYTE_IDENTICAL_PIN_CANDIDATE' for row in rows),
        source_config_modified=False, production_restarted=False, new_method_executions=0,
        new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(selected_mutable_families=len(rows), pin_candidates=report['pin_candidates'],
        source_config_modified=False, new_method_executions=0)), flush=True)


if __name__ == '__main__':
    main()
