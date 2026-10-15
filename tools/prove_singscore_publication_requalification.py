"""Replay the sealed complete singscore inventory after publication-only repair."""

import argparse
import ast
import base64
import csv
import hashlib
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
from tools import prove_frozen_a_harmonisation_dag as admission
from tools import prove_h5ad_subset_official_runtime as managed
from tools.prove_frozen_a_family_runtime import stopped
from tools.prove_locked_b_source_transport import actual_ports, regular
from tools.reconcile_ab_evidence_index import verify_archive

require, fact, write, strict_json = managed.require, managed.fact, managed.write, managed.strict_json
BUILD_SESSION = '54d4987610d14ce7882735c715368c8e'
BUILD_SEAL = 'd3b0c3bf7d4fc256ea1592d59a1ffd822e4b0657ab80a4769ecbd9847fd3da0f'
RUNNER_SHA = '636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b'
SCOPE = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
MANIFEST_MEMORY = '2g'
METHOD_MEMORY_BYTES = 2_000_000_000
SDK_RESOURCE_SOURCE = {
    'revision': '4256643c55ae6fb50e8c867069330ed6ac2b4bc0',
    'path': 'crates/container-runtime/src/podman.rs',
    'sha256': '85d53f3a10c8a7eeba67e7210f143b51d0bdb7c5f7313137478820a7acee81a8',
    'function': 'podman_size', 'g_multiplier': 1_000_000_000, 'gi_multiplier': 1 << 30,
}
HELPER_PINS = {
    'tools/prove_frozen_a_harmonisation_dag.py': '8e27e01930e97bdbd84d57ca398253b705bc0ff2e5d6a88d0f5781cde66ef54e',
    'tools/prove_frozen_a_harmonisation.py': '79b36d2f5a64409f0b8b87735b7773f29dd3dedeaa3809ddb14a4c7a97685018',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
    'tools/prove_locked_b_source_transport.py': '191b0dccfe26e21f9fdd0c727ef1be52306927791e98e01242d82d690691dd56',
    'tools/prove_current_ldsc.py': '939159c038af706bca99530302eac5b6eed95d768536b29d80bd6baf2cba229d',
    'tools/reconcile_ab_evidence_index.py': '44878add55a5a656f15e2c936e269ba1ef9b2c4a16c81e7a5c22733da6975c72',
}
REFERENCE_SEAL = 'bc29100f60061395cd96ae3b03effd988e9d763e64dd242af9f2c1e65b00b224'
OFFICIAL_TAR_SHA = 'b4ffcbcb215ec99b9c8159bcf47cebba02517ff2c76c6aebabd2d7848298fd5a'
ORIGINAL_SHA = '0ccfea285f042f05af15f61dd5de3ef8ff2d924387d8a6d07bf3852eac5a59b2'
SCRIPT_SHA = 'aebaa30e8394778f748427c186ea14ebd58bfe6c3cf83729fbb2cea3f1e329d3'
MANIFEST_SHA = 'acb7240150d80d3af965210855468782f975c2e3ec8878503e1fe9f9473ffa61'
CONTRACT_SHA = '1a17b35c2ba815ba0b166feeb30a7eeda6f12cf67a21613ac4c7c6a789e0222e'
VERIFIER_SHA = 'a794d1b196659db4c2611c437d66ed89b90dd6d85bb1ec3e9ce0c95f2e3d4af0'
REPAIR_SESSION = 'ec81ba947425422298ea94523ec8c332'
REPAIR_SEAL = '1c8c493a50347fb09aefb6417fa6b5c33e019bc83750145dd70c8eb3468fe261'
PREVIOUS_SESSION = '50e4b946d8f14e38bf34c7c3e16f0980'
PREVIOUS_SEAL = 'd8992bc43f98a69a71aaa5d580d190bd46f236716a03c18a79a36c099bc2eb5c'
IMAGE = 'ghcr.io/zj-2002/singscore-official@sha256:04981a66d7c3fc7055a185a0102dc9f337dd63381b676681c08e52e8c22e2ca5'
EXISTING = 'test_preexisting_score_is_not_overwritten'
INPUT_NAMES = ('matrix.tsv', 'signature.tsv', 'samples.tsv')
POSITIVE = {
    'test_all_ties_official_rank_and_all_scores', 'test_bidirectional_official_rank_and_all_scores',
    'test_gene_row_permutation_does_not_change_scores', 'test_group_labels_do_not_enter_scores',
    'test_lexical_gene_sample_and_group_ids', 'test_matrix_sample_order_is_preserved',
    'test_metadata_permutation_does_not_change_scores', 'test_one_sample_official_rank_and_all_scores',
    'test_up_only_official_rank_and_all_scores', 'official-author-example',
}
PINS = {
    'plugins/singscore/manifest.toml': MANIFEST_SHA,
    'plugins/singscore/scripts/singscore.sh': SCRIPT_SHA,
    'plugins/singscore/tests/test_contract.py': CONTRACT_SHA,
    'tests/test_singscore_publication_ownership.py': '68aebb7d359e1a1ae4c7ef557a92d3373fda9e0b7ac71e7e07ee624123c0d823',
    'tools/verify_singscore_joined.R': VERIFIER_SHA,
}
AST_AND_PACKAGE = r'''
arguments <- commandArgs(TRUE)
stopifnot(length(arguments)==4L, as.character(getRversion())=="4.6.1")
suppressPackageStartupMessages(library(singscore))
stopifnot(as.character(packageVersion("singscore"))=="1.32.0")
assigns <- function(value,name) is.call(value)&&identical(value[[1]],as.name("<-"))&&identical(value[[2]],as.name(name))
scientific <- function(path) {
 expressions<-parse(path)
 definition<-expressions[[which(vapply(expressions,assigns,logical(1),name="run_score"))]]
 outer<-as.list(body(eval(definition[[3]])))[-1]
 catcher<-which(vapply(outer,function(value)is.call(value)&&identical(value[[1]],as.name("tryCatch")),logical(1)))
 inner<-as.list(outer[[catcher]][[2]])[-1]
 first<-which(vapply(inner,assigns,logical(1),name="matrix_table"))
 last<-which(vapply(inner,assigns,logical(1),name="scores"))
 stopifnot(length(first)==1L,length(last)==1L,last-first+1L==31L)
 helpers<-lapply(c("read_tsv","validate_ids"),function(name)expressions[[which(vapply(expressions,assigns,logical(1),name=name))]])
 list(body=inner[first:last],helpers=helpers)
}
stopifnot(identical(scientific(arguments[1]),scientific(arguments[2])))
namespace<-asNamespace("singscore")
representation<-function(method)list(formals=paste(deparse(formals(method)),collapse="\n"),body=paste(deparse(body(method)),collapse="\n"))
functions<-list()
for(name in sort(ls(namespace,all.names=TRUE))) {
 value<-get(name,envir=namespace,inherits=FALSE)
 if(is.function(value)) functions[[name]]<-representation(value)
}
methods<-list()
for(name in c("rankGenes","simpleScore")) {
 found<-findMethods(name,where=namespace)
 methods[[name]]<-lapply(found[sort(names(found))],representation)
}
expected<-readRDS(arguments[3])
stopifnot(length(functions)==31L,length(methods$rankGenes)==5L,length(methods$simpleScore)==4L,
 identical(list(functions=functions,methods=methods),expected))
jsonlite::write_json(list(scientific_AST_statements_identical=31L,original_scientific_helpers_identical=2L,
 official_package_functions_identical=31L,rankGenes_methods_identical=5L,simpleScore_methods_identical=4L,
 R_version=as.character(getRversion()),singscore_version=as.character(packageVersion("singscore")),
 independent_reference_regenerated=FALSE,g0_granted=FALSE),arguments[4],auto_unbox=TRUE,pretty=TRUE)
'''


