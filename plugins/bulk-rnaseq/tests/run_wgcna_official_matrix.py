import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time


parser = argparse.ArgumentParser()
parser.add_argument('--image', required=True)
parser.add_argument('--reference-library', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--smoke', action='store_true')
arguments = parser.parse_args()
root = arguments.evidence.resolve()
root.mkdir(exist_ok=False)
reference = arguments.reference_library.resolve(strict=True)
tests = Path(__file__).resolve().parent
defaults = {'network_type': 'signed', 'cor': 'pearson', 'min_module_size': 5, 'deep_split': 2,
            'merge_threshold': .25, 'max_block_size': 500, 'threads': 1, 'power': 6,
            'power_cutoff': .85, 'max_p_outliers': 1, 'seed': 54321}
cases = [('smoke', {}, 'literal')]
if not arguments.smoke:
    cases = [(f'{network}-{cor}-split{split}', {'network_type': network, 'cor': cor, 'deep_split': split}, 'base')
             for network in ['signed', 'unsigned'] for cor in ['pearson', 'bicor'] for split in range(5)]
    cases += [('literal_ids', {}, 'literal'), ('qc_constant_gene', {}, 'constant'),
              ('reordered_genes', {}, 'reverse_genes'), ('reordered_samples', {}, 'reverse_samples'),
              ('multiblock', {}, 'multiblock'), ('threads2', {'threads': 2}, 'base'),
              ('fractional_fixed_power', {'power': 6.5}, 'base'), ('seed42', {'seed': 42}, 'multiblock'),
              ('minimum_module30', {'min_module_size': 30}, 'base'),
              ('merge_01', {'merge_threshold': .1}, 'base'), ('merge_06', {'merge_threshold': .6}, 'base'),
              ('bicor_outliers005', {'cor': 'bicor', 'max_p_outliers': .05}, 'outliers'),
              ('bicor_outliers01', {'cor': 'bicor', 'max_p_outliers': .1}, 'outliers'),
              ('bicor_outliers0', {'cor': 'bicor', 'max_p_outliers': 0}, 'outliers'),
              ('official_auto_signed', {'power': 0, 'power_cutoff': .1}, 'base'),
              ('official_auto_unsigned', {'power': 0, 'power_cutoff': .1, 'network_type': 'unsigned'}, 'base')]
manifest = {'cases': [name for name, changes, fixture in cases], 'required_count': len(cases),
            'image': arguments.image, 'tolerance': {'absolute': 1e-10, 'relative': 1e-10},
            'full_adjacency_and_TOM': 'exact SHA256 of serialized full numeric vectors', 'G0': False}
(root / 'PREDECLARED_MATRIX.json').write_text(json.dumps(manifest, indent=2) + '\n')
records = []
for name, changes, fixture in cases:
    directory = root / name
    directory.mkdir()
    request = defaults | changes
    (directory / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
    generator = random.Random(410612)
    samples = ['sample' + str(index + 1) for index in range(30)]
    latent = [[generator.gauss(0, 1) for sample in samples] for module in range(3)]
    rows = []
    for index in range(600 if fixture == 'multiblock' else 180):
        gene = str(index + 1).zfill(5) if fixture == 'literal' else 'gene' + str(index + 1)
        if fixture == 'literal' and index == 1:
            gene = 'NA'
        profile = [7 + latent[index % 3][sample_index] * generator.uniform(.7, 1.1) + generator.gauss(0, .2)
                   for sample_index in range(30)]
        if fixture == 'constant' and index == 0:
            profile = [7] * 30
        if fixture == 'outliers' and index % 4 == 0:
            profile[0] += 20
        rows.append([gene, *[format(value, '.17g') for value in profile]])
    if fixture == 'reverse_genes':
        rows.reverse()
    if fixture == 'reverse_samples':
        samples.reverse()
        rows = [[row[0], *reversed(row[1:])] for row in rows]
    with (directory / 'expression.tsv').open('w') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(['gene_id', *samples])
        writer.writerows(rows)
    common = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--cpus=2', '--memory=4g',
              '--userns=keep-id', '--mount', f'type=bind,src={directory},dst=/case', '--entrypoint', 'Rscript']
    environment = {f'AUTONOMICS_WGCNA_{key.upper()}': str(value) for key, value in request.items()}
    environment['AUTONOMICS_INPUT0'] = '/case/expression.tsv'
    outputs = ['soft.tsv', 'adjacency.tsv', 'tom.tsv', 'modules.tsv', 'eigengenes.tsv', 'report.json']
    environment.update({f'AUTONOMICS_OUTPUT{index}': '/case/' + filename for index, filename in enumerate(outputs)})
    node_command = common.copy()
    for key, value in environment.items():
        node_command += ['--env', key + '=' + value]
    node_command += [arguments.image, '--vanilla', '/opt/autonomics/wgcna_runner.R']
    author_command = common + ['--mount', f'type=bind,src={reference},dst=/reference,ro=true',
        '--mount', f'type=bind,src={tests},dst=/tests,ro=true', '--env', 'WGCNA_REFERENCE_LIBRARY=/reference',
        arguments.image, '--vanilla', '/tests/wgcna_official_reference.R']
    comparison_command = common + ['--mount', f'type=bind,src={tests},dst=/tests,ro=true',
        arguments.image, '--vanilla', '/tests/wgcna_compare_official.R']
    for phase, command in [('baked-runner', node_command), ('fresh-author', author_command), ('comparison', comparison_command)]:
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, timeout=600)
        (directory / (phase + '.stdout.txt')).write_bytes(result.stdout)
        (directory / (phase + '.stderr.txt')).write_bytes(result.stderr)
        (directory / (phase + '.execution.json')).write_text(json.dumps({'command': command,
            'exit': result.returncode, 'seconds': time.monotonic() - started}, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(f'{name} {phase} failed: ' + result.stderr.decode())
    record = json.loads((directory / 'comparison.json').read_text())
    record['case'] = name
    record['output_sha256'] = {filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
                               for filename in outputs}
    records.append(record)
    print(name, 'fresh official reference PASS', flush=True)
if len(records) != manifest['required_count'] or any(record['status'] != 'PASS' for record in records):
    raise RuntimeError('Mandatory case census is incomplete')
(root / 'OFFICIAL_MATRIX_RESULTS.json').write_text(json.dumps({'records': records, 'required_count': len(cases),
    'executed_count': len(records), 'zero_skips': True, 'G0': False}, indent=2) + '\n')
