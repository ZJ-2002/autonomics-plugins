"""Run all existing current pseudobulk contract cases in its fixed image."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write


ROOT = Path(__file__).resolve().parents[1]


def main():
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'pseudobulk-boundaries'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    source = output / 'source'
    (source / 'scripts').mkdir(parents=True)
    (source / 'tests').mkdir()
    files = ['test_assurance.sh', 'scripts/pseudobulk_counts.py', 'tests/test_assurance.py', 'manifest.toml']
    for name in files:
        shutil.copyfile(ROOT / 'plugins/pseudobulk' / name, source / name)
    hashes = {name: digest(source / name) for name in files}
    completed = subprocess.run(['bash', str(source / 'test_assurance.sh')],
        env=dict(os.environ, PSEUDOBULK_EVIDENCE=str(output / 'runs')), capture_output=True, timeout=600)
    (output / 'suite.stdout').write_bytes(completed.stdout)
    (output / 'suite.stderr').write_bytes(completed.stderr)
    if completed.returncode:
        raise RuntimeError('Full current fixed-image pseudobulk suite failed')
    summary = json.loads((output / 'runs/cases/SUMMARY.json').read_text())
    records = summary['records']
    if (summary['cases'] != len(records) or len(records) != 41
            or sum(record.get('exact_independent_reference', False) for record in records) != 20
            or sum(record.get('refused', False) for record in records) != 21
            or summary['source_sha256'] != hashes['scripts/pseudobulk_counts.py']):
        raise RuntimeError('Complete current pseudobulk inventory or method identity differs')
    symlink = output / 'runs/cases/output-symlink/counts.tsv'
    if not symlink.is_symlink() or os.readlink(symlink) != 'absent.tsv' or symlink.exists():
        raise RuntimeError('Verified intentional dangling fixture differs')
    symlink.unlink()
    write(output / 'dangling-fixture-receipt.json', dict(case='output-symlink', target='absent.tsv',
          unchanged_after_refusal=True, owned_fixture_removed_before_archive=True, g0_granted=False))
    if hashes != {name: digest(source / name) for name in files}:
        raise RuntimeError('Dispatched suite or method changed')
    write(output / 'verification.json', dict(status='CURRENT_PSEUDOBULK_ALL_41_CASES_PROVEN_SCOPED',
        positive_cases=20, refusal_cases=21, source_sha256=hashes,
        reference='Independent arbitrary precision integer grouping and preexisting Scanpy-scoped evidence; this suite does not invoke Scanpy',
        actual_aggregation='Official SciPy sparse matrix operations plus explicit engineering grouping/validation; not a statistical estimator or Rust implementation',
        versions=summary['versions'], new_study_or_daemon_qualified=False, g0_granted=False))
    print('PSEUDOBULK_CASES=41 POSITIVE=20 REFUSED=21 G0=false')


if __name__ == '__main__':
    main()
