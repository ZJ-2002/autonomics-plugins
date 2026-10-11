#!/usr/bin/env python3
"""Embed complete shared sources and dispatch only the declared joint node."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'study_plugins/mvmr-joint-contract/scripts'


def rendered(operation):
    files = [ROOT / 'study_plugins/shared/gwas-normalization-receipt.R', PLUGIN / 'union.R']
    if operation == 'clump':
        files += [ROOT / 'study_plugins/clump-contract/scripts/clump.R', PLUGIN / 'joint-receipt.R']
        function, inputs, outputs = 'joint_clump_main', 5, 5
        extra = ['/panels/plink_ref', '/work/joint-clump']
    elif operation == 'union':
        function, inputs, outputs = 'joint_union_main', 7, 4
        extra = ['/work/joint-union']
    elif operation == 'harmonise':
        files += [PLUGIN / 'harmonise.R']
        function, inputs, outputs = 'joint_harmonise_main', 12, 4
        extra = ['/work/joint-harmonise']
    else:
        raise ValueError('unknown declared joint operation')
    args = ['"$AUTONOMICS_INPUT' + str(i) + '"' for i in range(inputs)]
    args += extra
    args += ['"$AUTONOMICS_OUTPUT' + str(i) + '"' for i in range(outputs)]
    # Non-top-level evaluation preserves original source dispatch guards without
    # executing them. Only the declared dispatcher runs after loading all sources.
    return ('#!/bin/sh\nset -eu\nexport LC_ALL=C\nexec Rscript --vanilla - '
            + ' '.join(args) + " <<'AUTONOMICS_FROZEN_JOINT_R'\n"
            + 'local({\n' + '\n'.join(f.read_text() for f in files)
            + '\n}, envir = .GlobalEnv)\n'
            + 'tryCatch(' + function + '(commandArgs(TRUE)), error = function(e) {'
            + 'message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)})\n'
            + 'AUTONOMICS_FROZEN_JOINT_R\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for operation in ['union', 'clump', 'harmonise']:
        directory = ROOT / 'study_plugins/mvmr-joint-clump-contract/scripts' if operation == 'clump' else PLUGIN
        target = directory / ('run-' + operation + '.sh')
        if args.check:
            if target.is_symlink() or not target.is_file() or target.read_bytes() != rendered(operation).encode():
                raise SystemExit('joint wrapper absent or stale: ' + operation)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered(operation))
            target.chmod(0o755)
