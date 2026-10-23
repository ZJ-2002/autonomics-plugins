"""Managed, credential-free loader negatives for the deployment candidate.

Synthetic positive-path probes stop at a non-Podman create sentinel.
No container, OpenGWAS network API call, or author method is executed. Gateway reads are
limited to resident/plugin identity; no database is opened.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import secrets
import stat
import subprocess
import sys
import urllib.request

ROOT = Path('/home/zj-normal/Work/autonomics')
FAMILY = Path(__file__).resolve().parents[1]
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
CONSUMER_SESSION = '3de5533e881144d1b1643c4fd648ef7b'
CONSUMER_SEAL = '835bcb4368da6bccf05abf5dac61e51f88e71cfafa510851d2d6ac99d0082314'
CONSUMER_SHA = 'e289d372b8d0abd84e4371ce48b9091eb41965d5de1985865286a2f5bb09537a'
ENGINE_SESSION = '0f2306f2331345b7be15d657b4228eb3'
ENGINE_SEAL = '9243c8d26912ae028b2bf5f7befcf05ad799de77fce76d60e871d99f1c459945'
ENGINE_SHA = 'c0d7394f214a79c8d83222cd0ae651febfb48dd30d660c10edbb164ad2367224'
REVISION = '864b3a75a5e27c81cba0d78cbe834e796f51df26'
MANIFEST_SHA = '7611d0a7ea4efd229c75ec1f114d9871b9420509e1eb62aaa52f4063a634094e'
SCRIPT_SHA = 'b2d1c715a182b9d5630b42598e29649bf82f024cb568b00b1e3d01cc77a9dafe'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, record):
    path.write_text(json.dumps(record, indent=2) + '\n')


def api(route):
    path = Path.home() / '.autonomics/gateway.token'
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
            and stat.S_IMODE(before.st_mode) in (0o400, 0o600) and before.st_nlink == 1
            and before.st_size <= 65536, 'Unsafe gateway credential file')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        opened = os.fstat(descriptor)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                                  value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(identity(before) == identity(opened), 'Gateway credential file changed')
        raw = os.read(descriptor, 65537)
        require(len(raw) <= 65536 and identity(os.fstat(descriptor)) == identity(opened)
                and identity(path.lstat()) == identity(opened), 'Gateway credential file changed')
    finally:
        os.close(descriptor)
    token = raw.decode().strip()
    require(token and '\n' not in token and '\r' not in token, 'Invalid gateway credential')
    request = urllib.request.Request('http://127.0.0.1:8765/api/v1/' + route,
                                     headers={'Authorization': 'Bearer ' + token})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError('Gateway redirect refused')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=20) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
        require(response.status == 200 and len(raw) <= 8 * 1024 * 1024, 'Invalid gateway identity reply')
        return json.loads(raw)


def resident():
    status = api('gateway/status')
    pid = status['pid']
    process = Path('/proc') / str(pid)
    executable = process / 'exe'
    row = next(row for row in api('plugins')['plugins'] if row['name'] == 'ieugwasr-official')
    return dict(pid=pid, start_ticks=int((process / 'stat').read_text().rsplit(') ', 1)[1].split()[19]),
                executable=str(executable.resolve(strict=True)), binary_sha256=sha(executable),
                plugin=row, private_policy_present=(Path.home() / '.autonomics/plugin-private-environment.json').exists(),
                plugin_configuration_sha256=sha(Path.home() / '.autonomics/plugins.toml'),
                qualified_profile_sha256=sha(Path.home() / '.autonomics/qualified-image-store.json'))


def main():
    sys.path.insert(0, str(ROOT / 'scripts'))
    import research_validation_entry as entry
    require(entry.inside_session(), 'Managed validation session required')
    os.umask(0o077)
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ieugwasr-deployment-candidate'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    sys.path.insert(0, str(ROOT.parent / 'autonomics-plugins'))
    from tools.reconcile_ab_evidence_index import verify_archive
    for session, seal in ((CONSUMER_SESSION, CONSUMER_SEAL), (ENGINE_SESSION, ENGINE_SEAL)):
        require(verify_archive(ARCHIVES, session, seal)['positive_worker_exit_verified'], 'Build archive identity failed')
    engine = ARCHIVES / ENGINE_SESSION / 'artifacts/permanent/sjtu-release-collection/autonomics'
    original_runner = ARCHIVES / CONSUMER_SESSION / 'artifacts/permanent/sjtu-consumer-collection/official_plugin_dag'
    require(sha(engine) == ENGINE_SHA and sha(original_runner) == CONSUMER_SHA, 'Built candidate identity mismatch')
    require(sha(FAMILY / 'manifest.toml') == MANIFEST_SHA and sha(FAMILY / 'scripts/dispatch.R') == SCRIPT_SHA,
            'Author adapter changed')
    candidate = json.loads((FAMILY / 'deployment/plugin-private-environment.candidate.json').read_text())
    kinds = ['official_ieugwasr_call', 'official_ieugwasr_call_with_dataset']
    require(candidate['schema'] == 1 and [g['kind'] for g in candidate['grants']] == kinds
            and all(g == dict(plugin='ieugwasr-official', kind=g['kind'],
                              manifest_sha256='sha256:' + MANIFEST_SHA, script_sha256='sha256:' + SCRIPT_SHA,
                              image_reference='ghcr.io/zj-2002/ieugwasr-official@sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395',
                              names=['OPENGWAS_JWT']) for g in candidate['grants']), 'Unexpected credential grant')
    before = resident()
    scratch = Path(os.environ['TMPDIR']) / 'ieugwasr-deployment-negatives'
    scratch.mkdir(mode=0o700)
    runner = scratch / 'official_plugin_dag'
    shutil.copyfile(original_runner, runner)
    runner.chmod(0o500)
    require(sha(runner) == CONSUMER_SHA, 'Consumer copy differs')
    # No inherited credential values, proxy settings, loader policy or runtime path.
    base_environment = {name: os.environ[name] for name in
                        ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'AUTONOMICS_VALIDATION_PERMANENT',
                         'AUTONOMICS_VALIDATION_SESSION_ID') if name in os.environ}
    launcher_path = ROOT / 'scripts/research_preview_launch.py'
    require(sha(launcher_path) == 'c0a142a9a4b1264208c8b4c3c6ac15b44ebd0979c200142225188b75f56d2a60',
            'Audited credential loader changed')
    launcher = dict(__name__='credential_loader_without_main', __file__=str(launcher_path))
    exec(compile(launcher_path.read_bytes(), str(launcher_path), 'exec'), launcher)
    cases = []
    negative_count = 0
    for kind in kinds:
        for failure in ('wrong-identity', 'missing-credential', 'synthetic-private-channel'):
            name = kind + '-' + failure
            work = output / name
            work.mkdir(mode=0o700)
            home = scratch / name
            (home / '.autonomics').mkdir(mode=0o700, parents=True)
            programs = home / 'bin'
            programs.mkdir(mode=0o700)
            stub = programs / 'podman'
            calls = work / 'unexpected-podman-calls'
            policy = json.loads(json.dumps(candidate))
            if failure == 'wrong-identity':
                next(g for g in policy['grants'] if g['kind'] == kind)['manifest_sha256'] = 'sha256:' + '0' * 64
            policy_file = home / '.autonomics/plugin-private-environment.json'
            write(policy_file, policy)
            policy_file.chmod(0o600)
            dataset_kind = kind == kinds[1]
            write(work / 'request.json', dict(operation='ld_clump_api' if dataset_kind else 'gwasinfo',
                  arguments=dict(clump_kb=10000, clump_r2=0.001, clump_p=1, pop='EUR') if dataset_kind else dict(id=['ieu-a-2'])))
            nodes = [dict(id='request', kind='file_reference', spec=dict(path='vfs:///request.json', hash_content=True)),
                     dict(id='analysis', kind=kind, spec={})]
            edges = [dict(**{'from': 'request', 'to': 'analysis'}, from_port=0, to_port=0)]
            if dataset_kind:
                # Missing-credential refusal precedes dataset/R processing. An opaque
                # input tests the port connection without claiming a valid R object.
                (work / 'opaque-input.RDS').write_bytes(b'NOT_AN_AUTHOR_DATASET: unreachable credential-negative input\n')
                nodes.insert(1, dict(id='dataset', kind='file_reference', spec=dict(path='vfs:///opaque-input.RDS', hash_content=True)))
                edges.append(dict(**{'from': 'dataset', 'to': 'analysis'}, from_port=0, to_port=1))
            job = dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', run_root=str(work),
                       plugin_manifest=str(FAMILY / 'manifest.toml'), expected_plugin_name='ieugwasr-official',
                       plugin_manifest_sha256=MANIFEST_SHA, script_sha256={'scripts/dispatch.R': SCRIPT_SHA},
                       panel_overrides=[], bundles=[], panel_manifest_sha256={}, nodes=nodes, edges=edges)
            write(work / 'job.json', job)
            environment = dict(base_environment, HOME=str(home), AUTONOMICS_DAG_TASKS_ROOT=str(scratch / (name + '-tasks')))
            environment['PATH'] = str(programs) + os.pathsep + base_environment.get('PATH', '/usr/bin:/bin')
            synthetic = failure == 'synthetic-private-channel'
            if synthetic:
                toy_secret = secrets.token_urlsafe(40)
                toy_file = home / 'toy-private.env'
                toy_file.write_text('OPENGWAS_JWT=' + toy_secret + '\n')
                toy_file.chmod(0o600)
                environment, _ = launcher['credentials_environment'](environment, toy_file)
                marker = work / 'sentinel-create.json'
                expected_secret_hash = hashlib.sha256(toy_secret.encode()).hexdigest()
                sentinel = '''#!/usr/bin/python3
import hashlib,json,os,pathlib,sys
arguments=sys.argv[1:]
secret=os.environ.get('OPENGWAS_JWT','')
if 'create' in arguments:
    safe=bool(secret) and all(secret not in argument for argument in arguments)
    named=any(arguments[index:index+2]==['--env','OPENGWAS_JWT'] for index in range(len(arguments)-1))
    record=dict(synthetic_environment_received=hashlib.sha256(secret.encode()).hexdigest()==EXPECTED,
                credential_value_absent_from_argv=safe, name_only_env_option=named, real_podman_executed=False)
    pathlib.Path(MARKER).write_text(json.dumps(record))
    print(secret)
    print(secret,file=sys.stderr)
    raise SystemExit(91)
raise SystemExit(92)
'''.replace('EXPECTED',repr(expected_secret_hash)).replace('MARKER',repr(str(marker)))
                stub.write_text(sentinel)
                stub.chmod(0o700)
            else:
                stub.write_text('#!/usr/bin/python3\nfrom pathlib import Path\nPath(' + repr(str(calls)) + ').touch()\nraise SystemExit(91)\n')
                stub.chmod(0o700)
            result = subprocess.run([str(runner), str(work / 'job.json')], env=environment, capture_output=True, timeout=90)
            if synthetic:
                require(toy_secret.encode() not in result.stdout + result.stderr,
                        'Synthetic credential escaped runtime diagnostic suppression')
            (work / 'runner.stdout').write_bytes(result.stdout)
            (work / 'runner.stderr').write_bytes(result.stderr)
            require(not calls.exists(), 'Credential-negative unexpectedly reached Podman')
            if not synthetic:
                negative_count += 1
            if failure == 'wrong-identity':
                require(result.returncode != 0 and b'implementation identity mismatch' in result.stderr
                        and not (work / 'dag-report.json').exists(), 'Wrong candidate identity was not rejected')
                cases.append(dict(case=name, actual_runner_exit=result.returncode, passed=True, container_creates=0))
            else:
                require(result.returncode == 0, 'Consumer failed outside expected DAG refusal')
                report = json.loads((work / 'dag-report.json').read_text())
                require(report['engine_source_revision'] == REVISION and report['loaded_through_operator_policy_boundary'],
                        'Wrong loader source')
                analysis = next(node for node in report['first_run']['nodes'] if node['id'] == 'analysis')
                require(analysis['status'] == 'failed' and not analysis.get('output_files'), 'Missing credential was not refused')
                if synthetic:
                    observed = json.loads(marker.read_text())
                    require(all(observed[key] for key in ('synthetic_environment_received',
                            'credential_value_absent_from_argv', 'name_only_env_option'))
                            and not observed['real_podman_executed'], 'Synthetic private channel was not established')
                    for item in work.rglob('*'):
                        if item.is_file():
                            require(toy_secret.encode() not in item.read_bytes(), 'Synthetic credential leaked into saved case evidence')
                    cases.append(dict(case=name, actual_runner_exit=0, analysis_status='failed_at_create_sentinel',
                                      passed=True, container_creates=0, synthetic_private_channel=observed,
                                      synthetic_case_plaintext_scan_passed=True))
                else:
                    cases.append(dict(case=name, actual_runner_exit=0, analysis_status='failed', passed=True, container_creates=0))
    after = resident()
    require(before == after, 'Resident or shared configuration changed during read-only candidate check')
    sources = {str(path.relative_to(FAMILY)): sha(path) for path in sorted(FAMILY.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
    verification = dict(schema='IEUGWASR_DEPLOYMENT_CANDIDATE_VERIFICATION_V1', passed=True,
                        source_revision=REVISION, engine_sha256=ENGINE_SHA, consumer_sha256=CONSUMER_SHA,
                        new_negative_cases=negative_count, new_synthetic_channel_cases=len(cases)-negative_count, cases=cases, source_files=sources, resident=after,
                        production_changed=False, authenticated_requests=0, author_method_executions=0,
                        container_creates=0, scientific_release_granted=False, g0_granted=False)
    write(output / 'verification.json', verification)
    print(json.dumps(dict(passed=True, negative_cases=negative_count, synthetic_channel_cases=len(cases)-negative_count, container_creates=0, authenticated_requests=0,
                          evidence=str(output / 'verification.json'), sha256=sha(output / 'verification.json'))))


if __name__ == '__main__':
    main()
