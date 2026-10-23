"""One sealed synthetic A bridge through the existing policy-bound SDK consumer."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

HERE = Path(__file__).resolve().parent
ADAPTERS = HERE.parent
MAIN = Path('/home/zj-normal/Work/autonomics')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')
SEALS = {
    'dfe1e1f094054bd6add6b05e9d6cba1a': 'f5783c36f3abbd76222a13c2df948dda788d94e05e9c5c824f970b7164f04962',
    '3fddecd8263d4166888d41f582b35dca': 'c555dce6ba321e9048f65b571fef841e09acfadd646e97145455fa01589fdf68',
    '3de5533e881144d1b1643c4fd648ef7b': '835bcb4368da6bccf05abf5dac61e51f88e71cfafa510851d2d6ac99d0082314',
}
CONSUMER_SHA = 'e289d372b8d0abd84e4371ce48b9091eb41965d5de1985865286a2f5bb09537a'
CONSUMER_SOURCE_SHA = '290e615b725b7e663ed1449e415f9499dfd4203e5993fc460cdc7cd3f48db272'
WIRING = ADAPTERS / 'frozen-a-real-intake-dag-v1'
R_IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'
PY_IMAGE = 'docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def verify_archive(session, seal):
    root = ARCHIVES / session
    record = json.loads((root / 'SESSION.json').read_bytes())
    manifest = root / 'artifacts/MANIFEST.json'
    require(sha(manifest) == seal == record['manifest_sha256'], 'Prior manifest seal differs')
    require(record['state'] == 'CLEANED' and record['worker_exit_status'] == record['launcher_exit_status'] == 0,
            'Prior successful stopped session required')
    files = json.loads(manifest.read_bytes())['files']
    actual = {str(p.relative_to(root / 'artifacts')) for p in (root / 'artifacts').rglob('*') if p.is_file()}
    require(actual == set(files) | {'MANIFEST.json'}, 'Prior archive membership differs')
    for name, identity in files.items():
        path = root / 'artifacts' / name
        require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], name)
    return dict(session=session, seal=seal, members_rehashed=len(files), worker_exit=0, launcher_exit=0)


R_PREFLIGHT = r'''
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("stats"))=="4.6.1",
          requireNamespace("jsonlite",quietly=TRUE))
commands <- Sys.which(c("sh","sha256sum","cut","cp"))
stopifnot(all(nzchar(commands)))
cat(jsonlite::toJSON(list(R=as.character(getRversion()),stats=as.character(packageVersion("stats")),
                        jsonlite=as.character(packageVersion("jsonlite")),tools=as.list(commands)),auto_unbox=TRUE),"\n")
'''

R_VERIFY = r'''
actual <- readRDS("/actual/real-adjustment.RDS")
old <- readRDS("/baseline/real-adjustment.RDS")
table <- read.delim("/actual/real-adjusted.tsv",colClasses="character",na.strings=character(),check.names=FALSE)
vectors <- read.delim("/assembly/real-vectors.tsv",colClasses="character",na.strings=character(),check.names=FALSE)
family <- read.delim("/assembly/real-family.tsv",colClasses="character",na.strings=character(),check.names=FALSE)
receipt <- jsonlite::read_json("/actual/real-adjustment.json")
assembly <- jsonlite::read_json("/assembly/real-assembly.json")
stopifnot(length(actual$vectors)==6L,nrow(table)==840L,nrow(vectors)==840L,nrow(family)==564L,
          identical(actual$vectors,old$vectors),identical(actual$frozen_definition,old$frozen_definition),
          identical(actual$R_version,"4.6.1"),identical(actual$stats_version,"4.6.1"),
          receipt$scientific_authorization_granted==FALSE,receipt$g0_granted==FALSE)
cells <- 0L
for(key in names(actual$vectors)) {
 v <- actual$vectors[[key]]
 rows <- table[table$vector_id==key,,drop=FALSE]
 source <- vectors[vectors$vector_id==key,,drop=FALSE]
 stopifnot(identical(rows$analysis_id,v$analysis_id),identical(source$analysis_id,v$analysis_id),
           identical(v$analysis_id,unlist(assembly$family_ids[[unique(rows$family_id)]],use.names=FALSE)),
           identical(v$n_total,length(v$analysis_id)),all(is.na(v$p_primary)),all(v$p_for_adjustment==1),
           identical(as.numeric(rows$q_primary),v$q_primary),all(rows$p_primary=="NA"),
           identical(as.numeric(rows$p_for_adjustment),v$p_for_adjustment))
 cells <- cells+length(v$analysis_id)
}
stopifnot(cells==840L)
cat(jsonlite::toJSON(list(passed=TRUE,new_RDS_read=TRUE,old_RDS_separately_read=TRUE,
     all_six_vectors_identical_to_baseline=TRUE,ordered_values=840L,family_rows=564L,adjusted_rows=840L,
     provenance_input_hashes_equal=identical(actual$input_sha256,old$input_sha256)),auto_unbox=TRUE),"\n")
'''


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'a-native-dag'
    output.mkdir(mode=0o700)
    before = {p.name: sha(p) for p in HERE.iterdir() if p.is_file()}
    for name in before:
        shutil.copyfile(HERE / name, output / name)
    state = dict(schema='A_NATIVE_DAG_INCREMENTAL_PROOF_V1', actual_new_tests=0,
                 actual_native_dag_executions=0, actual_container_executions=0,
                 scientific_authorization_granted=False, g0_granted=False)
    def checkpoint():
        write(output / 'progress.json', state)
    try:
        state['verified_archives'] = [verify_archive(s, seal) for s, seal in SEALS.items()]
        base = ARCHIVES / '3fddecd8263d4166888d41f582b35dca/artifacts/permanent/a-real-input-v1-toy'
        old_wiring = ARCHIVES / 'dfe1e1f094054bd6add6b05e9d6cba1a/artifacts/permanent/a-real-intake-file-wiring'
        verify = json.loads((old_wiring / 'verification.json').read_bytes())
        for name, expected in verify['candidate_source_sha256'].items():
            require(sha(WIRING / name) == expected, 'Read-only wiring source changed: ' + name)
        for name, expected in json.loads((base / 'verification.json').read_bytes())['source_sha256'].items():
            require(sha(name) == expected, 'Read-only V1 source changed: ' + name)
        consumer_root = ARCHIVES / '3de5533e881144d1b1643c4fd648ef7b/artifacts/permanent/sjtu-consumer-collection'
        require(sha(consumer_root / 'official_plugin_dag') == CONSUMER_SHA and
                sha(consumer_root / 'official_plugin_dag.rs') == CONSUMER_SOURCE_SHA and
                sha(MAIN / 'crates/container-plugin/examples/official_plugin_dag.rs') == CONSUMER_SOURCE_SHA,
                'Consumer source/binary identity differs')
        state['consumer'] = dict(binary_sha256=CONSUMER_SHA, source_sha256=CONSUMER_SOURCE_SHA,
                                exact_sdk_source_commit='864b3a75a5e27c81cba0d78cbe834e796f51df26',
                                current_consumer_source_matches=True, new_compilation=False,
                                whole_current_checkout_sdk_claimed=False)
        executable = Path(os.environ['TMPDIR']) / 'official_plugin_dag'
        shutil.copyfile(consumer_root / 'official_plugin_dag', executable)
        executable.chmod(0o500)
        require(sha(executable) == CONSUMER_SHA, 'Executable copy differs')
        profile_path = Path.home() / '.autonomics/qualified-image-store.json'
        profile = json.loads(profile_path.read_bytes())
        primary = profile['primary']
        prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--storage-opt', 'additionalimagestore=' + profile['additional']['path'],
                  '--root', primary['graphroot'], '--runroot', primary['runroot'], '--tmpdir', primary['runroot'] + '/libpod-tmp',
                  '--storage-driver', primary['driver'], '--cgroup-manager=cgroupfs']
        profile_sha = sha(profile_path)
        state['images'] = {}
        for image in (PY_IMAGE, R_IMAGE):
            result = subprocess.run(prefix + ['image', 'inspect', image], capture_output=True, timeout=60)
            require(result.returncode == 0, 'Exact fixed image is not cached: ' + image)
            inspection = json.loads(result.stdout)
            require(len(inspection) == 1 and image in inspection[0]['RepoDigests'], 'Cached image digest differs')
            state['images'][image] = dict(config_id=inspection[0]['Id'], inspected_digest=image)
        guard_directory = Path(os.environ['TMPDIR']) / 'a-native-podman'
        guard_directory.mkdir()
        guard = '''#!/usr/bin/python3
import json,os,sys
arguments=sys.argv[1:]
if arguments[:1]==["create"]:
    if not any(image in arguments for image in __IMAGES__): raise SystemExit("Unexpected fixed image")
    def option(name): return arguments[arguments.index(name)+1] if name in arguments else None
    if option("--network")!="none" or option("--pull")!="never" or "--read-only" not in arguments:
        raise SystemExit("Fixed isolated image policy differs")
    if option("--cpus")!="1" or option("--memory") not in ("1073741824","1024m","1g","1G","1Gi","1GiB") or option("--pids-limit")!="64":
        raise SystemExit("Fixed resource policy differs")
    with open(__RECORD__,"a") as stream:
        stream.write(json.dumps(dict(image=next(i for i in __IMAGES__ if i in arguments),network="none",pull="never",read_only_rootfs=True,cpus=option("--cpus"),memory=option("--memory"),pids_limit=option("--pids-limit")))+"\\n")
os.execv(__PROGRAM__,__PREFIX__+arguments)
'''.replace('__IMAGES__', repr([PY_IMAGE,R_IMAGE])).replace('__RECORD__', repr(str(output / 'native-creates.jsonl'))).replace('__PROGRAM__', repr(prefix[0])).replace('__PREFIX__', repr(prefix))
        (guard_directory / 'podman').write_text(guard)
        (guard_directory / 'podman').chmod(0o700)
        environment = {k:v for k,v in os.environ.items() if not k.endswith(('_API_KEY','_TOKEN','_JWT'))}
        environment['PATH'] = str(guard_directory) + os.pathsep + environment['PATH']
        environment['AUTONOMICS_DAG_RECEIPTS_ROOT'] = str(output/'task-receipts')
        environment['AUTONOMICS_DAG_TASKS_ROOT'] = str(output/'task-receipts')
        def container(name, image, command, mounts=()):
            args = prefix + ['run','--rm','--network=none','--pull=never','--read-only','--security-opt=no-new-privileges',
                             '--userns=keep-id','--cpus=1','--memory=1073741824','--pids-limit=64','--tmpfs=/tmp:rw,nosuid,nodev']
            for source,target in mounts:
                args += ['--volume', str(source) + ':' + target + ':ro']
            result = subprocess.run(args + ['--entrypoint',command[0],image] + command[1:], capture_output=True, env=environment, timeout=90)
            (output / (name + '.stdout')).write_bytes(result.stdout)
            (output / (name + '.stderr')).write_bytes(result.stderr)
            state.setdefault('container_attempts',[]).append(dict(name=name,exit=result.returncode))
            require(result.returncode == 0, name + ' container exit ' + str(result.returncode))
            state['actual_container_executions'] += 1
            return result
        preflight = container('R-preflight', R_IMAGE, ['Rscript','--vanilla','-e',R_PREFLIGHT])
        state['R_preflight'] = json.loads(preflight.stdout)
        python = container('python-preflight', PY_IMAGE, ['python3','-c','import sys,json; assert sys.version_info[:3]==(3,14,7); print(json.dumps(dict(Python=sys.version.split()[0])))'])
        state['Python_preflight'] = json.loads(python.stdout)
        checkpoint()
        spec = importlib.util.spec_from_file_location('sealed_a_prepare', WIRING / 'prepare.py')
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        # Recover the same sealed synthetic request. Only canonical File locations
        # differ; the declared source values, opaque RDS and history bytes do not.
        inputs = output / 'synthetic-inputs'
        inputs.mkdir()
        shutil.copyfile(base / 'toy-results.tsv', inputs / 'results.tsv')
        shutil.copyfile(base / 'toy-original.RDS', inputs / 'original.RDS')
        ids = ['A_X01_M06','A_X01_M01','A_X01_M02']
        history = 'analysis_id\tfirst_result_viewed_at\tstatus\tallowed_identity\n' + ''.join(
            i + '\tON_OR_BEFORE_2026-01-01_EXACT_FIRST_VIEW_UNKNOWN\tLEGACY_PIPELINE_ANALYZED\tLEGACY_EXPLORATORY_TECHNICAL_REANALYSIS\n' for i in ids)
        (inputs / 'history.tsv').write_text(history)
        previous_closure = json.loads((old_wiring / 'materialization-success/candidate/file-closure.json').read_bytes())
        previous_dependencies = [e for e in previous_closure['entries'] if e['role'].startswith('request-dependency:')]
        require(sorted((e['sha256'],e['bytes']) for e in previous_dependencies) ==
                sorted((sha(inputs / n),(inputs / n).stat().st_size) for n in ('results.tsv','original.RDS','history.tsv')),
                'Synthetic dependency bytes differ from sealed wiring request')
        request = json.loads((base / 'toy-request.json').read_bytes())
        request['sources'][0]['path'] = str(inputs / 'results.tsv')
        for edge in request['edges']:
            if edge['rds']:
                edge['rds']['path'] = str(inputs / 'original.RDS')
        request['seen_history'] = [dict(source_id='synthetic-toy',sha256=sha(inputs / 'results.tsv'),
            declaration='ALREADY_SEEN_NOT_INDEPENDENT',precision='ON_OR_BEFORE_DATE',upper_bound_date='2026-01-01',
            exact_first_view_known=False,history_file=dict(path=str(inputs / 'history.tsv'),sha256=sha(inputs / 'history.tsv')),analysis_ids=ids)]
        # Reconstruct prior original request bytes with its sealed original paths;
        # this confirms semantic reuse independently of final numerical equality.
        restored = copy.deepcopy(request)
        previous_paths = {e['sha256']:e['original_path'] for e in previous_dependencies}
        restored['sources'][0]['path'] = previous_paths[sha(inputs / 'results.tsv')]
        restored['seen_history'][0]['history_file']['path'] = previous_paths[sha(inputs / 'history.tsv')]
        for edge in restored['edges']:
            if edge['rds']:
                edge['rds']['path'] = previous_paths[sha(inputs / 'original.RDS')]
        restored_bytes = prepare.bridge.encode(restored)
        require(hashlib.sha256(restored_bytes).hexdigest() == previous_closure['original_request_sha256'],
                'Reconstructed original synthetic request differs')
        (inputs / 'prior-request-reconstructed.json').write_bytes(restored_bytes)
        (inputs / 'request.json').write_bytes(prepare.bridge.encode(request))
        contract,candidate = prepare.prepare(inputs / 'request.json',STUDY,ADAPTERS,output / 'candidate')
        state['request_reuse'] = dict(prior_request_sha256=previous_closure['original_request_sha256'],
            prior_request_reconstructed_exactly=True,relocated_request_sha256=sha(inputs / 'request.json'),
            unique_dependencies=len(previous_dependencies),assembly_input_ports=len(contract['entries'])+1,
            aggregate_bytes=sum(e['bytes'] for e in contract['entries']),limit_unique_dependencies=239,limit_bytes=128*1024**2)
        def run_case(name, broken=False):
            work = output / name
            work.mkdir()
            staged = work / 'inputs'
            staged.mkdir()
            nodes = copy.deepcopy(candidate['nodes'])
            paths = [output / 'candidate/file-closure.json']+[Path(e['original_path']) for e in contract['entries']]
            for index,path in enumerate(paths):
                target = staged / str(index)
                shutil.copyfile(path,target)
                target.chmod(0o444)
                nodes[index]['spec']['path'] = 'vfs:///inputs/' + str(index)
            edges = copy.deepcopy(candidate['edges'])
            if broken:
                edges = [e for e in edges if not (e['to']=='assemble' and e['to_port']==len(paths)-1)]
            manifests = [output / 'candidate/assembly/manifest.toml',output / 'candidate/official/manifest.toml']
            def identity(path):
                data=tomllib.loads(path.read_text())
                return dict(plugin_manifest=str(path),plugin_manifest_sha256=sha(path),expected_plugin_name=data['plugin_name'],
                    script_sha256={n['command']['script_file']:sha(path.parent/n['command']['script_file']) for n in data['nodes']},panel_overrides=[])
            job = dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0',run_root=str(work),**identity(manifests[0]),
                       additional_plugins=[identity(manifests[1])],bundles=[],panel_manifest_sha256={},nodes=nodes,edges=edges)
            write(work / 'job.json',job)
            result = subprocess.run([str(executable),str(work / 'job.json')],capture_output=True,env=environment,timeout=500)
            (work / 'runner.stdout').write_bytes(result.stdout)
            (work / 'runner.stderr').write_bytes(result.stderr)
            state['native_runner_invocations'] = state.get('native_runner_invocations',0)+1
            state.setdefault('cases',[]).append(dict(name=name,runner_exit=result.returncode))
            # Runtime products live in managed TMPDIR. Capture declared output
            # ports immediately, including products from a failed assertion.
            report_path=work/'dag-report.json'
            if report_path.exists():
                report=json.loads(report_path.read_bytes())
                state['actual_native_dag_executions'] += 1
                collected=[]
                for node in report['first_run']['nodes']:
                    if node['id'] not in ('assemble','official'):
                        continue
                    for entry in node.get('output_files',[]):
                        source=Path(entry['path'])
                        require(source.is_absolute() and source.is_relative_to(Path(os.environ['TMPDIR'])) and source.is_file(),
                                'Declared SDK output must be in owned scratch')
                        target=work/'outputs'/node['id']/source.name
                        target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(source,target)
                        require(target.stat().st_size==entry['fingerprint']['size'],'Declared SDK output size differs')
                        collected.append(dict(node=node['id'],original_runtime_path=str(source),retained_path=str(target),
                                              bytes=target.stat().st_size,sha256=sha(target)))
                write(work/'output-capture.json',collected)
            checkpoint()
            return work,result
        work,result = run_case('connected')
        require(result.returncode == 0,'Connected native runner failed')
        report = json.loads((work / 'dag-report.json').read_bytes())
        nodes = {n['id']:n for n in report['first_run']['nodes']}
        require(all(n['status']=='success' for n in nodes.values()),'Connected native nodes did not all succeed')
        require(len(nodes['assemble']['output_files'])==4 and len(nodes['official']['output_files'])==3,
                'All seven output Files must be published')
        products = {}
        for filename in ('real-family.tsv','real-vectors.tsv','real-assembly.json','file-transport.json',
                         'real-adjusted.tsv','real-adjustment.RDS','real-adjustment.json'):
            found = list(work.rglob(filename))
            require(len(found)==1,'Unique declared output required: '+filename)
            products[filename]=found[0]
        for filename,baseline_path in [('real-family.tsv',base/'chain/real-family.tsv'),('real-vectors.tsv',base/'chain/real-vectors.tsv'),
                                       ('real-adjusted.tsv',base/'chain/official/real-adjusted.tsv')]:
            require(products[filename].read_bytes()==baseline_path.read_bytes(),'Full byte carrier mismatch: '+filename)
        actual_rds=products['real-adjustment.RDS']
        require(sha(actual_rds)!=sha(base/'chain/official/real-adjustment.RDS'),'New provenance-bearing RDS must be distinct')
        verified=container('R-full-readback',R_IMAGE,['Rscript','--vanilla','-e',R_VERIFY],
            [(actual_rds.parent,'/actual'),(base/'chain/official','/baseline'),(products['real-family.tsv'].parent,'/assembly')])
        state['full_output_readback'] = json.loads(verified.stdout)
        state['new_RDS_sha256']=sha(actual_rds)
        state['old_RDS_sha256']=sha(base/'chain/official/real-adjustment.RDS')
        state['actual_new_tests'] += 1
        work,negative = run_case('missing-upstream-file',True)
        # A graph-bound missing required File must never create either worker.
        report_path=work/'dag-report.json'
        if report_path.exists():
            report=json.loads(report_path.read_bytes())
            states={n['id']:n for n in report['first_run']['nodes']}
            require(states['assemble']['status'] in ('failed','skipped') and states['official']['status']=='skipped' and
                    not states['assemble'].get('output_files') and not states['official'].get('output_files'),
                    'Missing dependency unexpectedly published native outputs')
        else:
            require(negative.returncode==1 and negative.stderr.strip()==b'Error: PortDisconnected { node: "assemble", port: 19 }',
                    'Missing File must fail native graph admission at the exact missing port')
        state['actual_new_tests'] += 1
        creates=[json.loads(line) for line in (output/'native-creates.jsonl').read_text().splitlines()]
        require(len(creates)==2 and {c['image'] for c in creates}=={PY_IMAGE,R_IMAGE},'Exactly two connected SDK workers required')
        state['actual_container_executions'] += len(creates)
        state['native_container_policy']=creates
        require(sha(profile_path)==profile_sha,'Existing qualified profile changed')
        require(before=={p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'Proof source changed during execution')
        state['source_sha256']=before
        state['actual_exit']=0
        state['passed']=True
        state['pending']=['PRODUCTION_INSTALLATION','FINITE_PRIMARY_QUALIFICATION_INTERFACE','SCIENTIFIC_REVIEW_AND_G0']
    except Exception as error:
        state['actual_exit']=1
        state['passed']=False
        state['failure']=str(error)
        raise
    finally:
        state['source_sha256'] = before
        state['artifacts']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and p.name not in ('verification.json','progress.json')}
        write(output/'verification.json',state)
        print(json.dumps(dict(verification=str(output/'verification.json'),sha256=sha(output/'verification.json'),
                              actual_new_tests=state['actual_new_tests'],actual_exit=state['actual_exit'])))


if __name__=='__main__':
    main()
