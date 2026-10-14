"""Correct only one stopped technical reader receipt owner; never change its bytes or exit."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session = '3b70f091b0f04399bf0a4b85f54ec71f'
    workspace = Path.home() / '.cache/autonomics-validation-sessions' / session
    archive = Path.home() / '.local/state/autonomics/validation-archives' / session
    with (archive / 'session.lock').open('rb') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = json.loads((archive / 'SESSION.json').read_text())
        assert record['state'] == 'EXIT_RECORDED' and record['worker_exit_status'] == record['launcher_exit_status'] == 0
        observed = subprocess.run(['systemctl', '--user', 'show', record['unit'], '--property=ActiveState,MainPID'], capture_output=True, text=True)
        fields = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
        assert fields.get('ActiveState') in ['inactive', 'failed'] and fields.get('MainPID') == '0', fields
        status = workspace.lstat()
        assert stat.S_ISDIR(status.st_mode) and not workspace.is_symlink() and status.st_uid == os.getuid()
        assert [status.st_dev, status.st_ino] == record['workspace_identity']
        path = workspace / 'permanent/bulk-current-chain/R_READBACK.json'
        before = path.lstat()
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == before.st_gid == 100000
        payload = path.read_bytes()
        contents = json.loads(payload)
        assert len(contents['tables']) == 18 and len(contents['datasets']) == 2 and contents['G0'] is False
        completed = subprocess.run(['sudo', '-n', '/usr/bin/chown', '--from=100000:100000',
            str(os.getuid()) + ':' + str(os.getgid()), '--', str(path)], capture_output=True, text=True)
        if completed.returncode: raise RuntimeError('Exact scoped receipt ownership correction failed: ' + completed.stderr)
        after = path.lstat()
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mode) == (after.st_dev, after.st_ino, after.st_size, after.st_mode)
        assert after.st_uid == os.getuid() and after.st_gid == os.getgid() and path.read_bytes() == payload
        receipt = dict(session=session, action='ONE_STOPPED_TECHNICAL_JSON_OWNER_CORRECTED',
            old_uid=before.st_uid, old_gid=before.st_gid, new_uid=after.st_uid, new_gid=after.st_gid,
            file_sha256=hashlib.sha256(payload).hexdigest(), actual_unit_observation=fields,
            bytes_or_inode_or_mode_or_source_or_exit_changed=False, unrelated_paths_changed=False, g0_granted=False)
        encoded = json.dumps(receipt, indent=2) + '\n'
        for destination in [permanent / 'BULK_READER_OWNER_CORRECTION.json',
                            workspace / 'permanent/bulk-current-chain/POST_TERMINAL_READER_OWNER_CORRECTION.json']:
            with destination.open('x') as handle: handle.write(encoded)
    print('ONE_TECHNICAL_RECEIPT_OWNER_CORRECTED_BYTES_UNCHANGED G0=false')


if __name__ == '__main__': main()
