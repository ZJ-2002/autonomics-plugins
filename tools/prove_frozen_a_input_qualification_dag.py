"""Prove the locked raw-input DAG without archiving source links or raw payloads."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_frozen_a_input_qualification as direct
from tools.prove_frozen_a_harmonisation_dag import (
    checked_build, checked_task_receipts, executable_copy, file_identity, install_backend_launcher,
    validate_memory_report, verify_backend_launcher,
)
from tools.prove_locked_b_source_transport import actual_ports
from tools.reconcile_ab_evidence_index import verify_archive

require, write, digest = direct.require, direct.write, direct.digest
SCOPE = 'LOCKED_LEGACY_A_RAW_QC_LD_NO_MR_NOT_G0'
METHOD = 'frozen_a_v432_input_qualification'
DIRECT_SESSION = 'fe8d9c30ecfc46de9b1d38f81e3723be'
DIRECT_SEAL = '603b93a279e42c97e029454e418219d0e5f8cb149904fbbfd5057803d85e7193'
PANEL_HOST = Path.home() / '.autonomics/panels/wjixiang/catalog-plink-ref-1000g-eur-binary@sha256:9f483fd11fbb2e73a97ab1af172e45e569c7b8ed7edec5572e35a2b3fa614b21'
PANEL_ID = 'wjixiang/catalog-plink-ref-1000g-eur-binary'
PANEL_DIGEST = 'sha256:9f483fd11fbb2e73a97ab1af172e45e569c7b8ed7edec5572e35a2b3fa614b21'
PANEL_MANIFEST = 'fe6a3d9717ea70714dcf1c8c9d15b2790501f030a93283042adebab3e8f1ed2b'


def job_for(work, source):
    return dict(scope=SCOPE, run_root=str(work), plugin_manifest=str(source / 'manifest.toml'),
        expected_plugin_name='frozen-a-input-qualification', plugin_manifest_sha256=direct.SOURCE_PINS['manifest.toml'],
        script_sha256={'scripts/qualify.py': direct.SOURCE_PINS['scripts/qualify.py']}, panel_overrides=[],
        panel_manifest_sha256={'/locked-panels/1000g-eur': PANEL_MANIFEST}, locked_panel_source=str(PANEL_HOST),
        bundles=[dict(ident=PANEL_ID, desc='Frozen official 1000G EUR panel; read-only; not synthetic',
            vpath='/locked-panels/1000g-eur', source='/locked-panels/1000g-eur', digest=PANEL_DIGEST)], additional_plugins=[],
        nodes=[*[dict(id='input' + str(index), kind='file_reference', spec=dict(
            path='vfs:///locked-inputs/' + str(index) + '/' + original.name,
            format='file', hash_content=True)) for index, original in enumerate(direct.INPUT_PATHS)],
            dict(id='qualification', kind=METHOD, spec={})],
        edges=[{'from': 'input' + str(index), 'to': 'qualification', 'from_port': 0, 'to_port': index} for index in range(9)])


def validate_job(value):
    expected = job_for(Path(value['run_root']), Path(value['plugin_manifest']).parent)
    require(value == expected, 'Exact ten-node nine-edge raw qualification scope and original panel required')


def staged_basename(index, source):
    extension = Path(source.name[:-3]).suffix + '.gz' if source.name.endswith('.gz') else source.suffix
    return 'input-' + str(index) + extension


def bound_source_facts(scratch, nodes, method, job, expected_targets, before):
    edges = job['edges']
    bindings = method.get('inputs')
    require(isinstance(bindings, list) and len(bindings) == 9 and
        {item['to_port'] for item in bindings} == set(range(9)), 'Actual complete nine-port dispatch inventory required')
    observations = []
    for index, expected_target in enumerate(expected_targets):
        edge = edges[index]
        binding = next(item for item in bindings if item['to_port'] == index)
        require(binding['from'] == edge['from'] and binding['from_port'] == 0, 'Actual source edge differs')
        assignments = nodes[edge['from']]['port_assignments']
        require(set(assignments) == {'0'}, 'Each source reference must have exactly one output')
        reference = assignments['0']
        require(reference['path'] == job['nodes'][index]['spec']['path'] and reference['format'] == 'file' and
            reference['fingerprint']['size'] == before[index]['bytes'] and
            reference['fingerprint']['content_hash'] == 'sha256:' + before[index]['sha256'] and
            binding.get('kind') == 'File' and binding.get('path') == reference['path'] and
            binding['fingerprint']['size'] == before[index]['bytes'] and
            binding['fingerprint'].get('content_hash') == reference['fingerprint']['content_hash'],
            'Actual source reference content identity differs')
        candidates = [path for path in scratch.rglob(staged_basename(index, expected_target))
                      if path.parent.name == 'inputs' and path.parent.parent.name == '.autonomics']
        require(len(candidates) == 1, 'One actual staged input role required')
        staged = candidates[0]
        require(staged.is_symlink() and staged.parent.resolve().is_relative_to(scratch.resolve()) and
            os.readlink(staged) == str(expected_target) and staged.resolve(strict=True) == expected_target and
            direct.ordinary(expected_target).stat().st_size == before[index]['bytes'] and
            digest(expected_target) == before[index]['sha256'], 'Actual symlink staging must resolve to its admitted source; no raw-copy fallback')
        observations.append(dict(from_node=edge['from'], from_port=0, to_port=index, source_sha256=before[index]['sha256'],
            staged_sha256=before[index]['sha256'], staged_link_literal=os.readlink(staged), staged_link_resolved=str(expected_target),
            staged_path=str(staged), source_is_canonical_no_copy=True,
            source_vfs_reference=job['nodes'][index]['spec']['path']))
    return observations


def validate_report(report, job, build):
    validate_job(job)
    records = report.get('first_run', {}).get('nodes', [])
    require(isinstance(records, list) and len(records) == 10 and len({node['id'] for node in records}) == 10 and
        {node['id'] for node in records} == {node['id'] for node in job['nodes']}, 'Actual ten unique nodes required')
    nodes = {node['id']: node for node in records}
    require(all(nodes[record['id']].get('node_type') == record['kind'] and nodes[record['id']]['status'] == 'success' and
        nodes[record['id']].get('reused') is False for record in job['nodes']) and not report['first_run']['errors'],
        'Every actual node must execute successfully without reuse')
    require(report.get('scope') == 'REAL_LOCKED_LEGACY_A_RAW_QC_LD_NO_MR' and
        report.get('engine_source_revision') == build['engine_commit'] and report.get('input_hashing') == 'ContentRequired' and
        type(report.get('max_concurrency')) is int and report['max_concurrency'] == 1 and report.get('incremental') is False and
        report.get('plugin_name') == 'frozen-a-input-qualification' and
        report.get('original_manifest_sha256') == direct.SOURCE_PINS['manifest.toml'] and
        report.get('additional_plugin_identities') == [] and report.get('native_statistical_factories_registered') is False and
        report.get('explicit_replay_scope_allows_fit') is False and report.get('current_daemon_verified') is False and
        report.get('scientific_authorized') is False and report.get('g0_granted') is False and
        report.get('panel_bindings_are_explicit_synthetic_overrides') is False and
        'effective_synthetic_manifest_sha256' in report and report['effective_synthetic_manifest_sha256'] is None and
        isinstance(report.get('effective_manifest_sha256'), str) and
        re.fullmatch('[0-9a-f]{64}', report['effective_manifest_sha256']) and
        report.get('panel_transport') == 'TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT',
        'Exact original-panel no-fit source and actual engine identity required')
    panel_before, panel_after = report.get('locked_actual_panel_source_before'), report.get('locked_actual_panel_source_after')
    require(isinstance(panel_before, dict) and panel_before == panel_after and panel_before.get('host_source') == str(PANEL_HOST) and
        panel_before.get('manifest_sha256') == PANEL_MANIFEST and panel_before.get('digest') == PANEL_DIGEST and
        panel_before.get('catalog_bundle') == PANEL_ID and len(panel_before.get('payload_files', [])) == 66 and
        {item['path'] for item in panel_before['payload_files']} ==
        {f'1000G.EUR.QC.{chromosome}.{suffix}' for chromosome in range(1, 23) for suffix in ['bed', 'bim', 'fam']},
        'Exact original panel content and metadata must remain unchanged')
    execution = nodes['qualification'].get('execution')
    require(isinstance(execution, dict) and type(execution.get('exit_code')) is int and execution['exit_code'] == 0 and
        execution.get('image') == direct.IMAGE and execution.get('image_digest') == direct.IMAGE.split('@', 1)[1],
        'Actual official runtime must execute successfully; startup/OOM cannot pass')
    return nodes


def stopped_owned_containers(prefix, output, permanent):
    session = permanent.parent.name
    require(re.fullmatch('[0-9a-f]{32}', session), 'Literal current managed session required')
    path = permanent / 'container-intents.json'
    if not path.exists():
        return []
    checksum = digest(path)
    value = json.loads(path.read_text())
    require(value['session'] == session and len(value['intents']) <= 1 and
        len({row['token'] for row in value['intents']}) == len(value['intents']), 'Only this single-method session intent is admissible')
    owner = json.loads(direct.OWNER.read_text())
    observations = []
    for row in value['intents']:
        require(re.fullmatch('[0-9a-f]{32}', row['token']) and row['backend'] in
            [owner['runtime_backend'], [*owner['runtime_backend'], '--cgroup-manager=cgroupfs']],
            'Exact recorded existing backend and managed intent token required')
        command = [prefix[0], *row['backend'], 'ps', '-a', '--filter', 'label=autonomics.validation.session=' + session,
            '--filter', 'label=autonomics.validation.intent=' + row['token'], '--format=json']
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0 and json.loads(result.stdout) == [], 'Owned container is not proven absent; source links retained')
        observations.append(dict(token=row['token'], backend=row['backend'], command=command,
            actual_exit=result.returncode, containers_remaining=0))
    require(digest(path) == checksum, 'Owned intent inventory changed during stoppage observation')
    write(output / 'owned-container-stop-observations.json', dict(session=session, intents=observations,
        whole_managed_worker_stoppage_not_yet_certified=True, global_container_idle_claimed=False))
    return observations


def rejected_job_observation(result, work, before_intents, after_intents):
    require(type(result.returncode) is int and result.returncode == 1 and
        'raw A input ports must directly bind their exact read-only canonical source mount' in result.stderr and
        before_intents == after_intents and not (work / 'dag-report.json').exists() and not (work / 'artifacts').exists(),
        'Exact structural admission refusal without method/container execution required')


def structural_refusals(runner, output, source, permanent):
    observations = []
    intent_file = permanent / 'container-intents.json'
    for name in ['wrong-path', 'swapped-roles']:
        work = output / name
        work.mkdir()
        job = job_for(work, source)
        if name == 'wrong-path':
            job['nodes'][0]['spec']['path'] = 'vfs:///input0.input'
        else:
            first = job['nodes'][0]['spec']['path']
            job['nodes'][0]['spec']['path'] = job['nodes'][1]['spec']['path']
            job['nodes'][1]['spec']['path'] = first
        write(work / 'job.json', job)
        before = digest(intent_file) if intent_file.exists() else None
        result = subprocess.run([str(runner), '--validate-job', str(work / 'job.json')],
            capture_output=True, text=True, timeout=60)
        after = digest(intent_file) if intent_file.exists() else None
        (work / 'admission.stdout.log').write_text(result.stdout)
        (work / 'admission.stderr.log').write_text(result.stderr)
        write(work / 'admission-exit.json', dict(actual_exit=result.returncode))
        rejected_job_observation(result, work, before, after)
        observations.append(dict(case=name, actual_exit=result.returncode, admission_only=True,
            container_intent_inventory_unchanged=True, normal_outputs=0, method_execution=False))
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=Path)
    parser.add_argument('--build-record', required=True, type=Path)
    parser.add_argument('--build-seal', required=True)
    args = parser.parse_args()
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'frozen-a-input-qualification-dag'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    direct.resource_admission(output)
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    build, build_receipt = checked_build(archives, args.runner, args.build_record, args.build_seal)
    require(build_receipt['guard_count'] == 23, 'Exact twenty-three-guard canonical readonly mount build required')
    write(output / 'verified-build.json', build_receipt)
    runner, runner_identity = executable_copy(args.runner, Path(os.environ['TMPDIR']))
    checked = verify_archive(archives, DIRECT_SESSION, DIRECT_SEAL)
    require(checked['positive_worker_exit_verified'], 'Actual direct proof must have recorded zero exit')
    actual_direct = Path(checked['artifact_root']) / 'permanent/frozen-a-input-qualification'
    evidence = json.loads((actual_direct / 'verification.json').read_text())
    require(evidence['status'] == 'SCOPED_DIRECT_FROZEN_RAW_QC_OFFICIAL_PLINK_PROVEN_DAG_PENDING' and
        evidence['source_sha256'] == direct.SOURCE_PINS and evidence['g0_granted'] is False, 'Exact scoped direct predecessor required')
    runtime, prerequisites = direct.prerequisite_archives(archives)
    source = output / 'source'
    source.mkdir()
    for name, expected in direct.SOURCE_PINS.items():
        require(digest(direct.ordinary(direct.FAMILY / name)) == expected, 'Current candidate source changed')
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(direct.FAMILY / name, target)
        require(digest(target) == expected, 'Source snapshot differs')
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    definition = manifest['nodes'][0]
    require(manifest['image']['reference'] == direct.IMAGE and len(manifest['nodes']) == 1 and definition['kind'] == METHOD and
        manifest['plugin_name'] == 'frozen-a-input-qualification' and definition['stage_in_mode'] == 'symlink' and
        definition['resources']['read_only_rootfs'] is True and definition['resources']['memory'] == '2Gi' and
        len(definition['ports']['inputs']) == 9 and len(definition['ports']['outputs']) == 12 and not definition.get('params'),
        'Exact nine-input/twelve-output readonly official raw qualification manifest required')
    contract = json.loads((source / 'contracts/source-lock.json').read_text())
    prefix = direct.backend(output, runtime)
    launcher = install_backend_launcher(prefix, Path(os.environ['TMPDIR']), output)
    before = direct.source_facts(direct.INPUT_PATHS, contract)
    panel_manifest = json.loads(direct.INPUT_PATHS[7].read_text())
    panel_before = direct.panel_facts(PANEL_HOST, panel_manifest)
    refusals = structural_refusals(runner, output, source, permanent)
    work = output / 'positive'
    work.mkdir()
    job = job_for(work, source)
    validate_job(job)
    write(work / 'job.json', job)
    admission = subprocess.run([str(runner), '--validate-job', str(work / 'job.json')],
        capture_output=True, text=True, timeout=600)
    (work / 'admission.stdout.json').write_text(admission.stdout)
    (work / 'admission.stderr.log').write_text(admission.stderr)
    require(admission.returncode == 0, 'Actual no-container guarded job validation failed')
    admitted = json.loads(admission.stdout)
    require(admitted['scope'] == SCOPE and admitted['job_validated_without_execution'] is True and
        admitted['containers_started'] is False and admitted['scientific_results_computed'] is False and
        admitted['g0_granted'] is False, 'Actual no-execution validation receipt differs')
    result = subprocess.run([str(runner), str(work / 'job.json')], capture_output=True, text=True, timeout=2400,
        env=dict(os.environ, AUTONOMICS_DAG_TASKS_ROOT=str(work / 'task-receipts')))
    (work / 'runner.stdout.log').write_text(result.stdout)
    (work / 'runner.stderr.log').write_text(result.stderr)
    write(work / 'runner-exit.json', dict(actual_exit=result.returncode))
    require(result.returncode == 0, 'Actual raw qualification runner failed before valid reporting')
    report = json.loads((work / 'dag-report.json').read_text())
    nodes = validate_report(report, job, build)
    memory = validate_memory_report(report)
    receipts = checked_task_receipts(work, nodes)
    scratch = Path(os.environ['TMPDIR']) / 'official-plugin-container-workspaces' / work.name
    bindings = bound_source_facts(scratch, nodes, nodes['qualification'], job, direct.INPUT_PATHS, before)
    ports = actual_ports(work, definition, nodes['qualification'], scratch)
    require(len(ports) == 12, 'Every actual run-name-qualified output port required')
    published = ports[0].parent
    positive = direct.validate_positive(published, definition, contract, before, panel_before)
    for name in contract['existing_expected_outputs']:
        expected = actual_direct / 'positive' / name
        require(expected.relative_to(Path(checked['artifact_root'])).as_posix() in checked['member_identities'] and
            (published / name).read_bytes() == expected.read_bytes(), 'Complete DAG product differs from sealed direct execution')
    require(file_identity(args.runner) == runner_identity and digest(runner) == runner_identity['sha256'] and
        before == direct.source_facts(direct.INPUT_PATHS, contract) and
        panel_before == direct.panel_facts(PANEL_HOST, panel_manifest) and digest(direct.OWNER) == direct.OWNER_SHA and
        all(digest(direct.FAMILY / name) == expected == digest(source / name) for name, expected in direct.SOURCE_PINS.items()),
        'Canonical input/panel/candidate/owner changed during actual DAG')
    require({row['path']: {key: row[key] for key in ['bytes', 'sha256', 'device', 'inode']}
        for row in report['locked_actual_panel_source_before']['payload_files']} == panel_before,
        'Actual reported original panel must match every independently hashed source payload')
    stopped = stopped_owned_containers(prefix, output, permanent)
    require(len(stopped) == 1, 'Exactly one actual stopped qualification container required')
    verify_backend_launcher(launcher)
    post = direct.original_postcheck(output)
    write(work / 'transport-verification.json', dict(nodes=10, edges=9, bindings=bindings,
        positive_outputs=positive, canonical_sources_unchanged=True, original_panel_metadata_unchanged=True,
        actual_owned_task_receipts=len(receipts), actual_native_memory_guard=memory,
        plugin_resource_to_native_budget_mapping_verified=False,
        source_staging_symlinks_not_copied_to_archive=True, source_mount_contract_readonly=True,
        kernel_mount_snapshot_collected=False, no_raw_or_panel_payload_archived=True, g0_granted=False))
    require(not any(path.is_symlink() for path in output.rglob('*')), 'Only regular evidence may enter the archive')
    write(output / 'verification.json', dict(status='SCOPED_TEN_NODE_NINE_EDGE_OFFICIAL_RAW_QUALIFICATION_DAG_PROVEN_NOT_DEPLOYED',
        source_sha256=direct.SOURCE_PINS, build=build_receipt, prerequisites=prerequisites,
        direct_reference_session=DIRECT_SESSION, direct_reference_manifest_sha256=DIRECT_SEAL,
        actual_nodes=10, actual_edges=9, actual_ports=12, full_byte_equal_small_products=7,
        actual_owned_task_receipts=len(receipts), sealed_runner_unchanged=True,
        plugin_resource_to_native_budget_mapping_verified=False,
        structural_admission_refusals=refusals, actual_negative_DAG_method_executions=0,
        actual_clump_commands=13, actual_paircheck_commands=13, complete_haplotype_pairs=11,
        owned_source_links_created=0, raw_inputs_copied=False, canonical_panel_copied=False,
        panel_transport='TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT',
        temporary_executor_workspaces_archived=False, original_post_verifier=post,
        managed_terminal_and_full_stoppage_not_yet_certified=True, harmonisation_executed=False, MR_estimates_computed=False,
        current_daemon_verified=False, production_restarted=False, scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
