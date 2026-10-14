"""Verify current-engine missing-edge and unknown-parameter UCell preflight refusals."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_generic_plugin_guards import sealed


def exact_cause(name, messages):
    if name == 'unknown-parameter':
        return 'node `h5ad_ucell_score`: unknown param `unexpected_free_parameter`' in messages
    if name == 'missing-input-edge':
        return 'PortDisconnected { node: "analysis", port: 0 }' in messages
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--reference-session', required=True)
    parser.add_argument('--reference-seal', required=True)
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    reference = sealed(arguments.archives, arguments.reference_session, arguments.reference_seal, 'ucell-current-dag')
    build = json.loads(arguments.build_record.read_text())
    if build['actual_build_exit'] != 0 or digest(arguments.runner) != build['executable_sha256']:
        raise RuntimeError('Exact current generic probe required')
    runner = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build['executable_sha256']:
        raise RuntimeError('Owned executable copy differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-graph-controls'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    source = output / 'source'
    shutil.copytree(reference / 'source/ucell-h5ad', source)
    template = json.loads((reference / 'dense/job.json').read_text())
    records = []
    for name in ['unknown-parameter', 'missing-input-edge']:
        work = output / name
        work.mkdir()
        shutil.copyfile(reference / 'dense/input.h5ad', work / 'input.h5ad')
        job = copy.deepcopy(template)
        job.update(run_root=str(work), plugin_manifest=str(source / 'manifest.toml'))
        if name == 'unknown-parameter':
            job['nodes'][-1]['spec']['unexpected_free_parameter'] = 1
        else:
            job['edges'] = []
        write(work / 'job.json', job)
        completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=90)
        (work / 'runner.stdout').write_text(completed.stdout)
        (work / 'runner.stderr').write_text(completed.stderr)
        if (completed.returncode != 1 or not exact_cause(name, completed.stderr)
                or (work / 'dag-report.json').exists()
                or any(list((work / 'artifacts').rglob(filename)) for filename in ['output.h5ad', 'report.json'])):
            raise RuntimeError('Exact UCell graph preflight cause not enforced: ' + name)
        records.append(dict(case=name, exit_code=1, exact_cause_verified=True, DAG_execution_not_entered=True))
    write(output / 'verification.json', dict(status='CURRENT_UCELL_GRAPH_PREFLIGHT_CONTROLS_ENFORCED',
          engine_commit=build['engine_commit'], source_session=arguments.reference_session,
          source_manifest_sha256=arguments.reference_seal, cases=records, g0_granted=False))
    print('EXACT_PREFLIGHT_CONTROLS=2 G0=false')


if __name__ == '__main__':
    main()
