import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


parser = argparse.ArgumentParser()
parser.add_argument('--image', required=True)
parser.add_argument('--fixture', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
arguments = parser.parse_args()
root = arguments.evidence.resolve()
root.mkdir(exist_ok=False)
fixture = arguments.fixture.resolve(strict=True)
cases = ['ragged_long', 'ragged_short', 'duplicate_gene', 'empty_gene', 'duplicate_sample',
         'empty_sample', 'wrong_first_header', 'empty_input', 'header_only', 'blank_row',
         'embedded_nul', 'embedded_control', 'non_numeric', 'missing_value', 'nan', 'infinity',
         'overflow', 'invalid_network', 'invalid_cor', 'fractional_min_module', 'low_min_module',
         'overflow_min_module', 'fractional_deep_split', 'negative_deep_split', 'large_deep_split',
         'fractional_threads', 'zero_threads', 'overflow_threads', 'negative_seed', 'fractional_seed',
         'overflow_seed', 'fractional_block_size', 'small_block_size', 'overflow_block_size',
         'zero_merge', 'one_merge', 'nan_merge', 'negative_power', 'large_power', 'nan_power',
         'zero_power_cutoff', 'one_power_cutoff', 'negative_outlier_limit', 'large_outlier_limit',
         'automatic_power_unavailable', 'all_constant', 'one_sample', 'missing_input', 'input_directory',
         'missing_output', 'duplicate_output', 'aliased_output', 'existing_output', 'output_directory',
         'dangling_output', 'absent_output_parent', 'metadata_missing_sample', 'metadata_extra_sample',
         'metadata_duplicate_sample', 'metadata_wrong_header', 'metadata_collision', 'metadata_ragged']
(root / 'PREDECLARED_BOUNDARIES.json').write_text(json.dumps({'cases': cases, 'required_count': len(cases),
    'scope': 'Actual baked runner; metadata cases are legacy direct-script behavior, not a DAG port', 'G0': False}, indent=2) + '\n')
parameter_cases = {
    'invalid_network': ('NETWORK_TYPE', 'hybrid'), 'invalid_cor': ('COR', 'spearman'),
    'fractional_min_module': ('MIN_MODULE_SIZE', '5.5'), 'low_min_module': ('MIN_MODULE_SIZE', '4'),
    'overflow_min_module': ('MIN_MODULE_SIZE', '2147483648'), 'fractional_deep_split': ('DEEP_SPLIT', '2.5'),
    'negative_deep_split': ('DEEP_SPLIT', '-1'), 'large_deep_split': ('DEEP_SPLIT', '5'),
    'fractional_threads': ('THREADS', '1.5'), 'zero_threads': ('THREADS', '0'),
    'overflow_threads': ('THREADS', '2147483648'), 'negative_seed': ('SEED', '-1'),
    'fractional_seed': ('SEED', '1.5'), 'overflow_seed': ('SEED', '2147483648'),
    'fractional_block_size': ('MAX_BLOCK_SIZE', '500.5'), 'small_block_size': ('MAX_BLOCK_SIZE', '499'),
    'overflow_block_size': ('MAX_BLOCK_SIZE', '2147483648'), 'zero_merge': ('MERGE_THRESHOLD', '0'),
    'one_merge': ('MERGE_THRESHOLD', '1'), 'nan_merge': ('MERGE_THRESHOLD', 'NaN'),
    'negative_power': ('POWER', '-1'), 'large_power': ('POWER', '31'), 'nan_power': ('POWER', 'NaN'),
    'zero_power_cutoff': ('POWER_CUTOFF', '0'), 'one_power_cutoff': ('POWER_CUTOFF', '1'),
    'negative_outlier_limit': ('MAX_P_OUTLIERS', '-.1'), 'large_outlier_limit': ('MAX_P_OUTLIERS', '1.1'),
    'automatic_power_unavailable': ('POWER', '0')}
records = []
for name in cases:
    directory = root / name
    directory.mkdir()
    shutil.copyfile(fixture, directory / 'expression.tsv')
    rows = list(csv.reader(fixture.read_text().splitlines(), delimiter='\t'))
    environment = {'AUTONOMICS_INPUT0': '/case/expression.tsv', 'AUTONOMICS_WGCNA_POWER': '6',
                   'AUTONOMICS_WGCNA_MIN_MODULE_SIZE': '5', 'AUTONOMICS_WGCNA_MAX_BLOCK_SIZE': '500'}
    outputs = ['soft.tsv', 'adjacency.tsv', 'tom.tsv', 'modules.tsv', 'eigengenes.tsv', 'report.json']
    environment.update({f'AUTONOMICS_OUTPUT{index}': '/case/' + filename for index, filename in enumerate(outputs)})
    expected = 'input'
    if name in parameter_cases:
        parameter, value = parameter_cases[name]
        environment['AUTONOMICS_WGCNA_' + parameter] = value
        expected = 'official powerEstimate is unavailable' if name == 'automatic_power_unavailable' else (
            'network_type' if name == 'invalid_network' else 'cor must' if name == 'invalid_cor' else 'invalid scalar parameter')
    elif name.startswith('metadata_'):
        metadata = [['sample_id', 'group'], *[[sample, 'cohort'] for sample in rows[0][1:]]]
        if name == 'metadata_missing_sample': metadata.pop()
        if name == 'metadata_extra_sample': metadata.append(['EXTRA', 'cohort'])
        if name == 'metadata_duplicate_sample': metadata[-1][0] = metadata[1][0]
        if name == 'metadata_wrong_header': metadata[0][0] = 'donor'
        if name == 'metadata_collision': metadata[0][1] = 'ME1'
        if name == 'metadata_ragged': metadata[1].append('EXTRA')
        with (directory / 'metadata.tsv').open('w') as handle:
            csv.writer(handle, delimiter='\t', lineterminator='\n').writerows(metadata)
        environment['AUTONOMICS_INPUT1'] = '/case/metadata.tsv'
        expected = 'input rows must match' if name == 'metadata_ragged' else 'metadata'
    elif name == 'ragged_long': rows[1].append('0'); expected = 'header width'
    elif name == 'ragged_short': rows[1].pop(); expected = 'header width'
    elif name == 'duplicate_gene': rows[2][0] = rows[1][0]; expected = 'gene_id'
    elif name == 'empty_gene': rows[1][0] = ''; expected = 'gene_id'
    elif name == 'duplicate_sample': rows[0][2] = rows[0][1]; expected = 'headers'
    elif name == 'empty_sample': rows[0][1] = ''; expected = 'headers'
    elif name == 'wrong_first_header': rows[0][0] = 'genes'; expected = 'must start with gene_id'
    elif name == 'empty_input': rows = []; expected = 'header and nonempty'
    elif name == 'header_only': rows = rows[:1]; expected = 'header and nonempty'
    elif name == 'blank_row': rows.append([]); expected = 'header and nonempty'
    elif name == 'embedded_control': rows[1][0] = 'gene\x01'; expected = 'control'
    elif name in ['non_numeric', 'missing_value', 'nan', 'infinity', 'overflow']:
        rows[1][1] = {'non_numeric': 'abc', 'missing_value': 'NA', 'nan': 'NaN', 'infinity': 'Inf', 'overflow': '1e400'}[name]
        expected = 'expression values must be finite'
    elif name == 'all_constant':
        rows = [rows[0], *[[row[0], *(['1'] * (len(row) - 1))] for row in rows[1:]]]
        expected = 'Too few genes'
    elif name == 'one_sample': rows = [row[:2] for row in rows]; expected = 'at least two dimensions'
    elif name == 'missing_input': environment['AUTONOMICS_INPUT0'] = '/case/absent.tsv'; expected = 'existing regular file'
    elif name == 'input_directory': environment['AUTONOMICS_INPUT0'] = '/case'; expected = 'existing regular file'
    elif name == 'missing_output': del environment['AUTONOMICS_OUTPUT5']; expected = 'missing required environment'
    elif name in ['duplicate_output', 'aliased_output']:
        environment['AUTONOMICS_OUTPUT1'] = '/case/soft.tsv' if name == 'duplicate_output' else '/case/./soft.tsv'
        expected = 'output paths must be distinct'
    elif name == 'existing_output': (directory / 'soft.tsv').write_text('DO_NOT_OVERWRITE\n'); expected = 'existing outputs'
    elif name == 'output_directory': (directory / 'soft.tsv').mkdir(); expected = 'existing outputs'
    elif name == 'dangling_output': (directory / 'soft.tsv').symlink_to('/case/absent.tsv'); expected = 'existing outputs'
    elif name == 'absent_output_parent': environment['AUTONOMICS_OUTPUT5'] = '/case/absent/report.json'; expected = 'output parent'
    elif name != 'embedded_nul': raise RuntimeError('Unimplemented mandatory boundary: ' + name)
    with (directory / 'expression.tsv').open('w') as handle:
        csv.writer(handle, delimiter='\t', lineterminator='\n').writerows(rows)
    if name == 'embedded_nul':
        filename = directory / 'expression.tsv'
        filename.write_bytes(filename.read_bytes().replace(b'gene1\t', b'gene\x00one\t', 1))
        expected = 'embedded NUL'
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=4g',
               '--userns=keep-id', '--mount', f'type=bind,src={directory},dst=/case', '--entrypoint', 'Rscript']
    for key, value in environment.items(): command += ['--env', key + '=' + value]
    command += [arguments.image, '--vanilla', '/opt/autonomics/wgcna_runner.R']
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=300)
    (directory / 'stdout.txt').write_bytes(result.stdout)
    (directory / 'stderr.txt').write_bytes(result.stderr)
    record = {'case': name, 'command': command, 'exit': result.returncode, 'seconds': time.monotonic() - started,
              'expected_diagnostic': expected, 'G0': False}
    (directory / 'execution.json').write_text(json.dumps(record, indent=2) + '\n')
    if result.returncode == 0 or expected not in result.stderr.decode():
        raise RuntimeError(name + ' did not fail correctly: ' + result.stderr.decode())
    if name == 'existing_output' and (directory / 'soft.tsv').read_text() != 'DO_NOT_OVERWRITE\n':
        raise RuntimeError('Preexisting result changed')
    preserved = {'soft.tsv'} if name in ['existing_output', 'output_directory', 'dangling_output'] else set()
    if any((directory / filename).exists() or (directory / filename).is_symlink()
           for filename in set(outputs) - preserved):
        raise RuntimeError('Rejected case published partial analytical outputs: ' + name)
    record['status'] = 'PASS'
    record['failure_diagnostics'] = [filename.name for filename in directory.glob('wgcna-failure-*.rds')]
    records.append(record)
    print(name, 'correct refusal PASS', flush=True)
if len(records) != len(cases): raise RuntimeError('Mandatory boundary census incomplete')
(root / 'BOUNDARY_RESULTS.json').write_text(json.dumps({'records': records, 'count': len(records), 'zero_skips': True, 'G0': False}, indent=2) + '\n')
