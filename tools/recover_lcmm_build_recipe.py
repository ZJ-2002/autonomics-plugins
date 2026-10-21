import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
PLUGINS = Path('/home/zj-normal/Work/autonomics-plugins')
IMAGE = Path('/run/media/zj-normal/新加卷/Autonomics-cold-results-v41-20261017-v1/cachexia-v4.1.squashfs')
INDEX = 'a2069d3c25384cbfb32da36d3a573a43'
SEAL = 'c4c831052c893b4d01f864731b6120e567d2beffc0b9bfa42af7dc6822dcc00f'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0, str(PLUGINS))
    from tools.reconcile_ab_evidence_index import verify_archive
    require(verify_archive(ARCHIVES, INDEX, SEAL)['positive_worker_exit_verified'], 'Original frozen index not verified')
    index = json.loads((ARCHIVES / INDEX / 'artifacts/permanent/lcmm-original-proof-index/SELECTED_ORIGINAL_INDEX.json').read_text())
    require(index['original_seal_sha256'] == 'f93f9285b5f881f8a122c7a6a471a0b1467cb75b72b052e01deccb6545a27acd', 'Original inventory identity differs')
    records = {row['path']: row for row in index['bounded_fixture_candidates']}
    selected = ['lcmm-proof-v4/official-build/Dockerfile', 'lcmm-proof-v4/official-build/source-plan.json']
    require(sum(records[name]['size_bytes'] for name in selected) == 2865, 'Exact two-file byte budget required')
    mounts = json.loads(subprocess.check_output(['findmnt','--json','-T',str(IMAGE),'-o','TARGET,UUID']))['filesystems']
    require(len(mounts) == 1 and mounts[0]['uuid'] == 'D2F694CAF694B069'
            and mounts[0]['target'] == '/run/media/zj-normal/新加卷', 'Exact read-only cold-source identity required')

    def signature():
        value = IMAGE.stat()
        return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns]

    before = signature()
    require(before[2] == 27543273472, 'Frozen archive size differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'lcmm-build-recipe-recovery'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    for name in selected:
        response = subprocess.run(['unsquashfs','-processors','1','-mem','32M','-no-wildcards','-cat',str(IMAGE),
            'node-proof-lcmm-20261007/'+name],capture_output=True,timeout=90)
        record = records[name]
        require(response.returncode == 0 and len(response.stdout) == record['size_bytes']
                and hashlib.sha256(response.stdout).hexdigest() == record['sha256']
                and signature() == before, 'Exact archived recipe member identity differs')
        (output / Path(name).name).write_bytes(response.stdout)
    require(signature() == before, 'Cold source changed')
    report = dict(schema='LCMM_ORIGINAL_BUILD_RECIPE_RECOVERY_V1', passed=True,
        original_index_session=INDEX, original_index_seal=SEAL, selected_records=[records[name] for name in selected],
        source_bytes_recovered=2865, source_archive_unchanged=True, image_rebuilt=False,
        images_pushed=False, source_recipe_not_a_new_rebuild_certificate=True,
        new_method_executions=0,new_software_admissions=0,scientific_release_granted=False,g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
