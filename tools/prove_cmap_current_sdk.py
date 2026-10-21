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
FROZEN = 'a9dacd44b84d49f2ac2948e582ca1a36'
FROZEN_SEAL = '924bb2742bbcbf2445517e8193ea800d28106dce1a23d2de4b0fc99aaec9104f'
BUILD = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
ADAPTER_SHA = 'd73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194'
CHECK = r'''
import hashlib,json,math,struct,zipfile
from pathlib import Path
import pyarrow.parquet as pq
root=Path('/proof')
actual=root/'positive/actual'
frozen=Path('/frozen/pearson_gct')
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
cells=0
missing=0
finite=0
for name in ['scores.parquet','query.parquet','reference.parquet','metadata.parquet','gene_ledger.parquet']:
    first,second=pq.read_table(actual/name),pq.read_table(frozen/name)
    assert first.schema.equals(second.schema,check_metadata=True),(name,'schema')
    assert first.num_rows==second.num_rows and first.num_columns==second.num_columns
    for observed,expected in zip(first.to_pylist(),second.to_pylist(),strict=True):
        assert observed.keys()==expected.keys()
        for key,value in expected.items():
            cells+=1
            if isinstance(value,float):
                assert isinstance(observed[key],float)
                assert (math.isnan(value) and math.isnan(observed[key])) or struct.pack('!d',observed[key])==struct.pack('!d',value),(name,key)
                finite+=int(math.isfinite(value))
            else:
                assert observed[key]==value,(name,key)
                missing+=int(value is None)
sink=pq.read_table(root/'positive/materialized.parquet')
scores=pq.read_table(actual/'scores.parquet')
assert sink.schema.equals(scores.schema,check_metadata=True) and sink.to_pylist()==scores.to_pylist()
for name in ['request_ledger.tsv','cmap.log']:
    assert (actual/name).read_bytes()==(frozen/name).read_bytes(),name
source_names=['query.tsv','reference.bin','metadata.tsv','request.json']
with zipfile.ZipFile(actual/'source_inputs.zip') as archive:
    assert archive.namelist()==source_names
    for name in source_names:
        assert archive.read(name)==(frozen/name).read_bytes()
audit=json.loads((actual/'audit.json').read_text())
old=json.loads((frozen/'audit.json').read_text())
output_names=['scores.parquet','query.parquet','reference.parquet','metadata.parquet','audit.json','request_ledger.tsv','cmap.log','gene_ledger.parquet','source_inputs.zip']
assert set(audit['output_sha256'])=={str(index) for index in range(9) if index!=4}
for position,expected in audit['output_sha256'].items(): assert digest(actual/output_names[int(position)])==expected
audit['output_sha256'].pop('8')
old['output_sha256'].pop('8')
assert audit==old,'audit excluding only ZIP timestamp-dependent file hash'
assert not audit['G0_granted'] and audit['not_Broad_WTCS_NCS_tau']
assert scores.num_rows==6 and sum(row['status']=='ESTIMABLE' for row in scores.to_pylist())==5
result=dict(passed=True,parquet_tables_compared=5,fields_compared=cells,finite_float_bits_compared=finite,
    missing_fields_compared=missing,materialized_score_rows=sink.num_rows,
    exact_ledger_and_log=True,complete_source_ZIP_contents=True,
    complete_audit_except_verified_ZIP_container_bytes=True,
    source_ZIP_byte_identity_claimed=False,new_reference_statistics=0,g0_granted=False)
(root/'materialization-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def save(filename, value):
    filename.write_text(json.dumps(value, indent=2) + '\n')


def load(name, filename):
    specification = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0, str(PLUGINS))
    from tools.reconcile_ab_evidence_index import verify_archive
    from tools import prove_frozen_a_harmonisation_dag as admission
    from tools.prove_frozen_a_family_runtime import stopped
    require(verify_archive(ARCHIVES, FROZEN, FROZEN_SEAL)['positive_worker_exit_verified'], 'Frozen input and original outputs required')
    frozen = ARCHIVES / FROZEN / 'artifacts/permanent/network-cmap-saved-contract-reconciliation/selected/node-proof-cmap-ledger-20261008/cmap-DAG-v5'
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    output = permanent / 'cmap-current-sdk'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    source = output / 'source/cachexia-cmap'
    source.mkdir(parents=True)
    source_hashes = {}
    for name in ['manifest.toml', 'compare.py']:
        original = PLUGINS / 'research-adapters/cachexia-cmap' / name
        require(original.read_bytes() == (frozen / 'source/cachexia-cmap' / name).read_bytes(), 'Frozen source or interface changed')
        shutil.copyfile(original, source / name)
        source_hashes[name] = sha(original)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    definition = next(node for node in manifest['nodes'] if node['kind'] == 'cachexia_cmap_correlation')
    image = manifest['image']['reference']
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    require(image in profile['images'], 'Exact prequalified image required; no pull or rebuild')
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile.update(images=[image], delegate=dict(path=str(delegate), sha256=sha(delegate)))
    profile_file = output / 'managed-image-profile.json'
    save(profile_file, profile)
    profile_file.chmod(0o600)
    adapter = Path.home() / '.local/lib/autonomics/qualified-podman' / ADAPTER_SHA / 'podman'
    require(sha(adapter) == ADAPTER_SHA, 'Qualified adapter source changed')
    primary = profile['primary']
    backend = ['--root', primary['graphroot'], '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
               '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
    prefix = [str(adapter), *backend]
    environment = dict(os.environ, AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(profile_file))
    build_root = ARCHIVES / BUILD / 'artifacts/permanent/locked-b-probe-build'
    build, receipt = admission.checked_build(ARCHIVES, build_root / 'official_plugin_dag', build_root / 'build-record.json', BUILD_SEAL)
    runner, executable_identity = admission.executable_copy(build_root / 'official_plugin_dag', temporary)
    helper_file = ROOT / 'results/cachexia-v4.3.2/prove_lcmm_current_sdk_20261019.py'
    helper = load('ports', helper_file)
    shutil.copyfile(helper_file, output / 'port-transport-helper.py')
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
    if hashlib.sha256((mounts[0]/'.autonomics/script').read_bytes()).hexdigest()!=SCRIPT_HASH: raise SystemExit('Executed source changed')
    with open(RECORD,'a') as stream: stream.write(json.dumps(dict(workspace=str(mounts[0])))+'\\n')
os.execv(ADAPTER,PREFIX+arguments)
'''.replace('SCRATCH', repr(str(scratch))).replace('SCRIPT_HASH', repr(source_hashes['compare.py']))
                    .replace('RECORD', repr(str(output / 'creates.jsonl'))).replace('ADAPTER', repr(str(adapter))).replace('PREFIX', repr(prefix)))
    proxy.chmod(0o700)
    environment['PATH'] = str(launch) + ':' + os.environ['PATH']
    cases = []
    try:
        for negative in [False, True]:
            work = output / ('negative-hash' if negative else 'positive')
            work.mkdir()
            names = ['query.tsv', 'reference.bin', 'metadata.tsv', 'request.json']
            for name in names:
                shutil.copyfile(frozen / 'pearson_gct' / name, work / name)
            if negative:
                request = json.loads((work / 'request.json').read_text())
                request['input_sha256'][0] = '0' * 64
                save(work / 'request.json', request)
            nodes = [dict(id='source-' + str(index), kind='file_reference',
                spec=dict(path='vfs:///' + name, hash_content=True)) for index, name in enumerate(names)]
            nodes += [dict(id='analysis', kind=definition['kind'], spec={}),
                dict(id='reader', kind='file_to_dataframe', spec=dict(format='parquet')),
                dict(id='sink', kind='dataframe_to_file', spec=dict(path='vfs:///materialized.parquet', format='parquet'))]
            edges = [dict(**{'from':'source-' + str(index), 'to':'analysis'}, from_port=0, to_port=index) for index in range(4)]
            edges += [dict(**{'from':'analysis','to':'reader'}, from_port=0,to_port=0),
                      dict(**{'from':'reader','to':'sink'}, from_port=0,to_port=0)]
            job = dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', expected_plugin_name='cachexia-cmap', run_root=str(work),
                plugin_manifest=str(source / 'manifest.toml'), plugin_manifest_sha256=source_hashes['manifest.toml'],
                script_sha256={'compare.py':source_hashes['compare.py']}, additional_plugins=[], bundles=[],
                panel_overrides=[], panel_manifest_sha256={}, nodes=nodes, edges=edges)
            save(work / 'job.json', job)
            completed = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, timeout=180,
                env=dict(environment, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
            (work / 'runner.stdout').write_bytes(completed.stdout)
            (work / 'runner.stderr').write_bytes(completed.stderr)
            require(completed.returncode == 0 and (work / 'dag-report.json').is_file(), 'SDK failed before a retained graph report')
            report = json.loads((work / 'dag-report.json').read_text())
            actual = {node['id']:node for node in report['first_run']['nodes']}
            require(report['engine_source_revision'] == build['engine_commit'] and report['max_concurrency'] == 1, 'SDK identity/configuration differs')
            if negative:
                workspace = Path(json.loads((output / 'creates.jsonl').read_text().splitlines()[-1])['workspace'])
                for name in ['audit.json','request_ledger.tsv','cmap.log']:
                    require((workspace / name).is_file(), 'Failure diagnostic missing')
                    shutil.copyfile(workspace / name, work / name)
                audit = json.loads((work / 'audit.json').read_text())
                require(actual['analysis']['status'] == 'failed' and not actual['analysis'].get('port_assignments')
                    and audit['status'] == 'BLOCKED' and audit['error'] == 'Frozen source content differs'
                    and all(actual[node]['status'] == 'skipped' for node in ['reader','sink'])
                    and not (work / 'materialized.parquet').exists(), 'Hash failure leaked normal outputs or lost diagnostics')
            else:
                require(report['first_run']['ok'] and len(actual) == 7, 'Positive graph did not completely succeed')
                helper.ports(actual['analysis'], definition, work / 'actual', scratch)
            cases.append(dict(negative=negative, nodes=7, edges=6, downstream_skipped=2 if negative else 0))
        (output / 'review.py').write_text(CHECK)
        checked = subprocess.run([*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
            '--memory=512m', '--pids-limit=64', '--tmpfs=/tmp:rw,nosuid,nodev,size=32m', '--userns=keep-id',
            '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '-e', 'PYTHONDONTWRITEBYTECODE=1',
            '-v', str(output) + ':/proof:rw', '-v', str(frozen) + ':/frozen:ro', '--entrypoint=python3', image,
            '-I', '-B', '/proof/review.py'], capture_output=True, env=environment, timeout=90)
        (output / 'review.stdout').write_bytes(checked.stdout)
        (output / 'review.stderr').write_bytes(checked.stderr)
        require(checked.returncode == 0, 'Complete current output versus frozen output review failed')
    finally:
        intents = json.loads((permanent / 'container-intents.json').read_text())
        stopped([str(delegate), '--storage-opt', 'additionalimagestore=' + profile['additional']['path'], *backend],
                permanent, output, len(intents['intents']))
    require(len(intents['intents']) == 3 and all(sha(PLUGINS / 'research-adapters/cachexia-cmap' / name) == digest for name,digest in source_hashes.items()),
            'Source changed or actual container count differs')
    save(output / 'verification.json', dict(schema='CMAP_RETAINED_SDK_BRIDGE_V1', passed=True,
        function_id='FUNC_cmap_connectivity', cases=cases, selected_metric='pearson', source_hashes=source_hashes,
        image=image, retained_SDK_source=build['engine_commit'], materialization=json.loads((output/'materialization-review.json').read_text()),
        owned_containers_stopped=3, old_25_case_suite_repeated=False, Broad_algorithm_certified=False,
        current_resident_DAG_claimed=False, scientific_release_granted=False, new_software_admissions=0, g0_granted=False))
    print(json.dumps(dict(positive_DAGs=1, negative_DAGs=1, all_declared_ports_retained=9, g0_granted=False)), flush=True)


if __name__ == '__main__':
    main()
