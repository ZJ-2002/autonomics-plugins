"""Tiny synthetic DAG regression for publication repairs; no research or deployment admission."""

import argparse
import ast
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
from tools import prove_b_publication_runtime as runtime
from tools import prove_frozen_a_harmonisation_dag as admission
from tools.prove_locked_b_source_transport import actual_ports, expected_refusal, regular
from tools.prove_frozen_a_family_runtime import stopped
from tools.reconcile_ab_evidence_index import verify_archive

DIRECT_SESSION = '3916f488e09e4ded99b39890cfc4cf68'
DIRECT_SEAL = '001806a1bd052088aefe6e663624c6b859d6252b8b839779e45569f332f568ef'
BASELINE = runtime.BASELINE
SCOPE = 'TECHNICAL_PLUGIN_DAG_NOT_G0'
PANEL_ID = 'autonomics-technical/unused-celltypist-nonmodel-marker'
PANEL_VPATH = '/synthetic-panels/unused-celltypist-nonmodel-marker'
PANEL_PAYLOAD = b'THIS IS NOT A CELLTYPIST MODEL\nUNUSED SYNTHETIC TRANSPORT MARKER ONLY\n'
QC_SHA = '2c4a19aad9daaac942f04b9a95b18351e53ab979a49a9df477245e958bb36ac6'
METHODS = {'pseudobulk': 'pseudobulk_counts', 'score': 'gene_set_score'}
require = runtime.require
write = runtime.write
fact = runtime.fact
strict_json = runtime.strict_json
COMPARATOR = '''import ast,json,sys
from pathlib import Path
import anndata as ad
source=Path("/source/qc_compare.py").read_text()
tree=ast.parse(source)
compare=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="compare")
boundary=next(index for index,node in enumerate(compare.body) if isinstance(node,ast.Assign)
    and any(isinstance(target,ast.Name) and target.id=="report" for target in node.targets))
compare.body=compare.body[:boundary]+[ast.Return(value=ast.Dict(keys=[ast.Constant("whole_AnnData_and_HDF5_checked"),
    ast.Constant("finite_values_checked")],values=[ast.Constant(True),ast.Call(func=ast.Name(id="int",ctx=ast.Load()),
        args=[ast.Name(id="finite",ctx=ast.Load())],keywords=[])]))]
namespace={}
exec(compile(ast.fix_missing_locations(tree),"/source/qc_compare.py","exec"),namespace)
root=Path("/proof")
result=namespace["compare"](root)
assert result["whole_AnnData_and_HDF5_checked"] is True and result["finite_values_checked"]>0
result.update(scope="WHOLE_H5AD_TRANSPORT_COMPARISON_NOT_QC_REEVALUATION",actual_DAG_executed=False,G0=False)
(root/"whole-object-comparison.json").write_text(json.dumps(result,indent=2)+"\\n")
'''


def checked_direct(output):
    require(re.fullmatch('[0-9a-f]{32}', DIRECT_SESSION) and re.fullmatch('[0-9a-f]{64}', DIRECT_SEAL),
        'Complete official direct runtime must be sealed before DAG execution')
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    verified = verify_archive(archives, DIRECT_SESSION, DIRECT_SEAL)
    require(verified['positive_worker_exit_verified'], 'Recorded successful direct runtime required')
    root = Path(verified['artifact_root']) / 'permanent/b-publication-runtime'
    value = strict_json((root / 'verification.json').read_text())
    require(value.get('actual_method_containers') == 2 and value.get('owned_container_intents_verified') == 2 and
        value.get('containers_remaining') == 0 and value.get('actual_DAG_executed') is False and
        value.get('scientific_authorization_granted') is False and value.get('g0_granted') is False,
        'Actual complete bounded direct proof without scientific authority required')
    runtime.check_pseudobulk_summary(value['pseudobulk'], root / 'pseudobulk')
    runtime.check_score_summary(value['score_genes'], root / 'score')
    require(value['sources'] == runtime.source_facts(), 'Current exact repairs must equal the sealed direct source')
    write(output / 'verified-direct.json', dict(session=DIRECT_SESSION, seal=DIRECT_SEAL,
        files=verified['files'], bytes=verified['bytes'], all_members_rehashed=True))
    return root


