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


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = ROOT.parent / 'autonomics-plugins'
REVISION = 'ab7c254e02c8e010e13cabe69e16060d8de05c7a'
REMOTE = 'https://github.com/ZJ-2002/autonomics-plugins.git'
BINARY_SHA = '5a3131bedb394043045b4f11ae541c183cecf3cc36069e188cc981e9d64aea27'
UNIT = 'autonomics-gateway-registry-20261019.service'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(filename):
    with filename.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0, str(PLUGINS))
    from tools.reconcile_ab_evidence_index import verify_archive
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    verified = verify_archive(archives, '11ffa6758fa04b73b133ff2b36b8c391',
        'c93df1d1273294100ad9bbc11bf2223f7bd0e8868edc230122b11417728c19f1')
    require(verified['positive_worker_exit_verified'], 'Source audit not successful')
    audit_path = Path(verified['artifact_root']) / 'permanent/selected-mutable-source-audit/verification.json'
    require(sha(audit_path) == '687507f1fe5833fb679017339f632a5c2e4e13e45c28bf5a789216548002d627', 'Source audit identity differs')
    audit = json.loads(audit_path.read_bytes())
    candidates = [row for row in audit['rows'] if row['status'] == 'BYTE_IDENTICAL_PIN_CANDIDATE']
    require(len(candidates) == 12 and audit['published_revision'] == REVISION, 'Exact audited candidate set required')
    selected = {row['family']: row for row in candidates}
    state = Path.home() / '.autonomics'
    configuration = state / 'plugins.toml'
    metadata = configuration.lstat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
            and metadata.st_nlink == 1 and not metadata.st_mode & 0o022, 'Owner-controlled source configuration required')
    original = configuration.read_bytes()
    parsed = tomllib.loads(original.decode())
    require(set(parsed) == {'plugin'} and len(parsed['plugin']) == 103
        and all(set(row) <= {'name', 'path', 'git', 'rev', 'subdir', 'local_commit', 'local_digest'} for row in parsed['plugin']),
        'Unknown source configuration must be reviewed before retaining backup')
    require(all(not urlsplit(row.get('git') or '').username and not urlsplit(row.get('git') or '').password
                for row in parsed['plugin']), 'Credential-bearing source URL must not enter evidence')
    replacements = {name: dict(name=name, git=REMOTE, rev=REVISION, subdir=row['subdir']) for name, row in selected.items()}
    blocks = re.split(r'(?m)(?=^\[\[plugin\]\])', original.decode())
    for name, row in selected.items():
        found = [index for index, block in enumerate(blocks)
                 if re.search(r'(?m)^name\s*=\s*' + re.escape(json.dumps(name)) + r'\s*$', block)]
        require(len(found) == 1, 'Unique standalone plugin block required')
        require(tomllib.loads(blocks[found[0]])['plugin'] == [dict(name=name, path=str(PLUGINS / row['subdir']))],
                'Selected source configuration changed')
        blocks[found[0]] = '[[plugin]]\n' + ''.join(key + ' = ' + json.dumps(value) + '\n'
            for key, value in replacements[name].items()) + '\n'
    replacement = ''.join(blocks).encode()
    require(tomllib.loads(replacement.decode())['plugin'] == [replacements.get(row['name'], row) for row in parsed['plugin']],
            'Unselected configuration changed')
    runtime = state / 'plugins/runtime'
    links = {}
    for name, row in selected.items():
        target = runtime / name
        require(target.is_symlink() and target.resolve() == PLUGINS / row['subdir'], 'Expected selected runtime link changed')
        links[name] = os.readlink(target)
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'selected-plugin-source-pin-deployment'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    cache = runtime / '.git-sources' / hashlib.sha256(REMOTE.encode()).hexdigest() / REVISION
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')
    for key in ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES']:
        environment.pop(key, None)

    def git(*arguments):
        result = subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.askPass=', '-C', str(cache), *arguments],
                                env=environment, capture_output=True, timeout=180)
        require(result.returncode == 0, 'Immutable source cache operation failed: ' + arguments[0])
        return result.stdout

    if not cache.exists():
        cache.mkdir(mode=0o700, parents=True)
        git('init')
        git('remote', 'add', 'origin', REMOTE)
        git('sparse-checkout', 'init', '--cone')
        git('sparse-checkout', 'set', *[row['subdir'] for row in candidates])
        git('fetch', '--depth=1', '--filter=blob:none', 'origin', REVISION)
        git('checkout', '--detach', REVISION)
    require(cache.resolve() == cache and not (cache / '.git/objects/info/alternates').exists()
        and git('rev-parse', 'HEAD').decode().strip() == REVISION
        and git('remote', 'get-url', 'origin').decode().strip() == REMOTE and not git('status', '--porcelain').strip(),
        'Source cache must remain independent and clean')

    def check_sources():
        for row in candidates:
            for record in row['tracked_files']:
                for location in [PLUGINS / record['path'], cache / record['path']]:
                    require(location.is_file() and not location.is_symlink()
                        and location.stat().st_size == record['bytes'] and sha(location) == record['sha256'],
                        'Audited source bytes changed before cutover')
            require(tomllib.loads((cache / row['subdir'] / 'manifest.toml').read_text())['image']['reference'] == row['image'],
                    'Selected image reference changed')

    check_sources()
    live = load('live', ROOT / 'results/cachexia-v4.3.2/reload_two_official_ab_plugins_20261019.py')
    deploy = load('deploy', ROOT / 'results/cachexia-v4.3.2/deploy_static_ports_and_rstats_20261021.py')
    before = live.request_metadata('gateway/status')
    executable = Path('/proc') / str(before['pid']) / 'exe'
    require(sha(executable) == BINARY_SHA, 'Resident binary changed; no implicit upgrade')
    preview = executable.resolve().parent.parent / 'preview'
    nodes = {row['address']: row for row in live.request_metadata('nodes')['nodes']}
    require(len(nodes) == 660, 'Node denominator changed')

    def agents():
        return sorted((row['agent_id'], row['name'], row['status']['kind']) for row in live.request_metadata('agents'))

    agent_before = agents()
    time.sleep(3)
    require(agent_before == agents() and all(row[2] == 'idle' for row in agent_before), 'Agents not stably idle; no cutover')
    profile = state / 'qualified-image-store.json'
    panels = state / 'panels/index.json'
    profile_hash, panel_hash = sha(profile), sha(panels)
    require(configuration.read_bytes() == original and all(os.readlink(runtime / name) == value for name, value in links.items()),
            'Deployment configuration changed concurrently')
    (output / 'plugins-before.toml').write_bytes(original)
    (output / 'plugins-intended.toml').write_bytes(replacement)
    (output / 'preflight.json').write_text(json.dumps(dict(old_pid=before['pid'], families=sorted(selected),
        agents=agent_before, source_revision=REVISION, old_runtime_links=links), indent=2) + '\n')
    require(agents() == agent_before, 'Agent changed immediately before stop')
    halted = subprocess.run([str(preview), '--', 'serve', 'stop'], capture_output=True, timeout=45)
    require(halted.returncode == 0, 'Graceful stop refused; no forced kill')
    deadline = time.monotonic() + 45
    while (Path('/proc') / str(before['pid'])).exists() and time.monotonic() < deadline:
        time.sleep(1)
    require(not (Path('/proc') / str(before['pid'])).exists(), 'Old service persists; no duplicate start')
    deploy.replace_bytes(configuration, original, replacement, stat.S_IMODE(metadata.st_mode))
    for name, row in selected.items():
        require(os.readlink(runtime / name) == links[name], 'Concurrent runtime link change')
        pending = runtime / ('.source-pin-' + name + '-' + str(os.getpid()))
        require(not os.path.lexists(pending), 'Pending source link exists')
        pending.symlink_to(cache / row['subdir'], target_is_directory=True)
        os.replace(pending, runtime / name)
    restarted = subprocess.run(['systemctl', '--user', 'restart', UNIT], capture_output=True, timeout=180)
    require(restarted.returncode == 0, 'Service restart failed; retain diagnostics without database intervention')
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
    require(after is not None, 'New authenticated service not ready')
    require({row['address']: row for row in live.request_metadata('nodes')['nodes']} == nodes
            and agents() == agent_before, 'Visible node or agent metadata changed')
    registered = {row['name']: row for row in live.request_metadata('plugins')['plugins']}
    for name, row in selected.items():
        plugin = registered[name]
        require(plugin['registered'] and plugin['error'] is None and plugin['image'] == row['image']
            and plugin['source']['git'] == REMOTE and plugin['source']['rev'] == REVISION
            and plugin['source']['subdir'] == row['subdir'] and not plugin['source']['path']
            and (runtime / name).resolve() == cache / row['subdir'], 'Exact selected source not loaded')
    check_sources()
    require(configuration.read_bytes() == replacement and sha(profile) == profile_hash and sha(panels) == panel_hash
            and sha(Path('/proc') / str(after['pid']) / 'exe') == BINARY_SHA, 'Unexpected binary, source or resource change')
    cgroup = (Path('/proc') / str(after['pid']) / 'cgroup').read_text()
    require(UNIT in cgroup and 'autonomics-validation-' not in cgroup, 'Service depends on disposable acceptance ownership')
    process_environment = (Path('/proc') / str(after['pid']) / 'environ').read_bytes().split(b'\0')
    require(not any(entry.startswith(b'AUTONOMICS_VALIDATION_') or b'autonomics-validation-sessions/' in entry
                    for entry in process_environment), 'Service inherited disposable acceptance environment')
    process_environment.clear()
    report = dict(schema='SELECTED_PLUGIN_IMMUTABLE_SOURCE_DEPLOYMENT_V1', deployed=True,
        revision=REVISION, families=sorted(selected), immutable_source_families_loaded=len(selected),
        selected_source_files_verified=sum(len(row['tracked_files']) for row in candidates),
        old_pid=before['pid'], new_pid=after['pid'], unchanged_binary_sha256=BINARY_SHA,
        all_660_node_metadata_preserved=True, visible_agent_identities_and_idle_states_preserved=len(agent_before),
        unselected_configuration_entries_unchanged=91, images_or_reference_panels_changed=False,
        canonical_git_head_or_index_modified=False, live_database_opened=False, database_WAL_or_SHM_manipulated=False,
        statistical_methods_reexecuted=0, new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