def source_facts():
    values = {name: fact(regular(ROOT / name)) for name in PINS}
    require(all(values[name]['sha256'] == checksum for name, checksum in PINS.items()),
            'Frozen singscore source, contract or whole-object comparator changed')
    return values


def helper_payload(path, expected):
    path = Path(path).absolute()
    if not isinstance(expected, str) or re.fullmatch('[0-9a-f]{64}', expected) is None:
        raise ValueError('Fixed helper SHA256 required')
    if any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError('Helper source aliases forbidden')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 512 * 1024:
        raise ValueError('Bounded ordinary helper source required')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode,
                               value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if signature(os.fstat(handle.fileno())) != signature(before):
            raise ValueError('Helper changed before reading')
        payload = handle.read(512 * 1024 + 1)
        after = os.fstat(handle.fileno())
    checksum = hashlib.sha256(payload).hexdigest()
    if (signature(before) != signature(after) or signature(path.lstat()) != signature(before) or
            len(payload) != before.st_size or len(payload) > 512 * 1024 or checksum != expected):
        raise ValueError('Frozen helper source contents or identity changed')
    return dict(bytes=len(payload), sha256=checksum, identity=list(signature(after))), payload


def helper_source_facts(base=ROOT):
    result = {}
    for name, expected in HELPER_PINS.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Local helper source role required')
        result[name] = helper_payload(base / name, expected)[0]
    if sum(row['bytes'] for row in result.values()) > 2 * 1024**2:
        raise ValueError('Small helper source snapshot budget exceeded')
    return result


def check_loaded_helpers():
    bindings = [fact, write, strict_json, require, managed.cgroup_observation, managed.default_backend,
                admission.checked_build, admission.executable_copy, admission.checked_task_receipts,
                admission.validate_memory_report, admission.file_identity, admission.digest, admission.require,
                stopped, actual_ports, regular, actual_ports.__globals__['digest'], verify_archive]
    records = []
    for function in bindings:
        module = sys.modules[function.__module__]
        path = Path(module.__file__).absolute()
        name = path.relative_to(ROOT).as_posix()
        if (name not in HELPER_PINS or function.__globals__ is not module.__dict__ or
                Path(function.__code__.co_filename).absolute() != path):
            raise ValueError('Loaded proof function must originate in the pinned helper source')
        records.append(dict(module=module.__name__, function=function.__name__, source=name,
                            source_sha256=HELPER_PINS[name]))
    return records


def snapshot_helpers(destination, before, base=ROOT):
    if set(before) != set(HELPER_PINS):
        raise ValueError('Complete fixed helper inventory required')
    destination.mkdir(mode=0o700)
    result = {}
    for name, expected in HELPER_PINS.items():
        observed, payload = helper_payload(base / name, expected)
        if observed != before[name]:
            raise ValueError('Helper source changed before snapshot')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(payload)
        result[name] = helper_payload(target, expected)[0]
        if result[name]['bytes'] != before[name]['bytes']:
            raise ValueError('Helper source snapshot differs')
    return result


def checked_reference(root):
    root = root.absolute()
    manifest = regular(root / 'SEALED_FILES.json')
    require(fact(manifest)['sha256'] == REFERENCE_SEAL, 'Exact original reference seal required')
    rows = strict_json(manifest.read_text())
    require(isinstance(rows, list) and len(rows) == 907 and sum(row['bytes'] for row in rows) == 205782032,
            'Complete original reference inventory required')
    names = [row['path'] for row in rows]
    require(len(set(names)) == len(names) and all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names),
            'Unique local reference members required')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*')
              if not path.is_dir() and path.name != 'SEALED_FILES.json'}
    require(actual == set(names), 'Original reference membership changed')
    for row in rows:
        value = fact(regular(root / row['path']))
        require(value['bytes'] == row['bytes'] and value['sha256'] == row['sha256'], 'Original reference bytes changed')
    require(fact(regular(root / 'official-singscore_1.32.0.tar.gz'))['sha256'] == OFFICIAL_TAR_SHA and
            fact(regular(root / 'current-source/plugins/singscore/scripts/singscore.sh'))['sha256'] == ORIGINAL_SHA,
            'Original official source and previous adapter must remain immutable')
    methods = {node.name for node in ast.walk(ast.parse((ROOT / 'plugins/singscore/tests/test_contract.py').read_text()))
               if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}
    cases = {path.name for path in (root / 'after').iterdir() if path.is_dir()}
    require(len(methods) == 31 and cases == methods and EXISTING in cases and POSITIVE - {'official-author-example'} <= cases,
            'All original 31 contract cases required')
    inventory = sorted(cases - {EXISTING}) + ['official-author-example']
    require(len(inventory) == 31 and sum(name in POSITIVE for name in inventory) == 10,
            'Exact ten positive and twenty-one negative DAG inventory required')
    return inventory


