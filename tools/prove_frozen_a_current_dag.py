"""Run synthetic frozen-A six-node DAGs against a sealed official-method oracle."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_opentargets_direct_files import sealed_archive
from tools.prove_bulk_current_chain import plugin_spec
from tools.prove_current_ldsc import check_ports, digest, write


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/twosamplemr-v432-a'
BUILD_SESSION = 'f7e02ba49c024ceca6b934b4a123f751'
BUILD_SEAL = '431dd1cdf0ea5c2ea66ce98621354b65ebdac356d03d081ee71045b0c81d4caf'
ORACLE_SESSION = 'ae8a6659b7b74833b0d3b55b73e3fed0'
ORACLE_SEAL = 'a0fa6fb68487c7d2fbba7f0945a96e1313c3acfe3ec4adbab104a4b1b50cb65a'
ENGINE = '4ceefbd821baab8deebb070645a2fb8b1fa8e1ba'
EXECUTABLE = 'bbc1a387b508ba05c50e79eb95b3dc15f87cf274a6e2c3983bcd320246339481'
KIND = 'twosamplemr_v432_a_exploratory'
INPUTS = ['input.tsv', 'config.json', 'certificate.json', 'lock.tsv', 'proof.json']


def job_for(work, family):
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', run_root=str(work), **plugin_spec(family),
        bundles=[], panel_manifest_sha256={}, additional_plugins=[],
        nodes=[*[dict(id='input'+str(index), kind='file_reference',
            spec=dict(path='vfs:///'+name, format='tsv' if name.endswith('.tsv') else 'json'))
            for index, name in enumerate(INPUTS)], dict(id='analysis', kind=KIND, spec={})],
        edges=[{'from': 'input'+str(index), 'to': 'analysis', 'from_port': 0, 'to_port': index}
               for index in range(5)])


def checked_report(report, job, positive):
    first = report['first_run']
    nodes = {node['id']: node for node in first['nodes']}
    if (len(first['nodes']) != 6 or set(nodes) != {'analysis', *{'input'+str(index) for index in range(5)}}
            or report['engine_source_revision'] != ENGINE
            or report['native_statistical_factories_registered'] is not False
            or report['input_hashing'] != 'ContentRequired' or report['max_concurrency'] != 1
            or report['incremental'] is not False or report['current_daemon_verified'] is not False
            or report['original_manifest_sha256'] != job['plugin_manifest_sha256']
            or report['plugin_name'] != 'twosamplemr-v432-a'
            or report['additional_plugin_identities'] != [] or report['g0_granted'] is not False):
        raise RuntimeError('Exact isolated six-node current-engine graph identity required')
    if any(nodes['input'+str(index)]['status'] != 'success' for index in range(5)):
        raise RuntimeError('All five reference nodes must succeed')
    if positive:
        if first['errors'] or nodes['analysis']['status'] != 'success':
            raise RuntimeError('Actual A method DAG failed')
    elif not first['errors'] or nodes['analysis']['status'] != 'failed':
        raise RuntimeError('Bad-input A method DAG did not fail')
    return nodes['analysis']


def bound_inputs(work, analysis, scratch):
    bindings = analysis['inputs']
    if len(bindings) != 5 or {record['to_port'] for record in bindings} != set(range(5)):
        raise RuntimeError('Complete five-port method input bindings required')
    records = []
    for index, name in enumerate(INPUTS):
        original = work / name
        binding = next(record for record in bindings if record['to_port'] == index)
        staged = [path for path in scratch.rglob('input-'+str(index)+original.suffix)
                  if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        if (binding['from'] != 'input'+str(index) or binding['from_port'] != 0
                or binding['path'] != 'vfs:///'+name or len(staged) != 1
                or staged[0].is_symlink() or not staged[0].resolve().is_relative_to(scratch.resolve())
                or binding['fingerprint']['size'] != original.stat().st_size
                or digest(staged[0]) != digest(original)):
            raise RuntimeError('Actual staged input source, edge or bytes differ')
        records.append(dict(port=index, sha256=digest(original), staged_sha256=digest(staged[0]),
                            bytes=original.stat().st_size))
    return records


def exact_tables(actual, oracle):
    if len(actual) != 6:
        raise RuntimeError('All six table ports required')
    result = []
    for index, path in enumerate(actual):
        expected = oracle / ('output'+str(index))
        if not path.is_file() or path.read_bytes() != expected.read_bytes():
            raise RuntimeError('Complete frozen TSV bytes differ at port '+str(index))
        result.append(dict(port=index, sha256=digest(path), oracle_sha256=digest(expected)))
    return result


def compare_provenance(actual, oracle, script_sha):
    left, right = copy.deepcopy(actual), copy.deepcopy(oracle)
    if left.get('adapter_sha256') != script_sha or right.get('adapter_sha256') != 'beec8ef591d96180ac720c909288fd1090a7803e610c048e980b3de92636a53b':
        raise RuntimeError('Actual and immutable oracle adapter identities required')
    left.pop('adapter_sha256'); right.pop('adapter_sha256')
    if left != right:
        raise RuntimeError('Scientific/runtime/input provenance differs from the official-method oracle')
    return dict(only_adapter_source_identity_may_differ=True, all_other_fields_equal=True)


READBACK = '''root <- commandArgs(trailingOnly=TRUE)[1]
for (label in c("under","over")) {
 node <- file.path(root,label,"actual")
 oracle <- file.path(root,label,"oracle")
 stopifnot(identical(readRDS(file.path(node,"output6")),readRDS(file.path(oracle,"output6"))))
 for (position in 0:5) stopifnot(identical(
  read.delim(file.path(node,paste0("output",position)),check.names=FALSE),
  read.delim(file.path(oracle,paste0("output",position)),check.names=FALSE)))
 stopifnot(identical(readLines(file.path(node,"output7"),warn=FALSE),readLines(file.path(oracle,"output7"),warn=FALSE)))
 provenance <- jsonlite::read_json(file.path(node,"output8"),simplifyVector=TRUE)
 stopifnot(identical(provenance$scientific_authorization_granted,FALSE),
  identical(provenance$formal_scientific_pass_granted,FALSE))
}
jsonlite::write_json(list(status="ALL_NINE_PORTS_READ_COMPLETE_RDS_IDENTICAL",cases=2,
 six_tables_per_case=TRUE,complete_rds_per_case=TRUE,log_and_json_per_case=TRUE,g0_granted=FALSE),
 file.path(root,"R-readback-verification.json"),auto_unbox=TRUE,pretty=TRUE)
'''


def main():
    if len(sys.argv) != 1 or not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT'):
        raise RuntimeError('Managed technical session without scientific-data overrides required')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    build_archive, oracle_archive = archives / BUILD_SESSION, archives / ORACLE_SESSION
    receipts = [sealed_archive(build_archive, BUILD_SEAL, successful=True),
                sealed_archive(oracle_archive, ORACLE_SEAL, successful=True)]
    build_root = build_archive / 'artifacts/permanent/current-ldsc-build'
    build = json.loads((build_root / 'build-record.json').read_text())
    executable = build_root / 'official_plugin_dag'
    if (type(build['actual_build_exit']) is not int or build['actual_build_exit'] != 0
            or build['engine_commit'] != ENGINE or build['executable_sha256'] != EXECUTABLE
            or digest(executable) != EXECUTABLE):
        raise RuntimeError('Exact successful sealed current engine executable required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-current-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(build_root / 'build-record.json', output / 'build-record.json')
    source = output / 'source'; (source / 'scripts').mkdir(parents=True)
    for name in ['manifest.toml', 'scripts/mr.R']:
        shutil.copyfile(PLUGIN / name, source / name)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    definition = manifest['nodes'][0]
    if (manifest['plugin_name'] != 'twosamplemr-v432-a' or len(manifest['nodes']) != 1
            or definition['kind'] != KIND or definition['resources'] != dict(cpus=2.0, memory='2Gi',network='isolated',pull_policy='missing')
            or len(definition['ports']['inputs']) != 5 or len(definition['ports']['outputs']) != 9):
        raise RuntimeError('Exact frozen-A manifest and bounded resource declarations required')
    image = manifest['image']['reference']
    inspection = subprocess.run(['podman','image','inspect',image],capture_output=True,text=True,check=True)
    (output / 'image-inspect.json').write_text(inspection.stdout)
    runner = Path(os.environ['TMPDIR']) / 'frozen-a-official-plugin-dag'
    shutil.copyfile(executable,runner); runner.chmod(0o700)
    if digest(runner) != EXECUTABLE: raise RuntimeError('Owned runner copy differs')
    oracle_root = oracle_archive / 'artifacts/permanent/v432-a-method'
    completed_cases = []
    for label in ['under','over','badinput']:
        positive = label != 'badinput'
        oracle = oracle_root / (label if positive else 'input-byte-mismatch')
        work = output / label; work.mkdir()
        for name in INPUTS: shutil.copyfile(oracle / 'inputs' / name, work / name)
        before = {name:digest(work / name) for name in INPUTS}
        job = job_for(work, source); write(work / 'job.json',job)
        run = subprocess.run([str(runner),str(work / 'job.json')],capture_output=True,text=True,timeout=300)
        (work / 'runner.stdout').write_text(run.stdout); (work / 'runner.stderr').write_text(run.stderr)
        if run.returncode: raise RuntimeError('Runner failed outside the graph: '+label)
        report = json.loads((work / 'dag-report.json').read_text())
        analysis = checked_report(report,job,positive)
        scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / label
        inputs = bound_inputs(work,analysis,scratch)
        if before != {name:digest(work / name) for name in INPUTS}:
            raise RuntimeError('Graph changed an input fixture')
        if positive:
            if analysis['execution']['image'] != image or analysis['execution']['exit_code'] != 0:
                raise RuntimeError('Actual dispatched official image or exit differs')
            ports = check_ports(work,definition,analysis,scratch)
            (work / 'actual').mkdir(); (work / 'oracle').mkdir()
            for index,path in enumerate(ports):
                shutil.copyfile(path,work / 'actual' / ('output'+str(index)))
                shutil.copyfile(oracle / 'outputs' / ('output'+str(index)),work / 'oracle' / ('output'+str(index)))
            tables = exact_tables(ports[:6],oracle / 'outputs')
            if ports[7].read_bytes() != (oracle / 'outputs/output7').read_bytes():
                raise RuntimeError('Complete execution log differs from the method oracle')
            provenance = compare_provenance(json.loads(ports[8].read_text()),
                json.loads((oracle / 'outputs/output8').read_text()),digest(source / 'scripts/mr.R'))
            completed_cases.append(dict(case=label,nodes=6,edges=5,inputs=inputs,published_ports=9,
                exact_complete_TSVs=tables,complete_log_bytes_equal=True,provenance=provenance))
        else:
            normal = [path for port in definition['ports']['outputs'] if port['path'] != 'twosamplemr_v432_a.log'
                      for path in work.rglob(port['path'])]
            live_normal = [path for port in definition['ports']['outputs'] if port['path'] != 'twosamplemr_v432_a.log'
                           for path in scratch.rglob(port['path'])]
            if normal or live_normal or analysis['port_assignments']:
                raise RuntimeError('Failed method leaked normal result ports')
            logs = list(scratch.rglob('twosamplemr_v432_a.log'))
            for index,path in enumerate(logs): shutil.copyfile(path,work / ('diagnostic-'+str(index)+'.log'))
            completed_cases.append(dict(case=label,nodes=6,edges=5,inputs=inputs,
                method_failed=True,normal_result_files=0,diagnostic_logs=len(logs)))
        write(work / 'verification.json',completed_cases[-1])
    (output / 'readback.R').write_text(READBACK)
    command = ['podman','run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=2g',
        '--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),'--tmpfs=/tmp:rw,size=64m',
        '-v',str(output)+':/work:rw','--entrypoint=Rscript',image,'--vanilla','/work/readback.R','/work']
    write(output / 'readback-command.json',command)
    readback = subprocess.run(command,capture_output=True,text=True,timeout=180)
    (output / 'readback.stdout').write_text(readback.stdout); (output / 'readback.stderr').write_text(readback.stderr)
    if readback.returncode: raise RuntimeError('Full official RDS and nine-port R readback failed')
    for path in [source / 'manifest.toml',source / 'scripts/mr.R']:
        if digest(path) != digest(PLUGIN / path.relative_to(source)): raise RuntimeError('Adapter source changed during DAG proof')
    for archive,seal in [(build_archive,BUILD_SEAL),(oracle_archive,ORACLE_SEAL)]:
        sealed_archive(archive,seal,successful=True)
    write(output / 'verification.json',dict(status='SYNTHETIC_FROZEN_A_CURRENT_DAGS_PROVEN_NOT_DEPLOYED',
        cases=completed_cases,engine_revision=ENGINE,executable_sha256=EXECUTABLE,
        source_script_sha256=digest(source / 'scripts/mr.R'),source_manifest_sha256=digest(source / 'manifest.toml'),
        reference_receipts=[dict(session=value['session']['session'],manifest_sha256=value['session']['manifest_sha256'],
            members_rehashed=len(value['manifest']['files'])) for value in receipts],
        complete_RDS_object_comparison=json.loads((output / 'R-readback-verification.json').read_text()),
        actual_production_registry_or_study_qualified=False,g0_granted=False))
    print('A_CURRENT_DAGS=2_POSITIVE_1_REFUSAL; ALL_9_PORTS_READ; G0=false')


if __name__ == '__main__': main()
