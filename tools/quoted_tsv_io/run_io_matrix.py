import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess


ROOT = Path(os.environ['IO_EVIDENCE']).resolve()
SOURCE = Path(__file__).resolve().parents[2]
BASE = Path(os.environ['IO_AUTHOR_PACKETS']).resolve(strict=True)
IMAGES = {
    'producer': 'ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5',
    'deseq2': 'ghcr.io/zj-2002/deseq2@sha256:5931c509f7f30d44177033877a96b062bf8532d16e5762daebfa20564278a59f',
    'limma': 'ghcr.io/zj-2002/bulk-rnaseq-official@sha256:8b280a45781160f3dc1f5bfac90862b8a85d7d2bf1b89146e418658cca4ca85a',
}
SCRIPTS = {'producer': SOURCE / 'plugins/pseudobulk/scripts/pseudobulk_counts.py',
    'deseq2': SOURCE / 'plugins/deseq2/deseq2_runner.R',
    'limma': SOURCE / 'plugins/bulk-rnaseq/limma_voom_runner.R'}


def execute(kind, case, name, script, environment, reference=None, arguments=None):
    command = ['podman', 'run', '--rm', '--pull=never', '--cpus=2', '--memory=2g', '--network=none',
        '--mount', f'type=bind,src={case},dst=/case', '--mount', f'type=bind,src={script},dst=/method,ro=true',
        '--entrypoint', 'python' if kind == 'producer' else 'Rscript']
    if reference:
        command.extend(['--mount', f'type=bind,src={reference},dst=/reference-library,ro=true',
            '--env', 'REFERENCE_LIBRARY=/reference-library'])
    for key, value in environment.items():
        command.extend(['--env', key + '=' + value])
    command.extend([IMAGES[kind]])
    if kind != 'producer':
        command.append('--vanilla')
    command.extend(['/method', *(arguments or [])])
    result = subprocess.run(command, capture_output=True, timeout=240)
    (case / (name + '.stdout.txt')).write_bytes(result.stdout)
    (case / (name + '.stderr.txt')).write_bytes(result.stderr)
    record = {'command': command, 'exit': result.returncode,
        'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(), 'G0': False}
    (case / (name + '.execution.json')).write_text(json.dumps(record, indent=2) + '\n')
    assert result.returncode == 0, result.stderr.decode()


def table(path):
    with path.open(newline='') as handle:
        return list(csv.reader(handle, delimiter='\t', strict=True))


def compare(actual, reference, tolerance):
    left, right = table(actual), table(reference)
    assert left[0] == right[0], (actual.name, left[0], right[0])
    assert len(left) == len(right)
    maximum = 0.0
    checked = 0
    for observed, expected in zip(left[1:], right[1:]):
        assert observed[0] == expected[0], (observed[0], expected[0])
        assert len(observed) == len(expected) == len(left[0])
        for value, baseline in zip(observed[1:], expected[1:]):
            if value == 'NA' or baseline == 'NA':
                assert value == baseline
                continue
            numeric, target = float(value), float(baseline)
            assert math.isfinite(numeric) and math.isfinite(target)
            error = abs(numeric - target)
            assert error <= tolerance + tolerance * abs(target), (actual, numeric, target)
            maximum = max(maximum, error)
            checked += 1
    return {'file': str(actual.relative_to(ROOT)), 'rows': len(left) - 1,
        'numeric_fields': checked, 'max_absolute_error': maximum, 'atol': tolerance, 'rtol': tolerance}


def verify_reference_prefix(kind):
    packet = BASE / ('canonical-deseq2-v1-20261012' if kind == 'deseq2' else 'canonical-limma-voom-v1-20261012')
    entries = json.loads((packet / 'SEALED_FILES.json').read_text())['files']
    entries = [entry for entry in entries if entry['path'].startswith('official-reference-library/')]
    assert entries
    actual_payloads = {str(path.relative_to(packet)) for path in (packet / 'official-reference-library').rglob('*') if path.is_file()}
    assert actual_payloads == {entry['path'] for entry in entries}
    for entry in entries:
        path = packet / entry['path']
        assert path.stat().st_size == entry['size']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], path
    return packet / 'official-reference-library', {'kind': kind, 'inherited_sealed_author_library': True,
        'fresh_installation': False, 'sealed_files_verified': len(entries), 'complete_prefix_census_matches': True,
        'seal_sha256': hashlib.sha256((packet / 'SEALED_FILES.json').read_bytes()).hexdigest()}


