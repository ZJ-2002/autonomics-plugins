"""Compare double-link and direct-source container visibility using a tiny non-scientific fixture."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_frozen_a_input_qualification import IMAGE, OWNER, OWNER_SHA, backend, prerequisite_archives

PAYLOAD = b'PURE_TECHNICAL_FIXTURE_32_BYTES\n'
SCRIPT = r'''
import errno,json,sys
from pathlib import Path
path=Path('/work/.autonomics/inputs/input-0.bin')
expected=b'PURE_TECHNICAL_FIXTURE_32_BYTES\n'
if sys.argv[1]=='old':
    try: path.read_bytes()
    except FileNotFoundError as error:
        assert error.errno==errno.ENOENT
        print(json.dumps({'control':'OLD_DOUBLE_LINK','errno':error.errno,'status':'EXPECTED_ENOENT'}))
    else: raise AssertionError('Old unmounted final target unexpectedly readable')
else:
    assert path.read_bytes()==expected
    try:
        with path.open('ab') as stream: stream.write(b'FORBIDDEN')
    except OSError as error:
        assert error.errno==errno.EROFS, repr(error)
        print(json.dumps({'control':'FIXED_DIRECT_TARGET','bytes':len(expected),'errno':error.errno,'status':'BYTES_EQUAL_AND_EROFS'}))
    else: raise AssertionError('Source write was not refused')
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def identity(path):
    info = path.stat()
    return dict(device=info.st_dev, inode=info.st_ino, mode=info.st_mode,
                bytes=info.st_size, nlink=info.st_nlink, mtime_ns=info.st_mtime_ns,
                ctime_ns=info.st_ctime_ns, sha256=digest(path))


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'symlink-stage-visibility'
    output.mkdir()
    scratch = Path(os.environ['TMPDIR']) / 'symlink-stage-visibility'
    scratch.mkdir()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    require(available >= 512 * 1024**2 and shutil.disk_usage(scratch).free >= 64 * 1024**2,
            'Small toy requires memory and disk reserve')
    write(output / 'resource-admission.json', dict(memory_available_bytes=available,
          maximum_container_memory_bytes=64 * 1024**2, cpus=.25, sequential_containers=2,
          no_heavy_task_started=True))
    runtime, prerequisites = prerequisite_archives(Path.home() / '.local/state/autonomics/validation-archives')
    prefix = backend(output, runtime)
    canonical, fixture = scratch / 'canonical', scratch / 'fixture'
    canonical.mkdir()
    fixture.mkdir()
    source = canonical / 'source.bin'
    require(len(PAYLOAD) == 32, 'Exactly 32-byte synthetic payload required')
    source.write_bytes(PAYLOAD)
    (fixture / 'input.bin').symlink_to(source)
    before = identity(source)
    observations = []
    session = permanent.parent.name
    for mode in ['old', 'fixed']:
        workspace = scratch / ('workspace-' + mode)
        staged = workspace / '.autonomics/inputs'
        staged.mkdir(parents=True)
        target = fixture / 'input.bin' if mode == 'old' else source
        link = staged / 'input-0.bin'
        link.symlink_to(target)
        mounted_source = fixture if mode == 'old' else canonical
        name = 'autonomics-stage-' + session + '-' + mode
        command = [*prefix, 'run', '--rm', '--name=' + name, '--pull=never', '--network=none',
            '--read-only', '--cpus=.25', '--memory=64m', '--pids-limit=32', '--userns=keep-id',
            '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs=/tmp:rw,size=8m',
            '-v', str(workspace) + ':/work:rw', '-v', str(mounted_source) + ':' + str(mounted_source) + ':ro',
            '--entrypoint=python3', IMAGE, '-I', '-B', '-c', SCRIPT, mode]
        write(output / (mode + '-command.json'), command)
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / (mode + '-stdout.log')).write_text(result.stdout)
        (output / (mode + '-stderr.log')).write_text(result.stderr)
        require(result.returncode == 0, 'Actual small visibility control failed: ' + mode)
        actual = json.loads(result.stdout)
        require(actual == (dict(control='OLD_DOUBLE_LINK', errno=2, status='EXPECTED_ENOENT') if mode == 'old'
                else dict(control='FIXED_DIRECT_TARGET', bytes=32, errno=30, status='BYTES_EQUAL_AND_EROFS')),
                'Actual container visibility result differs from the declared control')
        stopped = subprocess.run([*prefix, 'container', 'exists', name], capture_output=True, text=True, timeout=30)
        require(stopped.returncode == 1, 'Exact toy container not proven absent after attached run')
        observations.append(dict(mode=mode, actual_exit=result.returncode, observation=actual,
                                 exact_named_container_exists_exit=stopped.returncode))
    after = identity(source)
    require(before == after and digest(OWNER) == OWNER_SHA, 'Toy source or shared software owner changed')
    write(output / 'EVIDENCE.json', dict(scope='PURE_TOY_CONTAINER_PATH_VISIBILITY_ONLY_NOT_VFS_DAG_OR_SCIENTIFIC_VALIDATION',
        driver_sha256=digest(Path(__file__)), prerequisites=prerequisites, image=IMAGE,
        source_before=before, source_after=after, source_unchanged=True, observations=observations,
        actual_containers=2, raw_GWAS_read=False, PLINK_executed=False, actual_VFS_or_DAG_executed=False,
        no_raw_input_copies=True, production_restarted=False, scientific_results_computed=False, g0_granted=False))


if __name__ == '__main__':
    main()
