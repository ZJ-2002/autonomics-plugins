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


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = ROOT.parent / 'autonomics-plugins'
REVISION = 'dc9a56a0dc9404bd0d6c5c0e7af645f3439669b9'
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
    verified = verify_archive(archives, 'd8665fb9d7ec4ed0b32210e523d355e6',
        '812d0a3265280ada6d5c8de6c2777be9d520b1c963493dee853a073a2fc78021')
    require(verified['positive_worker_exit_verified'], 'Shared source repair not successful')
    proof_path = Path(verified['artifact_root']) / 'permanent/shared-mrlap-reference-repair/verification.json'
    require(sha(proof_path) == '645ba20f28a3d6b3b984d6d3a6d65bb3ece5fe45b4902e8be02a3e1adf5a147a', 'Shared repair proof identity differs')
    proof = json.loads(proof_path.read_bytes())
    selected = {row['family']: row for row in proof['families']
                if row['deployed_source_matches_base_before_image_delta'] is True}
    require(set(selected) == {'donor-composition-official', 'frozen-a-family-adjustment', 'frozen-a-harmonisation',
        'r-stats', 'r-stats-lm', 'twosamplemr-v432-a'}, 'Exact six general source families required')
    state = Path.home() / '.autonomics'
    configuration = state / 'plugins.toml'
    information = configuration.lstat()
    require(stat.S_ISREG(information.st_mode) and information.st_uid == os.getuid()
        and information.st_nlink == 1 and not information.st_mode & 0o022, 'Owner-controlled source configuration required')
    original = configuration.read_bytes()
    parsed = tomllib.loads(original.decode())
    require(set(parsed) == {'plugin'} and len(parsed['plugin']) == 103
        and all(set(row) <= {'name', 'path', 'git', 'rev', 'subdir', 'local_commit', 'local_digest'} for row in parsed['plugin']),
        'Review unknown configuration before backing it up')
    entries = {row['name']: row for row in parsed['plugin']}
    replacements = {}
    for name, row in selected.items():
        require(set(entries[name]) == {'name', 'git', 'rev', 'subdir'} and entries[name]['git'] == REMOTE
            and entries[name]['subdir'] == row['subdir'], 'Expected explicit Git source changed')
        replacements[name] = dict(entries[name], rev=REVISION)
    blocks = re.split(r'(?m)(?=^\[\[plugin\]\])', original.decode())
    for name in selected:
        found = [index for index, block in enumerate(blocks)
            if re.search(r'(?m)^name\s*=\s*' + re.escape(json.dumps(name)) + r'\s*$', block)]
        require(len(found) == 1 and tomllib.loads(blocks[found[0]])['plugin'] == [entries[name]], 'Unique expected source block required')
        blocks[found[0]] = '[[plugin]]\n' + ''.join(key + ' = ' + json.dumps(value) + '\n'
            for key, value in replacements[name].items()) + '\n'
    replacement = ''.join(blocks).encode()
    require(tomllib.loads(replacement.decode())['plugin'] == [replacements.get(row['name'], row) for row in parsed['plugin']],
            'Unselected plugin configuration changed')
    runtime = state / 'plugins/runtime'
    links = {name: os.readlink(runtime / name) for name in selected}
    old_sources = {name: (runtime / name).resolve(strict=True) for name in selected}
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'shared-mrlap-reference-deployment'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    cache = runtime / '.git-sources' / hashlib.sha256(REMOTE.encode()).hexdigest() / REVISION
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')
    for key in ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES']:
        environment.pop(key, None)

    def git(*arguments):
        result = subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.askPass=', '-C', str(cache), *arguments],
            env=environment, capture_output=True, timeout=180)
        require(result.returncode == 0, 'Immutable source-cache operation failed: ' + arguments[0])
        return result.stdout

    if not cache.exists():
        cache.mkdir(mode=0o700, parents=True)
        git('init')
        git('remote', 'add', 'origin', REMOTE)
        git('sparse-checkout', 'init', '--cone')
        git('sparse-checkout', 'set', *[row['subdir'] for row in selected.values()])
        git('fetch', '--depth=1', '--filter=blob:none', 'origin', REVISION)
        git('checkout', '--detach', REVISION)
    require(cache.resolve() == cache and not (cache / '.git/objects/info/alternates').exists()
        and git('rev-parse', 'HEAD').decode().strip() == REVISION
        and git('remote', 'get-url', 'origin').decode().strip() == REMOTE and not git('status', '--porcelain').strip(),
        'Source cache must be independent and clean')

    def check_sources(check_old):
        for name, row in selected.items():
            for filename, digest in row['source_sha256'].items():
                new = cache / filename
                require(new.is_file() and not new.is_symlink() and sha(new) == digest
                    and sha(PLUGINS / filename) == digest, 'Qualified selected source changed')
                if check_old:
                    old = old_sources[name] / Path(filename).relative_to(row['subdir'])
                    expected = new.read_bytes()
                    if filename.endswith('/manifest.toml'):
                        require(expected.count(proof['new_reference'].encode()) == 1, 'Exact single image replacement required')
                        expected = expected.replace(proof['new_reference'].encode(), proof['old_reference'].encode())
                    require(old.is_file() and not old.is_symlink() and old.read_bytes() == expected,
                            'Active source differs by more than qualified image alias')

    check_sources(True)
    require(proof['new_reference'] in json.loads((state / 'qualified-image-store.json').read_text())['images'],
            'Qualified replacement image must already be enrolled')
    live = load('live', ROOT / 'results/cachexia-v4.3.2/reload_two_official_ab_plugins_20261019.py')
    deploy = load('deploy', ROOT / 'results/cachexia-v4.3.2/deploy_static_ports_and_rstats_20261021.py')
    before = live.request_metadata('gateway/status')
    executable = Path('/proc') / str(before['pid']) / 'exe'
    require(sha(executable) == BINARY_SHA, 'Resident binary changed; no implicit upgrade')
    preview = executable.resolve().parent.parent / 'preview'
    nodes = {row['address']: row for row in live.request_metadata('nodes')['nodes']}
    plugins_before = {row['name']: row for row in live.request_metadata('plugins')['plugins']}
    require(len(nodes) == 660, 'Node denominator changed')

    def agents():
        return sorted((row['agent_id'], row['name'], row['status']['kind']) for row in live.request_metadata('agents'))

    agent_before = agents()
    time.sleep(3)
    require(agents() == agent_before and all(row[2] == 'idle' for row in agent_before), 'Agents not stably idle; no cutover')
    profile_hash, panel_hash = sha(state / 'qualified-image-store.json'), sha(state / 'panels/index.json')
    require(configuration.read_bytes() == original and all(os.readlink(runtime / name) == link for name, link in links.items()),
            'Concurrent deployment configuration change')
    (output / 'plugins-before.toml').write_bytes(original)
    (output / 'plugins-intended.toml').write_bytes(replacement)
    require(agents() == agent_before, 'Agent changed immediately before graceful stop')
    halted = subprocess.run([str(preview), '--', 'serve', 'stop'], capture_output=True, timeout=45)
    require(halted.returncode == 0, 'Graceful stop refused; no forced kill')
    deadline = time.monotonic() + 45
    while (Path('/proc') / str(before['pid'])).exists() and time.monotonic() < deadline:
        time.sleep(1)
    require(not (Path('/proc') / str(before['pid'])).exists(), 'Old service persists; do not start duplicate or alter database')
    deploy.replace_bytes(configuration, original, replacement, stat.S_IMODE(information.st_mode))
    for name, row in selected.items():
        require(os.readlink(runtime / name) == links[name], 'Concurrent source link change')
        pending = runtime / ('.shared-image-pin-' + name + '-' + str(os.getpid()))
        require(not os.path.lexists(pending), 'Pending source link exists')
        pending.symlink_to(cache / row['subdir'], target_is_directory=True)
        os.replace(pending, runtime / name)
    restarted = subprocess.run(['systemctl', '--user', 'restart', UNIT], capture_output=True, timeout=180)
    require(restarted.returncode == 0, 'Persistent restart failed; retain state without database intervention')
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
        and agents() == agent_before, 'Node metadata or visible agent states changed')
    loaded = {row['name']: row for row in live.request_metadata('plugins')['plugins']}
    for name, row in selected.items():
        plugin = loaded[name]
        require(plugin['registered'] and plugin['error'] is None and plugin['image'] == proof['new_reference']
            and plugin['source']['git'] == REMOTE and plugin['source']['rev'] == REVISION
            and plugin['source']['subdir'] == row['subdir'] and not plugin['source']['path']
            and (runtime / name).resolve() == cache / row['subdir'], 'Qualified replacement not resident loaded')
    for name, plugin in plugins_before.items():
        if name not in selected:
            require(all(loaded[name][key] == plugin[key] for key in ['image', 'source', 'registered', 'error']),
                    'Unselected loaded plugin changed')
    check_sources(False)
    require(configuration.read_bytes() == replacement and sha(state / 'qualified-image-store.json') == profile_hash
        and sha(state / 'panels/index.json') == panel_hash
        and sha(Path('/proc') / str(after['pid']) / 'exe') == BINARY_SHA, 'Unexpected source, binary or resource change')
    cgroup = (Path('/proc') / str(after['pid']) / 'cgroup').read_text()
    require(UNIT in cgroup and 'autonomics-validation-' not in cgroup, 'Production depends on acceptance ownership')
    process_environment = (Path('/proc') / str(after['pid']) / 'environ').read_bytes().split(b'\0')
    require(not any(entry.startswith(b'AUTONOMICS_VALIDATION_') or b'autonomics-validation-sessions/' in entry
        for entry in process_environment), 'Production inherited disposable acceptance environment')
    process_environment.clear()
    remaining = sorted(name for name, row in loaded.items() if row['image'] == proof['old_reference'])
    report = dict(schema='SHARED_MRLAP_REFERENCE_RESIDENT_DEPLOYMENT_V1', deployed=True,
        revision=REVISION, families=sorted(selected), old_pid=before['pid'], new_pid=after['pid'],
        unchanged_binary_sha256=BINARY_SHA, all_660_node_metadata_preserved=True,
        visible_agent_identities_and_idle_states_preserved=len(agent_before),
        unselected_plugin_configuration_entries_preserved=97, qualified_image_profile_and_panels_unchanged=True,
        selected_sources_differ_only_by_qualified_image_reference=True,
        remaining_retired_reference_families_not_modified=remaining,
        frozen_study_launchers_modified=False, statistical_methods_reexecuted=0,
        new_image_downloads=0, new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