def checked_archive(archives, session, seal):
    checked = verify_archive(archives, session, seal)
    state = strict_json(regular(archives / session / 'SESSION.json').read_text())
    require(checked['positive_worker_exit_verified'] is True and type(state.get('launcher_exit_status')) is int and
            state['launcher_exit_status'] == 0, 'Failed archive cannot provide a successful proof')
    return Path(checked['artifact_root']), checked


def checked_prior(archives, output):
    repair, repair_record = checked_archive(archives, REPAIR_SESSION, REPAIR_SEAL)
    report = strict_json((repair / 'permanent/b-publication-ownership/verification.json').read_text())
    for name in ('plugins/singscore/scripts/singscore.sh', 'tests/test_singscore_publication_ownership.py'):
        require(report['current_sources'][name]['sha256'] == PINS[name] and
                fact(regular(repair / 'permanent/b-publication-ownership/source' / name))['sha256'] == PINS[name],
                'Publication engineering proof must cover these exact sources')
    require(type(report.get('actual_tests_run')) is int and report['actual_tests_run'] == 52 and
            report.get('complete') is True and report.get('official_UCell_or_singscore_computation_executed') is False,
            'Prior engineering proof cannot replace official method execution')
    previous, previous_record = checked_archive(archives, PREVIOUS_SESSION, PREVIOUS_SEAL)
    previous_root = previous / 'permanent/singscore-current-dag'
    previous_report = strict_json(regular(previous_root / 'verification.json').read_text())
    require(previous_report.get('fixed_original_cases') == 31 and previous_report.get('full_RDS_readbacks') == 10 and
            previous_report.get('method_sha256') == ORIGINAL_SHA and previous_report.get('original_reference_seal') == REFERENCE_SEAL and
            previous_report.get('formal_authorized') is False and previous_report.get('g0_granted') is False and
            fact(regular(previous_root / 'source/scripts/singscore.sh'))['sha256'] == ORIGINAL_SHA,
            'Complete original method inventory and immutable historical source required')
    write(output / 'verified-prior-archives.json', dict(repair=repair_record, previous=previous_record,
        prior_engineering_tests_not_node_certificates=True))
    return previous_root


def job_for(work, source):
    return dict(scope=SCOPE, expected_plugin_name='singscore', run_root=str(work),
        plugin_manifest=str(source / 'manifest.toml'), plugin_manifest_sha256=MANIFEST_SHA,
        script_sha256={'scripts/singscore.sh': SCRIPT_SHA}, additional_plugins=[], panel_overrides=[],
        bundles=[], panel_manifest_sha256={},
        nodes=[dict(id='input' + str(port), kind='file_reference', spec=dict(path='vfs:///' + name,
            format='tsv', hash_content=True)) for port, name in enumerate(INPUT_NAMES)] +
            [dict(id='analysis', kind='singscore_bspec', spec={})],
        edges=[{'from': 'input' + str(port), 'from_port': 0, 'to': 'analysis', 'to_port': port} for port in range(3)])


def validate_report(report, build, *, positive):
    require(report.get('engine_source_revision') == build['engine_commit'] and report.get('scope') == SCOPE and
            report.get('plugin_name') == 'singscore' and report.get('original_manifest_sha256') == MANIFEST_SHA and
            report.get('additional_plugin_identities') == [] and report.get('input_hashing') == 'ContentRequired' and
            report.get('incremental') is False and type(report.get('max_concurrency')) is int and report['max_concurrency'] == 1 and
            all(report.get(name) is False for name in ('native_statistical_factories_registered', 'current_daemon_verified',
                'scientific_authorized', 'g0_granted')), 'Exact isolated no-authority SDK report required')
    rows = report['first_run']['nodes']
    require(len(rows) == 4 and {row['id'] for row in rows} == {'input0', 'input1', 'input2', 'analysis'} and
            all(row.get('reused') is False for row in rows), 'All four fresh nodes must be recorded')
    nodes = {row['id']: row for row in rows}
    for port in range(3):
        node = nodes['input' + str(port)]
        require(node.get('status') == 'success' and node.get('node_type') == 'file_reference' and
                set(node.get('port_assignments', {})) == {'0'}, 'Every input reference must execute successfully')
    method = nodes['analysis']
    execution = method.get('execution', {})
    require(method.get('node_type') == 'singscore_bspec' and method.get('status') == ('success' if positive else 'failed') and
            type(execution.get('exit_code')) is int and execution['exit_code'] == (0 if positive else 1) and
            execution.get('image') == IMAGE and execution.get('image_digest') == IMAGE.split('@')[1],
            'Exact method outcome required; infrastructure failure is not a method refusal')
    expected_errors = {} if positive else {'analysis': method.get('error')}
    require(isinstance(report['first_run'].get('errors'), dict) and report['first_run']['errors'] == expected_errors and
            report['first_run'].get('ok') is positive and set(method.get('port_assignments', {})) ==
            ({'0', '1', '2'} if positive else set()), 'Failed method cannot publish normal ports or count as success')
    if positive:
        require(method.get('error') is None, 'Successful method must not retain errors')
    else:
        error = method.get('error')
        require(isinstance(error, dict) and error.get('kind') == 'node_error' and isinstance(error.get('message'), str)
                and error['message'], 'Attributable method error required')
    return nodes


