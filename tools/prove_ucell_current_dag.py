"""Replay the complete sealed UCell H5AD inventory on the current generic engine."""

import argparse
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
from tools.prove_generic_plugin_guards import sealed


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SEAL = '633c610ae6e69e203b63d07d13d2fdc6c68a928b2b21cf458803ab261b08cd7d'
FINAL_SEAL = '8f7efb82e743a09f0eaf9d46e1cfa4cb07dbabcffcfb5f1020e239bfb6af2d26'
DIRECT = {'h5ad-exists', 'report-exists', 'dangling-output', 'output-alias', 'input-overwrite', 'second-link-failure', 'R-failure'}


def reference(root):
    if digest(root / 'SEALED_FILES.json') != REFERENCE_SEAL or digest(root / 'FINAL_VERIFICATION.json') != FINAL_SEAL:
        raise RuntimeError('Exact original UCell evidence seal required')
    seal = json.loads((root / 'SEALED_FILES.json').read_text())
    records = {record['path']: record for record in seal['files']}
    links = {record['path']: record for record in seal['internal_links']}
    negative_links = {record['path']: record for record in seal['declared_negative_fixture_links']}
    if seal['undeclared_external_data_links'] or len(records) != 1901:
        raise RuntimeError('Original sealed membership differs')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    if actual != set(records) | set(links) | set(negative_links) | {'SEALED_FILES.json', 'FINAL_VERIFICATION.json'}:
        raise RuntimeError('Complete original membership required')
    for name, record in records.items():
        source = root / name
        if source.is_symlink() or source.stat().st_size != record['size'] or digest(source) != record['sha256']:
            raise RuntimeError('Sealed official UCell evidence differs')
    for name, record in links.items():
        source = root / name
        if not source.is_symlink() or source.resolve() != (root / record['target']).resolve() or digest(source) != record['sha256']:
            raise RuntimeError('Original internal reference differs')
    for name, record in negative_links.items():
        source = root / name
        if not source.is_symlink() or os.readlink(source) != record['target'] or source.exists():
            raise RuntimeError('Original intentional dangling fixture differs')
    evidence = json.loads((ROOT / 'evidence/canonical-h5ad-ucell-v1-20261012.json').read_text())
    for name, identity in [('manifest.toml', 'manifest_sha256'), ('scripts/score.py', 'script_sha256')]:
        if 'sha256:' + digest(ROOT / 'plugins/ucell-h5ad' / name) != evidence['implementation'][identity]:
            raise RuntimeError('Current UCell adapter differs from qualified reference')
    positives = json.loads((root / 'repaired-official-v1/SUMMARY.json').read_text())['records']
    negatives = json.loads((root / 'repaired-boundaries-v1/SUMMARY.json').read_text())['records']
    if len(positives) != 20 or len(negatives) != 34:
        raise RuntimeError('Complete 20 positive / 34 refusal inventory required')
    return [record['case'] for record in positives], [record['case'] for record in negatives]


def settings_for(name, original):
    programs = json.loads((original / 'request.json').read_text())
    overrides = {'empty-programs': {}, 'empty-signature': {'one': []}, 'numeric-member': {'one': [1]},
                 'empty-name': {'': ['A']}, 'score-collision': {'donor': ['A']},
                 'ambiguous-sign': {'one': ['A+', 'A-']}, 'no-overlap': {'one': ['ABSENT']},
                 'over-maxrank': {'one': ['A', *[f'absent-{index}' for index in range(12)]]},
                 'undefined-official-score': {'one': ['A']}}
    if name in overrides:
        programs = overrides[name]
    if name == 'missing-gene-sets':
        return {}
    value = 'not JSON' if name == 'malformed-json' else '{"one":["A"],"one":["B"]}' if name == 'duplicate-json-key' else json.dumps(programs, ensure_ascii=False)
    return {'gene_sets': value}


