import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
IMAGES = [
    ('survey', '4.5', '8186f7fc9fa4a75023821b8f0f22634b82c2112916c426a20ee40075c4753243',
     'a83c1fd019b14e4bedc2f113d372f4ae97fd38fe08cab1a2a82c84281426e59b'),
    ('mice', '3.19.0', '0a7b397b9fb5fca8128381525ab9482098445a2f29e309135464a8cd45fc0f57',
     '556d36b4a6b72828c268df82f1a23c61280a2ae365b64f50958dd13b684d8234'),
    ('lcmm', '2.2.2', '602bbf79fa81124edc1d78f366a71e2f8e55f1c768377810104eb81bb03ac97a',
     'ef26c21806ef2bddd36601c47a24a8f0ed2423ffe56174779ae7ad3aa450a822'),
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    for session, seal in [
        ('40a1d61213a54a9cb4cd708c9833b05f', '0283543dbc6ee6ff31bc47e116476bea943a14fb4c6b726eccd79c1c338bdba3'),
        ('a6138597ca8c4919b86d730585f5e0a5', 'a327284b27759736492c7eb6ba1600bcb0acffcbe15ef92cf7f1bd0f58571870'),
        ('f9a173977ea3458e9141fa597c00a15e', '45a11d2917d8413d86114f1b724612b63045d4ec91b2f31396a8e2654cb808a7'),
    ]:
        require(verify_archive(ARCHIVES, session, seal)['positive_worker_exit_verified'], 'Required image evidence not successful')
    review_path = ARCHIVES / 'f9a173977ea3458e9141fa597c00a15e/artifacts/permanent/conditional-build-log-review/verification.json'
    raw = review_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == '9b442a32845bb5d3b1d2bd6d8c75eb7bed81f5e75661d15f5cb87b2f28585c21'
            and json.loads(raw)['content_rules_passed'], 'Known build-context content review required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'conditional-official-image-publication'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    environment = {name: os.environ[name] for name in ('HOME', 'PATH', 'XDG_RUNTIME_DIR',
        'DBUS_SESSION_BUS_ADDRESS', 'LANG', 'LC_ALL', 'TMPDIR') if name in os.environ}
    profile_raw = (Path.home() / '.autonomics/qualified-image-store.json').read_bytes()
    profile = json.loads(profile_raw)
    primary = profile['primary']
    backend = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--storage-opt',
        'additionalimagestore=' + profile['additional']['path'], '--root', primary['graphroot'],
        '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
        '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']

    def command(label, arguments, timeout=120, stdin=None):
        result = subprocess.run(arguments, input=stdin, env=environment, capture_output=True, timeout=timeout)
        require(len(result.stdout) <= 16 * 1024**2 and len(result.stderr) <= 16 * 1024**2, 'Command output exceeds bound')
        write(output / (label + '-execution.json'), dict(label=label, actual_exit=result.returncode,
            raw_output_archived=False, credential_arguments_used=False))
        return result

    account = command('owner', ['gh', 'api', 'user', '--jq', '.login'])
    require(account.returncode == 0 and account.stdout.strip().lower() == b'zj-2002', 'Existing owner authentication unavailable')
    secret = command('existing-private-token', ['gh', 'auth', 'token'])
    require(secret.returncode == 0 and 0 < len(secret.stdout.strip()) < 16384, 'Existing private token unavailable')
    authfile = Path(os.environ['TMPDIR']) / 'conditional-registry-auth.json'
    descriptor = os.open(authfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write('{"auths":{}}\n')
    held = authfile.stat()
    try:
        login = command('registry-login', [*backend, 'login', '--authfile', str(authfile), '--username', 'ZJ-2002',
            '--password-stdin', 'ghcr.io'], stdin=secret.stdout.strip())
        del secret
        held = authfile.lstat()
        require(stat.S_ISREG(held.st_mode) and stat.S_IMODE(held.st_mode) == 0o600
                and held.st_uid == os.getuid() and held.st_nlink == 1, 'Private authfile properties changed')
        require(login.returncode == 0, 'Registry login failed; diagnostics withheld')
        records = []
        for family, version, local_digest, config_id in IMAGES:
            local = f'localhost/cachexia-{family}@sha256:{local_digest}'
            require(local in profile['images'], 'Only existing qualified images may be published')
            inspected = command(f'{family}-local', [*backend, 'image', 'inspect', local])
            require(inspected.returncode == 0, 'Qualified image unavailable')
            inspected = json.loads(inspected.stdout)
            require(len(inspected) == 1 and inspected[0]['Id'].removeprefix('sha256:') == config_id,
                    'Qualified image config changed')
            repository = f'ghcr.io/zj-2002/{family}-official'
            tag = repository + ':' + version + '-r4.6.1-20261021-v1'
            auth = ['--authfile=' + str(authfile)]
            existing = command(f'{family}-existing-tag', ['skopeo', 'inspect', *auth, '--retry-times=0', '--raw', 'docker://' + tag])
            if existing.returncode == 0:
                require(json.loads(existing.stdout)['config']['digest'] == 'sha256:' + config_id,
                        'Existing tag differs; do not overwrite')
                digest = 'sha256:' + hashlib.sha256(existing.stdout).hexdigest()
                pushed = False
            else:
                digestfile = output / (family + '-actual-digest.txt')
                result = command(f'{family}-push', [*backend, 'push', *auth, '--format=oci', '--retry=0',
                    '--digestfile=' + str(digestfile), local, 'docker://' + tag], timeout=1800)
                require(result.returncode == 0 and digestfile.is_file(), 'Registry push failed; no publication inferred')
                digest = digestfile.read_text().strip()
                pushed = True
            require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None, 'Invalid push digest')
            immutable = repository + '@' + digest
            remote = command(f'{family}-manifest', ['skopeo', 'inspect', *auth, '--retry-times=0', '--raw', 'docker://' + immutable])
            require(remote.returncode == 0 and 'sha256:' + hashlib.sha256(remote.stdout).hexdigest() == digest,
                    'Remote manifest identity differs')
            manifest = json.loads(remote.stdout)
            require(manifest['config']['digest'] == 'sha256:' + config_id, 'Remote config identity differs')
            remote_config = command(f'{family}-config', ['skopeo', 'inspect', *auth, '--retry-times=0', '--raw', '--config', 'docker://' + immutable])
            require(remote_config.returncode == 0 and hashlib.sha256(remote_config.stdout).hexdigest() == config_id,
                    'Remote config bytes differ')
            require(json.loads(remote_config.stdout)['rootfs']['diff_ids'] == inspected[0]['RootFS']['Layers'],
                    'Remote uncompressed layer axis differs')
            anonymous = command(f'{family}-anonymous', ['skopeo', 'inspect', '--no-creds', '--retry-times=0', '--raw', 'docker://' + immutable])
            record = dict(family=family, official_version=version, local_reference=local, requested_tag=tag,
                immutable_reference=immutable, config_sha256=config_id, remote_identity_verified=True,
                exact_uncompressed_layers_verified=True, new_push_performed=pushed,
                anonymous_manifest_read_verified=anonymous.returncode == 0 and anonymous.stdout == remote.stdout,
                fresh_full_image_pull_performed=False, production_binding_changed=False)
            records.append(record)
            write(output / 'publication-progress.json', records)
        require((Path.home() / '.autonomics/qualified-image-store.json').read_bytes() == profile_raw,
                'Qualified profile changed during publication')
        write(output / 'verification.json', dict(schema='CONDITIONAL_OFFICIAL_REGISTRY_PUBLICATION_V1', images=records,
            uploaded_images_verified=len(records), all_anonymous_read_verified=all(item['anonymous_manifest_read_verified'] for item in records),
            private_logs_published_as_source_evidence=False, credentials_recorded_or_in_arguments=False,
            account_permissions_changed=False, new_method_executions=0, new_software_admissions=0,
            scientific_release_granted=False, g0_granted=False))
        print(json.dumps(dict(images_verified=len(records), anonymous_read_verified=
            sum(item['anonymous_manifest_read_verified'] for item in records), new_method_executions=0)), flush=True)
    finally:
        current = authfile.lstat()
        require((current.st_dev, current.st_ino) == (held.st_dev, held.st_ino), 'Private authfile replaced; do not unlink replacement')
        authfile.unlink()
        write(output / 'credential-cleanup.json', dict(temporary_authfile_removed=not authfile.exists(), credential_values_recorded=False))


if __name__ == '__main__':
    main()