def checked_inputs(work, nodes, scratch, workspace):
    require(workspace.resolve(strict=True) == workspace and not workspace.is_symlink() and
            workspace.parent.parent == scratch and re.fullmatch('[0-9a-f]{2}', workspace.parent.name) and
            re.fullmatch('[0-9a-f]{62}', workspace.name) and workspace.stat().st_uid == os.getuid(),
            'Exact actual-create owned method workspace required')
    method = nodes['analysis']
    require(len(method.get('inputs', [])) == 3, 'Three actual input bindings required')
    result = []
    for port, name in enumerate(INPUT_NAMES):
        source = regular(work / name)
        identity = fact(source)
        matches = [row for row in method['inputs'] if type(row.get('to_port')) is int and row['to_port'] == port]
        require(len(matches) == 1, 'Unique typed input role required')
        bound = matches[0]
        expected_path = 'vfs:///' + name
        assigned = nodes['input' + str(port)]['port_assignments']['0']
        for row in (bound, assigned):
            require(row.get('path') == expected_path and row.get('fingerprint', {}).get('size') == identity['bytes'] and
                    row['fingerprint'].get('content_hash') == 'sha256:' + identity['sha256'], 'Complete bound source fingerprint required')
        require(bound.get('kind') == 'File' and bound.get('from') == 'input' + str(port) and type(bound.get('from_port')) is int and bound['from_port'] == 0 and
                assigned.get('format') == 'tsv', 'Source node and destination port must agree')
        staged = [path for path in scratch.rglob('input-' + str(port) + '.tsv')
                  if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        require(len(staged) == 1, 'One exact staged input required')
        require(staged[0].parent.parent.parent == workspace,
                'Every input role must belong to the same actual method-create workspace')
        before = staged[0].lstat()
        if stat.S_ISLNK(before.st_mode):
            require(os.readlink(staged[0]) == str(source) and staged[0].resolve(strict=True) == source,
                    'Staged link must point directly to its exact owned source')
            checksum = hashlib.sha256(staged[0].read_bytes()).hexdigest()
        else:
            checksum = fact(regular(staged[0]))['sha256']
        after = staged[0].lstat()
        fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(fields(before) == fields(after) and fact(source) == identity and checksum == identity['sha256'],
                'Staged/source bytes or identity changed')
        result.append(dict(port=port, name=name, bytes=identity['bytes'], sha256=checksum))
    return result


def expected_error(original):
    lines = [line for line in regular(original / 'node.stderr.txt').read_text().splitlines() if line.startswith('ERROR: ')]
    require(len(lines) == 1, 'One exact original method diagnostic required')
    return lines[0]


def write_case_checkpoint(output, records):
    names = [record['case'] for record in records]
    require(0 < len(records) <= 31 and len(set(names)) == len(names), 'Unique nonempty partial case inventory required')
    directory = output / 'case-checkpoints'
    directory.mkdir(mode=0o700, exist_ok=True)
    require(directory.resolve(strict=True) == directory and not directory.is_symlink(),
            'Owned unaliased checkpoint directory required')
    write(directory / (str(len(records)).zfill(3) + '.json'), dict(actual_completed_cases=len(records),
        completed_case_ids=names, latest_case=records[-1], complete_inventory_proven=False, g0_granted=False))


def run_recorded(command, work, label, *, timeout=180, environment=None):
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as error:
        (work / (label + '.stdout')).write_bytes(error.stdout or b'')
        (work / (label + '.stderr')).write_bytes(error.stderr or b'')
        write(work / (label + '-exit.json'), dict(actual_exit=None, timed_out=True))
        raise
    (work / (label + '.stdout')).write_bytes(completed.stdout)
    (work / (label + '.stderr')).write_bytes(completed.stderr)
    write(work / (label + '-exit.json'), dict(actual_exit=completed.returncode, timed_out=False))
    return completed


def preserve_logs(work, scratch):
    target = work / 'preserved-logs'
    target.mkdir(exist_ok=True)
    records = []
    if not scratch.exists():
        return records
    roots = [path for path in scratch.glob('*/*') if path.is_dir() and not path.is_symlink() and
             re.fullmatch('[0-9a-f]{2}', path.parent.name) and re.fullmatch('[0-9a-f]{62}', path.name)]
    require(len(roots) <= 1, 'Only this single-method workspace may supply diagnostic files')
    for root in roots:
        for relative in ('.autonomics/logs/stdout.log', '.autonomics/logs/stderr.log', 'singscore.log'):
            source = root / relative
            if not os.path.lexists(source):
                continue
            source = regular(source)
            before = fact(source)
            require(source.stat().st_uid == os.getuid() and before['bytes'] <= 32 * 1024**2,
                    'Bounded owned diagnostic required')
            destination = target / relative.replace('/', '__')
            with destination.open('xb') as stream:
                stream.write(source.read_bytes())
            require(fact(source) == before and fact(destination)['sha256'] == before['sha256'], 'Diagnostic changed while preserving')
            records.append(dict(source=str(source), destination=str(destination), bytes=before['bytes'], sha256=before['sha256']))
    write(work / 'preserved-log-index.json', records)
    return records


def graph(runner, build, work, source, definition, original, previous):
    job = job_for(work, source)
    write(work / 'job.json', job)
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    environment = dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts'))
    primary = None
    try:
        for label, flags in [('admission', ['--validate-job']), ('runner', [])]:
            completed = run_recorded([str(runner), *flags, str(work / 'job.json')], work, label, environment=environment)
            require(type(completed.returncode) is int and completed.returncode == 0, 'SDK runner failed before attributable reporting')
        report = strict_json(regular(work / 'dag-report.json').read_text())
        nodes = validate_report(report, build, positive=work.name in POSITIVE)
        method = nodes['analysis']
        created = [strict_json(line) for line in regular(work.parent / 'actual-container-create.jsonl').read_text().splitlines()]
        matching = [row for row in created if row.get('run_name') == method['execution']['run_name']]
        require(len(matching) == 1 and matching[0]['staged_script_sha256'] == SCRIPT_SHA and
                matching[0]['resources_overridden'] is False and matching[0]['input_count'] == matching[0]['output_count'] == 3 and
                matching[0]['actual_cpus'] == 2 and matching[0]['actual_memory_bytes'] == METHOD_MEMORY_BYTES,
                'One exact original-resource method create must bind this actual report')
        bindings = checked_inputs(work, nodes, scratch, Path(matching[0]['workspace']))
        memory = admission.validate_memory_report(report)
        receipts = admission.checked_task_receipts(work, nodes)
        require(len(receipts) == 4 and all(row['actual_task_resources'] == {} for row in receipts.values()),
                'Actual empty native resource leases must not be promoted to manifest limits')
        if work.name in POSITIVE:
            ports = actual_ports(work, definition, method, scratch)
            old_job = strict_json(regular(previous / work.name / 'job.json').read_text())
            previous_outputs = previous / work.name / definition['artifact_prefix'].removeprefix('/')
            old_ports = []
            for port in definition['ports']['outputs']:
                matches = list(previous_outputs.glob('*/' + port['path']))
                require(len(matches) == 1, 'One sealed previous result per declared port required')
                old_ports.append(regular(matches[0]))
            require(old_job.get('scope') == SCOPE and ports[0].read_bytes() == old_ports[0].read_bytes() and
                    ports[2].read_bytes() == old_ports[2].read_bytes(), 'Complete original score TSV/log bytes changed')
            copies = work / 'declared-outputs'
            copies.mkdir()
            for port in ports:
                shutil.copyfile(port, copies / port.name)
            write(work / 'normal-ports.json', [dict(port=index, path=str(copies / port.name), **fact(copies / port.name))
                                              for index, port in enumerate(ports)])
        else:
            marker = expected_error(original)
            stderr = regular(Path(method['execution']['stderr_log']['path']))
            require(stderr.is_relative_to(scratch) and marker in stderr.read_text() and marker in method['error']['message'],
                    'Exact original method refusal must appear in owned stderr and node error')
            logs = list(scratch.rglob('singscore.log'))
            require(len(logs) == 1 and marker in regular(logs[0]).read_text(), 'Declared failure log must preserve the exact original refusal')
            require(not any(list(root.rglob(name)) for root in (scratch, work / 'artifacts')
                            for name in ('singscore_scores.tsv', 'singscore.RDS')), 'Refusal must not leave normal results')
            ports = []
        record = dict(case=work.name, positive=work.name in POSITIVE, actual_nodes=4, actual_edges=3,
            input_bindings=bindings, actual_task_receipts=4, declared_output_ports=len(ports), memory=memory,
            method_exit=method['execution']['exit_code'], specific_refusal=None if ports else expected_error(original))
        write(work / 'verification.json', record)
        return record
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            preserve_logs(work, scratch)
        except Exception as error:
            write(work / 'diagnostic-preservation-error.json', dict(error_type=type(error).__name__, message=str(error),
                original_error_preserved=primary is not None, successful_proof=False))
            if primary is None:
                raise


def install_launcher(prefix, temporary, output):
    directory = temporary / 'singscore-backend-bin'
    directory.mkdir(mode=0o700)
    launcher = directory / 'podman'
    program = '''#!/usr/bin/python3
import hashlib,json,os,stat,sys
from pathlib import Path
arguments=sys.argv[1:]
if not arguments or arguments[0].startswith('-'): raise SystemExit('Backend option override refused')
if arguments[0]=='create':
 def observed_option(name):
  if arguments.count(name)!=1: return None
  index=arguments.index(name)+1
  return arguments[index] if index<len(arguments) else None
 observed=dict(run_name=observed_option('--name'),cpus=observed_option('--cpus'),memory=observed_option('--memory'),
  network=observed_option('--network'),pull=observed_option('--pull'),readonly_count=arguments.count('--read-only'),
  managed_backend_not_yet_invoked=True)
 descriptor=os.open(__OBSERVED__,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
 with os.fdopen(descriptor,'a') as handle: handle.write(json.dumps(observed)+'\\n')
 def option(name):
  if arguments.count(name)!=1: raise SystemExit('Missing or repeated resource option')
  return arguments[arguments.index(name)+1]
 if option('--cpus')!='2' or option('--memory')!=__MEMORY_STRING__: raise SystemExit('Unexpected original singscore resources')
 if arguments.count('--read-only')!=1 or arguments.count('--pull')!=1 or option('--pull')!='never': raise SystemExit('Original readonly/no-pull contract differs')
 if option('--network')!='none': raise SystemExit('Original isolated network contract differs')
 selected={}
 for index,value in enumerate(arguments[:-1]):
  if value=='--env':
   key,separator,content=arguments[index+1].partition('=')
   if key.startswith('AUTONOMICS_'):
    if not separator or key in selected: raise SystemExit('Duplicate or malformed SDK environment')
    selected[key]=content
 if selected.get('AUTONOMICS_SCRIPT')!='/work/.autonomics/script' or selected.get('AUTONOMICS_WORKDIR')!='/work' or selected.get('AUTONOMICS_INPUT_COUNT')!='3' or selected.get('AUTONOMICS_OUTPUT_COUNT')!='3': raise SystemExit('Original SDK script and input/output counts differ')
 for stem in ('INPUT','OUTPUT'):
  keys={key for key in selected if key.startswith('AUTONOMICS_'+stem) and key!='AUTONOMICS_'+stem+'_COUNT'}
  if keys!={'AUTONOMICS_'+stem+str(index) for index in range(3)}: raise SystemExit('Original SDK port roles differ')
 mounts=[]
 for index,value in enumerate(arguments[:-1]):
  if value=='--mount':
   pieces={}
   for piece in arguments[index+1].split(','):
    key,separator,content=piece.partition('=')
    if key in pieces: raise SystemExit('Duplicate mount field')
    pieces[key]=content if separator else True
   if pieces.get('destination')=='/work':
    if pieces.get('type')!='bind' or pieces.get('rw')!='true' or set(pieces)!={'type','source','destination','rw'}: raise SystemExit('Original owned workspace mount differs')
    mounts.append(Path(pieces['source']))
 if len(mounts)!=1: raise SystemExit('One SDK workspace required')
 workspace=mounts[0]
 allowed=Path(__ALLOWED__)
 if workspace.resolve()!=workspace or not workspace.is_relative_to(allowed) or workspace==allowed or workspace.is_symlink() or workspace.stat().st_uid!=os.getuid(): raise SystemExit('Owned SDK scratch workspace required')
 script=workspace/'.autonomics/script'
 before=script.lstat()
 identity=lambda value:(value.st_dev,value.st_ino,value.st_uid,value.st_gid,value.st_mode,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
 if not stat.S_ISREG(before.st_mode) or script.resolve()!=script or hashlib.sha256(script.read_bytes()).hexdigest()!=__SCRIPT_SHA__ or identity(script.lstat())!=identity(before): raise SystemExit('Exact staged scientific source required')
 if arguments.count(__IMAGE__)!=1: raise SystemExit('Original pinned official image differs')
 record=dict(run_name=option('--name'),original_cpus=2,original_memory_bytes=__MEMORY_BYTES__,
  actual_cpus=2,actual_memory_bytes=__MEMORY_BYTES__,resources_overridden=False,manifest_memory='2g',
  staged_script_sha256=__SCRIPT_SHA__,workspace=str(workspace),input_count=3,output_count=3)
 descriptor=os.open(__RECORD__,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
 with os.fdopen(descriptor,'a') as handle: handle.write(json.dumps(record)+'\\n')
os.execv(__PROGRAM__,__PREFIX__+arguments)
'''.replace('__RECORD__', repr(str(output / 'actual-container-create.jsonl'))).replace(
        '__OBSERVED__', repr(str(output / 'observed-create-declarations.jsonl'))).replace(
        '__MEMORY_STRING__', repr(str(METHOD_MEMORY_BYTES))).replace('__MEMORY_BYTES__', str(METHOD_MEMORY_BYTES)).replace(
        '__PROGRAM__', repr(prefix[0])).replace('__PREFIX__', repr(prefix)).replace(
        '__ALLOWED__', repr(str(temporary / 'official-plugin-container-workspaces'))).replace(
        '__SCRIPT_SHA__', repr(SCRIPT_SHA)).replace('__IMAGE__', repr(IMAGE))
    with launcher.open('x') as handle:
        handle.write(program)
    launcher.chmod(0o700)
    os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
    return launcher, fact(launcher)


def runner_identity_unchanged(path, expected):
    return admission.file_identity(regular(path)) == expected


def finalize_stoppage(prefix, permanent, output, primary):
    inventory = permanent / 'container-intents.json'
    if inventory.exists():
        expected = len(strict_json(regular(inventory).read_text())['intents'])
        return stopped(prefix, permanent, output, expected)
    creates = output / 'actual-container-create.jsonl'
    rows = [] if not creates.exists() else [strict_json(line) for line in regular(creates).read_text().splitlines()]
    require(primary is not None and not rows, 'Missing intents after managed create cannot certify stoppage')
    observed = output / 'observed-create-declarations.jsonl'
    write(output / 'container-not-started.json', dict(status='NOT_STARTED_NO_MANAGED_CREATE_INTENTS_NOT_SUCCESS',
        managed_intent_file_present=False, proxy_accepted_creates=0,
        proxy_observed_declarations=0 if not observed.exists() else len(regular(observed).read_text().splitlines()),
        original_error_type=type(primary).__name__, method_execution_proven=False,
        container_stoppage_certified=False, global_quiescence_claimed=False, g0_granted=False))
    return []


def runtime_backend(kind, output):
    shim = str(regular(Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])))
    if kind == 'default':
        prefix = [shim, '--cgroup-manager=cgroupfs']
        backend = managed.default_backend(prefix, output)
        storage = Path(backend['graph_root'])
    else:
        require(fact(regular(admission.OWNER))['sha256'] == admission.OWNER_SHA, 'Original software installation owner changed')
        owner = strict_json(admission.OWNER.read_text())
        for key in ('storage', 'runroot'):
            item = owner[key]
            value = Path(item['path']).stat()
            require((value.st_dev, value.st_ino, value.st_uid, value.st_gid) ==
                    (item['device'], item['inode'], item['uid'], item['gid']), 'Owned runtime store identity changed')
        prefix = [shim, *owner['runtime_backend']]
        storage = Path(owner['storage']['path'])
        backend = dict(kind=kind, owner_sha256=admission.OWNER_SHA, storage=str(storage), backend=owner['runtime_backend'])
    result = run_recorded([*prefix, 'image', 'inspect', IMAGE], output, 'image-inspect', timeout=60)
    require(result.returncode == 0, 'Image missing on explicitly selected backend; no pull or fallback allowed')
    rows = strict_json(result.stdout)
    require(isinstance(rows, list) and len(rows) == 1, 'One exact installed official image required')
    observed = rows[0]
    config = observed['Id'].removeprefix('sha256:')
    requested = IMAGE.split('@sha256:')[1]
    encoded = lambda name: '=' + base64.b64encode(name.encode()).decode()
    image_directory = storage / 'overlay-images' / config
    manifest_bytes = regular(image_directory / encoded('manifest-sha256:' + requested)).read_bytes()
    config_bytes = regular(image_directory / encoded('sha256:' + config)).read_bytes()
    require(hashlib.sha256(manifest_bytes).hexdigest() == requested and hashlib.sha256(config_bytes).hexdigest() == config and
            strict_json(manifest_bytes)['config']['digest'] == 'sha256:' + config,
            'Requested raw manifest/configuration identity differs')
    configuration = strict_json(config_bytes)
    require(configuration['os'] == 'linux' and configuration['architecture'] == 'amd64' and
            configuration['rootfs']['diff_ids'] == observed['RootFS']['Layers'], 'Actual image ordered layer identity differs')
    (output / 'image-manifest.json').write_bytes(manifest_bytes)
    (output / 'image-config.json').write_bytes(config_bytes)
    write(output / 'backend-identity.json', dict(backend=backend, reference=IMAGE, requested_manifest_sha256=requested,
        config_sha256=config, primary_digest=observed['Digest'], no_pull=True, no_fallback=True))
    return prefix, backend


