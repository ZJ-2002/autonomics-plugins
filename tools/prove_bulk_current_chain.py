"""Requalify the three-family raw-count chain on the current engine with sealed author oracles."""

import argparse
import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports, digest, write


ROOT = Path(__file__).resolve().parents[1]
MERGED = 'quoted-tsv-merged-integration-agent-v1-20261012'
MERGED_SEAL = '81f1bdac6d4833b8597fbfc0e9ce5f542b256a6589bd76137bf769b60ea90038'
FULL = 'canonical-r-output-publication-full-agent-v1-20261012'
FULL_SEAL = '0baff3edbfd25b6ddf0e19eb8c53bf61e01ceec72d6118195092fc3174d6efe1'


def checked_packet(root, identity, post_seal=None):
    if digest(root / 'SEALED_FILES.json') != identity:
        raise RuntimeError('Exact preexisting proof seal required')
    seal = json.loads((root / 'SEALED_FILES.json').read_text())
    files = {record['path']: record for record in seal['files']}
    links = {record['path']: record for record in seal['internal_links']}
    faults = {record['path']: record for record in seal.get('intentional_fault_links', [])}
    extra = {'SEALED_FILES.json'}
    if post_seal:
        if digest(root / 'ROOT_POST_SEAL_VERIFICATION.json') != post_seal:
            raise RuntimeError('Exact post-seal record required')
        extra.add('ROOT_POST_SEAL_VERIFICATION.json')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    if actual != set(files) | set(links) | set(faults) | extra:
        raise RuntimeError('Complete preexisting proof membership differs')
    for name, record in files.items():
        path = root / name
        if path.is_symlink() or path.stat().st_size != record['size'] or digest(path) != record['sha256']:
            raise RuntimeError('Sealed inherited file differs')
    for name, record in links.items():
        path = root / name
        target = root / record['resolved_path']
        if (not path.is_symlink() or os.readlink(path) != record['target']
                or path.resolve() != target.resolve() or not path.resolve().is_relative_to(root.resolve())
                or digest(path) != record['sha256']):
            raise RuntimeError('Sealed internal reference differs')
    for name, record in faults.items():
        path = root / name
        if not path.is_symlink() or os.readlink(path) != record['target']:
            raise RuntimeError('Declared owned negative symlink fixture differs')
    return dict(files=len(files), internal_links=len(links), intentional_fault_links=len(faults), seal_sha256=identity)


def references(base):
    merged = base / MERGED
    full = base / FULL
    receipts = [checked_packet(merged, MERGED_SEAL, 'd1cd2d46daad7e38c9635e05ae6ed9fc4c6e5a7cd7b47d0798b7c691cbf1f831'),
                checked_packet(full, FULL_SEAL)]
    fixtures = base / 'quoted-tsv-integration-v1-20261012/fixtures-v2'
    payloads = json.loads((merged / 'INHERITED_FIXTURE_PAYLOADS.json').read_text())['root_fixture_and_author_payload_census']
    for record in payloads:
        path = Path(record['path'])
        if (not path.is_relative_to(fixtures) or path.is_symlink() or path.stat().st_size != record['size']
                or digest(path) != record['sha256']):
            raise RuntimeError('Original decoded/author fixture differs')
    actual = {str(path) for path in fixtures.rglob('*') if path.is_file()}
    if actual != {record['path'] for record in payloads}:
        raise RuntimeError('Complete decoded/author fixture membership differs')
    for kind, filename in [('aggregate', 'canonical-pseudobulk-counts-io-closure-v2-20261012.json'),
                           ('deseq2', 'canonical-deseq2-de-io-closure-v2-20261012.json'),
                           ('limma', 'canonical-limma-voom-io-closure-v2-20261012.json')]:
        source = json.loads((full / filename).read_text())['source']
        if digest(ROOT / source['path']) != source['sha256']:
            raise RuntimeError('Current method differs from the requalified producer/consumer source: ' + kind)
    return fixtures, full, receipts, len(payloads)


