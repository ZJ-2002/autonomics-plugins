"""Reproduce or check UCell TSV path ownership using disposable synthetic files."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write


ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/zj-2002/cachexia-ucell-official@sha256:f5310020240016e9069783498aebbd1849c73c6ae4918058614803fe3b6bfca1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    parser.add_argument('--method-script', type=Path, default=ROOT / 'plugins/ucell/scripts/ucell.R')
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / ('ucell-tsv-io-' + arguments.phase)
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    if arguments.phase == 'before' and digest(arguments.method_script) != '43ca20c8a63417c4ef26d8c56a61b65b064fbe71f4974add726b75998b8624d0':
        raise RuntimeError('Before reproduction requires the exact preserved original source')
    shutil.copyfile(arguments.method_script, output / 'source.R')
    records = []
    for name in ['existing-outputs', 'input-alias', 'log-alias']:
        work = output / name
        work.mkdir()
        (work / 'matrix.tsv').write_text('gene\tC1\tC2\nG1\t1\t3\nG2\t4\t2\nG3\t2\t1\n')
        (work / 'signatures.tsv').write_text('signature\tgene\none\tG1\n')
        names = ['scores.tsv', 'result.RDS', 'log.txt', 'audit.json']
        if name == 'existing-outputs':
            for filename in names:
                (work / filename).write_bytes(b'PREEXISTING_TECHNICAL_SENTINEL\n')
        elif name == 'input-alias':
            names[0] = 'matrix.tsv'
        else:
            names[2] = 'matrix.tsv'
        before = {file.name: digest(file) for file in work.iterdir() if file.is_file()}
        variables = ['-e', 'AUTONOMICS_INPUT0=/work/matrix.tsv', '-e', 'AUTONOMICS_INPUT1=/work/signatures.tsv',
                     '-e', 'UCELL_MAX_RANK=3', '-e', 'UCELL_NEGATIVE_WEIGHT=1', '-e', 'UCELL_MISSING_GENES=invalid']
        for index, filename in enumerate(names):
            variables += ['-e', f'AUTONOMICS_OUTPUT{index}=/work/{filename}']
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g', '--userns=keep-id',
                   '--tmpfs=/tmp:rw,size=32m', '-v', str(work) + ':/work:rw', '-v', str(output / 'source.R') + ':/program.R:ro',
                   '--entrypoint=Rscript', *variables, IMAGE, '--vanilla', '/program.R']
        completed = subprocess.run(command, capture_output=True, timeout=90)
        (work / 'process.stdout').write_bytes(completed.stdout)
        (work / 'process.stderr').write_bytes(completed.stderr)
        after = {name: digest(work / name) if (work / name).is_file() else None for name in before}
        damaged = [name for name in before if before[name] != after[name]]
        expected = ['scores.tsv', 'result.RDS', 'log.txt', 'audit.json'] if name == 'existing-outputs' else ['matrix.tsv']
        if completed.returncode != 2 or (set(damaged) != set(expected) if arguments.phase == 'before' else damaged):
            raise RuntimeError('Unexpected UCell ownership outcome: ' + name)
        if arguments.phase == 'after' and b'BLOCKED:' not in completed.stderr:
            raise RuntimeError('Explicit protected-path refusal missing')
        records.append(dict(case=name, exit_code=completed.returncode, before=before, after=after, damaged=damaged))
    write(output / 'verification.json', dict(phase=arguments.phase, cases=records,
        status='DATA_LOSS_REPRODUCED' if arguments.phase == 'before' else 'PROTECTED_PATH_REFUSALS_ENFORCED',
        method_source_sha256=digest(output / 'source.R'), image=IMAGE, only_owned_synthetic_files_used=True, g0_granted=False))
    print('OWNED_SYNTHETIC_PATH_CASES=3 PHASE=' + arguments.phase + ' G0=false')


if __name__ == '__main__':
    main()
