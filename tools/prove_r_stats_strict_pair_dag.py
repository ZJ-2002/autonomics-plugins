"""Two isolated toy DAGs for the explicit complete-pair policy; no study release."""

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
COMPONENT = '018cae74e5924304982b881b64a4d006'
COMPONENT_SEAL = '89b2715e3163603ec2421d810b6757c73580911511e30b1663210df96a69ebb1'
BUILD = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
MANIFEST_SHA = '4f939a87463c0c35edb767a654e0256dcc6a397377b8420df552e70b0aaebcae'
SCRIPT_SHA = 'b9b8259ed0d4cc91c9227c955893c018687ec5bb4dca7ed4c7e86e11cde85684'
ADAPTER_SHA = 'd73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194'
IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(filename):
    with Path(filename).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(filename, value):
    with filename.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def rows(filename):
    with filename.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        fields = reader.fieldnames
        data = list(reader)
    require(fields and len(fields) == len(set(fields)) and all(
        set(row) == set(fields) and all(value is not None for value in row.values()) for row in data),
        'Complete rectangular TSV required')
    return data


def guarded_launcher(program, prefix, scratch, creates):
    constants = dict(PROGRAM=program, PREFIX=prefix, SCRATCH=str(scratch), CREATES=str(creates), IMAGE=IMAGE, SCRIPT=SCRIPT_SHA)
    return '#!/usr/bin/python3\n' + '\n'.join(key + '=' + repr(value) for key, value in constants.items()) + '''
import hashlib,json,os,sys
from pathlib import Path
arguments=sys.argv[1:]
if not arguments or arguments[0].startswith('-'): raise SystemExit('Unexpected backend entry')
if arguments[0]=='create':
 if arguments.count(IMAGE)!=1 or arguments[arguments.index('--pull')+1]!='never': raise SystemExit('Image/pull mismatch')
 environment={arguments[index+1].split('=',1)[0]:arguments[index+1].split('=',1)[1] for index,value in enumerate(arguments[:-1]) if value=='--env'}
 mounts={}
 for index,value in enumerate(arguments[:-1]):
  if value=='--mount':
   fields=dict(part.split('=',1) for part in arguments[index+1].split(',') if '=' in part)
   mounts[fields.get('destination')]=Path(fields['source'])
 workspace=mounts['/work']
 if workspace.resolve()!=workspace or not workspace.is_relative_to(Path(SCRATCH)): raise SystemExit('Unowned workspace')
 if hashlib.sha256((workspace/'.autonomics/script').read_bytes()).hexdigest()!=SCRIPT: raise SystemExit('Executed source mismatch')
 if environment.get('AUTONOMICS_INPUT_COUNT')!='2' or environment.get('AUTONOMICS_OUTPUT_COUNT')!='5' or environment.get('STATISTICS_OPERATION')!='t': raise SystemExit('Method or ports mismatch')
 with open(CREATES,'a') as handle: handle.write(json.dumps({'workspace':str(workspace),'operation':'t'})+'\\n')
os.execv(PROGRAM,PREFIX+arguments)
'''


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('AUTONOMICS_PODMAN_PROGRAM'),
            'Managed validation session required')
    sys.path.insert(0, str(ROOT))
    from tools import prove_current_r_stats as graph
    from tools import prove_frozen_a_harmonisation_dag as admission
    from tools.prove_frozen_a_family_runtime import stopped
    from tools.reconcile_ab_evidence_index import verify_archive
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'r-stats-strict-pair-sdk'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    checked = verify_archive(ARCHIVES, COMPONENT, COMPONENT_SEAL)
    require(checked['positive_worker_exit_verified'], 'Successful sealed component proof required')
    fixture = ARCHIVES / COMPONENT / 'artifacts/permanent/r-stats-strict-pair-contract'
    proof = json.loads((fixture / 'verification.json').read_text())
    require(proof['candidate_pair_contract_verified'] and proof['candidate_source_sha256'] == SCRIPT_SHA
            and proof['candidate_cases_passed'] == 10, 'Exact proven intake policy required')
    temporary = Path(os.environ['TMPDIR'])
    source = output / 'source'
    for filename, expected in [('manifest.toml', MANIFEST_SHA), ('scripts/statistics.R', SCRIPT_SHA)]:
        original = ROOT / 'plugins/r-stats' / filename
        require(sha(original) == expected, 'Candidate differs from component proof')
        destination = source / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
    definition = tomllib.loads((source / 'manifest.toml').read_text())
    require(definition['plugin_name'] == 'r-stats' and definition['image']['reference'] == IMAGE, 'Pinned family/image differs')
    build_root = ARCHIVES / BUILD / 'artifacts/permanent/locked-b-probe-build'
    build, receipt = admission.checked_build(ARCHIVES, build_root / 'official_plugin_dag',
                                           build_root / 'build-record.json', BUILD_SEAL)
    runner, runner_identity = admission.executable_copy(build_root / 'official_plugin_dag', temporary)
    write(output / 'retained-build-receipt.json', receipt)
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    require(IMAGE in profile['images'], 'Exact image is not operator-qualified')
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile.update(images=[IMAGE], delegate=dict(path=str(delegate), sha256=sha(delegate)))
    profile_path = output / 'managed-readonly-image-profile.json'
    write(profile_path, profile)
    profile_path.chmod(0o600)
    adapter = Path.home() / '.local/lib/autonomics/qualified-podman' / ADAPTER_SHA / 'podman'
    require(sha(adapter) == ADAPTER_SHA, 'Qualified adapter source changed')
    primary = profile['primary']
    backend = ['--root', primary['graphroot'], '--runroot', primary['runroot'],
               '--tmpdir', str(Path(primary['runroot']) / 'libpod-tmp'),
               '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
    prefix = [str(adapter), *backend]
    environment = dict(os.environ, AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(profile_path),
                       TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2')
    inspect = subprocess.run([*prefix, 'image', 'inspect', '--format',
        '{"Id":{{json .ID}},"Digest":{{json .Digest}},"RepoDigests":{{json .RepoDigests}}}', IMAGE],
        capture_output=True, env=environment, timeout=60)
    write(output / 'image-inspect-exit.json', dict(actual_exit=inspect.returncode))
    require(inspect.returncode == 0, 'Qualified exact image unavailable; no pull or substitute')
    image = json.loads(inspect.stdout)
    require(image['Id'].removeprefix('sha256:') == '294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c'
            and (image['Digest'] == IMAGE.split('@', 1)[1] or IMAGE in image['RepoDigests']), 'Image identity differs')
    write(output / 'filtered-image-identity.json', image)
    scratch = temporary / 'official-plugin-container-workspaces'
    guard_dir = temporary / 'strict-pair-guard'
    guard_dir.mkdir()
    launcher = guard_dir / 'podman'
    launcher.write_text(guarded_launcher(str(adapter), prefix, scratch, output / 'actual-creates.jsonl'))
    launcher.chmod(0o700)
    compile(launcher.read_text(), str(launcher), 'exec')
    environment['PATH'] = str(guard_dir) + os.pathsep + environment.get('PATH', '/usr/bin:/bin')
    results = []
    try:
        for name, negative in [('strict-complete', False), ('strict-incomplete', True)]:
            work = output / name
            work.mkdir()
            expected = fixture / 'after' / name
            shutil.copyfile(expected / 'input.tsv', work / 'input0.tsv')
            shutil.copyfile(expected / 'contract.tsv', work / 'input1.tsv')
            expected_rows = [] if negative else rows(expected / 'statistics.tsv')
            identifiers = [row['test_id'] for row in expected_rows]
            case = dict(id=name, operation='t', negative='true' if negative else 'false')
            job = graph.make_job(work, source, case, identifiers)
            for node in job['nodes']:
                if node['kind'] == 'file_reference':
                    node['spec']['hash_content'] = True
            next(node for node in job['nodes'] if node['id'] == 'analysis')['kind'] = 't_test'
            job.update(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', expected_plugin_name='r-stats',
                plugin_manifest_sha256=MANIFEST_SHA, script_sha256={'scripts/statistics.R': SCRIPT_SHA},
                additional_plugins=[], bundles=[], panel_overrides=[], panel_manifest_sha256={})
            write(work / 'job.json', job)
            run = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, timeout=600,
                env=dict(environment, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
            (work / 'runner.stdout').write_bytes(run.stdout)
            (work / 'runner.stderr').write_bytes(run.stderr)
            require(run.returncode == 0 and (work / 'dag-report.json').is_file(), 'SDK failed before a complete report')
            report = json.loads((work / 'dag-report.json').read_text())
            require(report['engine_source_revision'] == build['engine_commit'] and report['scope'] == job['scope']
                    and report['input_hashing'] == 'ContentRequired' and report['incremental'] is False
                    and report['native_statistical_factories_registered'] is False and report['g0_granted'] is False,
                    'SDK identity or execution discipline differs')
            nodes = {node['id']: node for node in report['first_run']['nodes']}
            require(set(nodes) == {node['id'] for node in job['nodes']} and len(job['edges']) == 7, 'Eight-node graph is incomplete')
            creations = [json.loads(line) for line in (output / 'actual-creates.jsonl').read_text().splitlines()]
            require(len(creations) == len(results) + 1, 'Exactly one owned method container per DAG required')
            workspace = Path(creations[-1]['workspace'])
            require(workspace.is_relative_to(scratch), 'Container output outside owned scratch')
            actual = work / 'actual'
            actual.mkdir()
            for product in next(node for node in definition['nodes'] if node['kind'] == 't_test')['ports']['outputs']:
                filename = workspace / product['path']
                if filename.is_file():
                    shutil.copyfile(filename, actual / product['path'])
            if negative:
                require(nodes['analysis']['status'] == 'failed' and not nodes['analysis'].get('port_assignments')
                        and all(nodes[key]['status'] == 'skipped' for key in ['raw_read', 'raw_write', 'typed', 'typed_read', 'sink'])
                        and not (work / 'materialized.tsv').exists(), 'Missing pairs escaped failure propagation')
                require('Incomplete frozen pair; no official test executed' in (actual / 'audit.tsv').read_text()
                        and not any((actual / filename).exists() for filename in ['statistics.tsv', 'parameters.tsv', 'statistics.RDS']),
                        'Expected specific missing-pair refusal without analytical products')
            else:
                require(report['first_run']['ok'] and all(node['status'] == 'success' for node in nodes.values()), 'Positive DAG failed')
                require(set(nodes['analysis']['port_assignments']) == set(map(str, range(5))), 'Five output ports required')
                for filename in ('statistics.tsv', 'parameters.tsv'):
                    require((actual / filename).read_bytes() == (expected / filename).read_bytes(), 'Complete scalar/parameter output changed')
                graph.compare_rows(rows(work / 'materialized.tsv'), expected_rows, 't')
                readback = subprocess.run(['Rscript', '--vanilla', '-e',
                    'args<-commandArgs(TRUE);stopifnot(identical(readRDS(args[1]),readRDS(args[2])));cat("COMPLETE_RDS_IDENTICAL\\n")',
                    str(actual / 'statistics.RDS'), str(expected / 'statistics.RDS')], capture_output=True, timeout=60)
                (work / 'RDS-readback.stdout').write_bytes(readback.stdout)
                (work / 'RDS-readback.stderr').write_bytes(readback.stderr)
                require(readback.returncode == 0 and b'COMPLETE_RDS_IDENTICAL' in readback.stdout, 'Complete existing RDS reference differs')
            results.append(dict(case=name, negative=negative, nodes=8, edges=7,
                                all_normal_outputs_and_materialization_verified=not negative,
                                specific_missing_pair_failure_and_five_skips_verified=negative))
    finally:
        inventory = permanent / 'container-intents.json'
        if inventory.exists():
            count = len(json.loads(inventory.read_text())['intents'])
            stopped([str(delegate), '--storage-opt', 'additionalimagestore=' + profile['additional']['path'], *backend],
                    permanent, output, count)
    require(len(results) == 2 and sha(runner) == runner_identity['sha256']
            and sha(ROOT / 'plugins/r-stats/manifest.toml') == MANIFEST_SHA
            and sha(ROOT / 'plugins/r-stats/scripts/statistics.R') == SCRIPT_SHA, 'Coverage or fixed source identity changed')
    result = dict(schema='R_STATS_STRICT_PAIR_TWO_ISOLATED_DAGS_V1', passed=True, cases=results,
        positive_DAGs=1, refusal_DAGs=1, actual_method_containers=2,
        retained_SDK_source=build['engine_commit'], retained_SDK_build_session=BUILD, retained_SDK_build_seal=BUILD_SEAL,
        component_fixture_session=COMPONENT, component_fixture_seal=COMPONENT_SEAL,
        no_new_independent_oracle_or_168_case_suite=True, new_Cargo_builds=0,
        current_resident_engine_equivalence_assumed=False, production_installed=False,
        whole_B_SPEC_or_complete_family_certified=False, scientific_data_fits=0,
        new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    write(output / 'verification.json', result)
    print(json.dumps(dict(passed=True, positive_DAGs=1, refusal_DAGs=1, resident_deployed=False, g0_granted=False)))


if __name__ == '__main__':
    main()
