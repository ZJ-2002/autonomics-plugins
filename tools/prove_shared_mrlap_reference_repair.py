import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
BASE = '9f9990071c266d0c8c7f36033441d383bdf8ed09'
OLD = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
NEW = 'ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'
SUBDIRS = ['research-adapters/frozen-a-family-adjustment', 'research-adapters/frozen-a-harmonisation',
    'research-adapters/cachexia-mrlap', 'plugins/r-stats', 'plugins/donor-composition-official',
    'plugins/r-stats-lm', 'plugins/twosamplemr-v432-a']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    proof = verify_archive(ARCHIVES, '9615f0f810d94b61a1c3bb70e5f66af5',
        'd32ca36bed875dc108975d89fddbcb28dc4666c0ce0e8c5fc0115f35240a4bf1')
    require(proof['positive_worker_exit_verified'], 'Prior exact image alias identity proof required')
    prior = json.loads((Path(proof['artifact_root']) / 'permanent/mrlap-registry-reference-repair/verification.json').read_bytes())
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'shared-mrlap-reference-repair'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1')
    for key in ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES']:
        environment.pop(key, None)

    def git(*arguments):
        result = subprocess.run(['git', '-C', str(ROOT), *arguments], env=environment, capture_output=True, timeout=90)
        require(result.returncode == 0, 'Source identity read failed: ' + arguments[0])
        return result.stdout

    configuration = (Path.home() / '.autonomics/plugins.toml').read_bytes()
    deployed = {row['name']: row for row in tomllib.loads(configuration.decode())['plugin']}
    families = []
    for subdir in SUBDIRS:
        relative = subdir + '/manifest.toml'
        old = git('show', BASE + ':' + relative)
        current = (ROOT / relative).read_bytes()
        require(old.count(OLD.encode()) == 1 and current == old.replace(OLD.encode(), NEW.encode()),
                'Only the single qualified image reference may change')
        previous_contract = tomllib.loads(old.decode())
        document = tomllib.loads(current.decode())
        require(previous_contract['image'].pop('reference') == OLD and document['image'].pop('reference') == NEW
                and previous_contract == document, 'Non-image method contract changed')
        source_hashes = {}
        for record in git('ls-tree', '-r', '-z', BASE, '--', subdir).split(b'\0'):
            if not record:
                continue
            metadata, raw_path = record.split(b'\t', 1)
            mode, kind, identity = metadata.decode().split()
            filename = raw_path.decode()
            require(kind == 'blob' and mode in {'100644', '100755'}, 'Unreviewed source kind')
            payload = (ROOT / filename).read_bytes()
            if filename != relative:
                require(payload == git('cat-file', 'blob', identity), 'Method script or other tracked file changed')
            source_hashes[filename] = hashlib.sha256(payload).hexdigest()
        family = tomllib.loads(current.decode())['plugin_name']
        active_entry = deployed.get(family)
        active_unchanged_before_repin = None
        if active_entry and active_entry.get('subdir') == subdir:
            require(active_entry.get('git') == 'https://github.com/ZJ-2002/autonomics-plugins.git', 'Unexpected deployed source repository')
            require(not git('diff', '--name-only', active_entry['rev'], BASE, '--', subdir).strip(),
                    'Do not silently upgrade an unrelated deployed method delta')
            active_unchanged_before_repin = True
        families.append(dict(family=family, subdir=subdir, manifest_sha256=hashlib.sha256(current).hexdigest(),
            stable_contract_excluding_image_sha256=hashlib.sha256(json.dumps(document, sort_keys=True,
                ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(), source_sha256=source_hashes,
            deployed_source_matches_base_before_image_delta=active_unchanged_before_repin))
    test = ROOT / 'tests/test_mrlap_shared_image_references.py'
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'),
        '-p', test.name, '-v'], capture_output=True, timeout=60)
    (output / 'tests.stdout').write_bytes(result.stdout)
    (output / 'tests.stderr').write_bytes(result.stderr)
    require(result.returncode == 0 and b'Ran 2 tests' in result.stderr and b'\nOK\n' in result.stderr,
            'Both shared dependency regression checks must execute')
    require((Path.home() / '.autonomics/plugins.toml').read_bytes() == configuration, 'Production configuration changed')
    report = dict(schema='SHARED_MRLAP_IMAGE_REFERENCE_REPAIR_V1', passed=True, source_base=BASE,
        families=families, changed_manifests=7, actual_regression_tests_passed=2,
        regression_test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
        old_reference=OLD, new_reference=NEW, reused_image_identity_proof_schema=prior['schema'],
        method_scripts_parameters_ports_resources_unchanged=True, production_configuration_changed=False,
        new_image_downloads=0, new_statistical_fits=0, new_software_admissions=0,
        scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(changed_manifests=7, actual_regression_tests_passed=2,
        new_statistical_fits=0, production_configuration_changed=False)), flush=True)


if __name__ == '__main__':
    main()
