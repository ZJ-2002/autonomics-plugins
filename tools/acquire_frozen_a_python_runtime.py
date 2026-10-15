"""Seal official CPython image identities and append only its immutable image."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import urllib.request


INDEX = '51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d'
MANIFEST = '7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d'
CONFIG = 'ea130d51594b38acddd30f9f2542a38c37736000f1710fb8c1058b6c3e613f8c'
IMAGE = 'docker.io/library/python@sha256:' + MANIFEST
RECIPE_COMMIT = '688a0b86bb44289df16a363e9f41d90514c1a5f9'
RECIPE_SHA = '4abd3e86a4f5f89e615405ce0cb90411a8164f14a4949a11818ce1490585e158'
SOURCE_SHA = '3b48dac8fb59f62eaa67ac83c1eb12bda1b7a08406dd286e252c11a66be27f81'
OWNER = Path.home() / '.autonomics/containers-overlay/SOFTWARE_INSTALLATION_OWNER.json'
OWNER_SHA = '7d88bee121dbbdc974787b64cbcccc1e5304a09e805303d897d3ea28ef7d2bbc'
LAYERS = [
    ('6b37362b3da78869050b894b799ad4df04f1f3b52774087db0d81151570244c8', 29830418),
    ('5c21337b2448c4a8923205ad1e092a6464c809780ac426755a2065a39c03369d', 1294128),
    ('8def98961a31d91a4dc44e69faedbed1efdc1fd5e756d5d4c7c42dd6c8e24f62', 12363879),
    ('ad232412d02ef04c3744a3b575ed85f8ce49361d8c38bb81b2b6a9fbbe014dcf', 249),
]
ACCEPT = 'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode), 'Ordinary unlinked file required')
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def fetch(output, name, url, expected_sha, expected_bytes, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        require(response.status == 200, 'Exact successful official response required')
        payload = response.read(2 * 1024**2 + 1)
        require(len(payload) <= 2 * 1024**2, 'Metadata response exceeds bound')
        observed = {key: response.headers.get(key) for key in ['Content-Type', 'Content-Length', 'Docker-Content-Digest']}
    require(len(payload) == expected_bytes and hashlib.sha256(payload).hexdigest() == expected_sha,
        'Pinned official metadata bytes differ: ' + name)
    with (output / name).open('xb') as handle:
        handle.write(payload)
    write(output / (name + '.receipt.json'), dict(url=url, status=200, bytes=len(payload), sha256=expected_sha,
        headers=observed, authorization_recorded=False, retries=0))
    return payload


def command(output, label, argv, timeout):
    write(output / (label + '.command.json'), argv)
    process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    (output / (label + '.stdout.log')).write_text(process.stdout)
    (output / (label + '.stderr.log')).write_text(process.stderr)
    write(output / (label + '.exit.json'), dict(actual_exit=process.returncode))
    require(type(process.returncode) is int and process.returncode == 0, 'Actual runtime operation failed: ' + label)
    return process.stdout


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-python-runtime'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    require(digest(OWNER) == OWNER_SHA, 'Original software owner differs')
    owner_identity = OWNER.stat().st_dev, OWNER.stat().st_ino, OWNER.stat().st_uid, OWNER.stat().st_gid
    owner = json.loads(OWNER.read_text())
    for name in ['storage', 'runroot']:
        expected = owner[name]
        observed = Path(expected['path']).stat()
        require((observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid) ==
            (expected['device'], expected['inode'], expected['uid'], expected['gid']), 'Existing backend ownership differs')
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    require(not shim.is_symlink() and "'--tmpdir'" in shim.read_text(), 'Existing managed Podman shim required')
    prefix = [str(shim), *owner['runtime_backend']]
    memory = {line.split(':', 1)[0]: int(line.split(':', 1)[1].split()[0]) * 1024
              for line in Path('/proc/meminfo').read_text().splitlines()}
    require(memory['MemAvailable'] >= 4 * 1024**3 and shutil.disk_usage(output).free >= 2 * 1024**3,
        'Memory or free-space reserve inadequate')
    capacity = command(output, 'btrfs-capacity', ['/usr/bin/btrfs', 'filesystem', 'usage', '-b', '/home'], 30)
    values = {}
    for line in capacity.splitlines():
        if line.strip().startswith('Device unallocated:'):
            values['unallocated_bytes'] = int(line.split(':')[1])
        if line.startswith('Metadata,DUP:'):
            fields = re.fullmatch(r'Metadata,DUP: Size:\s*(\d+), Used:\s*(\d+) \([\d.]+%\)', line)
            require(fields is not None, 'Exact Btrfs metadata accounting required')
            values['metadata_allocated_bytes'] = int(fields[1])
            values['metadata_used_bytes'] = int(fields[2])
    require(values.get('unallocated_bytes', 0) >= 2 * 1024**3 and
        values.get('metadata_used_bytes', 1) / values.get('metadata_allocated_bytes', 1) < .90,
        'Btrfs metadata or unallocated reserve inadequate')
    command(output, 'other-containers-observed-not-modified', [*prefix, 'ps', '--format', '{{.ID}}\t{{.Image}}\t{{.Status}}'], 30)
    write(output / 'resource-admission.json', dict(mem_available_bytes=memory['MemAvailable'], btrfs=values,
        container_memory_bytes=128 * 1024**2, container_cpus=1, maximum_our_concurrent_containers=1,
        global_container_exclusivity_claimed=False, compressed_layers_bytes=43488674, no_build=True))

    token_url = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull'
    with urllib.request.urlopen(token_url, timeout=60) as response:
        require(response.status == 200, 'Anonymous registry token response failed')
        token_payload = response.read(65537)
    require(len(token_payload) <= 65536, 'Anonymous token response exceeds bound')
    token = json.loads(token_payload)['token']
    headers = {'Accept': ACCEPT, 'Authorization': 'Bearer ' + token}
    registry = 'https://registry-1.docker.io/v2/library/python/'
    index = json.loads(fetch(output, 'index.json', registry + 'manifests/sha256:' + INDEX, INDEX, 10365, headers))
    matches = [item for item in index['manifests'] if item.get('platform', {}).get('os') == 'linux' and
               item.get('platform', {}).get('architecture') == 'amd64']
    require(len(matches) == 1 and matches[0]['digest'] == 'sha256:' + MANIFEST and matches[0]['size'] == 1745,
        'Exact linux amd64 index descriptor required')
    manifest = json.loads(fetch(output, 'amd64-manifest.json', registry + 'manifests/sha256:' + MANIFEST,
        MANIFEST, 1745, headers))
    require(manifest['config']['digest'] == 'sha256:' + CONFIG and manifest['config']['size'] == 4942 and
        [(item['digest'], item['size']) for item in manifest['layers']] == [('sha256:' + sha, size) for sha, size in LAYERS],
        'Exact config and all four compressed layer descriptors required')
    config = json.loads(fetch(output, 'config.json', registry + 'blobs/sha256:' + CONFIG, CONFIG, 4942, headers))
    environment = config['config']['Env']
    require(config['architecture'] == 'amd64' and config['os'] == 'linux' and
        'PYTHON_VERSION=3.14.7' in environment and 'PYTHON_SHA256=' + SOURCE_SHA in environment and
        config['rootfs']['type'] == 'layers' and len(config['rootfs']['diff_ids']) == 4,
        'Exact CPython source/version and four installed layers required')
    recipe_url = 'https://raw.githubusercontent.com/docker-library/python/' + RECIPE_COMMIT + '/3.14/slim-trixie/Dockerfile'
    recipe = fetch(output, 'Dockerfile', recipe_url, RECIPE_SHA, 4366).decode()
    require(re.search(r'^ENV PYTHON_VERSION(?: |=)3\.14\.7$', recipe, re.MULTILINE) and
        re.search(r'^ENV PYTHON_SHA256(?: |=)' + SOURCE_SHA + '$', recipe, re.MULTILINE),
        'Pinned official Dockerfile source/version differs')
    command(output, 'pull-immutable-python', [*prefix, 'pull', IMAGE], 600)
    inspection = json.loads(command(output, 'installed-image-inspect', [*prefix, 'image', 'inspect', IMAGE], 60))
    require(len(inspection) == 1, 'One exact installed image required')
    installed = inspection[0]
    require(installed['Digest'] == 'sha256:' + MANIFEST and installed['Id'].removeprefix('sha256:') == CONFIG and
        installed['RootFS']['Layers'] == config['rootfs']['diff_ids'], 'Actual installed manifest/config/layers differ')
    program = ('import sys,platform,json,gzip,csv,io,hashlib; '
        'assert sys.version_info[:3]==(3,14,7); '
        'assert platform.python_implementation()=="CPython"; '
        'assert gzip.decompress(gzip.compress(b"stdlib-toy"))==b"stdlib-toy"; '
        'assert list(csv.reader(io.StringIO("a,b\\n1,2\\n")))==[["a","b"],["1","2"]]; '
        'print(json.dumps(dict(version=platform.python_version(),implementation=platform.python_implementation(),'
        'machine=platform.machine(),executable=sys.executable,stdlib_smoke=True,scientific_inputs_read=False)))')
    smoke = json.loads(command(output, 'python-stdlib-smoke', [*prefix, 'run', '--rm', '--pull=never', '--network=none',
        '--read-only', '--cpus=1', '--memory=128m', '--pids-limit=32', '--userns=keep-id',
        '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs=/tmp:rw,size=16m',
        '--entrypoint=/usr/local/bin/python3', IMAGE, '-I', '-B', '-c', program], 30))
    require(smoke['version'] == '3.14.7' and smoke['machine'] == 'x86_64' and smoke['stdlib_smoke'] is True,
        'Actual installed CPython smoke differs')
    require(digest(OWNER) == OWNER_SHA and
        (OWNER.stat().st_dev, OWNER.stat().st_ino, OWNER.stat().st_uid, OWNER.stat().st_gid) == owner_identity,
        'Original software owner changed')
    write(output / 'verification.json', dict(status='OFFICIAL_CPYTHON_3_14_7_IMAGE_INSTALLED_NONFIT_SMOKE_ONLY',
        image=IMAGE, index_sha256=INDEX, manifest_sha256=MANIFEST, config_sha256=CONFIG,
        source_tar_sha256_from_official_recipe=SOURCE_SHA, official_recipe_commit=RECIPE_COMMIT,
        official_recipe_sha256=RECIPE_SHA, compressed_layer_descriptors=LAYERS, compressed_bytes=43488674,
        installed_diff_ids=config['rootfs']['diff_ids'], actual_smoke=smoke, managed_shim_sha256=digest(shim),
        original_software_owner_sha256=OWNER_SHA, original_software_owner_unchanged=True,
        prior_shared_images_removed=False, dependency_environment_copied=False, image_built=False,
        scientific_inputs_read=False, scientific_fit_executed=False, production_restarted=False,
        production_deployed=False, current_QC_DAG_proven=False, g0_granted=False))


if __name__ == '__main__':
    main()
