"""Managed minimal official HEAD canaries; never download/reparse the GMT."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = Path(__file__).resolve().parents[2]
FAMILY = Path(__file__).resolve().parent
URL = 'https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/h.all.v2025.1.Hs.symbols.gmt'
CANARY = '''import json,os,requests
from urllib.parse import urlsplit
url = %r
proxies = requests.utils.get_environ_proxies(url)
selected = requests.utils.select_proxy(url, proxies)
record = dict(method='HEAD', url=url, requests_version=requests.__version__,
              effective_proxy_present=bool(selected),
              effective_proxy_loopback=urlsplit(selected or '').hostname in ('127.0.0.1','localhost','::1'),
              no_proxy=os.environ.get('no_proxy') == 'data.broadinstitute.org',
              NO_PROXY=os.environ.get('NO_PROXY') == 'data.broadinstitute.org',
              tls_verification=True, redirects_followed=False, response_body_bytes_read=0,
              status='NOT_RECEIVED', complete_file_sha256='NOT_DOWNLOADED',
              complete_file_bytes='NOT_DOWNLOADED', GMT_parsed=False)
try:
    with requests.Session() as session:
        with session.head(url,allow_redirects=False,timeout=(8,15),
                          headers={'Accept-Encoding':'identity','User-Agent':'autonomics-msigdb-transport-canary/1'}) as response:
            record.update(status=response.status_code, content_length=response.headers.get('Content-Length'),
                          content_type=response.headers.get('Content-Type'))
except requests.RequestException as error:
    record['error_class'] = type(error).__name__
print(json.dumps(record))
''' % URL


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(sys.argv[1:] in ([], ['--installed']), 'Only --installed is supported')
    installed = sys.argv[1:] == ['--installed']
    selected = Path.home()/'.autonomics/plugins/runtime/cachexia-msigdb' if installed else FAMILY
    if installed:
        require(all(sha(selected/name)==sha(FAMILY/name) for name in ('manifest.toml','scripts/gmt.py')),
                'Installed MSigDB source differs from the reviewed candidate; do not run canary')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'msigdb-node-network-candidate'
    output.mkdir(mode=0o700)
    snapshot = dict(os.environ)
    protected = [Path.home()/'.autonomics/plugins.toml', Path.home()/'.autonomics/qualified-image-store.json',
                 Path.home()/'.autonomics/plugins/runtime/cachexia-msigdb/manifest.toml',
                 Path.home()/'.autonomics/plugins/runtime/cachexia-msigdb/scripts/gmt.py']
    before = {str(path): sha(path) for path in protected}
    for name in ('manifest.toml', 'scripts/gmt.py', 'README.md', 'prove_network_candidate.py'):
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        origin = selected/name if name in ('manifest.toml', 'scripts/gmt.py') else FAMILY/name
        target.write_bytes(origin.read_bytes())
    for name in ('test_msigdb_network.py', 'test_msigdb_publication.py'):
        (output / name).write_bytes((PLUGINS/'tests'/name).read_bytes())
    prior_diff = subprocess.run(['git','-C',str(PLUGINS),'diff','--','research-adapters/cachexia-msigdb/scripts/gmt.py',
                                'research-adapters/cachexia-msigdb/README.md'],capture_output=True,check=True)
    (output/'preexisting-gmt-readme.diff').write_bytes(prior_diff.stdout)
    tests = subprocess.run([sys.executable,'-B','-m','unittest','test_msigdb_network','-v'],
                           cwd=PLUGINS/'tests',capture_output=True,timeout=30)
    (output/'network-unit-tests.log').write_bytes(tests.stdout+tests.stderr)
    require(tests.returncode == 0, 'Transport policy unit tests failed')
    manifest = tomllib.loads((selected/'manifest.toml').read_text())
    image = manifest['image']['reference']
    online = next(node for node in manifest['nodes'] if node['kind']=='cachexia_msigdb_gmt')
    policy = online['command']['env']
    original_profile = json.loads(protected[1].read_text())
    require(image in original_profile['images'], 'Pinned image must already be qualified')
    require(image not in original_profile.get('drop_host_proxy_for_images',[]), 'Unexpected image-wide proxy bypass')
    profile = dict(original_profile)
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile.update(images=[image], delegate={'path':str(delegate),'sha256':sha(delegate)})
    profile['drop_host_proxy_for_images'] = []
    spec = importlib.util.spec_from_file_location('qualified_router',ROOT/'scripts/podman_qualified_image_store.py')
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    primary = profile['primary']
    backend = ['--root',primary['graphroot'],'--runroot',primary['runroot'],
               '--tmpdir',primary['runroot']+'/libpod-tmp','--storage-driver',primary['driver'],
               '--cgroup-manager=cgroupfs']

    def run(arguments, timeout=45):
        command, env = router.execution(backend+arguments,os.environ,profile)
        return subprocess.run(command,env=env,capture_output=True,timeout=timeout)

    inspection = run(['image','inspect',image])
    require(inspection.returncode == 0, 'Pinned image unavailable; no pull allowed')
    metadata = json.loads(inspection.stdout)[0]
    save(output/'image-identity.json',dict(image=image,Id=metadata['Id'],RepoDigests=metadata['RepoDigests']))
    observations = []
    cases = [('candidate-node-env',policy)] if installed else [('current-inherited',{}),('candidate-node-env',policy)]
    for label, environment in cases:
        name = 'msigdb-'+permanent.parent.name[:12]+'-'+label
        arguments = ['create','--name',name,'--pull=never','--network=default','--cpus=1',
                     '--memory=512m','--read-only']
        for key,value in environment.items():
            arguments += ['--env',key+'='+value]
        arguments += [image,'python3','-c',CANARY]
        created = run(arguments)
        require(created.returncode == 0, 'Canary creation failed; private session diagnostics retained')
        try:
            executed = run(['start','--attach',name],timeout=40)
            require(executed.returncode == 0, 'Canary subprocess failed')
            record = json.loads(executed.stdout)
            inspected = run(['inspect',name])
            require(inspected.returncode == 0, 'Owned canary state unavailable')
            information = json.loads(inspected.stdout)[0]
            require(not information['State']['Running'] and information['State']['ExitCode']==0,
                    'Canary worker must stop successfully')
            actual = dict(entry.split('=',1) for entry in information['Config']['Env'] if '=' in entry)
            record.update(case=label,container_exit_code=information['State']['ExitCode'],
                          manifest_environment_reached_container=all(actual.get(k)==v for k,v in environment.items()),
                          network_mode=information['HostConfig']['NetworkMode'],image_id=information['Image'])
            require(record['manifest_environment_reached_container'],'Candidate environment filtered before container')
            if label=='candidate-node-env':
                require(not record['effective_proxy_present'] and record['no_proxy'] and record['NO_PROXY'],
                        'Candidate official-domain proxy policy ineffective')
            observations.append(record)
            save(output/(label+'.json'),record)
        finally:
            removed = run(['rm',name])
            require(removed.returncode==0,'Owned stopped canary removal failed')
    after = {str(path):sha(path) for path in protected}
    require(before==after and snapshot==dict(os.environ),'Protected configuration or parent environment changed')
    retained = run(['ps','-a','--filter','label=autonomics.validation.session='+permanent.parent.name,'--format=json'])
    require(retained.returncode==0 and json.loads(retained.stdout)==[],'Session container remains')
    save(output/'verification.json',dict(schema='MSIGDB_NODE_TRANSPORT_CANDIDATE_V1',
        image=image,source_hashes={name:sha(FAMILY/name) for name in ('manifest.toml','scripts/gmt.py')},
        protected_hashes_before=before,protected_hashes_after=after,parent_environment_unchanged=True,
        container_canaries=observations,unit_tests=2,requests_environment_matrix_cases=9,
        owned_containers_removed=len(cases),full_resource_downloads=0,full_GMT_parses=0,
        selected_source=str(selected),installed_source_identity_checked=installed,
        production_deployed=False,resident_acceptance='PENDING',scientific_release_granted=False,g0_granted=False))
    print(json.dumps({'evidence':str(output),'observations':observations}))


if __name__=='__main__':
    main()
