"""Materialize a stopped owned technical fixture alias without changing any evidence bytes."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    session = '37472e74e49340d3bf8096ecdf83b943'
    home = Path.home()
    archive = home / '.local/state/autonomics/validation-archives' / session
    workspace = home / '.cache/autonomics-validation-sessions' / session
    with (archive / 'session.lock').open('rb') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = json.loads((archive / 'SESSION.json').read_text())
        assert record['state'] == 'EXIT_RECORDED' and record['worker_exit_status'] == record['launcher_exit_status'] == 0
        unit = record['unit']
        observed = subprocess.run(['systemctl', '--user', 'show', unit, '--property=ActiveState,LoadState,MainPID'], capture_output=True, text=True)
        fields = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
        assert fields.get('ActiveState') in ['inactive', 'failed'] and fields.get('MainPID') == '0', fields
        status = workspace.lstat()
        assert stat.S_ISDIR(status.st_mode) and not workspace.is_symlink() and status.st_uid == os.getuid()
        assert [status.st_dev, status.st_ino] == record['workspace_identity']
        parent = workspace / 'permanent/ucell-tsv-failures/hardlinked-output'
        source, alias = parent / 'signatures.tsv', parent / 'scores.tsv'
        source_status, alias_status = source.lstat(), alias.lstat()
        expected = b'signature\tgene\none\tG1\n'
        assert source.read_bytes() == alias.read_bytes() == expected
        assert stat.S_ISREG(source_status.st_mode) and stat.S_ISREG(alias_status.st_mode)
        assert source_status.st_uid == alias_status.st_uid == os.getuid()
        assert (source_status.st_dev, source_status.st_ino) == (alias_status.st_dev, alias_status.st_ino)
        assert source_status.st_nlink == alias_status.st_nlink == 2
        descriptor, temporary = tempfile.mkstemp(prefix='.materialize-owned-fixture-', dir=parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(expected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, alias)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        assert source.read_bytes() == alias.read_bytes() == expected
        assert source.stat().st_nlink == alias.stat().st_nlink == 1
        receipt = dict(session=session, action='OWNED_TECHNICAL_ALIAS_MATERIALIZED_AFTER_ACTUAL_ZERO_EXIT',
            stopped_unit_observation=fields, old_device=source_status.st_dev, old_shared_inode=source_status.st_ino,
            sha256=hashlib.sha256(expected).hexdigest(), evidence_file_bytes_changed=False,
            source_code_or_exit_status_changed=False, deletion_authorization_for_other_paths=False, g0_granted=False)
        payload = json.dumps(receipt, indent=2) + '\n'
        with (workspace / 'permanent/ucell-tsv-failures/POST_TERMINAL_FIXTURE_MATERIALIZATION.json').open('x') as handle: handle.write(payload)
        with (permanent / 'UCELL_TOY_HARDLINK_MATERIALIZATION.json').open('x') as handle: handle.write(payload)
    print('OWNED_ALIAS_MATERIALIZED_BYTES_UNCHANGED G0=false')


if __name__ == '__main__':
    main()
