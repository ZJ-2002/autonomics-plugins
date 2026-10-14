"""Check actual TSV UCell method failure and graph preflight refusal without fallback."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_ucell_tsv_dag import configurations, fixture, job_for, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact current engine required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']:
        raise RuntimeError('Owned executable differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-graph-failures'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    source = output / 'source'
    (source / 'scripts').mkdir(parents=True)
    for filename in ['manifest.toml', 'scripts/ucell.R']:
        shutil.copyfile(ROOT / 'plugins/ucell' / filename, source / filename)
    records = []
    for name in ['invalid-policy', 'unknown-parameter', 'missing-signature-edge']:
        work = output / name
        work.mkdir()
        fixture(work, 'main')
        job = job_for(work, source, configurations()[0]['parameters'])
        if name == 'invalid-policy': job['nodes'][-1]['spec']['missing_genes'] = 'invalid'
        elif name == 'unknown-parameter': job['nodes'][-1]['spec']['unexpected_free_parameter'] = 1
        else: job['edges'] = [edge for edge in job['edges'] if edge['to_port'] != 1]
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=120)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        if name == 'invalid-policy':
            report = json.loads((work / 'dag-report.json').read_text())
            analysis = next(node for node in report['first_run']['nodes'] if node['id'] == 'analysis')
            scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / name
            logs = list(scratch.rglob('ucell.log'))
            if (report['engine_source_revision'] != build['engine_commit']
                    or report['native_statistical_factories_registered'] is not False
                    or not report['first_run']['errors'] or analysis['status'] != 'failed'
                    or analysis['execution']['exit_code'] != 2 or len(logs) != 1
                    or 'BLOCKED: Frozen UCell parameters invalid' not in logs[0].read_text()
                    or any(list(scratch.rglob(filename)) for filename in ['ucell_scores.tsv', 'ucell.RDS', 'audit.json'])
                    or any(list((work / 'artifacts').rglob(filename)) for filename in ['ucell_scores.tsv', 'ucell.RDS', 'audit.json'])):
                raise RuntimeError('Exact method failure/no normal result propagation failed')
            shutil.copyfile(logs[0], work / 'preserved-failure.log')
        else:
            cause = ('node `cachexia_ucell_official`: unknown param `unexpected_free_parameter`' if name == 'unknown-parameter'
                     else 'PortDisconnected { node: "analysis", port: 1 }')
            if completed.returncode != 1 or cause not in completed.stderr or (work / 'dag-report.json').exists():
                raise RuntimeError('Exact graph preflight cause missing')
        records.append(dict(case=name, exact_refusal=True, normal_result_absent=True, kernel_fallback_used=False))
    write(output / 'verification.json', dict(status='TSV_UCELL_DAG_FAILURES_AND_GRAPH_GUARDS_ENFORCED',
        engine_commit=build['engine_commit'], cases=records,
        method_source_sha256=digest(source / 'scripts/ucell.R'), g0_granted=False))
    print('METHOD_DAG_FAILURES=1 GRAPH_PREFLIGHT_REFUSALS=2 G0=false')


if __name__ == '__main__':
    main()