def snapshot_families(output):
    result = {}
    for family, changed in [('pseudobulk', 'scripts/pseudobulk_counts.py'),
            ('single-cell', 'scripts/score_genes.py')]:
        root = 'plugins/' + family + '/'
        manifest_bytes = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + root + 'manifest.toml'])
        require(hashlib.sha256(manifest_bytes).hexdigest() == runtime.PINNED[root + 'manifest.toml'],
            'Unchanged original family manifest required')
        manifest = tomllib.loads(manifest_bytes.decode())
        names = {'manifest.toml'} | {node['command']['script_file'] for node in manifest['nodes']}
        require(len(manifest['nodes']) == (2 if family == 'pseudobulk' else 10), 'Complete original family kind inventory required')
        target = output / 'sources' / family
        hashes = {}
        for name in sorted(names):
            payload = regular(ROOT / (root + name)).read_bytes()
            expected = runtime.PINNED[root + name] if name in ['manifest.toml', changed] else hashlib.sha256(
                subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + root + name])).hexdigest()
            require(hashlib.sha256(payload).hexdigest() == expected, 'Unrelated family implementation changed')
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as handle:
                handle.write(payload)
            hashes[name] = fact(destination)
        label = 'pseudobulk' if family == 'pseudobulk' else 'score'
        definition = next(node for node in manifest['nodes'] if node['kind'] == METHODS[label])
        result[label] = dict(source=target, manifest=manifest, definition=definition, identities=hashes)
    return result


def panel_fixture(work):
    directory = work / PANEL_VPATH.lstrip('/')
    directory.mkdir(parents=True)
    (directory / 'NOT_A_MODEL.txt').write_bytes(PANEL_PAYLOAD)
    files = [dict(path='NOT_A_MODEL.txt', size=len(PANEL_PAYLOAD),
        sha256='sha256:' + hashlib.sha256(PANEL_PAYLOAD).hexdigest())]
    digest = 'sha256:' + hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    write(directory / 'manifest.json', dict(schema_version=1, id=PANEL_ID,
        version='explicit-unused-nonmodel-technical-v1', digest=digest, files=files))
    return dict(ident=PANEL_ID, desc='UNUSED SYNTHETIC NONMODEL MARKER; NOT A CELLTYPIST MODEL',
        vpath=PANEL_VPATH, source=PANEL_VPATH, digest=digest), {PANEL_VPATH: fact(directory / 'manifest.json')['sha256']}


def job_for(work, family, *, negative=False):
    pseudobulk = family['manifest']['plugin_name'] == 'pseudobulk'
    if pseudobulk:
        parameters = dict(sample_col='donor', celltype_col='celltype', min_cells=1, layer='',
            schema='deseq2', allow_non_integer=False,
            condition_column='TECHNICAL_MISSING_CONDITION' if negative else 'condition',
            id_schema='sample__celltype')
        panels, bundles, hashes = [], [], {}
    else:
        parameters = dict(gene_sets=json.dumps({'score': ['G' + str(index) for index in range(100)]
            if negative else ['G0', 'G1']}), ctrl_size=50, random_state=0)
        bundle, hashes = panel_fixture(work)
        bundles = [bundle]
        panels = [dict(binding='model', declared_bundle='wjixiang/catalog-celltypist-models-pan-immune',
            mount='/panels/celltypist_model', synthetic_bundle=PANEL_ID)]
    return dict(scope=SCOPE, run_root=str(work), plugin_manifest=str(family['source'] / 'manifest.toml'),
        expected_plugin_name=family['manifest']['plugin_name'], plugin_manifest_sha256=family['identities']['manifest.toml']['sha256'],
        script_sha256={name: value['sha256'] for name, value in family['identities'].items() if name != 'manifest.toml'},
        additional_plugins=[], panel_overrides=panels, bundles=bundles, panel_manifest_sha256=hashes,
        nodes=[dict(id='input', kind='file_reference', spec=dict(path='vfs:///input.h5ad', format='h5ad', hash_content=True)),
            dict(id='analysis', kind=family['definition']['kind'], spec=parameters)],
        edges=[dict(from_node='input', from_port=0, to='analysis', to_port=0)])


