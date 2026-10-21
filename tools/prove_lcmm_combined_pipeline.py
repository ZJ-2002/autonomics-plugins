import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = ROOT.parent / 'autonomics-plugins'
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
RECOVERY = 'ff9aa6a4a3fc47948522ed8c8df8b80f'
RECOVERY_SEAL = 'cc5b547781d01741eb690f06b7bef8abe0887401593cabe3c0a0e7bf74887880'
BUILD = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
ADAPTER_SHA = 'd73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194'
PREPARE_R = '''library(jsonlite)
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("lcmm"))=="2.2.2")
root <- "/proof"
second <- readRDS(file.path(root,"frozen_m2.rds"))
first <- fromJSON(file.path(root,"fit1.json"),simplifyVector=FALSE)
stopifnot(second$mode=="fit",inherits(second$fit,"hlme"),second$fit$conv==1L,
  second$request$mode=="fit",second$request$params$ng==2L,
  second$request$params$initialization=="FROZEN_CONVERGED_SINGLE_CLASS_FIT",
  identical(second$source_sha256,first$input0_sha256),
  identical(unlist(second$request$expected_row_ids,use.names=FALSE),unlist(first$expected_row_ids,use.names=FALSE)))
request <- second$request
request$input0_sha256 <- request$input2_sha256 <- "UPSTREAM_CONTENT_HASH"
write_json(request,file.path(root,"fit2.json"),auto_unbox=TRUE,pretty=TRUE,digits=NA,null="null")
write_json(list(extracted_from_complete_frozen_fit=TRUE,parameters_changed=FALSE,
  ng=request$params$ng,source_sha256=second$source_sha256),file.path(root,"template-extraction.json"),auto_unbox=TRUE)
'''


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(name, filename):
    specification = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def sha(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def save(filename, value):
    filename.write_text(json.dumps(value, indent=2) + '\n')


def main():
    sys.path.insert(0, str(PLUGINS))
    from tools import prove_frozen_a_harmonisation_dag as admission
    from tools.prove_frozen_a_family_runtime import stopped
    sealed = load('sealed', ROOT / 'results/generic-node-production-20261019/issue_eight_plugin_scoped_admission_20261019.py')
    prior = load('prior', ROOT / 'results/cachexia-v4.3.2/prove_lcmm_current_sdk_20261019.py')
    frozen = sealed.sealed_member(RECOVERY, RECOVERY_SEAL, 'permanent/lcmm-frozen-cases/RECOVERY_COMPLETE.json')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    output = permanent / 'lcmm-combined-pipeline'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    staged = output / 'fixtures'
    staged.mkdir()
    indexed = {item['path']: item for item in frozen['recovered_records']}
    recovered = ARCHIVES / RECOVERY / 'artifacts/permanent/lcmm-frozen-cases/files'
    cases = {item['mode']: item for item in frozen['cases']}

    def copy_frozen(member, destination):
        original = recovered / member
        require(original.stat().st_size == indexed[member]['size_bytes'] and sha(original) == indexed[member]['sha256'],
                'Frozen synthetic source identity differs')
        shutil.copyfile(original, destination)

    copy_frozen(cases['fit']['inputs'][0], staged / 'data.tsv')
    copy_frozen(cases['fit']['inputs'][1], staged / 'fit1.json')
    copy_frozen(cases['fit']['inputs'][2], staged / 'receipt.json')
    copy_frozen(cases['predict']['inputs'][0], staged / 'frozen_m2.rds')
    copy_frozen(cases['predict']['inputs'][2], staged / 'newdata.tsv')
    for mode in ['predict', 'compare']:
        request = dict(cases[mode]['frozen_request'])
        request['input0_sha256'] = request['input2_sha256'] = 'UPSTREAM_CONTENT_HASH'
        save(staged / (mode + '.json'), request)
    sources = {}
    manifests = []
    for family, script in [('cachexia-lcmm', 'scripts/lcmm.R'), ('cachexia-lcmm-typed-values', 'scripts/typed_values.py')]:
        directory = output / 'source' / family
        (directory / 'scripts').mkdir(parents=True)
        for name in ['manifest.toml', script]:
            original = PLUGINS / 'research-adapters' / family / name
            shutil.copyfile(original, directory / name)
            sources[family + '/' + name] = sha(original)
        manifests.append(tomllib.loads((directory / 'manifest.toml').read_text()))
    require(sources['cachexia-lcmm/scripts/lcmm.R'] == '92bedf32d5c48070df0354b0ee08c0d0f64e0fcb7cf44d7abd0da2945a0d43d8',
            'No method changes permitted')
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    images = [manifest['image']['reference'] for manifest in manifests]
    require(all(image in profile['images'] for image in images), 'Both exact qualified images required')
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile.update(images=images, delegate=dict(path=str(delegate), sha256=sha(delegate)))
    profile_file = output / 'managed-image-profile.json'
    save(profile_file, profile)
    profile_file.chmod(0o600)
    adapter = Path.home() / '.local/lib/autonomics/qualified-podman' / ADAPTER_SHA / 'podman'
    require(sha(adapter) == ADAPTER_SHA, 'Qualified adapter changed')
    primary = profile['primary']
    backend = ['--root', primary['graphroot'], '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
               '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
    prefix = [str(adapter), *backend]
    environment = dict(os.environ, AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(profile_file))
    (staged / 'extract.R').write_text(PREPARE_R)
    result = subprocess.run([*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=512m', '--pids-limit=64', '--tmpfs=/tmp:rw,nosuid,nodev,size=32m', '--userns=keep-id',
        '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '-e', 'OPENBLAS_NUM_THREADS=1',
        '-v', str(staged) + ':/proof:rw', '--entrypoint=Rscript', images[0], '--vanilla', '/proof/extract.R'],
        capture_output=True, env=environment, timeout=90)
    (output / 'extract.stdout').write_bytes(result.stdout)
    (output / 'extract.stderr').write_bytes(result.stderr)
    require(result.returncode == 0, 'Frozen class-two request extraction failed')
    build_root = ARCHIVES / BUILD / 'artifacts/permanent/locked-b-probe-build'
    build, receipt = admission.checked_build(ARCHIVES, build_root / 'official_plugin_dag', build_root / 'build-record.json', BUILD_SEAL)
    runner, identity = admission.executable_copy(build_root / 'official_plugin_dag', temporary)
    scratch = temporary / 'official-plugin-container-workspaces'
    launch = temporary / 'backend'
    launch.mkdir()
    proxy = launch / 'podman'
    proxy.write_text('''#!/usr/bin/python3
import hashlib,json,os,sys
from pathlib import Path
arguments=sys.argv[1:]
if arguments and arguments[0]=='create':
    mounts=[]
    for position,argument in enumerate(arguments[:-1]):
        if argument=='--mount':
            fields=dict(item.split('=',1) for item in arguments[position+1].split(',') if '=' in item)
            if fields.get('destination')=='/work': mounts.append(Path(fields['source']))
    if len(mounts)!=1 or not mounts[0].resolve().is_relative_to(Path(SCRATCH)): raise SystemExit('Unowned method workspace')
    with open(RECORD,'a') as stream: stream.write(json.dumps(dict(workspace=str(mounts[0])))+'\\n')
os.execv(ADAPTER,PREFIX+arguments)
'''.replace('SCRATCH', repr(str(scratch))).replace('RECORD', repr(str(output / 'creates.jsonl')))
                    .replace('ADAPTER', repr(str(adapter))).replace('PREFIX', repr(prefix)))
    proxy.chmod(0o700)
    environment['PATH'] = str(launch) + ':' + os.environ['PATH']
    records = []
    try:
        for negative in [False, True]:
            work = output / ('negative-source-hash' if negative else 'positive')
            work.mkdir()
            for name in ['data.tsv', 'receipt.json', 'fit1.json', 'fit2.json', 'predict.json', 'compare.json', 'newdata.tsv']:
                shutil.copyfile(staged / name, work / name)
            if negative:
                request = json.loads((work / 'fit1.json').read_text())
                request['input0_sha256'] = '0' * 64
                save(work / 'fit1.json', request)
            nodes = [dict(id=name, kind='file_reference', spec=dict(path='vfs:///' + filename, format=Path(filename).suffix[1:], hash_content=True))
                     for name, filename in [('data', 'data.tsv'), ('receipt', 'receipt.json'), ('fit1config', 'fit1.json'),
                         ('fit2config', 'fit2.json'), ('predconfig', 'predict.json'), ('compareconfig', 'compare.json'), ('newdata', 'newdata.tsv')]]
            definitions = {row['command']['env']['CACHEXIA_LCMM_MODE']: row for row in manifests[0]['nodes']}
            for name, mode in [('fit1', 'fit'), ('bindfit2', 'bind'), ('fit2', 'fit'), ('bindpred', 'bind'),
                               ('predict', 'predict'), ('bindcompare', 'bind'), ('compare', 'compare')]:
                nodes.append(dict(id=name, kind=definitions[mode]['kind'], spec={}))
            nodes += [dict(id='typed', kind=manifests[1]['nodes'][0]['kind'], spec={}),
                      dict(id='reader', kind='file_to_dataframe', spec=dict(format='parquet')),
                      dict(id='sink', kind='dataframe_to_file', spec=dict(path='vfs:///materialized.csv', format='csv'))]
            edges = []

            def connect(source, destination, port, source_port=0):
                edges.append(dict(**{'from': source, 'to': destination}, from_port=source_port, to_port=port))

            for source, port in [('data', 0), ('fit1config', 1), ('receipt', 2)]:
                connect(source, 'fit1', port)
            for binder, target, source0, source2, config, source0_port, source2_port in [
                ('bindfit2', 'fit2', 'data', 'fit1', 'fit2config', 0, 1),
                ('bindpred', 'predict', 'fit2', 'newdata', 'predconfig', 1, 0),
                ('bindcompare', 'compare', 'fit1', 'fit2', 'compareconfig', 1, 1)]:
                for destination in [binder, target]:
                    connect(source0, destination, 0, source0_port)
                    connect(source2, destination, 2, source2_port)
                connect(config, binder, 1)
                connect(binder, target, 1)
            connect('compare', 'typed', 0)
            connect('compare', 'typed', 1, 2)
            connect('typed', 'reader', 0)
            connect('reader', 'sink', 0)
            job = dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', expected_plugin_name='cachexia-lcmm', run_root=str(work),
                plugin_manifest=str(output / 'source/cachexia-lcmm/manifest.toml'), plugin_manifest_sha256=sources['cachexia-lcmm/manifest.toml'],
                script_sha256={'scripts/lcmm.R': sources['cachexia-lcmm/scripts/lcmm.R']},
                additional_plugins=[dict(plugin_manifest=str(output / 'source/cachexia-lcmm-typed-values/manifest.toml'),
                    expected_plugin_name='cachexia-lcmm-typed-values', plugin_manifest_sha256=sources['cachexia-lcmm-typed-values/manifest.toml'],
                    script_sha256={'scripts/typed_values.py': sources['cachexia-lcmm-typed-values/scripts/typed_values.py']}, panel_overrides=[])],
                bundles=[], panel_overrides=[], panel_manifest_sha256={}, nodes=nodes, edges=edges)
            save(work / 'job.json', job)
            execution = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, timeout=1200,
                env=dict(environment, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
            (work / 'runner.stdout').write_bytes(execution.stdout)
            (work / 'runner.stderr').write_bytes(execution.stderr)
            require(execution.returncode == 0 and (work / 'dag-report.json').exists(), 'SDK did not retain a complete graph report')
            report = json.loads((work / 'dag-report.json').read_text())
            mapped = {row['id']: row for row in report['first_run']['nodes']}
            diagnostics = work / 'diagnostics'
            diagnostics.mkdir()
            if (output / 'creates.jsonl').exists():
                for index, creation in enumerate((output / 'creates.jsonl').read_text().splitlines()):
                    workspace = Path(json.loads(creation)['workspace'])
                    retained = diagnostics / str(index)
                    retained.mkdir()
                    for filename in ['audit.json', 'lcmm.log', 'bind_audit.json', 'bind.log', 'failed_fit.rds',
                                     '.autonomics/logs/stdout.log', '.autonomics/logs/stderr.log']:
                        original = workspace / filename
                        if original.is_file():
                            require(original.stat().st_size <= 16 * 1024**2, 'Diagnostic exceeds bounded retention')
                            shutil.copyfile(original, retained / filename.replace('/', '_'))
            require(report['max_concurrency'] == 1 and report['engine_source_revision'] == build['engine_commit'], 'Exact sequential SDK required')
            if negative:
                require(mapped['fit1']['status'] == 'failed' and all(mapped[name]['status'] == 'skipped'
                    for name in ['fit2', 'predict', 'compare', 'typed', 'reader', 'sink'])
                    and not (work / 'materialized.csv').exists(), 'Source failure did not propagate')
                require(mapped['fit1']['execution']['exit_code'] == 1
                        and 'Frozen input content hash differs' in str(mapped['fit1']['error']), 'Wrong source refusal cause')
            else:
                require(all(row['status'] == 'success' for row in mapped.values()), 'Combined pipeline contains a failed node')
                for name, mode in [('fit1', 'fit'), ('fit2', 'fit'), ('predict', 'predict'), ('compare', 'compare'),
                                   ('bindfit2', 'bind'), ('bindpred', 'bind'), ('bindcompare', 'bind')]:
                    prior.ports(mapped[name], definitions[mode], work / (name + '-ports'), scratch)
                prior.ports(mapped['typed'], manifests[1]['nodes'][0], work / 'typed-ports', scratch)
                for binder, config, first, second in [('bindfit2', 'fit2.json', work / 'data.tsv', work / 'fit1-ports/state.rds'),
                    ('bindpred', 'predict.json', work / 'fit2-ports/state.rds', work / 'newdata.tsv'),
                    ('bindcompare', 'compare.json', work / 'fit1-ports/state.rds', work / 'fit2-ports/state.rds')]:
                    request = json.loads((work / config).read_text())
                    request.update(input0_sha256=sha(first), input2_sha256=sha(second))
                    require(json.loads((work / (binder + '-ports/resolved_contract.json')).read_text()) == request,
                            'Binder changed more than actual upstream content identities')
                copy_frozen(cases['compare']['expected']['summary'], work / 'expected-compare.tsv')
                numerical = prior.compare_table(work / 'compare-ports/summary.tsv', work / 'expected-compare.tsv')
                for mode, node in [('fit', 'fit1'), ('predict', 'predict')]:
                    expected = work / ('expected-' + mode + '.tsv')
                    copy_frozen(cases[mode]['expected']['summary'], expected)
                    prior.compare_table(work / (node + '-ports/summary.tsv'), expected)
                require((work / 'materialized.csv').is_file(), 'Final typed table missing')
                save(work / 'comparison.json', numerical)
            records.append(dict(negative=negative, nodes=len(nodes), edges=len(edges), report_retained=True))
    finally:
        intents = json.loads((permanent / 'container-intents.json').read_text())
        stopped([str(delegate), '--storage-opt', 'additionalimagestore=' + profile['additional']['path'], *backend],
                permanent, output, len(intents['intents']))
    require(all(sha(PLUGINS / 'research-adapters' / filename) == digest for filename, digest in sources.items()), 'Source changed during proof')
    save(output / 'verification.json', dict(schema='LCMM_SINGLE_COMBINED_SYNTHETIC_PIPELINE_V1', passed=True,
        cases=records, new_class1_and_class2_refits=True, actual_prediction_and_comparison=True,
        actual_upstream_RDS_hash_binding_verified=True, statistical_parameters_from_frozen_objects=True,
        sources=sources, retained_SDK_source=build['engine_commit'], current_resident_DAG_claimed=False,
        actual_research_inputs_used=False, scientific_freeze_modified=False,
        new_software_admissions=0, g0_granted=False))
    print(json.dumps(dict(combined_pipeline_passed=True, positive_DAGs=1, refusal_DAGs=1, g0_granted=False)))


if __name__ == '__main__':
    main()
