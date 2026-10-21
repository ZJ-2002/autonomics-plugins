import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import tomllib
from urllib.parse import urlsplit


ROOT=Path('/home/zj-normal/Work/autonomics')
PLUGINS=ROOT.parent/'autonomics-plugins'
REMOTE='https://github.com/ZJ-2002/autonomics-plugins.git'
REVISION='c8fcc0e26cfc4f0dfe2d8ae5a46ec5b87c0511c2'
IMAGE='ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'
CONFIG_ID='294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c'
ADAPTER_SHA='d73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194'
BINARY_SHA='5a3131bedb394043045b4f11ae541c183cecf3cc36069e188cc981e9d64aea27'
UNIT='autonomics-gateway-registry-20261019.service'


def require(condition,message):
    if not condition:
        raise RuntimeError(message)


def sha(filename):
    with filename.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def save(filename,value):
    filename.write_text(json.dumps(value,indent=2)+'\n')


def load(name,filename):
    specification=importlib.util.spec_from_file_location(name,filename)
    module=importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0,str(PLUGINS))
    from tools.prove_frozen_a_family_runtime import stopped
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'mrlap-pinned-source-deployment'
    output.mkdir(mode=0o700)
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    live=load('live',ROOT/'results/cachexia-v4.3.2/reload_two_official_ab_plugins_20261019.py')
    deploy=load('deploy',ROOT/'results/cachexia-v4.3.2/deploy_static_ports_and_rstats_20261021.py')
    sealed=load('sealed',ROOT/'results/generic-node-production-20261019/issue_eight_plugin_scoped_admission_20261019.py')
    proof=sealed.sealed_member('a206517262cb481f89b406f8b5e136b6',
        '499a0dfcc85ff4ee12a98127d27f6fac84f702a9454767c6b1644c8de8497487',
        'permanent/mrlap-registry-source-repair/verification.json')
    require(proof['passed'] and proof['actual_source_regression_tests_passed']==3
        and proof['image_config']==CONFIG_ID and proof['identical_uncompressed_layers']==12,'Source/image repair not qualified')
    state=Path.home()/'.autonomics'
    configuration=state/'plugins.toml'
    information=configuration.lstat()
    require(stat.S_ISREG(information.st_mode) and information.st_uid==os.getuid()
        and information.st_nlink==1 and not information.st_mode & 0o022,'Owner-controlled source configuration required')
    original=configuration.read_bytes()
    parsed=tomllib.loads(original.decode())
    require(set(parsed)=={'plugin'} and all(set(row)<={'name','path','git','rev','subdir','local_commit','local_digest'} for row in parsed['plugin']),
        'Review unknown configuration fields before retaining a backup')
    require(all(not urlsplit(row.get('git') or '').username and not urlsplit(row.get('git') or '').password for row in parsed['plugin']),
        'Credential-bearing source URLs must not enter evidence')
    selected=[row for row in parsed['plugin'] if row['name']=='mrlap']
    require(selected==[dict(name='mrlap',path=str(PLUGINS/'plugins/mrlap'))],'Expected explicit mutable source changed; reconcile before replacing it')
    blocks=re.split(r'(?m)(?=^\[\[plugin\]\])',original.decode())
    found=[index for index,block in enumerate(blocks) if re.search(r'(?m)^name\s*=\s*"mrlap"\s*$',block)]
    require(len(found)==1 and tomllib.loads(blocks[found[0]])['plugin']==selected,'Exact standalone family block required')
    replacement_entry=dict(name='mrlap',git=REMOTE,rev=REVISION,subdir='plugins/mrlap')
    blocks[found[0]]='[[plugin]]\n'+''.join(key+' = '+json.dumps(value)+'\n' for key,value in replacement_entry.items())+'\n'
    replacement=''.join(blocks).encode()
    expected=[replacement_entry if row['name']=='mrlap' else row for row in parsed['plugin']]
    require(tomllib.loads(replacement.decode())['plugin']==expected,'Unrelated plugin configuration changed')
    runtime=state/'plugins/runtime/mrlap'
    require(runtime.is_symlink() and runtime.resolve()==PLUGINS/'plugins/mrlap','Expected mutable runtime link changed')
    old_link=os.readlink(runtime)
    cache=runtime.parent/'.git-sources'/hashlib.sha256(REMOTE.encode()).hexdigest()/REVISION
    environment=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_OPTIONAL_LOCKS='0',GIT_NO_REPLACE_OBJECTS='1')
    for key in ['GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES']:
        environment.pop(key,None)

    def git(*arguments):
        response=subprocess.run(['git','-c','credential.helper=','-c','core.askPass=','-C',str(cache),*arguments],
            env=environment,capture_output=True,timeout=180)
        require(response.returncode==0,'Pinned source-cache operation failed: '+arguments[0])
        return response.stdout

    if not cache.exists():
        cache.mkdir(parents=True,mode=0o700)
        git('init')
        git('remote','add','origin',REMOTE)
        git('sparse-checkout','init','--cone')
        git('sparse-checkout','set','plugins/mrlap')
        git('fetch','--depth=1','--filter=blob:none','origin',REVISION)
        git('checkout','--detach',REVISION)
    require(cache.resolve()==cache and not (cache/'.git/objects/info/alternates').exists()
        and git('rev-parse','HEAD').decode().strip()==REVISION and git('remote','get-url','origin').decode().strip()==REMOTE
        and not git('status','--porcelain').strip(),'Pinned selected source cache is not independent and clean')
    source=cache/'plugins/mrlap'
    source_hashes={name.split('plugins/mrlap/',1)[1]:digest for name,digest in proof['source_sha256'].items() if name.startswith('plugins/mrlap/')}
    require(set(source_hashes)=={'manifest.toml','scripts/mrlap.sh'}
        and all(sha(source/name)==digest for name,digest in source_hashes.items()),'Published cache differs from tested selected files')
    require(tomllib.loads((source/'manifest.toml').read_text())['image']['reference']==IMAGE,'Pinned selected image differs')
    profile_file=state/'qualified-image-store.json'
    old_profile=profile_file.read_bytes()
    profile=json.loads(old_profile)
    require(IMAGE not in profile['images'],'Reference already enrolled; reconcile rather than repeating a deployment')
    profile['images'].append(IMAGE)
    new_profile=(json.dumps(profile,indent=2)+'\n').encode()
    primary=profile['primary']
    backend=['--root',primary['graphroot'],'--runroot',primary['runroot'],'--tmpdir',primary['runroot']+'/libpod-tmp',
        '--storage-driver',primary['driver'],'--cgroup-manager=cgroupfs']
    delegate=Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    direct=[str(delegate),'--storage-opt','additionalimagestore='+profile['additional']['path'],*backend]
    inspection=subprocess.run([*direct,'image','inspect',IMAGE],capture_output=True,timeout=60)
    require(inspection.returncode==0,'New exact reference is not already cached; no implicit pull')
    image=json.loads(inspection.stdout)
    require(len(image)==1 and image[0]['Id']==CONFIG_ID and IMAGE in image[0]['RepoDigests'],'Cached replacement identity differs')
    scoped=json.loads(new_profile)
    scoped.update(images=[IMAGE],delegate=dict(path=str(delegate),sha256=sha(delegate)))
    scoped_profile=output/'managed-image-profile.json'
    save(scoped_profile,scoped)
    scoped_profile.chmod(0o600)
    adapter=Path.home()/'.local/lib/autonomics/qualified-podman'/ADAPTER_SHA/'podman'
    require(sha(adapter)==ADAPTER_SHA,'Qualified image adapter changed')
    program='stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("MRlap"))=="0.0.3.3",as.character(packageVersion("TwoSampleMR"))=="0.7.11",as.character(packageVersion("GenomicSEM"))=="0.0.5");cat("PINNED_PACKAGE_VERSIONS_PASS\\n")'
    try:
        probe=subprocess.run([str(adapter),*backend,'run','--rm','--pull=never','--network=none','--read-only',
            '--cpus=1','--memory=512m','--pids-limit=64','--tmpfs=/tmp:rw,nosuid,nodev,size=32m',
            '--entrypoint=Rscript',IMAGE,'--vanilla','-e',program],capture_output=True,timeout=90,
            env=dict(os.environ,AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(scoped_profile)))
        (output/'version-probe.stdout').write_bytes(probe.stdout)
        (output/'version-probe.stderr').write_bytes(probe.stderr)
        require(probe.returncode==0 and b'PINNED_PACKAGE_VERSIONS_PASS' in probe.stdout,'New exact reference could not run pinned package metadata probe')
    finally:
        stopped(direct,Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']),output,1)
    before=live.request_metadata('gateway/status')
    executable=Path('/proc')/str(before['pid'])/'exe'
    require(sha(executable)==BINARY_SHA,'Resident executable changed; no implicit binary upgrade')
    preview=executable.resolve().parent.parent/'preview'
    nodes=live.request_metadata('nodes')
    require(len(nodes['nodes'])==660,'Runtime node denominator changed')
    keyed_nodes={row['address']:row for row in nodes['nodes']}

    def agents():
        return sorted([(row['agent_id'],row['name'],row['status']['kind']) for row in live.request_metadata('agents')])

    agent_before=agents()
    time.sleep(3)
    require(agent_before==agents() and all(row[2]=='idle' for row in agent_before),'Agents are not stably idle; source prepared but do not cut over')
    require(configuration.read_bytes()==original and profile_file.read_bytes()==old_profile and os.readlink(runtime)==old_link,
        'Deployment inputs changed concurrently')
    panel_hash=sha(state/'panels/index.json')
    (output/'plugins-before.toml').write_bytes(original)
    (output/'image-profile-before.json').write_bytes(old_profile)
    save(output/'preflight.json',dict(gateway=before,registered_addresses=660,agents=agent_before,
        revision=REVISION,source_sha256=source_hashes,old_link=old_link,new_source=str(source),panels_sha256=panel_hash))
    require(agent_before==agents(),'Agent state changed immediately before graceful stop')
    halt=subprocess.run([str(preview),'--','serve','stop'],capture_output=True,timeout=45)
    (output/'stop.stdout').write_bytes(halt.stdout)
    (output/'stop.stderr').write_bytes(halt.stderr)
    require(halt.returncode==0,'Graceful stop refused; no forced kill')
    deadline=time.monotonic()+45
    while (Path('/proc')/str(before['pid'])).exists() and time.monotonic()<deadline:
        time.sleep(1)
    require(not (Path('/proc')/str(before['pid'])).exists(),'Old gateway persists; no database intervention or duplicate start')
    deploy.replace_bytes(configuration,original,replacement,stat.S_IMODE(information.st_mode))
    deploy.replace_bytes(profile_file,old_profile,new_profile,0o600)
    pending=runtime.with_name('.mrlap-registry-pin-'+str(os.getpid()))
    require(not os.path.lexists(pending) and os.readlink(runtime)==old_link,'Concurrent runtime-link change')
    pending.symlink_to(source,target_is_directory=True)
    os.replace(pending,runtime)
    restarted=subprocess.run(['systemctl','--user','restart',UNIT],capture_output=True,timeout=180)
    save(output/'restart-result.json',dict(actual_exit=restarted.returncode))
    require(restarted.returncode==0,'Persistent service restart failed; retain diagnostics, do not alter database files')
    deadline=time.monotonic()+120
    after=None
    while time.monotonic()<deadline:
        try:
            candidate=live.request_metadata('gateway/status')
            if candidate['pid']!=before['pid']:
                after=candidate
                break
        except (OSError,ValueError):
            pass
        time.sleep(2)
    require(after is not None,'New authenticated gateway did not become ready')
    current_nodes=live.request_metadata('nodes')
    require({row['address']:row for row in current_nodes['nodes']}==keyed_nodes and agents()==agent_before,
        'Node metadata or visible agent identities/states changed')
    loaded=next(row for row in live.request_metadata('plugins')['plugins'] if row['name']=='mrlap')
    require(loaded['registered'] and loaded['error'] is None and loaded['image']==IMAGE
        and loaded['source']['git']==REMOTE and loaded['source']['rev']==REVISION
        and loaded['source']['subdir']=='plugins/mrlap' and not loaded['source']['path'], 'Exact immutable selected source is not resident-loaded')
    new_executable=Path('/proc')/str(after['pid'])/'exe'
    require(sha(new_executable)==BINARY_SHA and runtime.resolve()==source
        and configuration.read_bytes()==replacement and profile_file.read_bytes()==new_profile
        and all(sha(source/name)==digest for name,digest in source_hashes.items())
        and sha(state/'panels/index.json')==panel_hash,'Binary/source/configuration/panels changed during cutover')
    cgroup=(Path('/proc')/str(after['pid'])/'cgroup').read_text()
    require(UNIT in cgroup and 'autonomics-validation-' not in cgroup,'Production service uses acceptance ownership')
    process_environment=dict(item.split(b'=',1) for item in (Path('/proc')/str(after['pid'])/'environ').read_bytes().split(b'\0') if b'=' in item)
    require(not any(key.startswith(b'AUTONOMICS_VALIDATION_') for key in process_environment), 'Production inherited disposable worker environment')
    process_environment.clear()
    report=dict(schema='MRLAP_IMMUTABLE_SOURCE_AND_REGISTRY_REPIN_DEPLOYMENT_V1',deployed=True,
        revision=REVISION,source_sha256=source_hashes,image=IMAGE,image_config=CONFIG_ID,
        old_pid=before['pid'],new_pid=after['pid'],unchanged_binary_sha256=BINARY_SHA,
        registered_addresses=660,all_prior_node_metadata_preserved=True,
        visible_agent_ids_names_and_idle_states_preserved=len(agent_before),
        mutable_path_replaced_with_exact_git_revision=True,new_exact_image_reference_enrolled=True,
        all_previous_image_references_preserved=True,images_pulled=0,images_rebuilt=0,
        version_only_container_executed_and_stopped=True,new_statistical_method_executions=0,
        actual_resident_statistical_DAG_claimed=False,new_software_admissions=0,
        scientific_release_granted=False,g0_granted=False,live_database_opened=False,
        database_WAL_or_SHM_moved_or_deleted=False,frozen_study_configuration_changed=False)
    save(output/'verification.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