def plugin_spec(source):
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    scripts = {node['command']['script_file'] for node in manifest['nodes']}
    return dict(plugin_manifest=str(source / 'manifest.toml'), expected_plugin_name=manifest['plugin_name'],
                plugin_manifest_sha256=digest(source / 'manifest.toml'),
                script_sha256={name: digest(source / name) for name in scripts}, panel_overrides=[])


def job_for(work, families):
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', run_root=str(work), **plugin_spec(families['aggregate']),
        bundles=[], panel_manifest_sha256={}, additional_plugins=[plugin_spec(families[name]) for name in ['deseq2', 'limma']],
        nodes=[dict(id='input', kind='file_reference', spec=dict(path='vfs:///input.h5ad', format='h5ad')),
            dict(id='aggregate', kind='pseudobulk_counts', spec=dict(sample_col='donor', celltype_col='celltype', condition_column='condition', min_cells=1)),
            dict(id='deseq2', kind='deseq2_de', spec=dict(condition_reference='ctrl', condition_test='case', fit_type='mean', lfc_shrink='none')),
            dict(id='limma', kind='limma_voom', spec=dict(outcome_var='condition', contrast_var='condition', contrast_levels='ctrl,case', normalization='tmm'))],
        edges=[{'from': 'input', 'to': 'aggregate', 'from_port': 0, 'to_port': 0},
               *[{'from': 'aggregate', 'to': name, 'from_port': index, 'to_port': index} for name in ['deseq2', 'limma'] for index in [0, 1]]])


def table(path):
    with path.open(newline='') as handle:
        return list(csv.reader(handle, delimiter='\t', strict=True))


def numeric_table(actual, expected, tolerance):
    left, right = table(actual), table(expected)
    if not left or left[0] != right[0] or len(left) != len(right):
        raise RuntimeError('Complete author table shape/header differs')
    checked = 0
    maximum = 0.0
    for observed, baseline in zip(left[1:], right[1:]):
        if len(observed) != len(left[0]) or len(observed) != len(baseline) or observed[0] != baseline[0]:
            raise RuntimeError('Author table ID, order or width differs')
        for value, target in zip(observed[1:], baseline[1:]):
            if value == 'NA' or target == 'NA':
                if value != target: raise RuntimeError('Exact author missing mask differs')
                continue
            number, expected_number = float(value), float(target)
            difference = abs(number - expected_number)
            if not math.isfinite(number) or not math.isfinite(expected_number) or difference > tolerance + tolerance * abs(expected_number):
                raise RuntimeError('Unrounded official numeric field differs')
            maximum = max(maximum, difference)
            checked += 1
    return dict(rows=len(left)-1, finite_fields=checked, max_absolute_error=maximum, atol=tolerance, rtol=tolerance)


