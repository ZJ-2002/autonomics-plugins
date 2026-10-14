"""Official-source reference and declared-port DAG validation for the repaired TSV adapter."""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports, digest, write
from tools.prove_ldsc_precision_dag import check_inputs
from tools.prove_ucell_current_dag import reference


ROOT = Path(__file__).resolve().parents[1]


def configurations():
    cases = []
    for name, rank, weight, missing in [('main', 1500, 1, 'impute'), ('rank1000', 1000, 1, 'impute'),
        ('rank2000', 2000, 1, 'impute'), ('skip', 1500, 1, 'skip'), ('weight0', 1500, 0, 'impute'),
        ('weight-half', 1500, .5, 'impute'), ('weight2', 1500, 2, 'impute'), ('skip-weight2', 1500, 2, 'skip'),
        ('reordered-genes', 1500, 1, 'impute'), ('reordered-cells', 1500, 1, 'impute'),
        ('up-only', 1500, 1, 'impute'), ('negative-only', 1500, 1, 'impute')]:
        cases.append(dict(name=name, parameters=dict(max_rank=rank, negative_weight=weight, missing_genes=missing)))
    return cases


def fixture(work, name):
    genes = ['NA', '0001', *[f'G{index:04d}' for index in range(1, 2009)]]
    cells = ['0001', 'NA', '炎症', 'C4']
    rows = [[gene, str(2010 - index), str(index), str(index % 7), str(index % 2)] for index, gene in enumerate(genes)]
    if name == 'reordered-genes':
        rows.reverse()
    if name == 'reordered-cells':
        cells.reverse()
        rows = [[row[0], *reversed(row[1:])] for row in rows]
    features = {'positive': ['G0010', 'G1000', 'G1500'], 'signed': ['G0001+', 'G2000-'],
                'negative': ['G2000-'], 'partial': ['G0002', 'ABSENT'], 'NA': ['NA', '0001']}
    if name == 'up-only':
        features = {'positive': features['positive']}
    if name == 'negative-only':
        features = {'negative': features['negative']}
    with (work / 'matrix.tsv').open('x', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(['gene', *cells])
        writer.writerows(rows)
    with (work / 'signatures.tsv').open('x', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(['signature', 'gene'])
        writer.writerows([signature, gene] for signature, members in features.items() for gene in members)


def job_for(work, source, parameters):
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', expected_plugin_name='cachexia-ucell', run_root=str(work),
        plugin_manifest=str(source / 'manifest.toml'), plugin_manifest_sha256=digest(source / 'manifest.toml'),
        script_sha256={'scripts/ucell.R': digest(source / 'scripts/ucell.R')}, bundles=[], panel_overrides=[], panel_manifest_sha256={},
        nodes=[dict(id='input0', kind='file_reference', spec=dict(path='vfs:///matrix.tsv', format='tsv')),
               dict(id='input1', kind='file_reference', spec=dict(path='vfs:///signatures.tsv', format='tsv')),
               dict(id='analysis', kind='cachexia_ucell_official', spec=parameters)],
        edges=[{'from': 'input0', 'to': 'analysis', 'from_port': 0, 'to_port': 0},
               {'from': 'input1', 'to': 'analysis', 'from_port': 0, 'to_port': 1}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--author-packet', type=Path, required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    reference(arguments.author_packet)
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact current engine required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']:
        raise RuntimeError('Owned executable copy differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(arguments.build_record, output / 'build-record.json')
    shutil.copyfile(ROOT / 'tools/ucell_tsv_reference.R', output / 'reference.R')
    source = output / 'source'
    (source / 'scripts').mkdir(parents=True)
    for filename in ['manifest.toml', 'scripts/ucell.R']:
        shutil.copyfile(ROOT / 'plugins/ucell' / filename, source / filename)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    image = manifest['image']['reference']
    cases = configurations()
    for case in cases:
        work = output / case['name']
        work.mkdir()
        fixture(work, case['name'])
    write(output / 'positive-cases.json', cases)
    def author(mode):
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g',
            '--userns=keep-id', '--tmpfs=/tmp:rw,size=64m', '-v', str(output) + ':/work:rw',
            '-v', str(arguments.author_packet / 'fresh-author-R') + ':/author:ro', '--entrypoint=Rscript',
            image, '--vanilla', '/work/reference.R', mode, '/work', '/author']
        completed = subprocess.run(command, capture_output=True, timeout=180)
        (output / (mode + '.stdout')).write_bytes(completed.stdout)
        (output / (mode + '.stderr')).write_bytes(completed.stderr)
        if completed.returncode or (mode.upper() + ' CASES 12').encode() not in completed.stdout:
            raise RuntimeError('Fresh-source official reference/readback failed: ' + mode)
    author('reference')
    records = []
    for case in cases:
        name = case['name']
        work = output / name
        job = job_for(work, source, case['parameters'])
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=180)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        report = json.loads((work / 'dag-report.json').read_text())
        if (completed.returncode or report['engine_source_revision'] != build['engine_commit']
                or report['native_statistical_factories_registered'] is not False
                or report['input_hashing'] != 'ContentRequired' or report['incremental'] is not False
                or report['max_concurrency'] != 1 or report['plugin_name'] != 'cachexia-ucell'
                or report['original_manifest_sha256'] != job['plugin_manifest_sha256']
                or report['scope'] != job['scope'] or report['g0_granted'] is not False
                or report['first_run']['errors'] or len(report['first_run']['nodes']) != 3
                or any(node['status'] != 'success' for node in report['first_run']['nodes'])):
            raise RuntimeError('Actual current official TSV UCell graph failed: ' + name)
        analysis = next(node for node in report['first_run']['nodes'] if node['id'] == 'analysis')
        if analysis['execution']['image'] != image:
            raise RuntimeError('Actual UCell image differs')
        scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / name
        inputs = check_inputs(work, [work / 'matrix.tsv', work / 'signatures.tsv'], analysis, scratch)
        ports = check_ports(work, manifest['nodes'][0], analysis, scratch)
        for index, filename in enumerate(['ucell_scores.tsv', 'ucell.RDS', 'ucell.log', 'audit.json']):
            shutil.copyfile(ports[index], work / filename)
        records.append(dict(case=name, parameters=case['parameters'], nodes=3, edges=2,
                            input_bindings=inputs, published_ports=4))
        (output / 'completed-cases.json').write_text(json.dumps(records, indent=2) + '\n')
        print(name, 'DAG_PASS', flush=True)
    author('compare')
    write(output / 'verification.json', dict(status='REPAIRED_TSV_UCELL_OFFICIAL_OBJECTS_CURRENT_DAG_PROVEN_SCOPED',
        engine_commit=build['engine_commit'], executable_sha256=build['executable_sha256'], cases=records,
        independent_reference='direct API in rehashed fresh raw author-source UCell namespace; shared frozen runtime/dependencies',
        exact_complete_RDS_objects=12, namespace='/author/UCell', method_source_sha256=digest(source / 'scripts/ucell.R'),
        container_image=image, daemon_or_scientific_admission_granted=False, g0_granted=False))
    print('CURRENT_OFFICIAL_DAGS=12 INPUT_BINDINGS=24 PUBLISHED_PORTS=48 G0=false')


if __name__ == '__main__':
    main()