def main():
    ROOT.mkdir(parents=True, exist_ok=False)
    execute('producer', ROOT, 'fixtures', Path(__file__).with_name('build_fixture.py'), {},
        arguments=['/case/fixtures-v2'])
    prefixes, provenance = {}, []
    for kind in ('deseq2', 'limma'):
        prefixes[kind], record = verify_reference_prefix(kind)
        provenance.append(record)
    (ROOT / 'REFERENCE_INHERITANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    evidence = []
    for case in sorted((ROOT / 'fixtures-v2').iterdir()):
        oracle = json.loads((case / 'decoded-oracle.json').read_text())
        execute('producer', case, 'producer', SCRIPTS['producer'], {
            'AUTONOMICS_INPUT0': '/case/input.h5ad', 'AUTONOMICS_OUTPUT0': '/case/counts.tsv',
            'AUTONOMICS_OUTPUT1': '/case/metadata.tsv', 'AUTONOMICS_OUTPUT2': '/case/producer.log',
            'PB_SAMPLE_COL': 'donor', 'PB_CELLTYPE_COL': 'celltype', 'PB_MIN_CELLS': '1',
            'PB_LAYER': '', 'PB_SCHEMA': 'deseq2', 'PB_CONDITION_COLUMN': 'condition'})
        counts = table(case / 'counts.tsv')
        assert counts[0] == ['gene_id', *oracle['samples']]
        assert counts[1:] == [[gene, *map(str, row)] for gene, row in zip(oracle['genes'], oracle['count_rows'])]
        metadata = table(case / 'metadata.tsv')
        metadata_dicts = [dict(zip(metadata[0], row)) for row in metadata[1:]]
        assert [row['sample_id'] for row in metadata_dicts] == oracle['samples']
        assert [row['sample'] for row in metadata_dicts] == oracle['donors']
        assert [row['condition'] for row in metadata_dicts] == oracle['conditions']
        assert all(row['n_cells'] == '3' for row in metadata_dicts)
        for kind in ('deseq2', 'limma'):
            outputs = ['results.tsv', 'normalized.tsv', 'size_factors.tsv', 'dataset.rds', 'report.json'] if kind == 'deseq2' else ['results.tsv', 'weights.tsv', 'normalized.tsv', 'contrasts.tsv', 'report.json']
            directory = case / (kind + '-node')
            directory.mkdir()
            environment = {'AUTONOMICS_INPUT0': '/case/counts.tsv', 'AUTONOMICS_INPUT1': '/case/metadata.tsv'}
            environment.update({'AUTONOMICS_OUTPUT' + str(index): '/case/' + directory.name + '/' + name for index, name in enumerate(outputs)})
            if kind == 'deseq2':
                environment.update({'AUTONOMICS_DESEQ2_CONDITION_REFERENCE': 'ctrl', 'AUTONOMICS_DESEQ2_CONDITION_TEST': 'case',
                    'AUTONOMICS_DESEQ2_FIT_TYPE': 'mean', 'AUTONOMICS_DESEQ2_LFC_SHRINK': 'none', 'AUTONOMICS_DESEQ2_THREADS': '1'})
            else:
                environment.update({'AUTONOMICS_LIMMA_OUTCOME': 'condition', 'AUTONOMICS_LIMMA_CONTRAST_VAR': 'condition',
                    'AUTONOMICS_LIMMA_CONTRAST_LEVELS': 'ctrl,case', 'AUTONOMICS_LIMMA_OUTCOME_MODE': 'categorical',
                    'AUTONOMICS_LIMMA_NORMALIZATION': 'tmm', 'AUTONOMICS_LIMMA_THREADS': '1'})
            execute(kind, case, kind + '-node', SCRIPTS[kind], environment)
            execute(kind, case, kind + '-author', Path(__file__).with_name('official_decoded_reference.R'), {},
                prefixes[kind], [kind, '/case'])
            comparisons = [compare(directory / name, case / (kind + '-reference') / name,
                1e-10 if kind == 'deseq2' else 1e-12) for name in outputs[:3]]
            evidence.append({'case': case.name, 'kind': kind, 'comparisons': comparisons, 'status': 'PASS',
                'reference_does_not_read_producer_tsv': True, 'G0': False})
            (ROOT / 'IO_MATRIX.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
            print(case.name, kind, 'PASS', flush=True)


if __name__ == '__main__':
    main()
