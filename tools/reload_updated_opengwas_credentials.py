import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


ROOT = Path('/home/zj-normal/Work/autonomics')
UNIT = 'autonomics-gateway-registry-20261019.service'
BINARY_SHA = '5a3131bedb394043045b4f11ae541c183cecf3cc36069e188cc981e9d64aea27'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, address):
        return None


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'opengwas-credential-resident-reload'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    source = subprocess.run(['git', '-C', str(ROOT), 'show',
        '0a2b87e17261b0ecf80c151568fdffada3058297:scripts/research_preview_launch.py'],
        check=True, capture_output=True, timeout=30).stdout
    require(hashlib.sha256(source).hexdigest() == 'c0a142a9a4b1264208c8b4c3c6ac15b44ebd0979c200142225188b75f56d2a60', 'Pinned loader changed')
    namespace = dict(__name__='credential_reload', __file__=str(ROOT / 'scripts/research_preview_launch.py'))
    exec(compile(source, '<pinned-loader>', 'exec'), namespace)
    credentials, metadata = namespace['credentials_environment']({})
    token = credentials.get('OPENGWAS_TOKEN', '').strip()
    require(token and credentials.get('OPENGWAS_JWT', '').strip() == token, 'Private JWT variables must be configured consistently')
    specification = importlib.util.spec_from_file_location('live', ROOT / 'results/cachexia-v4.3.2/reload_two_official_ab_plugins_20261019.py')
    live = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(live)
    before = live.request_metadata('gateway/status')
    executable = Path('/proc') / str(before['pid']) / 'exe'
    require(sha(executable) == BINARY_SHA, 'Binary changed; no implicit upgrade')
    preview = executable.resolve().parent.parent / 'preview'
    nodes = {row['address']: row for row in live.request_metadata('nodes')['nodes']}
    require(len(nodes) == 660, 'Node denominator changed')
    state = Path.home() / '.autonomics'
    source_files = [state / 'plugins.toml', state / 'qualified-image-store.json', state / 'panels/index.json']
    source_hashes = [sha(path) for path in source_files]

    def agents():
        return sorted((row['agent_id'], row['name'], row['status']['kind']) for row in live.request_metadata('agents'))

    previous_agents = agents()
    time.sleep(3)
    require(agents() == previous_agents and all(row[2] == 'idle' for row in previous_agents), 'Agents not stably idle; leave production running')
    require(agents() == previous_agents, 'Agents changed immediately before stop')
    halted = subprocess.run([str(preview), '--', 'serve', 'stop'], capture_output=True, timeout=45)
    require(halted.returncode == 0, 'Graceful stop refused; no forced kill')
    deadline = time.monotonic() + 45
    while (Path('/proc') / str(before['pid'])).exists() and time.monotonic() < deadline:
        time.sleep(1)
    require(not (Path('/proc') / str(before['pid'])).exists(), 'Old process persists; no duplicate start or database manipulation')
    restarted = subprocess.run(['systemctl', '--user', 'restart', UNIT], capture_output=True, timeout=180)
    require(restarted.returncode == 0, 'Persistent service restart failed')
    deadline = time.monotonic() + 120
    after = None
    while time.monotonic() < deadline:
        try:
            candidate = live.request_metadata('gateway/status')
            if candidate['pid'] != before['pid']:
                after = candidate
                break
        except (OSError, ValueError):
            pass
        time.sleep(2)
    require(after is not None, 'New authenticated service did not become ready')
    process_root = Path('/proc') / str(after['pid'])
    process = dict(entry.split(b'=', 1) for entry in (process_root / 'environ').read_bytes().split(b'\0') if b'=' in entry)
    matched = process.get(b'OPENGWAS_TOKEN') == token.encode() and process.get(b'OPENGWAS_JWT') == token.encode()
    require(matched, 'Running credential values do not match private file; do not declare rotation complete')
    require(not any(name.startswith(b'AUTONOMICS_VALIDATION_') for name in process), 'Production inherited acceptance ownership')
    request = urllib.request.Request('https://api.opengwas.io/api/user',
        headers={'Authorization': 'Bearer ' + process[b'OPENGWAS_TOKEN'].decode(), 'Accept': 'application/json'})
    authentication = dict(actual_requests=1, user_response_body_saved=False)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
            raw = response.read(65537)
            require(len(raw) <= 65536, 'Bounded user response required')
            document = json.loads(raw)
            authentication.update(HTTP_status=response.status,
                valid_user_object=isinstance(document, dict) and bool(document) and 'error' not in document)
    except urllib.error.HTTPError as error:
        authentication.update(HTTP_status=error.code, valid_user_object=False)
    except (OSError, ValueError):
        authentication.update(HTTP_status=None, valid_user_object=False)
    process.clear()
    credentials.clear()
    token = ''
    require({row['address']: row for row in live.request_metadata('nodes')['nodes']} == nodes
        and agents() == previous_agents and [sha(path) for path in source_files] == source_hashes
        and sha(process_root / 'exe') == BINARY_SHA, 'Unexpected source, binary, node or agent change')
    cgroup = (process_root / 'cgroup').read_text()
    require(UNIT in cgroup and 'autonomics-validation-' not in cgroup, 'Production must remain outside disposable worker cgroup')
    report = dict(schema='OPENGWAS_RESIDENT_CREDENTIAL_ROTATION_V1', old_pid=before['pid'], new_pid=after['pid'],
        private_file_both_variables_loaded=True, resident_credential_authentication=authentication,
        all_660_node_metadata_preserved=True, visible_agent_ids_names_and_idle_states_preserved=len(previous_agents),
        binary_plugins_image_profile_and_panels_unchanged=True, private_credential_file_modified=False,
        credential_values_or_hashes_saved=False, live_database_opened=False, database_WAL_or_SHM_manipulated=False,
        new_gwas_data_queries=0, new_method_executions=0, new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    require(authentication.get('HTTP_status') == 200 and authentication['valid_user_object'], 'Resident token authentication not verified')


if __name__ == '__main__':
    main()
