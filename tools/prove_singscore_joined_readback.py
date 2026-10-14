"""Check all complete sealed current-engine Singscore RDS objects, without rerunning DAGs."""

import argparse
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_generic_plugin_guards import sealed


SESSION = '50e4b946d8f14e38bf34c7c3e16f0980'
SEAL = 'd8992bc43f98a69a71aaa5d580d190bd46f236716a03c18a79a36c099bc2eb5c'


def reference_path(value, reference):
    if not value.startswith('/work/'):
        raise RuntimeError('Exact original comparison path required')
    relative = Path(value[len('/work/'):])
    if '..' in relative.parts or not (reference / relative).is_file():
        raise RuntimeError('Comparison path outside the sealed archive')
    return '/reference/' + relative.as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', required=True, type=Path)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    reference = sealed(arguments.archives, SESSION, SEAL, 'singscore-current-dag')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'singscore-joined-readback'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    verifier = Path(__file__).with_name('verify_singscore_joined.R')
    shutil.copyfile(verifier, output / verifier.name)
    with (reference / 'readback-pairs.tsv').open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        fields = reader.fieldnames
        if fields != ['case', 'actual_rds', 'reference_rds', 'scores_tsv', 'metadata_tsv']:
            raise RuntimeError('Exact comparison schema required')
        records = list(reader)
    if len(records) != 10 or len({record['case'] for record in records}) != 10:
        raise RuntimeError('Complete ten positive cases required')
    for record in records:
        for name in fields[1:]:
            record[name] = reference_path(record[name], reference)
    with (output / 'pairs.tsv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
    manifest = tomllib.loads((reference / 'source/manifest.toml').read_text())
    image = manifest['image']['reference']
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
               '--cpus=1', '--memory=1g', '--tmpfs=/tmp:rw,size=32m',
               '-v', str(reference) + ':/reference:ro', '-v', str(output) + ':/work:rw',
               '--entrypoint=Rscript', image, '--vanilla', '/work/' + verifier.name,
               '/work/pairs.tsv', '/work/mutations']
    with (output / 'readback.stdout').open('wb') as stdout, (output / 'readback.stderr').open('wb') as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120)
    messages = (output / 'readback.stdout').read_text()
    if completed.returncode or 'VERIFIED_COMPLETE_PAIRS 10 REJECTED_MUTATIONS 6' not in messages:
        raise RuntimeError('Complete joined-object validation failed; preserved diagnostic required')
    write(output / 'verification.json', dict(
        status='COMPLETE_SINGSCORE_RDS_LIST_FIELDS_TYPES_ATTRIBUTES_IDENTICAL',
        source_session=SESSION, source_manifest_sha256=SEAL,
        verifier_sha256=digest(verifier), image=image, compared_cases=[record['case'] for record in records],
        positive_complete_objects=10, explicit_mutation_refusals=6,
        mutant_fields=['group', 'TotalScore', 'extra_field', 'class', 'row_names', 'nonfinite'],
        original_sealed_outputs_or_reference_changed=False, DAG_or_method_recomputed=False,
        scientific_admission_granted=False, g0_granted=False))
    print('COMPLETE_RDS_PAIRS=10 MUTANT_REFUSALS=6 G0=false')


if __name__ == '__main__':
    main()