def graph_controls(runner, source, fixture, output):
    records = []
    for name in ('missing-metadata-edge', 'unknown-parameter'):
        work = output / name
        work.mkdir()
        for filename in INPUT_NAMES:
            shutil.copyfile(fixture / filename, work / filename)
        job = job_for(work, source)
        if name == 'missing-metadata-edge':
            job['edges'] = job['edges'][:2]
        else:
            job['nodes'][-1]['spec'] = {'unexpected_free_parameter': 1}
        write(work / 'job.json', job)
        run = run_recorded([str(runner), str(work / 'job.json')], work, 'construction')
        text = run.stderr.decode()
        require(type(run.returncode) is int and run.returncode == 1 and
                (('PortDisconnected { node: "analysis", port: 2 }' in text) if name == 'missing-metadata-edge' else
                 'unexpected_free_parameter' in text), 'Exact pre-execution graph refusal required')
        require(not (work / 'dag-report.json').exists() and not (work / 'task-receipts').exists(),
                'Graph construction refusal must not create method results or task receipts')
        records.append(dict(case=name, actual_exit=run.returncode, actual_method_execution=False))
    return records


def official_readback(prefix, source, reference, output, cases):
    pairs = []
    for case in cases:
        if case not in POSITIVE:
            continue
        work = output / case
        original = reference / ('official-example-fixture' if case == 'official-author-example' else 'after/' + case)
        shutil.copyfile(regular(original / 'official_reference.RDS'), work / 'sealed-official-reference.RDS')
        pairs.append(dict(case=case, actual_rds='/proof/' + case + '/declared-outputs/singscore.RDS',
            reference_rds='/proof/' + case + '/sealed-official-reference.RDS',
            scores_tsv='/proof/' + case + '/declared-outputs/singscore_scores.tsv', metadata_tsv='/proof/' + case + '/samples.tsv'))
    require(len(pairs) == 10 and {row['case'] for row in pairs} == POSITIVE, 'All ten full official objects required')
    with (output / 'readback-pairs.tsv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pairs[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(pairs)
    with (source / 'ast-and-package.R').open('x') as handle:
        handle.write(AST_AND_PACKAGE)
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=1073741824', '--pids-limit=128', '--tmpfs=/tmp:rw,size=64m',
        '-v', str(source) + ':/source:ro', '-v', str(reference) + ':/reference:ro', '-v', str(output) + ':/proof:rw',
        '--entrypoint=Rscript', IMAGE, '--vanilla', '-e',
        'args<-c("/reference/current-source/plugins/singscore/scripts/singscore.sh","/source/scripts/singscore.sh",'
        '"/reference/fresh-official-package.RDS","/proof/ast-package-verification.json");'
        'commandArgs<-function(trailingOnly=FALSE)args;source("/source/ast-and-package.R");'
        'commandArgs<-function(trailingOnly=FALSE)c("/proof/readback-pairs.tsv","/proof/mutations");'
        'source("/source/verify_singscore_joined.R")']
    write(output / 'readback-command.json', command)
    result = run_recorded(command, output, 'official-readback', timeout=240)
    text = result.stdout.decode()
    require(type(result.returncode) is int and result.returncode == 0 and
            'VERIFIED_COMPLETE_PAIRS 10 REJECTED_MUTATIONS 6' in text and
            sum(line.endswith('COMPLETE_RDS_IDENTICAL_JOINED_FIELDS_AND_ATTRIBUTES_PASS') for line in text.splitlines()) == 10 and
            sum(line.endswith('MUTATED_COMPLETE_RDS_REJECTED') for line in text.splitlines()) == 6,
            'All ten complete objects and six comparator mutants must really execute')
    observed = strict_json(regular(output / 'ast-package-verification.json').read_text())
    expected = dict(scientific_AST_statements_identical=31, original_scientific_helpers_identical=2,
        official_package_functions_identical=31, rankGenes_methods_identical=5, simpleScore_methods_identical=4,
        R_version='4.6.1', singscore_version='1.32.0', independent_reference_regenerated=False, g0_granted=False)
    require(json.dumps(observed, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False),
        'Actual installed official package and unchanged scientific AST must match the frozen independent reference')
    return observed


