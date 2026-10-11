#!/usr/bin/env python3
"""Generate the full self-contained MVMR entry point; --check never writes."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render():
    body = (ROOT/'study_plugins/mvmr-contract/scripts/mvmr.R').read_text()
    variables = ['"$AUTONOMICS_INPUT'+str(i)+'"' for i in range(7)]
    variables += ['"$AUTONOMICS_OUTPUT'+str(i)+'"' for i in range(4)]
    return '#!/bin/sh\nset -eu\nSCRIPT=$(mktemp /tmp/autonomics-mvmr-contract-XXXXXX.R)\ntrap \'rm -f "$SCRIPT"\' EXIT HUP INT TERM\ncat > "$SCRIPT" <<\'AUTONOMICS_FROZEN_MVMR\'\n'+body+'\nAUTONOMICS_FROZEN_MVMR\nRscript --vanilla "$SCRIPT" '+' '.join(variables)+'\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT/'study_plugins/mvmr-contract/scripts/run-mvmr.sh'
    if args.check:
        if target.is_symlink() or not target.is_file() or target.read_bytes() != render().encode():
            raise SystemExit('MVMR wrapper absent or stale; regenerate from complete source')
    else:
        target.write_text(render())
        target.chmod(0o755)