def wire_job(job):
    result = dict(job)
    result['edges'] = [{'from': edge['from_node'], **{name: value for name, value in edge.items() if name != 'from_node'}}
        for edge in job['edges']]
    return result


def default_launcher(prefix, temporary, output):
    original = regular(Path(prefix[0]))
    before = fact(original)
    require(prefix[1:] == ['--cgroup-manager=cgroupfs'] and
        os.environ['AUTONOMICS_PODMAN_PROGRAM'] == str(original), 'Exact original default managed shim required')
    directory = temporary / 'b-publication-default-bin'
    directory.mkdir()
    launcher = directory / 'podman'
    source = '''#!/usr/bin/python3
import json,os,sys
arguments=sys.argv[1:]
if arguments and arguments[0]=="create":
    def option(name):
        return arguments[arguments.index(name)+1] if name in arguments else None
    mounts=[arguments[index+1] for index,value in enumerate(arguments[:-1])
        if value=="--mount" and "destination=/panels/" in arguments[index+1]]
    record=dict(operation="create",name=option("--name"),cpus=option("--cpus"),
        memory=option("--memory"),panel_mounts=mounts)
    descriptor=os.open(__RECORD__,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(descriptor,"a") as handle: handle.write(json.dumps(record)+"\\n")
os.execv(__PROGRAM__,__PREFIX__+arguments)
'''.replace('__RECORD__', repr(str(output / 'actual-container-create.jsonl'))).replace(
        '__PROGRAM__', repr(str(original))).replace('__PREFIX__', repr(prefix))
    launcher.write_text(source)
    launcher.chmod(0o700)
    os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
    write(output / 'backend-launcher.json', dict(launcher=fact(launcher), original_shim=before,
        exact_backend_arguments=prefix[1:], parent_environment_changed=False, private_AB_backend_used=False))
    return original, before, launcher, fact(launcher)


