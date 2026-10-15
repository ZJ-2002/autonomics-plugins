"""Four tiny original R-kind DAGs against sealed full-entry replay, not a new oracle."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_r_publication_runtime as direct
from tools import prove_b_publication_dag as inherited
from tools.reconcile_ab_evidence_index import verify_archive

require, fact, write, strict_json = direct.require, direct.fact, direct.write, direct.strict_json
BUILD_SESSION = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
RUNNER_SHA = '636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b'
SCOPE = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
KINDS = {'deseq2': 'deseq2_de', 'limma': 'limma_voom'}
PARAMETERS = {
    'deseq2': dict(condition_reference='ctrl', condition_test='case', covariates='batch',
                   fit_type='mean', lfc_shrink='none', alpha=0.1, threads=1),
    'limma': dict(outcome_var='condition', contrast_var='condition', contrast_levels='ctrl,case',
                  covariates='batch', outcome_mode='categorical', normalization='tmm', alpha=0.05, threads=1),
}
REFUSALS = {'deseq2': 'all count values must be finite nonnegative integers within R integer range',
            'limma': 'count values must be exactly representable nonnegative integers'}
RDS_READER = '''suppressPackageStartupMessages(library(DESeq2))
arguments <- commandArgs(trailingOnly=TRUE)
stopifnot(length(arguments)==3L)
reference <- readRDS(arguments[[1L]])
actual <- readRDS(arguments[[2L]])
answer <- all.equal(reference,actual,check.environment=FALSE,tolerance=0)
stopifnot(isTRUE(answer))
jsonlite::write_json(list(complete_object_equal_excluding_environment=TRUE,tolerance=0,
    check_environment=FALSE,R_version=as.character(getRversion()),DESeq2_version=as.character(packageVersion("DESeq2")),
    new_statistical_fit_executed=FALSE,independent_new_oracle_generated=FALSE,G0=FALSE),
    arguments[[3L]],auto_unbox=TRUE,pretty=TRUE)
'''


def expected_environment(label):
    if label == 'deseq2':
        suffixes = {'CONDITION_REFERENCE': 'ctrl', 'CONDITION_TEST': 'case', 'COVARIATES': 'batch',
                    'FIT_TYPE': 'mean', 'LFC_SHRINK': 'none', 'ALPHA': '0.1', 'THREADS': '1'}
        prefix = 'AUTONOMICS_DESEQ2_'
    else:
        suffixes = {'OUTCOME': 'condition', 'CONTRAST_VAR': 'condition', 'CONTRAST_LEVELS': 'ctrl,case',
                    'COVARIATES': 'batch', 'OUTCOME_MODE': 'categorical', 'NORMALIZATION': 'tmm',
                    'ALPHA': '0.05', 'THREADS': '1'}
        prefix = 'AUTONOMICS_LIMMA_'
    return {prefix + key: value for key, value in suffixes.items()}


def exact_json(actual, reference):
    if type(actual) is not type(reference):
        return False
    if isinstance(actual, dict):
        return set(actual) == set(reference) and all(exact_json(actual[key], reference[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(reference) and all(exact_json(first, second) for first, second in zip(actual, reference))
    return actual == reference


def checked_direct(archives, session, seal, output):
    require(re.fullmatch('[0-9a-f]{32}', session) is not None and
            re.fullmatch('[0-9a-f]{64}', seal) is not None, 'A successful full-image runtime seal is required')
    verified = verify_archive(archives, session, seal)
    require(verified['positive_worker_exit_verified'] is True, 'Failed direct runtime cannot supply the reference')
    state = strict_json((archives / session / 'SESSION.json').read_text())
    require(type(state.get('launcher_exit_status')) is int and state['launcher_exit_status'] == 0,
            'Successful direct launcher required')
    root = Path(verified['artifact_root']) / 'permanent/r-publication-runtime'
    report = strict_json((root / 'verification.json').read_text())
    require(report.get('sources') == direct.sources() and report.get('actual_full_entries') == 14 and
            report.get('actual_method_containers') == 2 and report.get('stopped_intents') == 2 and
            report.get('actual_DAG_executed') is False and report.get('real_research_inputs_read') is False and
            report.get('scientific_authorization_granted') is False and report.get('g0_granted') is False,
            'Exact current source and successful bounded full-entry reference required')
    for label in KINDS:
        direct.validate_summary(report['reports'][label], label, root / label)
    write(output / 'verified-direct.json', dict(session=session, seal=seal, files=verified['files'],
        bytes=verified['bytes'], all_members_rehashed=True, independent_new_oracle_generated=False))
    return root


def snapshot_families(output):
    families = {}
    for label, item in direct.FAMILIES.items():
        source = output / 'source' / label
        source.mkdir(parents=True)
        manifest_raw = inherited.regular(ROOT / item['manifest']).read_bytes()
        require(hashlib.sha256(manifest_raw).hexdigest() == item['manifest_sha'], 'Original manifest changed')
        manifest = tomllib.loads(manifest_raw.decode())
        require(manifest['image']['reference'] == item['image'], 'Original image changed')
        script_name = Path(item['script']).name
        names = {'manifest.toml'} | {node['command']['script_file'] for node in manifest['nodes']}
        identities = {}
        for name in sorted(names):
            if name == 'manifest.toml':
                raw = manifest_raw
            elif name == script_name:
                raw = inherited.regular(ROOT / item['script']).read_bytes()
                require(hashlib.sha256(raw).hexdigest() == item['fixed'], 'Reviewed fixed R source changed')
            else:
                relative = str(Path(item['manifest']).parent / name)
                raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', direct.BASELINE + ':' + relative])
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
            identities[name] = fact(target)
        definition = next(node for node in manifest['nodes'] if node['kind'] == KINDS[label])
        require(len(definition['ports']['inputs']) == 2 and len(definition['ports']['outputs']) == 5,
                'Original two-input five-output R interface required')
        families[label] = dict(source=source, manifest=manifest, definition=definition, identities=identities)
    return families


def job_for(work, label, family):
    return dict(scope=SCOPE, run_root=str(work), plugin_manifest=str(family['source'] / 'manifest.toml'),
        expected_plugin_name=family['manifest']['plugin_name'],
        plugin_manifest_sha256=family['identities']['manifest.toml']['sha256'],
        script_sha256={name: value['sha256'] for name, value in family['identities'].items() if name != 'manifest.toml'},
        additional_plugins=[], panel_overrides=[], bundles=[], panel_manifest_sha256={},
        nodes=[dict(id=name, kind='file_reference', spec=dict(path='vfs:///' + filename, format='tsv', hash_content=True))
               for name, filename in [('counts', 'counts.tsv'), ('samples', 'samples.tsv')]] +
              [dict(id='analysis', kind=KINDS[label], spec=dict(PARAMETERS[label]))],
        edges=[{'from': name, 'from_port': 0, 'to': 'analysis', 'to_port': port}
               for port, name in enumerate(('counts', 'samples'))])


def fractional_counts(raw):
    rows = list(csv.reader(io.StringIO(raw.decode()), delimiter='\t'))
    require(len(rows) == 201 and all(len(row) == 13 for row in rows), 'Exact complete 200-by-12 sealed fixture required')
    original = rows[1][1]
    require(re.fullmatch('[0-9]+', original) is not None, 'Original selected count must be an integer')
    rows[1][1] = str(int(original)) + '.5'
    stream = io.StringIO(newline='')
    csv.writer(stream, delimiter='\t', quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(rows)
    return stream.getvalue().encode()


def validate_report(report, build, family, label, negative):
    require(report.get('scope') == SCOPE and report.get('engine_source_revision') == build['engine_commit'] and
            report.get('original_manifest_sha256') == family['identities']['manifest.toml']['sha256'] and
            report.get('plugin_name') == family['manifest']['plugin_name'] and
            report.get('additional_plugin_identities') == [] and type(report.get('max_concurrency')) is int and
            report['max_concurrency'] == 1 and report.get('incremental') is False and
            report.get('input_hashing') == 'ContentRequired' and all(report.get(key) is False for key in
            ['native_statistical_factories_registered', 'current_daemon_verified', 'scientific_authorized', 'g0_granted']),
            'Exact isolated official R report identity and no-authority scope required')
    rows = report['first_run']['nodes']
    require(len(rows) == 3 and {row['id'] for row in rows} == {'counts', 'samples', 'analysis'} and
            all(row.get('reused') is False for row in rows), 'Three fresh original nodes required')
    nodes = {row['id']: row for row in rows}
    for name in ('counts', 'samples'):
        node = nodes[name]
        require(node.get('status') == 'success' and node.get('node_type') == 'file_reference' and
                set(node.get('port_assignments', {})) == {'0'}, 'Both file sources must execute successfully')
    method = nodes['analysis']
    image = family['manifest']['image']['reference']
    execution = method.get('execution', {})
    expected = 1 if negative else 0
    require(method.get('node_type') == KINDS[label] and method.get('status') == ('failed' if negative else 'success') and
            type(execution.get('exit_code')) is int and execution['exit_code'] == expected and
            execution.get('image') == image and execution.get('image_digest') == image.split('@', 1)[1],
            'Specific method outcome from the exact fixed image required, not infrastructure failure')
    assignments = method.get('port_assignments', {})
    errors = report['first_run'].get('errors')
    expected_errors = {'analysis': method.get('error')} if negative else {}
    require(isinstance(errors, dict) and errors == expected_errors and
            report['first_run'].get('ok') is (not negative) and
            set(assignments) == (set() if negative else {str(index) for index in range(5)}),
            'Method refusal cannot publish normal ports or count as successful output')
    if negative:
        error = method.get('error')
        require(isinstance(error, dict) and set(error) == {'kind', 'message'} and error['kind'] == 'node_error' and
                isinstance(error['message'], str) and error['message'], 'Exact attributable SDK node error map required')
    else:
        require(method.get('error') is None, 'Successful method cannot retain a node error')
    return nodes


def checked_inputs(work, method, nodes, scratch):
    bindings = method.get('inputs', [])
    require(len(bindings) == 2, 'Both declared R inputs must be bound')
    checked = []
    for port, name in enumerate(('counts', 'samples')):
        source = inherited.regular(work / (name + '.tsv'))
        before = fact(source)
        matching = [binding for binding in bindings if type(binding.get('to_port')) is int and binding['to_port'] == port]
        require(len(matching) == 1, 'Unique typed destination port required')
        binding = matching[0]
        expected_path = 'vfs:///' + name + '.tsv'
        fingerprint = dict(size=before['bytes'], content_hash='sha256:' + before['sha256'])
        require(binding.get('from') == name and type(binding.get('from_port')) is int and binding['from_port'] == 0 and
                binding.get('path') == expected_path and binding.get('fingerprint', {}).get('size') == fingerprint['size'] and
                binding['fingerprint'].get('content_hash') == fingerprint['content_hash'], 'Complete actual bound R input identity differs')
        assigned = nodes[name]['port_assignments']['0']
        require(assigned.get('path') == expected_path and assigned.get('format') == 'tsv' and
                assigned.get('fingerprint', {}).get('size') == before['bytes'] and
                assigned['fingerprint'].get('content_hash') == fingerprint['content_hash'], 'Actual source output identity differs')
        matches = [path for path in scratch.rglob('input-' + str(port) + '.tsv')
                   if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        require(len(matches) == 1, 'One actual staged R input per port required')
        staged = matches[0]
        staged_before = staged.lstat()
        if stat.S_ISLNK(staged_before.st_mode):
            require(os.readlink(staged) == str(source) and staged.resolve(strict=True) == source,
                    'Staged link must point directly to the exact owned synthetic source')
            digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        else:
            digest = fact(staged)['sha256']
        staged_after = staged.lstat()
        signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(signature(staged_before) == signature(staged_after) and fact(source) == before and digest == before['sha256'],
                'Actual staged R input changed or differs from the declared bytes')
        checked.append(dict(port=port, source=name, bytes=before['bytes'], sha256=digest))
    return checked


def expected_r_refusal(node, image, marker, scratch):
    execution = node.get('execution', {})
    require(node.get('status') == 'failed' and type(execution.get('exit_code')) is int and execution['exit_code'] == 1 and
            execution.get('image') == image and execution.get('image_digest') == image.split('@', 1)[1] and
            node.get('port_assignments') == {}, 'Exact Rscript stop exit one, pinned image and zero ports required')
    stderr = inherited.regular(Path(execution['stderr_log']['path']))
    require(stderr.resolve().is_relative_to(scratch.resolve()) and marker in stderr.read_text() and
            marker in node.get('error', {}).get('message', ''),
            'Specific R input refusal must be in the actual owned stderr and node error, not an arbitrary exit')
    return stderr


def install_launcher(prefix, temporary, output):
    original = inherited.regular(Path(prefix[0]))
    require(prefix[1:] == ['--cgroup-manager=cgroupfs'] and os.environ['AUTONOMICS_PODMAN_PROGRAM'] == str(original),
            'Original managed default-backend shim required')
    directory = temporary / 'r-publication-backend-bin'
    directory.mkdir()
    launcher = directory / 'podman'
    source = '''#!/usr/bin/python3
import json,os,sys
arguments=sys.argv[1:]
if not arguments or arguments[0].startswith('-'): raise SystemExit('Unexpected backend option')
if arguments[0]=='create':
    def option(name):
        if arguments.count(name)!=1: raise SystemExit('Missing or repeated resource option')
        return arguments[arguments.index(name)+1]
    name=option('--name')
    original=dict(cpus=option('--cpus'),memory=option('--memory'))
    declarations={'4294967296':'4Gi','6442450944':'6Gi'}
    if original['cpus']!='2' or original['memory'] not in declarations: raise SystemExit('Unexpected original declaration')
    original.update(manifest_memory=declarations[original['memory']],memory_bytes=int(original['memory']))
    arguments[arguments.index('--cpus')+1]='1'
    arguments[arguments.index('--memory')+1]='1073741824'
    method_environment={}
    for position,argument in enumerate(arguments[:-1]):
        if argument=='--env':
            key,separator,value=arguments[position+1].partition('=')
            if key.startswith(('AUTONOMICS_DESEQ2_','AUTONOMICS_LIMMA_')):
                if not separator or key in method_environment: raise SystemExit('Malformed or duplicate method environment')
                method_environment[key]=value
    record=dict(run_name=name,original_resources=original,actual_resources=dict(cpus='1',memory='1073741824',memory_bytes=1073741824,human_memory_label='1Gi'),technical_override_only=True,method_environment=method_environment)
    descriptor=os.open(__RECORD__,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(descriptor,'a') as stream: stream.write(json.dumps(record)+'\\n')
os.execv(__PROGRAM__,__PREFIX__+arguments)
'''.replace('__RECORD__', repr(str(output / 'actual-container-create.jsonl'))).replace(
        '__PROGRAM__', repr(str(original))).replace('__PREFIX__', repr(prefix))
    launcher.write_text(source)
    launcher.chmod(0o700)
    os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
    return original, fact(original), launcher, fact(launcher)


def graph(runner, build, work, family, label, negative):
    write(work / 'job.json', job_for(work, label, family))
    for stage, flags in [('admission', ['--validate-job']), ('runner', [])]:
        result = subprocess.run([str(runner), *flags, str(work / 'job.json')], capture_output=True, text=True,
            timeout=900, env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
        (work / (stage + '.stdout')).write_text(result.stdout)
        (work / (stage + '.stderr')).write_text(result.stderr)
        write(work / (stage + '-exit.json'), dict(actual_exit=result.returncode))
        require(type(result.returncode) is int and result.returncode == 0, 'Runner failed before attributable method reporting')
    report = strict_json((work / 'dag-report.json').read_text())
    nodes = validate_report(report, build, family, label, negative)
    method = nodes['analysis']
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    inputs = checked_inputs(work, method, nodes, scratch)
    memory = inherited.admission.validate_memory_report(report)
    receipts = inherited.admission.checked_task_receipts(work, nodes)
    require(len(receipts) == 3 and all(record['actual_task_resources'] == {} for record in receipts.values()),
            'All three real empty native resource leases must be recorded, not invented from manifests')
    if negative:
        error = expected_r_refusal(method, family['manifest']['image']['reference'], REFUSALS[label], scratch)
        shutil.copyfile(error, work / 'expected-refusal.stderr')
        require(not any(list(root.rglob(port['path'])) for root in [work / 'artifacts', scratch]
                        for port in family['definition']['ports']['outputs']), 'Refusal left a normal declared R output')
        ports = []
    else:
        ports = inherited.actual_ports(work, family['definition'], method, scratch)
    created = [strict_json(line) for line in (work.parent / 'actual-container-create.jsonl').read_text().splitlines()]
    matching = [row for row in created if row['run_name'] == method['execution']['run_name']]
    require(len(matching) == 1 and matching[0]['actual_resources'] == dict(cpus='1', memory='1073741824',
                memory_bytes=1073741824, human_memory_label='1Gi'),
            'Actual method create must use the explicit serial tiny-fixture resource override')
    require(matching[0]['original_resources']['manifest_memory'] == family['definition']['resources']['memory'],
            'Actual SDK byte quantity must correspond to this unchanged family manifest declaration')
    require(matching[0]['method_environment'] == expected_environment(label),
            'Actual SDK method environment must bind the unchanged condition, model, alpha and thread contract')
    write(work / 'graph-verification.json', dict(nodes=3, edges=2, receipts=3, inputs=inputs,
        actual_published_ports=len(ports), expected_method_refusal=negative, memory=memory,
        actual_container_create=matching[0], manifest_resource_budget_certified=False,
        independent_new_oracle_generated=False, scientific_authorization_granted=False, g0_granted=False))
    return ports


def compare_reports(actual, reference, work, reference_inputs, actual_rds=None, reference_rds=None):
    actual_raw, reference_raw = actual.read_bytes(), reference.read_bytes()
    actual_report, reference_report = strict_json(actual_raw.decode()), strict_json(reference_raw.decode())
    exceptions = []
    for port, (key, filename) in enumerate((('count_matrix', 'counts.tsv'), ('sample_metadata', 'samples.tsv'))):
        original = inherited.regular(reference_inputs / filename)
        staged = inherited.regular(work / filename)
        require(original.read_bytes() == staged.read_bytes(), 'Report comparison requires exact complete original input bytes')
        checksum = hashlib.md5(original.read_bytes(), usedforsecurity=False).hexdigest()
        expected = reference_report['inputs'][key]
        observed = actual_report['inputs'][key]
        require(set(expected) == set(observed) == {'path', 'md5'} and expected['path'] == original.name and
                observed['path'] == 'input-' + str(port) + '.tsv' and expected['md5'] == observed['md5'] == checksum,
                'Only exact proven source-versus-staged basename transport differences are allowed')
        exceptions.append(dict(pointer='/inputs/' + key + '/path', reference=expected['path'], actual=observed['path'],
                               actual_input_md5=checksum, complete_original_input_bytes_equal=True))
        observed['path'] = expected['path']
    if actual_rds is not None:
        require(reference_rds is not None, 'Both real RDS files are required')
        expected = reference_report['outputs']['dataset']
        observed = actual_report['outputs']['dataset']
        actual_md5 = hashlib.md5(actual_rds.read_bytes(), usedforsecurity=False).hexdigest()
        reference_md5 = hashlib.md5(reference_rds.read_bytes(), usedforsecurity=False).hexdigest()
        require(set(expected) == set(observed) == {'path', 'md5'} and expected['path'] == reference_rds.name and
                observed['path'] == actual_rds.name and expected['md5'] == reference_md5 and observed['md5'] == actual_md5,
                'Each report dataset MD5 must match its own complete actual RDS bytes')
        exceptions.append(dict(pointer='/outputs/dataset/md5', reference=reference_md5, actual=actual_md5,
                               reference_rds_sha256=fact(reference_rds)['sha256'], actual_rds_sha256=fact(actual_rds)['sha256']))
        observed['md5'] = expected['md5']
    require(exact_json(actual_report, reference_report), 'Other JSON fields, types, structure or keys changed')
    return dict(reference_sha256=hashlib.sha256(reference_raw).hexdigest(), actual_sha256=hashlib.sha256(actual_raw).hexdigest(),
                original_JSON_bytes_equal=actual_raw == reference_raw, exact_remaining_JSON_fields_equal=True,
                individually_verified_transport_exceptions=exceptions)


def compare_reference(ports, reference, label, work, reference_inputs, rds_comparison=None):
    result = []
    for port, path in enumerate(ports):
        expected = inherited.regular(reference / direct.FAMILIES[label]['outputs'][port])
        actual = inherited.regular(path)
        observed = dict(port=port, name=expected.name, sha256=fact(actual)['sha256'], bytes=fact(actual)['bytes'],
                        reference_sha256=fact(expected)['sha256'], complete_reference_bytes_equal=actual.read_bytes() == expected.read_bytes())
        if label == 'deseq2' and port == 3:
            require(isinstance(rds_comparison, dict) and rds_comparison.get('complete_object_equal_excluding_environment') is True and
                    exact_json(rds_comparison.get('tolerance'), 0) and rds_comparison.get('check_environment') is False and
                    rds_comparison.get('actual_rds_sha256') == fact(actual)['sha256'] and
                    rds_comparison.get('reference_rds_sha256') == fact(expected)['sha256'], 'Actual bound complete RDS readback required')
            observed['RDS_readback'] = rds_comparison
        elif port == 4:
            observed['JSON_field_comparison'] = compare_reports(actual, expected, work, reference_inputs,
                ports[3] if label == 'deseq2' else None, reference / direct.FAMILIES[label]['outputs'][3] if label == 'deseq2' else None)
        else:
            require(observed['complete_reference_bytes_equal'], 'Complete sealed normal table bytes differ: ' + expected.name)
        result.append(observed)
    require(len(result) == 5, 'All five declared outputs require complete reference comparison')
    return result


def readback_rds(prefix, output, actual, reference):
    source = output / 'rds-readback-source'
    source.mkdir()
    source_file = source / 'readback.R'
    source_file.write_text(RDS_READER)
    destination = output / 'rds-readback'
    destination.mkdir()
    shutil.copyfile(inherited.regular(actual), source / 'actual.rds')
    shutil.copyfile(inherited.regular(reference), source / 'reference.rds')
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1073741824',
        '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=128m', '-v', str(source) + ':/source:ro', '-v', str(destination) + ':/proof:rw',
        '--entrypoint=/opt/autonomics/Rscript-vanilla', direct.FAMILIES['deseq2']['image'],
        '/source/readback.R', '/source/reference.rds', '/source/actual.rds', '/proof/verification.json']
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    (destination / 'stdout.log').write_text(result.stdout)
    (destination / 'stderr.log').write_text(result.stderr)
    write(destination / 'command.json', command)
    write(destination / 'execution.json', dict(actual_exit=result.returncode, statistical_fit_executed=False))
    require(type(result.returncode) is int and result.returncode == 0, 'Actual full RDS readback failed')
    report = strict_json((destination / 'verification.json').read_text())
    require(report.get('complete_object_equal_excluding_environment') is True and report.get('check_environment') is False and
            exact_json(report.get('tolerance'), 0) and report.get('R_version') == '4.5.3' and report.get('DESeq2_version') == '1.50.2' and
            report.get('new_statistical_fit_executed') is False and report.get('independent_new_oracle_generated') is False and
            report.get('G0') is False, 'Complete exact official RDS readback contract differs')
    report.update(actual_rds_sha256=fact(actual)['sha256'], reference_rds_sha256=fact(reference)['sha256'])
    require(fact(source / 'actual.rds')['sha256'] == report['actual_rds_sha256'] and
            fact(source / 'reference.rds')['sha256'] == report['reference_rds_sha256'] and source_file.read_text() == RDS_READER,
            'Readback must use the exact actual/reference objects and unchanged comparison source')
    write(destination / 'bound-verification.json', report)
    return report


def finalize_stoppage(prefix, permanent, output, expected, primary_error=None):
    try:
        intents = permanent / 'container-intents.json'
        if intents.exists():
            return direct.stopped(prefix, permanent, output, expected)
        creation_log = output / 'actual-container-create.jsonl'
        records = [] if not creation_log.exists() else [strict_json(line) for line in creation_log.read_text().splitlines()]
        require(primary_error is not None and not records, 'Missing container intents cannot certify successful execution')
        write(output / 'zero-create-failure-diagnostic.json', dict(
            expected_attempts_before_failure=expected, recorded_proxy_creates=0, actual_intent_file_present=False,
            primary_error_type=type(primary_error).__name__, successful_stoppage_or_method_execution_certified=False,
            original_failure_preserved=True, g0_granted=False))
        return []
    except Exception as cleanup_error:
        if primary_error is None:
            raise
        write(output / 'stoppage-failure-diagnostic.json', dict(primary_error_type=type(primary_error).__name__,
            stoppage_error_type=type(cleanup_error).__name__, original_failure_preserved=True,
            successful_stoppage_or_method_execution_certified=False, g0_granted=False))
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--build-record', type=Path, required=True)
    parser.add_argument('--direct-session', required=True)
    parser.add_argument('--direct-seal', required=True)
    args = parser.parse_args()
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    temporary = Path(os.environ['TMPDIR'])
    output = permanent / 'r-publication-dag'
    output.mkdir(mode=0o700)
    own_source = fact(Path(__file__))
    shutil.copyfile(Path(__file__), output / 'driver.py')
    before = direct.sources()
    initial = direct.runtime.cgroup_observation()
    require(initial['memory_max_bytes'] == 2 * 1024**3 and
            int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith('MemAvailable:'))) * 1024 >= 4 * 1024**3 and
            shutil.disk_usage(output).free >= 1024**3, 'Bounded 2Gi parent, host reserve and disk required')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    require(args.build_record.is_relative_to(archives / BUILD_SESSION), 'Exact sealed 23-guard build required')
    build, build_receipt = inherited.admission.checked_build(archives, args.runner, args.build_record, BUILD_SEAL)
    runner, identity = inherited.copy_runner(args.runner, temporary)
    require(fact(runner)['sha256'] == RUNNER_SHA, 'Exact existing reviewed SDK runner required')
    reference = checked_direct(archives, args.direct_session, args.direct_seal, output)
    families = snapshot_families(output)
    prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--cgroup-manager=cgroupfs']
    for name in ('backend-before', 'backend-after', 'images'):
        (output / name).mkdir()
    backend = direct.runtime.default_backend(prefix, output / 'backend-before')
    images = {label: direct.inspect_image(prefix, output / 'images', label + '-before', item['image'])
              for label, item in direct.FAMILIES.items()}
    launcher = install_launcher(prefix, temporary, output)
    results = {}
    attempted = 0
    primary_error = None
    try:
        for label in KINDS:
            for negative in (False, True):
                name = label + ('-refusal' if negative else '-positive')
                work = output / name
                work.mkdir()
                for filename in ('counts.tsv', 'samples.tsv'):
                    original = inherited.regular(reference / label / 'input' / filename)
                    raw = original.read_bytes()
                    (work / filename).write_bytes(fractional_counts(raw) if negative and filename == 'counts.tsv' else raw)
                attempted += 1
                ports = graph(runner, build, work, families[label], label, negative)
                rds_comparison = None
                if not negative and label == 'deseq2':
                    attempted += 1
                    rds_comparison = readback_rds(prefix, output, ports[3], reference / label / 'fixed-normal/deseq2_dataset.rds')
                comparison = [] if negative else compare_reference(ports, reference / label / 'fixed-normal', label,
                    work, reference / label / 'input', rds_comparison)
                results[name] = dict(expected_method_refusal=negative, normal_ports=len(ports),
                                     complete_reference_comparisons=comparison)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        stopped = finalize_stoppage(prefix, permanent, output, attempted, primary_error)
    require(attempted == 5 and len(stopped) == 5, 'All four method containers and one comparison must stop')
    require(direct.runtime.default_backend(prefix, output / 'backend-after') == backend and direct.sources() == before and
            all(images[label] == direct.inspect_image(prefix, output / 'images', label + '-after', item['image'])
                for label, item in direct.FAMILIES.items()), 'Runtime, source or fixed image changed')
    require(fact(launcher[0]) == launcher[1] and fact(launcher[2]) == launcher[3] and
            inherited.admission.file_identity(args.runner) == identity and fact(runner)['sha256'] == RUNNER_SHA,
            'Original managed shim, owned launcher or immutable SDK changed')
    require(fact(Path(__file__)) == own_source and fact(output / 'driver.py')['sha256'] == own_source['sha256'],
            'The exact reviewed DAG driver changed during execution')
    write(output / 'verification.json', dict(scope='FOUR_SYNTHETIC_R_PUBLICATION_DAGS_SEALED_REFERENCE_REPLAY_ONLY',
        build=build_receipt, direct_session=args.direct_session, direct_seal=args.direct_seal, cases=results,
        actual_graphs=4, actual_nodes=12, actual_edges=8, actual_task_receipts=12,
        actual_method_containers=4, actual_nonfitting_RDS_comparison_containers=1,
        stopped_owned_containers=len(stopped), official_numeric_oracle_recomputed=False,
        cache_reuse_or_complete_engine_output_content_hashes_certified=False,
        original_manifest_resources_certified=False, resource_override_container_memory_bytes=1024**3,
        initial_parent=initial, final_parent=direct.runtime.cgroup_observation(), research_raw_data_read=False,
        current_daemon_verified=False, production_restarted=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