def bound_inputs(analysis, originals, source_node, scratch, workspace):
    bindings = analysis['inputs']
    if len(bindings) != len(originals): raise RuntimeError('Complete source input inventory required')
    for index, original in enumerate(originals):
        binding = next(record for record in bindings if record['to_port'] == index)
        suffix = ''.join(original.suffixes)
        paths = [path for path in workspace.rglob('input-' + str(index) + suffix)
                 if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        if (binding['from'] != source_node or binding['from_port'] != index or len(paths) != 1
                or binding['fingerprint']['size'] != original.stat().st_size
                or not (paths[0].resolve().is_relative_to(scratch) or paths[0].resolve() == original.resolve())
                or digest(paths[0]) != digest(original)):
            raise RuntimeError('Actual upstream artifact bytes/edge differ')
    return len(bindings)


def normalized_report(report, input_files, output_files):
    result = copy.deepcopy(report)
    if set(result['inputs']) != set(input_files) or set(result['outputs']) != set(output_files):
        raise RuntimeError('Complete report file identity schema differs')
    for field, files in [('inputs', input_files), ('outputs', output_files)]:
        for label, path in files.items():
            record = result[field][label]
            if set(record) != {'path', 'md5'} or Path(record['path']).name != record['path']:
                raise RuntimeError('Report file identity record differs')
            if record['md5'] != hashlib.md5(path.read_bytes()).hexdigest():
                raise RuntimeError('Report digest does not identify the actual file')
            record.update(path='VERIFIED_DECLARED_FILE_' + label, md5='ACTUAL_FILE_MD5_VERIFIED')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--packets', type=Path, required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ: raise RuntimeError('Managed validation required')
    fixtures, full, reference_receipts, payloads = references(arguments.packets)
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact current multi-manifest compiler output required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']: raise RuntimeError('Owned executable differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'bulk-current-chain'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(arguments.build_record, output / 'build-record.json')
    families = {}
    manifests = {}
    for name, family in [('aggregate', 'pseudobulk'), ('deseq2', 'deseq2'), ('limma', 'bulk-rnaseq')]:
        destination = output / 'source' / family
        destination.mkdir(parents=True)
        manifest = tomllib.loads((ROOT / 'plugins' / family / 'manifest.toml').read_text())
        for relative in ['manifest.toml', *{node['command']['script_file'] for node in manifest['nodes']}]:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'plugins' / family / relative, target)
        families[name] = destination
        manifests[name] = manifest
    records = []
    readback = dict(tables=[], datasets=[])
    for name in ['simple-identities', 'quoted-identities']:
        work = output / name
        work.mkdir()
        original = fixtures / name
        shutil.copyfile(original / 'input.h5ad', work / 'input.h5ad')
        shutil.copyfile(original / 'decoded-oracle.json', work / 'decoded-oracle.json')
        job = job_for(work, families)
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=600)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        report = json.loads((work / 'dag-report.json').read_text())
        if (completed.returncode or report['engine_source_revision'] != build['engine_commit']
                or report['native_statistical_factories_registered'] is not False or report['first_run']['errors']
                or len(report['first_run']['nodes']) != 4 or any(node['status'] != 'success' for node in report['first_run']['nodes'])
                or report['input_hashing'] != 'ContentRequired' or report['max_concurrency'] != 1 or report['incremental'] is not False
                or report['original_manifest_sha256'] != job['plugin_manifest_sha256'] or report['g0_granted'] is not False
                or {record['plugin_name'] for record in report['additional_plugin_identities']} != {'deseq2', 'bulk-rnaseq'}):
            raise RuntimeError('Actual complete three-family graph failed')
        for identity in report['additional_plugin_identities']:
            expected = next(item for item in job['additional_plugins'] if item['expected_plugin_name'] == identity['plugin_name'])
            if identity['original_manifest_sha256'] != expected['plugin_manifest_sha256'] or identity['script_sha256'] != expected['script_sha256']:
                raise RuntimeError('Actual extra family identity differs')
        nodes = {node['id']: node for node in report['first_run']['nodes']}
        scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / name
        ports = {}
        for identifier in ['aggregate', 'deseq2', 'limma']:
            if nodes[identifier]['execution']['image'] != manifests[identifier]['image']['reference']:
                raise RuntimeError('Actual dispatched family image differs')
            definition = next(node for node in manifests[identifier]['nodes'] if node['kind'] == nodes[identifier]['node_type'])
            ports[identifier] = check_ports(work, definition, nodes[identifier], scratch)
        aggregate_workspace = Path(nodes['aggregate']['port_assignments']['0']['path']).parent
        if bound_inputs(nodes['aggregate'], [work / 'input.h5ad'], 'input', scratch, aggregate_workspace) != 1:
            raise RuntimeError('Raw H5AD input not bound')
        for identifier in ['deseq2', 'limma']:
            workspace = Path(nodes[identifier]['port_assignments']['0']['path']).parent
            bound_inputs(nodes[identifier], ports['aggregate'][:2], 'aggregate', scratch, workspace)
        if table(ports['aggregate'][0]) != table(original / 'counts.tsv') or table(ports['aggregate'][1]) != table(original / 'metadata.tsv'):
            raise RuntimeError('Complete donor counts or metadata differs from decoded oracle fixture')
        comparisons = []
        for identifier in ['deseq2', 'limma']:
            names = ['results.tsv', 'normalized.tsv', 'size_factors.tsv'] if identifier == 'deseq2' else ['results.tsv', 'weights.tsv', 'normalized.tsv']
            for index, filename in enumerate(names):
                comparisons.append(dict(node=identifier, port=index, **numeric_table(ports[identifier][index], original / (identifier + '-reference') / filename, 1e-10 if identifier == 'deseq2' else 1e-12)))
            expected_root = full / 'fixtures' / name / (identifier + '-node')
            current_inputs = dict(count_matrix=ports['aggregate'][0], sample_metadata=ports['aggregate'][1])
            expected_inputs = dict(count_matrix=expected_root.parent / 'counts.tsv', sample_metadata=expected_root.parent / 'metadata.tsv')
            labels = ['results', 'normalized_counts', 'size_factors', 'dataset'] if identifier == 'deseq2' else ['results', 'weights', 'normalized', 'contrast_summary']
            old_names = ['results.tsv', 'normalized.tsv', 'size_factors.tsv', 'dataset.rds'] if identifier == 'deseq2' else ['results.tsv', 'weights.tsv', 'normalized.tsv', 'contrasts.tsv']
            current_report = normalized_report(json.loads(ports[identifier][4].read_text()), current_inputs, dict(zip(labels, ports[identifier][:4])))
            old_report = normalized_report(json.loads((expected_root / 'report.json').read_text()), expected_inputs, dict(zip(labels, [expected_root / filename for filename in old_names])))
            if json.dumps(current_report, sort_keys=True, allow_nan=False) != json.dumps(old_report, sort_keys=True, allow_nan=False):
                raise RuntimeError('Complete diagnostics/report semantics differ: ' + identifier)
            if identifier == 'limma' and table(ports[identifier][3]) != table(expected_root / 'contrasts.tsv'):
                raise RuntimeError('Exact contrast ledger differs')
        for identifier, paths in ports.items():
            target = work / identifier
            target.mkdir()
            for index, path in enumerate(paths):
                shutil.copyfile(path, target / path.name)
                if path.suffix == '.tsv':
                    rows = table(path)
                    readback['tables'].append(dict(container_path='/work/' + str((target / path.name).relative_to(output)), header=rows[0], rows=rows[1:]))
            if identifier == 'deseq2':
                shutil.copyfile(original / 'deseq2-reference/dataset.rds', target / 'author-dataset.rds')
                readback['datasets'].append(dict(node_path='/work/' + str((target / paths[3].name).relative_to(output)),
                    reference_path='/work/' + str((target / 'author-dataset.rds').relative_to(output))))
        records.append(dict(case=name, nodes=4, edges=5, input_bindings=5, published_ports=13,
            exact_donor_counts_metadata_and_full_reports=True, numerical_comparisons=comparisons))
        (output / 'completed-cases.json').write_text(json.dumps(records, indent=2) + '\n')
        print(name, 'CURRENT_CHAIN_PASS', flush=True)
    write(output / 'readback-input.json', readback)
    shutil.copyfile(arguments.packets / MERGED / 'readback_R.R', output / 'readback.R')
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g',
        '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-v', str(output) + ':/work:rw', '--entrypoint=Rscript',
        manifests['deseq2']['image']['reference'], '--vanilla', '/work/readback.R', '/work']
    completed = subprocess.run(command, capture_output=True, timeout=180)
    (output / 'readback.stdout').write_bytes(completed.stdout)
    (output / 'readback.stderr').write_bytes(completed.stderr)
    if completed.returncode: raise RuntimeError('Independent R table/DDS semantic readback failed')
    write(output / 'verification.json', dict(status='CURRENT_THREE_FAMILY_COUNTS_DESEQ2_LIMMA_CHAIN_PROVEN_SCOPED',
        engine_commit=build['engine_commit'], executable_sha256=build['executable_sha256'], cases=records,
        reference_receipts=reference_receipts, inherited_fixture_payloads_rehashed=payloads,
        independent_author_reference_recomputed=False, pure_scipy_count_aggregation_not_claimed_as_scanpy_execution=True,
        RDS_scope='All DESeq2 assays, row/column identities, colData, model matrix, size factors, mcols and dispersion fit type; not every environment/slot',
        actual_study_or_resident_daemon_qualified=False, g0_granted=False))
    print('CURRENT_THREE_FAMILY_DAGS=2 LIVE_PUBLISHED_PORTS=26 G0=false')


if __name__ == '__main__':
    main()
