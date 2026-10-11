import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import time


ROOT = Path(os.environ['DESEQ2_NUMERICAL_EVIDENCE']).resolve()
ROOT.mkdir(exist_ok=False)
SOURCE = Path(__file__).resolve().parents[1]
IMAGE = os.environ['DESEQ2_NUMERICAL_IMAGE']
if not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', IMAGE):
    raise RuntimeError('Mandatory immutable image required')
LIBRARY = Path(os.environ['DESEQ2_REFERENCE_LIBRARY']).resolve(strict=True)
if not all((LIBRARY / name).is_dir() for name in ['DESeq2', 'apeglm']):
    raise RuntimeError('Mandatory independently source-installed official library is missing')
CONTRACT = json.loads((Path(__file__).parent / 'validation_contract.json').read_text())
ATTEMPT = os.environ.get('DESEQ2_PROOF_ATTEMPT', '')


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def execute(command, directory, prefix):
    if (directory / (prefix + '.execution.json')).exists():
        raise RuntimeError('Refusing to overwrite an execution record')
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=600)
    (directory / (prefix + '.stdout.txt')).write_bytes(result.stdout)
    (directory / (prefix + '.stderr.txt')).write_bytes(result.stderr)
    (directory / (prefix + '.execution.json')).write_text(json.dumps({'command': command,
        'exit': result.returncode, 'seconds': time.monotonic() - started, 'G0': False}, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(prefix + ': ' + result.stderr.decode())


def fixture(directory, special):
    if special == 'pasilla':
        shutil.copyfile(SOURCE / 'fixtures/pasilla_gene_counts.tsv', directory / 'counts.tsv')
        shutil.copyfile(SOURCE / 'fixtures/pasilla_sample_metadata.tsv', directory / 'metadata.tsv')
        return ['untreated', 'treated']
    generator = random.Random(410612)
    samples = [str(index + 1) if special == 'numeric_sample_ids' else 'sample' + str(index + 1) for index in range(12)]
    levels = ['control-read', 'case-read'] if special == 'hyphen_levels' else ['ctrl', 'case']
    if special == 'numeric_conditions':
        levels = ['0', '1']
    cutoff = 4 if special == 'unbalanced' else 6
    metadata = [[sample, levels[0] if index < cutoff else levels[1], str(20 + (index * 7) % 17),
                 'batchA' if index % 2 else 'batchB'] for index, sample in enumerate(samples)]
    genes = ['gene' + str(index + 1) for index in range(200)]
    if special == 'literal_gene_ids':
        genes[:3] = ['00001', 'NA', '12345']
    rows = []
    for index, gene in enumerate(genes):
        baseline = generator.uniform(70, 1500)
        values = [str(max(1, round(generator.gammavariate(8, baseline / 8) *
                  (2 if index < 20 and sample_index >= cutoff else 1) * (0.7 + sample_index / 20))))
                  for sample_index in range(12)]
        rows.append([gene, *values])
    if special == 'zero_genes':
        rows.append(['zero_gene', *(['0'] * 12)])
    if special == 'cook_outlier':
        rows[0][1] = '10000000'
    if special == 'exact_decimal_counts':
        rows[0][1] = '.5e1'
        rows[1][1] += '.0000000000'
        rows[2][1] += 'e0'
        rows[3][1] = '+' + rows[3][1]
    if special == 'reordered_metadata':
        generator.shuffle(metadata)
    for name, header, values in [('counts.tsv', ['gene_id', *samples], rows),
                                 ('metadata.tsv', ['sample_id', 'condition', 'age', 'batch'], metadata)]:
        with (directory / name).open('w') as handle:
            writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
            writer.writerow(header)
            writer.writerows(values)
    if special == 'reverse_contrast':
        levels.reverse()
    return levels


def compare_tables(actual_file, expected_file):
    with actual_file.open() as handle:
        actual = list(csv.reader(handle, delimiter='\t'))
    with expected_file.open() as handle:
        expected = list(csv.reader(handle, delimiter='\t'))
    if actual[0] != expected[0] or len(actual) != len(expected):
        raise RuntimeError('Output header or shape differs')
    compared, missing, maximum = 0, 0, 0.0
    for actual_row, expected_row in zip(actual[1:], expected[1:]):
        if len(actual_row) != len(actual[0]) or len(actual_row) != len(expected_row) or actual_row[0] != expected_row[0]:
            raise RuntimeError('Output row identity or width differs')
        for actual_text, expected_text in zip(actual_row[1:], expected_row[1:]):
            if expected_text == 'NA':
                if actual_text != 'NA':
                    raise RuntimeError('Official NA mask differs')
                missing += 1
                continue
            actual_value, expected_value = float(actual_text), float(expected_text)
            if not math.isfinite(actual_value) or not math.isfinite(expected_value):
                raise RuntimeError('Unexpected nonfinite result')
            error = abs(actual_value - expected_value)
            if error > CONTRACT['absolute_tolerance'] + CONTRACT['relative_tolerance'] * abs(expected_value):
                raise RuntimeError(f'Numerical mismatch {actual_file.name}: {actual_text} vs {expected_text}')
            maximum = max(maximum, error)
            compared += 1
    return {'numeric_fields_compared': compared, 'matching_official_NA_fields': missing,
            'max_absolute_error': maximum, 'rows': len(actual) - 1,
            'axes_and_header_exact': True, 'node_sha256': digest(actual_file), 'reference_sha256': digest(expected_file),
            'byte_identical': actual_file.read_bytes() == expected_file.read_bytes()}


def run_case(name, fit_type, shrink, covariates, special='default'):
    directory = ROOT / ('author-' + name + ATTEMPT)
    directory.mkdir(exist_ok=False)
    for context in ['node', 'reference']:
        (directory / context).mkdir()
    levels = fixture(directory, special)
    alpha = .05 if special == 'alpha_05' else .1
    config = {'counts_path': '/case/counts.tsv', 'metadata_path': '/case/metadata.tsv',
              'output': '/case/reference', 'node_dataset': '/case/node/dataset.rds',
              'levels': levels, 'covariates': covariates, 'formula': '~ ' + ' + '.join([*covariates, 'condition']),
              'column_types': {name: 'numeric' if name == 'age' else 'factor' for name in covariates},
              'fit_type': fit_type, 'lfc_shrink': shrink, 'alpha': alpha, 'G0': False}
    (directory / 'reference-config.json').write_text(json.dumps(config, indent=2) + '\n')
    common = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=4g',
              '--userns=keep-id', '--mount', f'type=bind,src={directory},dst=/case',
              '--env', 'OMP_NUM_THREADS=1', '--env', 'OPENBLAS_NUM_THREADS=1', '--env', 'MKL_NUM_THREADS=1']
    environment = {'AUTONOMICS_INPUT0': '/case/counts.tsv', 'AUTONOMICS_INPUT1': '/case/metadata.tsv',
                   'AUTONOMICS_DESEQ2_CONDITION_REFERENCE': levels[0], 'AUTONOMICS_DESEQ2_CONDITION_TEST': levels[1],
                   'AUTONOMICS_DESEQ2_COVARIATES': ','.join(covariates), 'AUTONOMICS_DESEQ2_FIT_TYPE': fit_type,
                   'AUTONOMICS_DESEQ2_LFC_SHRINK': shrink, 'AUTONOMICS_DESEQ2_ALPHA': str(alpha), 'AUTONOMICS_DESEQ2_THREADS': '1'}
    environment.update({'AUTONOMICS_OUTPUT' + str(index): '/case/node/' + filename for index, filename in
                        enumerate(['results.tsv', 'normalized.tsv', 'size_factors.tsv', 'dataset.rds', 'report.json'])})
    command = common + ['--entrypoint', '/opt/autonomics/Rscript-vanilla']
    for key, value in environment.items():
        command += ['--env', key + '=' + value]
    execute(command + [IMAGE, '/opt/autonomics/deseq2_runner.R'], directory, 'baked-node')
    command = common + ['--mount', f'type=bind,src={Path(__file__).parent},dst=/proof,ro=true', '--mount', f'type=bind,src={LIBRARY},dst=/reference,ro=true', '--env', 'REFERENCE_LIBRARY=/reference',
                       '--env', 'REFERENCE_CONFIG=/case/reference-config.json', '--entrypoint', 'Rscript', IMAGE,
                       '--vanilla', '/proof/official_reference.R']
    execute(command, directory, 'fresh-official-reference')
    comparisons = {filename: compare_tables(directory / 'node' / filename, directory / 'reference' / filename)
                   for filename in ['results.tsv', 'normalized.tsv', 'size_factors.tsv']}
    report = json.loads((directory / 'node/report.json').read_text())
    identity = json.loads((directory / 'reference/reference-identity.json').read_text())
    for key in ['all_gene_ids', 'all_zero_gene_ids', 'pvalue_unavailable_gene_ids',
                'independent_filter_only_gene_ids', 'adjusted_pvalue_available_gene_ids']:
        if report['gene_ledger'][key] != identity[key]:
            raise RuntimeError('Official gene ledger differs: ' + key)
    if report['analysis']['node'] != 'deseq2_de' or report['analysis']['actual_dispersion_fit_type'] != identity['actual_fit_type']:
        raise RuntimeError('Node identity or actual dispersion branch differs')
    if report['analysis']['design'] != config['formula']:
        raise RuntimeError('Design report differs')
    for output_name, filename in [('results', 'results.tsv'), ('normalized_counts', 'normalized.tsv'),
                           ('size_factors', 'size_factors.tsv'), ('dataset', 'dataset.rds')]:
        if report['outputs'][output_name]['md5'] != hashlib.md5((directory / 'node' / filename).read_bytes()).hexdigest():
            raise RuntimeError('Report output digest differs')
    record = {'case': name, 'fit_type': fit_type, 'actual_fit_type': identity['actual_fit_type'],
              'lfc_shrink': shrink, 'covariates': covariates, 'special': special, 'comparisons': comparisons,
              'dataset_semantic_fields_compared': identity['dataset_semantic_fields_compared'],
              'all_gene_ledgers_match': True, 'status': 'PASS', 'G0': False}
    (directory / 'CHECKS.json').write_text(json.dumps(record, indent=2) + '\n')
    print(name, 'PASS', flush=True)
    return record


def main():
    cases = [(fit + '-' + shrink + ('-age' if covariates else '-no-covariate'), fit, shrink, covariates)
             for fit in ['parametric', 'local', 'mean'] for shrink in ['none', 'apeglm'] for covariates in [[], ['age']]]
    cases += [(special, 'mean', 'apeglm', ['batch', 'age'] if special == 'factor_numeric_covariates' else [], special)
              for special in ['literal_gene_ids', 'numeric_sample_ids', 'reordered_metadata', 'zero_genes',
                              'hyphen_levels', 'numeric_conditions', 'factor_numeric_covariates', 'alpha_05', 'exact_decimal_counts']]
    cases += [('pasilla-' + shrink, 'parametric', shrink, ['type'], 'pasilla') for shrink in ['none', 'apeglm']]
    cases += [(special, 'mean', 'apeglm', [], special) for special in ['reverse_contrast', 'unbalanced', 'cook_outlier']]
    records = [run_case(*case) for case in cases]
    (ROOT / ('AUTHOR_MATRIX' + ATTEMPT + '.json')).write_text(json.dumps({'status': 'PASS', 'case_count': len(records), 'cases': records,
        'validation_contract_sha256': digest(Path(__file__).parent / 'validation_contract.json'), 'image': IMAGE,
        'official_reference_independently_source_installed': True, 'shared_R_and_dependencies': True, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
