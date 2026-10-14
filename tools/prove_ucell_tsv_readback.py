"""Finish typed metadata and official-object readback without rerunning the sealed DAG stage."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_generic_plugin_guards import sealed
from tools.prove_ucell_tsv_io import IMAGE, ROOT
from tools.prove_ucell_current_dag import reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--author-packet', type=Path, required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    reference(arguments.author_packet)
    original = sealed(arguments.archives, 'f2deb00d5d964dfd95e065260aaa60e0',
        'bbfd3ff5916c2b152e4cd3a1921c48dcab14d32f699a4a11b7fd9c4acd37ea86', 'ucell-tsv-dag')
    if digest(original / 'source/scripts/ucell.R') != digest(ROOT / 'plugins/ucell/scripts/ucell.R'):
        raise RuntimeError('Current method differs from the actual DAG method')
    records = json.loads((original / 'completed-cases.json').read_text())
    cases = json.loads((original / 'positive-cases.json').read_text())
    if len(records) != 12 or len(cases) != 12 or {case['case'] for case in records} != {case['name'] for case in cases}:
        raise RuntimeError('Complete actual twelve-case stage required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-readback'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(ROOT / 'tools/ucell_tsv_reference.R', output / 'reference.R')
    shutil.copyfile(original / 'positive-cases.json', output / 'positive-cases.json')
    for case in cases:
        work = output / case['name']
        work.mkdir()
        for filename in ['matrix.tsv', 'signatures.tsv', 'ucell_scores.tsv', 'ucell.RDS', 'ucell.log', 'audit.json', 'author-reference.RDS']:
            shutil.copyfile(original / case['name'] / filename, work / filename)
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g',
        '--userns=keep-id', '--tmpfs=/tmp:rw,size=64m', '-v', str(output) + ':/work:rw',
        '-v', str(arguments.author_packet / 'fresh-author-R') + ':/author:ro', '--entrypoint=Rscript', IMAGE,
        '--vanilla', '/work/reference.R', 'compare', '/work', '/author']
    completed = subprocess.run(command, capture_output=True, timeout=180)
    (output / 'compare.stdout').write_bytes(completed.stdout)
    (output / 'compare.stderr').write_bytes(completed.stderr)
    if completed.returncode or b'COMPARE CASES 12' not in completed.stdout:
        raise RuntimeError('Strict typed official-object readback failed')
    compared = json.loads((output / 'readback-verification.json').read_text())
    write(output / 'verification.json', dict(status='REPAIRED_TSV_UCELL_COMPLETE_OFFICIAL_OBJECT_READBACK_PROVEN',
        DAG_stage_session='f2deb00d5d964dfd95e065260aaa60e0',
        DAG_stage_manifest_sha256='bbfd3ff5916c2b152e4cd3a1921c48dcab14d32f699a4a11b7fd9c4acd37ea86',
        compared_cases=compared, official_score_objects_or_reference_files_modified=False,
        reference_metadata_correction='JSON integer w_neg constructed as integer by the first reference harness; declared wrapper RDS schema uses as.numeric(double). Exact value and all score/feature objects remain strict.',
        method_source_sha256=digest(ROOT / 'plugins/ucell/scripts/ucell.R'),
        method_or_DAG_recomputed=False, worker_exit_of_original_stage_rewritten=False, g0_granted=False))
    print('EXACT_OFFICIAL_OBJECT_READBACKS=12 NO_DAG_RECOMPUTATION=true G0=false')


if __name__ == '__main__':
    main()
