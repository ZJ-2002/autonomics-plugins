import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = ROOT.parent / 'autonomics-plugins'
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
PARENT = 'f6ee70f351a64917aff9d0d9fa72a221'
SEAL = 'e3310633e944ee0c206323a57184c51bd40220e4964283733216934e1ca67bd1'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(filename, value):
    filename.write_text(json.dumps(value, indent=2) + '\n')


def sha(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def main():
    sys.path.insert(0, str(PLUGINS))
    from tools.reconcile_ab_evidence_index import verify_archive
    from tools.prove_frozen_a_family_runtime import stopped
    parent = verify_archive(ARCHIVES, PARENT, SEAL)
    require(parent['worker_exit_status'] == 1, 'Retain actual unsuccessful parent, not a relabelled pass')
    previous = ARCHIVES / PARENT / 'artifacts/permanent/cmap-current-sdk'
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'cmap-current-sdk-materialization-review'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    definition = ROOT / 'results/cachexia-v4.3.2/prove_cmap_current_sdk_20261021.py'
    specification = importlib.util.spec_from_file_location('original_bridge', definition)
    bridge = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(bridge)
    old_driver = (previous / 'driver.py').read_bytes()
    corrected = old_driver.replace(b"source_names=['query.tsv','reference.bin','metadata.tsv']",
        b"source_names=['query.tsv','reference.bin','metadata.tsv','request.json']")
    require(corrected != old_driver and corrected == definition.read_bytes(), 'Only the verified missing ZIP member expectation may change')
    (output / 'corrected-bridge-driver.py').write_bytes(corrected)
    for negative in [False, True]:
        case = previous / ('negative-hash' if negative else 'positive')
        report = json.loads((case / 'dag-report.json').read_text())
        nodes = {node['id']: node for node in report['first_run']['nodes']}
        require(report['engine_source_revision'] == '4256643c55ae6fb50e8c867069330ed6ac2b4bc0'
                and report['max_concurrency'] == 1 and len(nodes) == 7
                and not report['current_daemon_verified'] and not report['g0_granted'], 'Retained SDK identity or scope differs')
        require(all(nodes['source-' + str(index)]['status'] == 'success' for index in range(4)), 'Actual source execution missing')
        if negative:
            audit = json.loads((case / 'audit.json').read_text())
            require(nodes['analysis']['status'] == 'failed' and not nodes['analysis'].get('port_assignments')
                and audit['error'] == 'Frozen source content differs'
                and all(nodes[name]['status'] == 'skipped' for name in ['reader', 'sink'])
                and not (case / 'materialized.parquet').exists(), 'Specific failure or skip propagation missing')
        else:
            require(report['first_run']['ok'] and all(node['status'] == 'success' for node in nodes.values())
                    and len(nodes['analysis']['port_assignments']) == 9, 'Complete positive graph not executed')
    prior_stops = json.loads((previous / 'owned-container-stops.json').read_text())
    require(len(prior_stops) == 3 and all(row['actual_exit'] == 0 and row['remaining'] == 0 for row in prior_stops), 'Parent container stoppage not proved')
    frozen = ARCHIVES / bridge.FROZEN / 'artifacts/permanent/network-cmap-saved-contract-reconciliation/selected/node-proof-cmap-ledger-20261008/cmap-DAG-v5'
    require(verify_archive(ARCHIVES, bridge.FROZEN, bridge.FROZEN_SEAL)['positive_worker_exit_verified'], 'Original synthetic reference identity differs')
    program = bridge.CHECK.replace("(root/'materialization-review.json')", "(Path('/review')/'materialization-review.json')")
    require(program != bridge.CHECK, 'Separate read-only-review output path required')
    (output / 'review.py').write_text(program)
    profile = json.loads((Path.home() / '.autonomics/qualified-image-store.json').read_text())
    image = 'ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5'
    require(image in profile['images'], 'Exact qualified image unavailable')
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile.update(images=[image], delegate=dict(path=str(delegate), sha256=sha(delegate)))
    profile_file = output / 'managed-image-profile.json'
    save(profile_file, profile)
    profile_file.chmod(0o600)
    adapter = Path.home() / '.local/lib/autonomics/qualified-podman' / bridge.ADAPTER_SHA / 'podman'
    require(sha(adapter) == bridge.ADAPTER_SHA, 'Qualified adapter identity differs')
    primary = profile['primary']
    backend = ['--root',primary['graphroot'],'--runroot',primary['runroot'],'--tmpdir',primary['runroot']+'/libpod-tmp',
               '--storage-driver',primary['driver'],'--cgroup-manager=cgroupfs']
    environment = dict(os.environ, AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(profile_file))
    try:
        result = subprocess.run([str(adapter),*backend,'run','--rm','--pull=never','--network=none','--read-only',
            '--cpus=1','--memory=512m','--pids-limit=64','--tmpfs=/tmp:rw,nosuid,nodev,size=32m','--userns=keep-id',
            '--user='+str(os.getuid())+':'+str(os.getgid()),'-e','PYTHONDONTWRITEBYTECODE=1',
            '-v',str(previous)+':/proof:ro','-v',str(frozen)+':/frozen:ro','-v',str(output)+':/review:rw',
            '--entrypoint=python3',image,'-I','-B','/review/review.py'],
            capture_output=True, env=environment, timeout=90)
        (output / 'review.stdout').write_bytes(result.stdout)
        (output / 'review.stderr').write_bytes(result.stderr)
        save(output / 'execution.json', dict(actual_exit=result.returncode))
        require(result.returncode == 0, 'Corrected read-only complete materialization review failed')
    finally:
        stopped([str(delegate),'--storage-opt','additionalimagestore='+profile['additional']['path'],*backend],
            Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']),output,1)
    report = dict(schema='CMAP_RETAINED_SDK_BRIDGE_REVIEW_V1', passed=True,
        function_id='FUNC_cmap_connectivity', parent_session=PARENT,parent_seal=SEAL,parent_worker_exit_status=1,
        parent_not_relabelled_as_pass=True, positive_DAGs=1, negative_DAGs=1, nodes_per_DAG=7,edges_per_DAG=6,
        declared_ports_preserved=9, downstream_skipped=2, prior_owned_containers_stopped=3,
        readonly_review_owned_container_stopped=1, review=json.loads((output/'materialization-review.json').read_text()),
        selected_metric='pearson', retained_SDK_source='4256643c55ae6fb50e8c867069330ed6ac2b4bc0',
        graph_execution_repeated=False, old_25_case_suite_repeated=False, new_method_executions=0,
        current_resident_DAG_claimed=False, Broad_algorithm_certified=False,
        scientific_release_granted=False, new_software_admissions=0,g0_granted=False)
    save(output/'verification.json',report)
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