def preexisting_control(prefix, source, reference, output):
    work = output / EXISTING
    work.mkdir()
    original = reference / 'after' / EXISTING
    for name in INPUT_NAMES:
        shutil.copyfile(regular(original / name), work / name)
    sentinel = work / 'singscore_scores.tsv'
    sentinel.write_bytes(regular(original / 'output/scores.tsv').read_bytes())
    before = fact(sentinel)
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=1073741824', '--pids-limit=128', '--tmpfs=/tmp:rw,size=64m',
        '-v', str(work) + ':/proof:rw', '-v', str(source) + ':/source:ro', '--entrypoint=Rscript']
    for port, name in enumerate(INPUT_NAMES):
        command += ['-e', 'AUTONOMICS_INPUT' + str(port) + '=/proof/' + name]
    for port, name in enumerate(('singscore_scores.tsv', 'singscore.RDS', 'singscore.log')):
        command += ['-e', 'AUTONOMICS_OUTPUT' + str(port) + '=/proof/' + name]
    result = run_recorded([*command, IMAGE, '--vanilla', '/source/scripts/singscore.sh'], work, 'direct')
    marker = expected_error(original)
    require(type(result.returncode) is int and result.returncode == 1 and fact(sentinel) == before and
            not (work / 'singscore.RDS').exists() and marker in regular(work / 'singscore.log').read_text(),
            'Actual preexisting-output refusal must preserve the entire foreign artifact identity')
    return dict(case=EXISTING, actual_exit=1, sentinel=before, foreign_identity_and_bytes_unchanged=True,
                specific_refusal=marker, not_counted_as_DAG=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--runtime-backend', required=True, choices=('default', 'owner-canonical'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require(args.execute and os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),
            'Explicit --execute within a managed session required')
    permanent, temporary = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']), Path(os.environ['TMPDIR'])
    output = permanent / 'singscore-publication-requalification'
    output.mkdir(mode=0o700)
    helpers_before = helper_source_facts()
    loaded_helpers = check_loaded_helpers()
    helpers_snapshot = snapshot_helpers(output / 'helper-source', helpers_before)
    write(output / 'helper-source-provenance.json', dict(sources=helpers_before, snapshots=helpers_snapshot,
        loaded_function_bindings=loaded_helpers,
        scope='PINNED_USED_HELPER_CALL_PATH_SOURCES_NOT_WHOLE_PYTHON_ENVIRONMENT_OR_HOSTILE_MEMORY_ATTESTATION',
        unused_transitive_imports_and_standard_library_not_certified=True,
        malicious_concurrent_hotpatch_protection_claimed=False))
    before = source_facts()
    own_before = fact(regular(Path(__file__)))
    shutil.copyfile(Path(__file__), output / 'driver.py')
    parent = managed.cgroup_observation()
    require(parent['memory_max_bytes'] == 2 * 1024**3 and shutil.disk_usage(output).free >= 2 * 1024**3,
            'Recorded 2Gi managed service and scratch reserve required')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    require(args.build_record.is_relative_to(archives / BUILD_SESSION), 'Exact already-sealed repaired-kernel SDK required')
    build, built = admission.checked_build(archives, args.runner, args.build_record, BUILD_SEAL)
    runner, runner_before = admission.executable_copy(args.runner, temporary)
    require(fact(runner)['sha256'] == RUNNER_SHA, 'No SDK fallback allowed')
    write(output / 'verified-build.json', built)
    cases = checked_reference(args.reference)
    previous = checked_prior(archives, output)
    source = output / 'source'
    (source / 'scripts').mkdir(parents=True)
    for name, destination in [('plugins/singscore/manifest.toml', 'manifest.toml'),
            ('plugins/singscore/scripts/singscore.sh', 'scripts/singscore.sh'),
            ('tools/verify_singscore_joined.R', 'verify_singscore_joined.R')]:
        shutil.copyfile(regular(ROOT / name), source / destination)
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    require(manifest['image']['reference'] == IMAGE and len(manifest['nodes']) == 1 and
            manifest['nodes'][0]['kind'] == 'singscore_bspec' and
            manifest['nodes'][0]['resources']['memory'] == MANIFEST_MEMORY and
            manifest['nodes'][0]['resources']['cpus'] == 2, 'Original single-kind interface and SI resource declaration required')
    write(output / 'sdk-resource-semantics.json', dict(source=SDK_RESOURCE_SOURCE,
        original_manifest_memory=MANIFEST_MEMORY, expected_actual_argv_memory=str(METHOD_MEMORY_BYTES),
        binary_GiB_not_assumed=True, existing_SDK_not_rebuilt=True))
    snapshot_before = {name: fact(regular(source / name)) for name in
                       ('manifest.toml', 'scripts/singscore.sh', 'verify_singscore_joined.R')}
    prefix, backend_before = runtime_backend(args.runtime_backend, output)
    launcher, launcher_before = install_launcher(prefix, temporary, output)
    results, controls, no_clobber, readback, observations = [], [], None, None, []
    primary = None
    try:
        controls = graph_controls(runner, source, args.reference / 'after/test_bidirectional_official_rank_and_all_scores', output)
        for name in cases:
            original = args.reference / ('after-official-example-dag-final' if name == 'official-author-example' else 'after/' + name)
            work = output / name
            work.mkdir()
            for filename in INPUT_NAMES:
                shutil.copyfile(regular(original / filename), work / filename)
            results.append(graph(runner, build, work, source, manifest['nodes'][0], original, previous))
            write_case_checkpoint(output, results)
        write(output / 'completed-cases.json', results)
        no_clobber = preexisting_control(prefix, source, args.reference, output)
        readback = official_readback(prefix, source, args.reference, output, cases)
        creates = [strict_json(line) for line in (output / 'actual-container-create.jsonl').read_text().splitlines()]
        require(len(creates) == 31 and len({row['run_name'] for row in creates}) == 31 and
                all(type(row['actual_cpus']) is int and row['actual_cpus'] == 2 and
                    type(row['actual_memory_bytes']) is int and row['actual_memory_bytes'] == METHOD_MEMORY_BYTES and
                    row['resources_overridden'] is False and row['staged_script_sha256'] == SCRIPT_SHA and
                    row['input_count'] == row['output_count'] == 3 for row in creates),
                'All thirty-one actual DAG method creates require the unchanged original resource declarations')
    except BaseException as error:
        primary = error
        raise
    finally:
        secondary = []
        for name, action in [('stoppage', lambda: finalize_stoppage(prefix, permanent, output, primary)),
                ('source-postcheck', lambda: require(source_facts() == before and fact(regular(Path(__file__))) == own_before and
                    runner_identity_unchanged(args.runner, runner_before) and fact(launcher) == launcher_before and
                    all(fact(regular(source / name)) == value for name, value in snapshot_before.items()),
                    'Proof or method source, runner, or launcher changed')),
                ('helper-postcheck', lambda: require(helper_source_facts() == helpers_before and
                    helper_source_facts(output / 'helper-source') == helpers_snapshot and check_loaded_helpers() == loaded_helpers,
                    'Pinned helper source, snapshot or loaded function binding changed')),
                ('reference-postcheck', lambda: require(checked_reference(args.reference) == cases, 'Reference inventory changed'))]:
            try:
                value = action()
                if name == 'stoppage':
                    observations = value
            except Exception as error:
                secondary.append(dict(stage=name, error_type=type(error).__name__, message=str(error)))
        write(output / 'finalization.json', dict(primary_error_type=None if primary is None else type(primary).__name__,
            secondary_errors=secondary, source_and_reference_postchecks_passed=not secondary,
            success_not_inferred_from_cleanup=True, g0_granted=False))
        if primary is None:
            require(not secondary, 'Final source/reference/stoppage verification failed')
    require(len(results) == 31 and sum(row['positive'] for row in results) == 10 and len(observations) == 33 and
            len(controls) == 2, 'Complete 31 DAGs, two admission refusals and 33 stopped containers required')
    write(output / 'verification.json', dict(schema='SINGSCORE_PUBLICATION_REQUALIFICATION_V1',
        status='SCOPED_FIXED_SOURCE_COMPLETE_OLD_INVENTORY_OFFICIAL_AND_ISOLATED_DAG_REPLAY',
        sources=before, build=built, engine_commit=build['engine_commit'], backend=backend_before,
        helper_sources=helpers_before, helper_source_snapshots=helpers_snapshot,
        helper_source_scope='USED_CALL_PATH_ONLY_NOT_WHOLE_ENVIRONMENT_OR_HOSTILE_HOTPATCH_ATTESTATION',
        original_reference_seal=REFERENCE_SEAL, reference_members=907, reference_bytes=205782032,
        actual_DAGs=31, positive_DAGs=10, exact_method_refusals=21, nodes_per_DAG=4, edges_per_DAG=3,
        actual_input_bindings=93, actual_task_receipts=124, actual_normal_ports=30,
        graph_initialization_refusals=controls, direct_existing_output_refusal=no_clobber,
        official_whole_RDS_comparisons=10, comparator_mutant_refusals=6, method_and_package_identity=readback,
        actual_container_intents=33, stopped_intents=len(observations),
        native_task_resources_are_empty=True, manifest_resources_certified=False,
        resources_overridden=False, observed_method_resources=dict(cpus=2, memory_bytes=METHOD_MEMORY_BYTES,
            original_manifest_memory=MANIFEST_MEMORY, source=SDK_RESOURCE_SOURCE),
        independent_new_oracle_generated=False, real_research_inputs_read=False, production_changed=False,
        resident_method_execution_proven=False, scientific_authorization_granted=False, g0_granted=False))
    print('SINGSCORE_DAGS=31 FULL_OBJECTS=10 SPECIFIC_REFUSALS=21 STOPPED=33 G0=false')


if __name__ == '__main__':
    main()