def checked_input(work, method, scratch):
    original = regular(work / 'input.h5ad')
    expected = fact(original)
    bindings = method.get('inputs', [])
    require(len(bindings) == 1 and bindings[0]['from'] == 'input' and bindings[0]['from_port'] == 0 and
        bindings[0]['to_port'] == 0 and bindings[0]['path'] == 'vfs:///input.h5ad' and
        bindings[0]['fingerprint']['size'] == expected['bytes'] and
        bindings[0]['fingerprint']['content_hash'] == 'sha256:' + expected['sha256'],
        'Actual bound input must preserve its exact source role and complete byte identity')
    matches = [path for path in scratch.rglob('input-0.h5ad')
        if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
    require(len(matches) == 1, 'One actual staged method input required')
    staged = matches[0]
    before = staged.lstat()
    if stat.S_ISLNK(before.st_mode):
        require(os.readlink(staged) == str(original) and staged.resolve(strict=True) == original,
            'Only a direct symlink to this exact owned synthetic input is allowed')
        with staged.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        require(os.readlink(staged) == str(original), 'Staged input link changed during hashing')
        mode = 'EXACT_OWNED_SOURCE_SYMLINK'
    else:
        digest = fact(staged)['sha256']
        mode = 'REGULAR_BYTE_COPY'
    after = staged.lstat()
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(signature(before) == signature(after) and digest == expected['sha256'] and fact(original) == expected,
        'Complete staged input bytes or identity changed')
    return dict(mode=mode, bytes=expected['bytes'], sha256=expected['sha256'])


def graph(runner, build, work, family, *, negative=False):
    job = wire_job(job_for(work, family, negative=negative))
    write(work / 'job.json', job)
    for label, arguments in [('admission', ['--validate-job']), ('runner', [])]:
        result = subprocess.run([str(runner), *arguments, str(work / 'job.json')], capture_output=True, text=True,
            timeout=600, env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
        (work / (label + '.stdout')).write_text(result.stdout)
        (work / (label + '.stderr')).write_text(result.stderr)
        write(work / (label + '-exit.json'), dict(actual_exit=result.returncode))
        require(type(result.returncode) is int and result.returncode == 0, 'Actual graph runner/admission failed before expected reporting')
    report = strict_json((work / 'dag-report.json').read_text())
    rows = report['first_run']['nodes']
    require(len(rows) == 2 and {row['id'] for row in rows} == {'input', 'analysis'} and
        report['scope'] == SCOPE and report['engine_source_revision'] == build['engine_commit'] and
        report['original_manifest_sha256'] == family['identities']['manifest.toml']['sha256'] and
        report['plugin_name'] == family['manifest']['plugin_name'] and report['additional_plugin_identities'] == [] and
        report['max_concurrency'] == 1 and report['incremental'] is False and report['input_hashing'] == 'ContentRequired' and
        all(report[name] is False for name in ['native_statistical_factories_registered', 'current_daemon_verified',
            'scientific_authorized', 'g0_granted']), 'Exact actual two-node synthetic method report required')
    nodes = {row['id']: row for row in rows}
    require(all(node.get('reused') is False for node in nodes.values()) and nodes['input']['status'] == 'success',
        'Both nodes must execute freshly, without cache reuse')
    method = nodes['analysis']
    reference = nodes['input']
    require(reference.get('node_type') == 'file_reference' and set(reference['port_assignments']) == {'0'},
        'The actual source must remain one original engineering file reference')
    assigned = reference['port_assignments']['0']
    require(assigned['path'] == 'vfs:///input.h5ad' and assigned['format'] == 'h5ad' and
        assigned['fingerprint']['size'] == (work / 'input.h5ad').stat().st_size and
        assigned['fingerprint']['content_hash'] == 'sha256:' + fact(work / 'input.h5ad')['sha256'],
        'The source port must retain the exact synthetic input byte identity')
    require(method['node_type'] == family['definition']['kind'], 'Registered original method kind required')
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    binding = checked_input(work, method, scratch)
    memory = admission.validate_memory_report(report)
    receipts = admission.checked_task_receipts(work, nodes)
    require(len(receipts) == 2, 'Both actually executed nodes require complete task receipts')
    require(all(record['actual_task_resources'] == {} for record in receipts.values()),
        'Record the real empty native resource leases rather than inventing manifest mapping')
    image = family['manifest']['image']['reference']
    ports = []
    if negative:
        marker = 'obs column missing: TECHNICAL_MISSING_CONDITION' if method['node_type'] == 'pseudobulk_counts' else 'No control genes found'
        stderr = expected_refusal(method, image, marker, scratch)
        shutil.copyfile(stderr, work / 'expected-refusal.stderr')
        require(report['first_run']['errors'] and not method['port_assignments'] and
            not any(list(root.rglob(port['path'])) for root in [work / 'artifacts', scratch]
                for port in family['definition']['ports']['outputs']),
            'Expected scientific-input refusal must leave no normal declared output')
    else:
        execution = method['execution']
        require(method['status'] == 'success' and type(execution.get('exit_code')) is int and execution['exit_code'] == 0 and
            execution.get('image') == image and execution.get('image_digest') == image.split('@', 1)[1] and
            not report['first_run']['errors'], 'Actual original pinned method must complete successfully')
        ports = actual_ports(work, family['definition'], method, scratch)
    for stream in ['stdout', 'stderr']:
        reference = method['execution'].get(stream + '_log')
        if reference is None:
            continue
        require(isinstance(reference, dict) and isinstance(reference.get('path'), str),
            'Present execution log must be an explicit file reference')
        log = regular(Path(reference['path']))
        receipt = Path(method['execution']['workspace'])
        require(log.is_relative_to(scratch) or (receipt.parent == work / 'task-receipts' and
            log == receipt / (stream + '.log')), 'Only actual owned run or task logs may enter proof')
        fingerprint = reference.get('fingerprint')
        if fingerprint is not None:
            require(fingerprint.get('size') == log.stat().st_size and
                fingerprint.get('content_hash') in [None, 'sha256:' + fact(log)['sha256']],
                'Recorded actual execution log differs')
        shutil.copyfile(log, work / ('method.' + stream))
    creation_log = work.parent / 'actual-container-create.jsonl'
    creations = [strict_json(line) for line in creation_log.read_text().splitlines()]
    matched = [row for row in creations if row['name'] == method['execution']['run_name']]
    require(len(matched) == 1, 'One actual OCI create record must bind this exact method run')
    if family['manifest']['plugin_name'] == 'single-cell':
        require(len(matched[0]['panel_mounts']) == 1 and
            'destination=/panels/celltypist_model,readonly' in matched[0]['panel_mounts'][0],
            'The explicit unused nonmodel bundle must actually mount read-only')
        cache = Path(os.environ['TMPDIR']) / 'official-plugin-panel-cache' / work.name
        markers = list(cache.rglob('NOT_A_MODEL.txt'))
        require(len(markers) == 1 and regular(markers[0]).read_bytes() == PANEL_PAYLOAD,
            'Actual materialized unused marker bytes differ')
    else:
        require(matched[0]['panel_mounts'] == [], 'Pseudobulk must not acquire a model panel')
    write(work / 'graph-verification.json', dict(nodes=2, edges=1, owned_task_receipts=2,
        actual_binding=binding, actual_published_ports=len(ports), expected_method_refusal=negative,
        actual_native_memory_guard=memory, actual_OCI_declaration=matched[0], original_manifest_resources_certified=False,
        plugin_resources_to_native_budget_mapping_proven=False, actual_resident_daemon=False, g0_granted=False))
    return ports


def comparator_source():
    source = regular(ROOT / 'plugins/single-cell/tests/qc_compare.py')
    require(fact(source)['sha256'] == QC_SHA, 'Exact existing whole-object comparator required')
    return source


def copy_runner(original, temporary):
    executable, identity = admission.executable_copy(original, temporary)
    require(isinstance(executable, Path) and executable.is_absolute() and
        admission.file_identity(original) == identity and fact(executable)['sha256'] == identity['sha256'],
        'Actual executable-copy ABI must return an owned path and the preserved original identity')
    return executable, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--build-seal', required=True)
    arguments = parser.parse_args()
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'b-publication-dag'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    initial_parent = runtime.subset.cgroup_observation()
    require(int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))) * 1024 >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3,
        'Tiny synthetic graph plus system reserve unavailable')
    build, build_receipt = admission.checked_build(Path.home() / '.local/state/autonomics/validation-archives',
        arguments.runner, arguments.build_record, arguments.build_seal)
    runner, runner_identity = copy_runner(arguments.runner, Path(os.environ['TMPDIR']))
    direct = checked_direct(output)
    canonical_before = runtime.source_facts()
    families = snapshot_families(output)
    prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], '--cgroup-manager=cgroupfs']
    for name in ['backend-before', 'backend-after', 'images']:
        (output / name).mkdir()
    backend = runtime.subset.default_backend(prefix, output / 'backend-before')
    images = dict(pseudobulk=runtime.inspect_pseudobulk(prefix, output / 'images', 'pseudobulk-before'),
        score=runtime.subset.inspect(prefix, output / 'images', 'score-before'))
    launcher = default_launcher(prefix, Path(os.environ['TMPDIR']), output)
    results = {}
    for label in ['pseudobulk', 'score']:
        for negative in [False, True]:
            name = label + ('-refusal' if negative else '-positive')
            work = output / name
            work.mkdir()
            if label == 'pseudobulk':
                original = direct / 'pseudobulk/fixed/cases/dense/input.h5ad'
            else:
                matches = list((direct / 'score/descriptor-h5ad-readback').glob('owned-*.h5ad'))
                require(len(matches) == 1, 'One fully read-back sealed score fixture required')
                original = matches[0]
            shutil.copyfile(regular(original), work / 'input.h5ad')
            require(fact(work / 'input.h5ad')['sha256'] == fact(original)['sha256'], 'Sealed synthetic fixture byte transport changed')
            ports = graph(runner, build, work, families[label], negative=negative)
            if not negative and label == 'pseudobulk':
                for port, filename in [(ports[0], 'counts.tsv'), (ports[1], 'samples.tsv')]:
                    require(port.read_bytes() == (direct / 'pseudobulk/fixed/cases/dense' / filename).read_bytes(),
                        'Complete pseudobulk matrix or donor metadata changed')
            if not negative and label == 'score':
                require(ports[1].read_bytes() == (direct / 'score/original-existing-output/report.json').read_bytes(),
                    'Complete original scoring method report changed')
            results[name] = dict(ports=[str(path) for path in ports], expected_method_refusal=negative)
    compare = output / 'whole-score-comparison'
    compare.mkdir()
    actual = Path(results['score-positive']['ports'][0])
    reference = direct / 'score/original-existing-output/output.h5ad'
    shutil.copyfile(actual, compare / 'output.h5ad')
    shutil.copyfile(regular(reference), compare / 'fresh-author.h5ad')
    compare_source = output / 'comparison-source'
    compare_source.mkdir()
    shutil.copyfile(comparator_source(), compare_source / 'qc_compare.py')
    (compare_source / 'compare-score.py').write_text(COMPARATOR)
    runtime.run_inner(prefix, compare_source, compare, 'whole-score', runtime.subset.IMAGE, ['/source/compare-score.py'])
    compared = strict_json((compare / 'whole-object-comparison.json').read_text())
    require(compared.get('whole_AnnData_and_HDF5_checked') is True and
        type(compared.get('finite_values_checked')) is int and compared['finite_values_checked'] > 0 and compared.get('G0') is False,
        'Full AnnData and HDF5 numerical readback must actually complete')
    stops = stopped(prefix, Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']), output, 5)
    require(runtime.subset.default_backend(prefix, output / 'backend-after') == backend and
        images == dict(pseudobulk=runtime.inspect_pseudobulk(prefix, output / 'images', 'pseudobulk-after'),
            score=runtime.subset.inspect(prefix, output / 'images', 'score-after')) and
        runtime.source_facts() == canonical_before and fact(launcher[0]) == launcher[1] and fact(launcher[2]) == launcher[3],
        'Runtime, exact canonical repair sources or managed launcher changed')
    require(admission.file_identity(arguments.runner) == runner_identity and
        fact(runner)['sha256'] == runner_identity['sha256'], 'Sealed runner or owned executable copy changed')
    write(output / 'verification.json', dict(
        status='BOUNDED_FOUR_SYNTHETIC_ORIGINAL_KIND_DAGS_NOT_DEPLOYED', build=build_receipt,
        direct_session=DIRECT_SESSION, direct_seal=DIRECT_SEAL, graphs=results,
        actual_graphs=4, actual_nodes=8, actual_edges=4, actual_task_receipts=8,
        actual_method_containers=4, actual_comparison_containers=1, stopped_owned_containers=len(stops),
        score_whole_object_comparison=compared, original_manifest_resources_certified=False,
        unused_panel_marker_is_not_a_model=True, CellTypist_model_qualification_granted=False,
        initial_parent=initial_parent, final_parent=runtime.subset.cgroup_observation(),
        research_raw_data_read=False, current_daemon_verified=False, production_restarted=False,
        scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
