#!/usr/bin/env python3
"""Generate the byte-bound MRlap container entrypoint, not a method approval."""
import hashlib
from pathlib import Path


def wrapper(root):
    payload = (root / 'scripts/mrlap.R').read_bytes()
    source = payload.decode()
    token = 'AUTONOMICS_FROZEN_MRLAP_R'
    if token in source:
        raise ValueError('R source collides with the fixed heredoc boundary')
    arguments = ' '.join('"${AUTONOMICS_INPUT%d:?}"' % i for i in range(10))
    arguments += ' ' + ' '.join('"${AUTONOMICS_OUTPUT%d:?}"' % i for i in range(5))
    return ('#!/bin/sh\nset -eu\n# Generated from mrlap.R SHA256 ' + hashlib.sha256(payload).hexdigest() +
            '\nR_SOURCE="$(mktemp /tmp/autonomics-mrlap-XXXXXX.R)"\n'
            'trap \'rm -f "$R_SOURCE"\' EXIT HUP INT TERM\n'
            'cat > "$R_SOURCE" <<\'' + token + "'\n" + source + '\n' + token + '\n'
            'Rscript --vanilla "$R_SOURCE" ' + arguments + '\n')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / 'study_plugins/mrlap-contract'
    target = root / 'scripts/run-mrlap.sh'
    target.write_text(wrapper(root))
    target.chmod(0o755)
