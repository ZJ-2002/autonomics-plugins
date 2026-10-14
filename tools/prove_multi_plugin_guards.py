"""Actual multi-manifest identity refusals and a failed-producer dependency control."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_bulk_current_chain import job_for, ROOT
from tools.prove_generic_plugin_guards import sealed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--archives', type=Path, required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ: raise RuntimeError('Managed validation required')
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact actual compiler artifact required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']: raise RuntimeError('Owned executable differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'multi-plugin-guards'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    negative = sealed(arguments.archives, '8e7ea5f5a7ab48ac8acff5c2c15e0031',
        '0c9697fb969218877f9bfa9306ef483549f424b1ae4b268e5cc0bd4673aa3656', 'pseudobulk-boundaries')
    families = {}
    for name, family in [('aggregate', 'pseudobulk'), ('deseq2', 'deseq2'), ('limma', 'bulk-rnaseq')]:
        destination = output / 'source' / family
        destination.mkdir(parents=True)
        manifest = tomllib.loads((ROOT / 'plugins' / family / 'manifest.toml').read_text())
        for filename in ['manifest.toml', *{node['command']['script_file'] for node in manifest['nodes']}]:
            path = destination / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'plugins' / family / filename, path)
        families[name] = destination
    cases = [('extra-manifest-hash', 'additional canonical manifest bytes differ'),
        ('extra-name', 'additional plugin identity empty, repeated or mismatched'),
        ('repeated-plugin', 'additional plugin identity empty, repeated or mismatched'),
        ('duplicate-kind', 'duplicate method kind across plugin manifests'),
        ('engineering-collision', 'additional plugin cannot replace an engineering factory'),
        ('extra-script-hash', 'actual dispatched script differs'),
        ('extra-script-traversal', 'nonlocal script path forbidden'),
        ('extra-panel-mapping', 'additional plugins with panels are not supported by this technical probe'),
        ('additional-array-type', 'additional plugins must be an explicit array')]
    records = []
    for name, message in cases:
        work = output / name
        work.mkdir()
        job = job_for(work, families)
        extra = job['additional_plugins'][0]
        if name == 'extra-manifest-hash': extra['plugin_manifest_sha256'] = '0' * 64
        elif name == 'extra-name': extra['expected_plugin_name'] = 'wrong-plugin'
        elif name == 'repeated-plugin': job['additional_plugins'].append(copy.deepcopy(extra))
        elif name == 'extra-script-hash': extra['script_sha256']['deseq2_runner.R'] = '0' * 64
        elif name == 'extra-panel-mapping': extra['panel_overrides'] = [{}]
        elif name == 'additional-array-type': job['additional_plugins'] = {}
        else:
            modified = work / 'modified-source'
            shutil.copytree(families['deseq2'], modified)
            path = modified / 'manifest.toml'
            text = path.read_text()
            if name == 'duplicate-kind': text = text.replace('kind = "deseq2_de"', 'kind = "pseudobulk_counts"')
            elif name == 'engineering-collision': text = text.replace('kind = "deseq2_de"', 'kind = "file_reference"')
            else: text = text.replace('script_file = "deseq2_runner.R"', 'script_file = "../outside.R"')
            path.write_text(text)
            extra.update(plugin_manifest=str(path), plugin_manifest_sha256=digest(path))
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=90)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        if completed.returncode != 1 or message not in completed.stderr or (work / 'dag-report.json').exists() or (work / 'artifacts').exists():
            raise RuntimeError('Exact multi-plugin preflight refusal missing: ' + name)
        records.append(dict(case=name, exact_message=message, exit_code=1, DAG_not_entered=True))
    work = output / 'failed-producer'
    work.mkdir()
    shutil.copyfile(negative / 'runs/cases/nan/input.h5ad', work / 'input.h5ad')
    job = job_for(work, families)
    write(work / 'job.json', job)
    completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=120)
    (work / 'runner.stdout').write_text(completed.stdout)
    (work / 'runner.stderr').write_text(completed.stderr)
    report = json.loads((work / 'dag-report.json').read_text())
    nodes = {node['id']: node for node in report['first_run']['nodes']}
    if (report['engine_source_revision'] != build['engine_commit'] or not report['first_run']['errors']
            or nodes['aggregate']['status'] != 'failed' or nodes['aggregate']['execution']['exit_code'] != 2
            or any(nodes[name]['status'] == 'success' or nodes[name].get('execution') is not None for name in ['deseq2', 'limma'])
            or any(path.name in ['results.tsv', 'pseudobulk_counts.tsv', 'pseudobulk_samples.tsv'] for path in (work / 'artifacts').rglob('*'))):
        raise RuntimeError('Failed producer incorrectly released dependent analyses')
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces/failed-producer'
    logs = list(scratch.rglob('stderr.log'))
    messages = '\n'.join(path.read_text() for path in logs)
    if 'non-finite (NaN/Inf)' not in messages: raise RuntimeError('Actual invalid-count cause missing')
    (work / 'preserved-producer.stderr').write_text(messages)
    write(output / 'verification.json', dict(status='MULTI_PLUGIN_EXACT_GUARDS_AND_FAILED_PRODUCER_ENFORCED',
        engine_commit=build['engine_commit'], preflight_cases=records, failed_producer=dict(
            actual_exit=2, normal_result_absent=True, both_downstream_methods_not_executed=True), g0_granted=False))
    print('EXACT_MULTI_GUARDS=9 FAILED_PRODUCER_BLOCKS_BOTH_METHODS=true G0=false')


if __name__ == '__main__': main()