def job_for(work, source, settings):
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', expected_plugin_name='ucell-h5ad',
        run_root=str(work), plugin_manifest=str(source / 'manifest.toml'),
        plugin_manifest_sha256=digest(source / 'manifest.toml'),
        script_sha256={'scripts/score.py': digest(source / 'scripts/score.py')},
        bundles=[], panel_overrides=[], panel_manifest_sha256={},
        nodes=[dict(id='input0', kind='file_reference', spec=dict(path='vfs:///input.h5ad', format='h5ad')),
               dict(id='analysis', kind='h5ad_ucell_score', spec=settings)],
        edges=[{'from': 'input0', 'to': 'analysis', 'from_port': 0, 'to_port': 0}])


def expected_error(original):
    lines = [line for line in (original / 'declared-node-script.stderr.txt').read_text().splitlines() if line.startswith('h5ad_ucell_score: ')]
    if len(lines) != 1:
        raise RuntimeError('Exact frozen UCell diagnostic required')
    return lines[0].split('existing output: ')[0].rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--finish-session')
    parser.add_argument('--finish-seal')
    parser.add_argument('--archives', type=Path)
    arguments = parser.parse_args()
    if any([arguments.finish_session, arguments.finish_seal, arguments.archives]) and not all([
            arguments.finish_session, arguments.finish_seal, arguments.archives]):
        raise RuntimeError('Finishing a sealed DAG stage requires session, seal and archive root')
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    positives, negatives = reference(arguments.reference)
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact current generic probe required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']:
        raise RuntimeError('Owned executable copy differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-current-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(arguments.build_record, output / 'build-record.json')
    source = output / 'source/ucell-h5ad'
    (source / 'scripts').mkdir(parents=True)
    for name in ['manifest.toml', 'scripts/score.py']:
        shutil.copyfile(ROOT / 'plugins/ucell-h5ad' / name, source / name)
    comparison_source = output / 'source/single-cell/tests'
    comparison_source.mkdir(parents=True)
    shutil.copyfile(ROOT / 'plugins/single-cell/tests/qc_compare.py', comparison_source / 'qc_compare.py')
    shutil.copyfile(ROOT / 'tools/verify_ucell_current_h5ad.py', output / 'verify_ucell_current_h5ad.py')
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    image = manifest['image']['reference']
    definition = manifest['nodes'][0]
    records = []
    dag_output = output
    inventory = positives + [name for name in negatives if name not in DIRECT]
    if arguments.finish_session:
        dag_output = sealed(arguments.archives, arguments.finish_session, arguments.finish_seal, 'ucell-current-dag')
        records = json.loads((dag_output / 'completed-cases.json').read_text())
        if len(records) != 47 or {record['case'] for record in records} != set(inventory):
            raise RuntimeError('Complete unchanged DAG stage required')
        for name in ['manifest.toml', 'scripts/score.py']:
            if digest(dag_output / 'source/ucell-h5ad' / name) != digest(source / name):
                raise RuntimeError('Resumed method source differs from actual DAG stage')
        for record in records:
            name = record['case']
            if name == 'missing-gene-sets':
                if 'node `h5ad_ucell_score`: missing required param `gene_sets`' not in (dag_output / name / 'runner.stderr').read_text():
                    raise RuntimeError('Exact required parameter refusal missing')
                continue
            report = json.loads((dag_output / name / 'dag-report.json').read_text())
            if report['engine_source_revision'] != build['engine_commit'] or report['native_statistical_factories_registered'] is not False:
                raise RuntimeError('Actual sealed DAG engine differs')
            analysis = next(node for node in report['first_run']['nodes'] if node['id'] == 'analysis')
            if record['positive'] != (analysis['status'] == 'success') or record['positive'] != (name in positives):
                raise RuntimeError('Actual DAG outcome differs from recorded method case')
        inventory = []
    for name in inventory:
        positive = name in positives
        original = arguments.reference / ('repaired-official-v1' if positive else 'repaired-boundaries-v1') / name
        work = output / name
        work.mkdir()
        shutil.copyfile(original / 'input.h5ad', work / 'input.h5ad')
        shutil.copyfile(original / 'request.json', work / 'request.json')
        job = job_for(work, source, settings_for(name, original))
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=240)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        if name == 'missing-gene-sets':
            if (completed.returncode != 1
                    or 'node `h5ad_ucell_score`: missing required param `gene_sets`' not in completed.stderr
                    or (work / 'dag-report.json').exists()):
                raise RuntimeError('Missing required parameter did not fail before execution')
            record = dict(case=name, route='GRAPH_PREFLIGHT', explicit_refusal=True, normal_result_absent=True)
        else:
            report = json.loads((work / 'dag-report.json').read_text())
            if (report['engine_source_revision'] != build['engine_commit'] or report['plugin_name'] != 'ucell-h5ad'
                    or report['original_manifest_sha256'] != job['plugin_manifest_sha256']
                    or report['scope'] != job['scope'] or report['g0_granted'] is not False
                    or report['input_hashing'] != 'ContentRequired' or report['incremental'] is not False
                    or report['max_concurrency'] != 1 or report['native_statistical_factories_registered'] is not False):
                raise RuntimeError('Current-engine identity/scope differs')
            first = report['first_run']
            if len(first['nodes']) != 2 or {node['id'] for node in first['nodes']} != {'input0', 'analysis'}:
                raise RuntimeError('Complete actual two-node graph required')
            analysis = next(node for node in first['nodes'] if node['id'] == 'analysis')
            scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / name
            inputs = check_inputs(work, [original / 'input.h5ad'], analysis, scratch)
            if analysis['execution']['image'] != image:
                raise RuntimeError('Actual official UCell image differs')
            record = dict(case=name, route='DAG', positive=positive, nodes=2, edges=1, input_bindings=inputs)
            if positive:
                if completed.returncode or first['errors'] or any(node['status'] != 'success' for node in first['nodes']):
                    raise RuntimeError('Valid current UCell graph failed: ' + name)
                ports = check_ports(work, definition, analysis, scratch)
                for index, filename in enumerate(['output.h5ad', 'report.json']):
                    shutil.copyfile(ports[index], work / filename)
                for filename in ['fresh-author.h5ad', 'author-scores.tsv']:
                    shutil.copyfile(original / filename, work / filename)
                shutil.copyfile(original / 'report.json', work / 'sealed-report.json')
                record['published_ports'] = 2
            else:
                logs = list(scratch.rglob('stderr.log'))
                messages = '\n'.join(path.read_text() for path in logs)
                if (not first['errors'] or analysis['status'] != 'failed' or analysis['execution']['exit_code'] != 2
                        or expected_error(original) not in messages
                        or any(list(scratch.rglob(filename)) for filename in ['output.h5ad', 'report.json'])
                        or any(list((work / 'artifacts').rglob(filename)) for filename in ['output.h5ad', 'report.json'])):
                    raise RuntimeError('Exact UCell refusal/no-publication failed: ' + name)
                (work / 'preserved-method.stderr').write_text(messages)
                record.update(explicit_refusal=True, normal_result_absent=True, published_ports=0)
        records.append(record)
        (output / 'completed-cases.json').write_text(json.dumps(records, indent=2) + '\n')
        print(name, 'PASS', flush=True)
    write(output / 'positive-cases.json', positives)
    compare_command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g', '--userns=keep-id',
        '--tmpfs=/tmp:rw,size=64m', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(output) + ':/work:rw',
        '-v', str(dag_output) + ':/reference:ro', '--entrypoint=python', image,
        '/work/verify_ucell_current_h5ad.py', '/reference', '--output', '/work/whole-object-readback.json']
    compared = subprocess.run(compare_command, capture_output=True, timeout=180)
    (output / 'comparison.stdout').write_bytes(compared.stdout)
    (output / 'comparison.stderr').write_bytes(compared.stderr)
    if compared.returncode or b'VERIFIED_COMPLETE_H5AD_CASES 20' not in compared.stdout:
        raise RuntimeError('Complete frozen-author H5AD/report readback failed')
    direct_records = []
    for name in sorted(DIRECT):
        original = arguments.reference / 'repaired-boundaries-v1' / name
        work = output / name
        work.mkdir()
        shutil.copyfile(original / 'input.h5ad', work / 'input.h5ad')
        variables = ['-e', 'AUTONOMICS_INPUT0=/work/input.h5ad', '-e', 'AUTONOMICS_OUTPUT0=/work/output.h5ad',
                     '-e', 'AUTONOMICS_OUTPUT1=/work/report.json', '-e', 'SC_P_JSON_GENE_SETS=' + settings_for(name, original)['gene_sets']]
        sentinel = work / ('report.json' if name == 'report-exists' else 'output.h5ad')
        if name in ['h5ad-exists', 'report-exists']:
            sentinel.write_bytes((original / sentinel.name).read_bytes())
        elif name == 'dangling-output':
            sentinel.symlink_to('absent.h5ad')
        if name == 'output-alias':
            variables[5] = 'AUTONOMICS_OUTPUT1=/work/output.h5ad'
        elif name == 'input-overwrite':
            variables[3] = 'AUTONOMICS_OUTPUT0=/work/input.h5ad'
        original_command = json.loads((original / 'declared-node-script.execution.json').read_text())['command']
        if name in ['second-link-failure', 'R-failure']:
            code = original_command[2].replace('/source/ucell-h5ad/scripts/score.py', '/program.py')
            (work / 'fault-injection.py').write_text(code + '\n')
            invocation = ['/work/fault-injection.py']
        else:
            invocation = ['/program.py']
        before = digest(work / 'input.h5ad')
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g', '--userns=keep-id',
                   '--tmpfs=/tmp:rw,size=64m', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(work) + ':/work:rw',
                   '-v', str(source / 'scripts/score.py') + ':/program.py:ro', '--entrypoint=python', *variables, image, *invocation]
        completed = subprocess.run(command, capture_output=True, timeout=120)
        (work / 'direct.stdout').write_bytes(completed.stdout)
        (work / 'direct.stderr').write_bytes(completed.stderr)
        expected_exit = json.loads((original / 'declared-node-script.execution.json').read_text())['exit']
        if completed.returncode != expected_exit or expected_error(original) not in completed.stderr.decode() or digest(work / 'input.h5ad') != before:
            raise RuntimeError('Exact direct UCell boundary failed: ' + name)
        for filename in ['output.h5ad', 'report.json']:
            path = work / filename
            if path == sentinel and name in ['h5ad-exists', 'report-exists']:
                if digest(path) != digest(original / filename):
                    raise RuntimeError('Existing sentinel changed')
            elif path == sentinel and name == 'dangling-output':
                if not path.is_symlink() or os.readlink(path) != 'absent.h5ad' or path.exists():
                    raise RuntimeError('Intentional dangling sentinel changed')
                path.unlink()
                write(work / 'dangling-fixture-receipt.json', dict(original_target='absent.h5ad', unchanged=True, owned_fixture_unlinked_for_archive=True))
            elif path.exists():
                raise RuntimeError('Direct refusal left a normal output')
        if list(work.glob('.ucell-*')):
            raise RuntimeError('Direct refusal left staging debris')
        direct_records.append(dict(case=name, exact_refusal=True, input_unchanged=True, not_a_DAG_case=True, exit_code=completed.returncode))
        (output / 'direct-cases.json').write_text(json.dumps(direct_records, indent=2) + '\n')
        print(name, 'DIRECT_PASS', flush=True)
    write(output / 'verification.json', dict(status='CURRENT_UCELL_H5AD_DAG_AND_COMPLETE_AUTHOR_OBJECTS_PROVEN_SCOPED',
        engine_commit=build['engine_commit'], executable_sha256=build['executable_sha256'], original_cases=54,
        DAG_cases=records, direct_cases=direct_records, author_reference_recomputed=False,
        sealed_DAG_stage_session=arguments.finish_session, sealed_DAG_stage_manifest_sha256=arguments.finish_seal,
        DAGs_recomputed_in_finish_session=False if arguments.finish_session else None,
        source_reference_seal=REFERENCE_SEAL, daemon_or_scientific_admission_granted=False, g0_granted=False))
    print('COMPLETE_ORIGINAL_INVENTORY=54 G0=false', flush=True)


if __name__ == '__main__':
    main()
