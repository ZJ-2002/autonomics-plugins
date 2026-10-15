"""Exercise the legacy-MR lineage barrier without estimating any new effects."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tomllib
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_h5ad_subset_official_runtime as runtime
from tools import prove_r_publication_runtime as installed
from tools import prove_frozen_a_harmonisation as qualification
from tools import prove_frozen_a_input_qualification as raw
from tools.prove_frozen_a_family_runtime import stopped
from tools.reconcile_ab_evidence_index import verify_archive

FAMILY = 'research-adapters/frozen-a-legacy-family-gate'
HELPER = 'research-adapters/frozen-a-family-assembly/scripts/family.py'
HELPER_SHA = '338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a'
HELPER_BYTES = 26620
MR_SCRIPT_SHA = '33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe'
MR_DRIVER_SHA = '6685b2d86362fb7e4da6d7b0cdeeb66d8b2e05c2e51308d48d438bc586616cf9'
MR_CHECKER_SHA = '9b656c39926c6fdaeecafba8df8dc2c5216cba81c891255e00f36ad328a688d8'
IMAGE = 'docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d'
MR_PORTS = ['ALL_METHODS_EXPLORATORY.tsv', 'HETEROGENEITY.tsv', 'EGGER_INTERCEPT.tsv',
    'ALL_LEAVE_ONE_OUT.tsv', 'ALL_REGION_SENSITIVITIES.tsv', 'QUALIFIED_INPUT.tsv',
    'twosamplemr_v432_a.RDS', 'twosamplemr_v432_a.log', 'INPUT_METHOD_PROVENANCE.json']
OUTPUTS = ['family-request.json', 'eligibility-projection.tsv', 'gate-receipt.json', 'gate.log']
PINS = {
    FAMILY + '/manifest.toml': 'f07cd4c67cd01037dc9285670fcf3ec021990a4e2e0ebe356a601358e24bf1c1',
    FAMILY + '/scripts/gate.py': '6c921c4ed2cfece1bc56031a0a40b83c1c1efbdd643d6e32f370ee851da42537',
    HELPER: HELPER_SHA,
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_r_publication_runtime.py': 'db91460fb9875bad822e15dfa4abbc7283b1e5121455c5447eab47c76c7578c9',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
    'tools/prove_frozen_a_harmonisation.py': '79b36d2f5a64409f0b8b87735b7773f29dd3dedeaa3809ddb14a4c7a97685018',
    'tools/prove_frozen_a_input_qualification.py': 'c694f8b92a10663ece28927103914ef163767adb2aaa178db9ee201ff46be719',
    'tools/reconcile_ab_evidence_index.py': '44878add55a5a656f15e2c936e269ba1ef9b2c4a16c81e7a5c22733da6975c72',
}
REQUEST = dict(schema='FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1',
    scope='FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH', scenario='REAL_FROZEN_NA_LEDGER', edges=[])
require, fact, write, strict_json = runtime.require, runtime.fact, runtime.write, runtime.strict_json


def family_helper():
    path = ROOT / HELPER
    before = fact(path)
    require(before['sha256'] == HELPER_SHA and before['bytes'] == HELPER_BYTES,
        'Exact previously verified family helper required')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    expected = tuple(before[key] for key in ('device', 'inode', 'bytes', 'mtime_ns', 'ctime_ns'))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode) and signature(os.fstat(handle.fileno())) == expected,
            'Frozen helper changed before its bounded source read')
        payload = handle.read(HELPER_BYTES + 1)
        require(signature(os.fstat(handle.fileno())) == expected, 'Frozen helper changed during its source read')
    require(fact(path) == before and len(payload) == HELPER_BYTES and hashlib.sha256(payload).hexdigest() == HELPER_SHA,
        'Frozen helper changed before approved-byte execution')
    module = types.ModuleType('gate_runtime_frozen_family')
    module.__file__ = str(path)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    return module


def observed_sources():
    observed = {name: fact(ROOT / name) for name in PINS}
    require(all(observed[name]['sha256'] == expected for name, expected in PINS.items()),
        'Exact reviewed gate, manifest, family helper and acceptance sources required')
    return observed


def checked_mr_archive(archives, session, seal):
    checked = verify_archive(archives, session, seal)
    require(checked['positive_worker_exit_verified'], 'Completed real legacy replay with actual exit zero required')
    directory = Path(checked['artifact_root']) / 'permanent/frozen-a-legacy-mr-runtime'
    require(fact(directory / 'driver.py')['sha256'] == MR_DRIVER_SHA and
        fact(directory / 'source/tools/check_frozen_a_legacy_mr_runtime.R')['sha256'] == MR_CHECKER_SHA,
        'Exact reviewed independent MR driver and reference checker required')
    value = strict_json((directory / 'verification.json').read_bytes())
    require(value.get('status') == 'SCOPED_REAL_ALREADY_SEEN_39_IV_DIRECT_OFFICIAL_REPLAY_NOT_DAG_OR_G0' and
        value.get('scope') == 'FROZEN_V432_A_LEGACY' and value.get('actual_DAG_executed') is False and
        value.get('production_changed') is False and value.get('scientific_authorization_granted') is False and
        value.get('g0_granted') is False, 'MR replay must not claim scientific, DAG or production authority')
    reference = value.get('reference', {})
    require(reference.get('six_complete_TSVs_byte_equal') is True and
        reference.get('six_complete_TSVs_readback_equal') is True and
        reference.get('complete_RDS_object_identical') is True and
        type(reference.get('RDS_numeric_tolerance')) is int and reference['RDS_numeric_tolerance'] == 0 and
        reference.get('all_nine_current_ports_checked') is True and
        reference.get('full_provenance_contract_checked') is True and
        reference.get('original_verifier_not_faked') is True and
        reference.get('whole_original_cli_executed') is False and
        reference.get('overlap_class') == 'O2' and reference.get('primary_p_source') == 'NA',
        'Full independent official-object comparison and explicit original-script envelope required')
    source_records = value.get('original_sources', {})
    require(source_records.get('plugins/twosamplemr-v432-a/scripts/mr.R', {}).get('sha256') == MR_SCRIPT_SHA,
        'The current reviewed MR adapter, not a previous canary, must have produced the ports')
    ports = value.get('current_ports')
    require(isinstance(ports, list) and len(ports) == 9 and
        all(isinstance(record, dict) and type(record.get('port')) is int and
            type(record.get('bytes')) is int and record['bytes'] > 0 for record in ports) and
        [record.get('port') for record in ports] == list(range(9)) and
        [record.get('name') for record in ports] == MR_PORTS, 'All nine ordered MR ports required')
    paths = []
    for record, name in zip(ports, MR_PORTS, strict=True):
        path = directory / 'current' / name
        observed = fact(path)
        require(all(observed[key] == record.get(key) for key in ('bytes', 'sha256')),
            'Actual MR product differs from its sealed producer record')
        paths.append(path)
    return paths, dict(session=session, seal=seal, all_members_rehashed=True,
        independent_official_object_comparison=True, full_original_cli_execution_claimed=False)


def frozen_inputs(helper):
    audit = qualification.STUDY / qualification.AUDIT
    paths = [audit / name for name in ('A_ANALYSIS_CONFIG.json', 'G0_V432_CERTIFICATE.json', 'R_DEPENDENCY_LOCK.tsv')]
    paths.append(ROOT / 'plugins/twosamplemr-v432-a/contracts/frozen-method-proof.json')
    paths.extend(qualification.STUDY / name for name, size, sha in helper.SOURCES)
    paths.append(ROOT / HELPER)
    require(len(paths) == 14, 'Exactly fourteen frozen contract/helper roles required')
    return paths


def definition():
    manifest = tomllib.loads((ROOT / FAMILY / 'manifest.toml').read_text())
    require(manifest['plugin_name'] == 'frozen-a-legacy-family-gate' and
        manifest['image']['reference'] == IMAGE and len(manifest['nodes']) == 1 and not manifest.get('panels'),
        'One exact panel-free engineering barrier required')
    node = manifest['nodes'][0]
    require(node['kind'] == 'frozen_a_legacy_family_gate' and not node.get('params') and
        node['stage_in_mode'] == 'copy' and len(node['ports']['inputs']) == 23 and
        all(port == {'type': 'file'} for port in node['ports']['inputs']) and
        [port['path'] for port in node['ports']['outputs']] == OUTPUTS and
        type(node['resources']['cpus']) in (int, float) and node['resources']['cpus'] == 1.0 and
        node['resources']['memory'] == '1Gi' and
        node['resources']['network'] == 'isolated' and node['resources']['read_only_rootfs'] is True and
        node['resources']['pull_policy'] == 'never' and node['command']['interpreter'] == 'python3' and
        node['command']['script_file'] == 'scripts/gate.py', 'Exact real gate ABI and bounded resources required')
    return node


def execute(prefix, node, inputs, output, expected_exit, diagnostic=None, foreign=None):
    require(len(inputs) == 23 and type(expected_exit) is int and expected_exit in (0, 2), 'Exact gate inputs and exit contract required')
    output.mkdir(mode=0o700)
    foreign_path = output / OUTPUTS[0]
    if foreign is not None:
        foreign_path.write_bytes(foreign)
    before_foreign = fact(foreign_path) if foreign is not None else None
    script = ROOT / FAMILY / node['command']['script_file']
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only',
        '--cpus=1', '--memory=1073741824', '--pids-limit=64', '--userns=keep-id',
        '--user=' + str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs=/tmp:rw,size=64m',
        '-e', 'TMPDIR=/tmp', '-e', 'PYTHONDONTWRITEBYTECODE=1',
        '-v', str(script) + ':/method/gate.py:ro', '-v', str(output) + ':/outputs:rw']
    before = [fact(path) for path in inputs]
    for index, path in enumerate(inputs):
        destination = '/inputs/input' + str(index)
        command.extend(['-v', str(path) + ':' + destination + ':ro', '-e',
            'AUTONOMICS_INPUT' + str(index) + '=' + destination])
    for index, name in enumerate(OUTPUTS):
        command.extend(['-e', 'AUTONOMICS_OUTPUT' + str(index) + '=/outputs/' + name])
    command.extend(['--entrypoint=python3', IMAGE, '-I', '-B', '/method/gate.py'])
    process = subprocess.run(command, capture_output=True, timeout=300)
    (output / 'container.stdout').write_bytes(process.stdout)
    (output / 'container.stderr').write_bytes(process.stderr)
    write(output / 'execution.json', dict(command=command, actual_exit=process.returncode,
        expected_exit=expected_exit, expected_diagnostic=diagnostic, input_identities=before))
    require(process.returncode == expected_exit and [fact(path) for path in inputs] == before,
        'Actual gate exit or immutable input identities differ')
    if expected_exit:
        require(isinstance(diagnostic, str) and diagnostic and
            diagnostic.encode() in process.stderr + (output / OUTPUTS[-1]).read_bytes(),
            'Specific injected failure must explain the actual refusal')
        require(all(not (output / name).exists() for name in OUTPUTS[:-1] if foreign is None or name != OUTPUTS[0]),
            'Gate refusal must not emit normal products')
        require(foreign is None or fact(foreign_path) == before_foreign, 'Foreign output changed during refusal')
    else:
        require(all(fact(output / name)['bytes'] > 0 for name in OUTPUTS), 'Every positive declared output must materialize')


def validate_positive(output, helper, inputs):
    request = strict_json((output / OUTPUTS[0]).read_bytes())
    require(request == REQUEST and type(request['edges']) is list, 'MR exploratory P values cannot enter the primary family request')
    expected = helper.assemble([*inputs[13:22], output / OUTPUTS[0]])
    ledger_reader = csv.DictReader(io.StringIO(inputs[15].read_text()), delimiter='\t')
    projection = [row for row in ledger_reader if row['family_id'] in helper.COUNTS]
    require(len(projection) == 564 and (output / OUTPUTS[1]).read_bytes() == helper.tsv(projection, ledger_reader.fieldnames),
        'The full 564-row eligibility projection must preserve every original ledger column and value')
    receipt = strict_json((output / OUTPUTS[2]).read_bytes())
    require(receipt.get('schema') == 'FROZEN_A_LEGACY_FAMILY_GATE_RECEIPT_V1' and
        all(receipt.get(name) is False for name in ('MR_estimates_computed', 'official_MR_numerical_equivalence_certified',
            'primary_estimates_created', 'scientific_authorization_granted', 'formal_scientific_pass_granted', 'g0_granted')),
        'Barrier receipt must carry explicit non-scientific authority')
    require(receipt.get('request') == REQUEST and
        receipt.get('MR_lineage') == strict_json(inputs[8].read_bytes()) and
        receipt.get('family_validation') == strict_json(expected['assembly-receipt.json']) and
        receipt.get('family_counts') == helper.COUNTS and receipt.get('eligibility_rows') == 564 and
        type(receipt.get('unresolved_overlap_entries_preserved')) is int and
        receipt['unresolved_overlap_entries_preserved'] == 275 and
        type(receipt.get('real_primary_p_values_filled')) is int and receipt['real_primary_p_values_filled'] == 0 and
        type(receipt.get('real_overlap_assignments_made')) is int and receipt['real_overlap_assignments_made'] == 0,
        'Every family, unresolved overlap and unchanged missing primary must remain explicit')
    records = receipt.get('input_files')
    require(isinstance(records, list) and len(records) == 23 and
        all(type(record.get('port')) is int and record['port'] == index and
            all(record.get(key) == fact(path)[key] for key in ('bytes', 'sha256'))
            for index, (record, path) in enumerate(zip(records, inputs, strict=True))),
        'Every consumed source and MR artifact must be bound to its actual complete bytes')
    opaque = receipt.get('opaque_RDS', {})
    require(opaque.get('readRDS_performed') is False and opaque.get('independent_official_readback_required') is True and
        all(opaque.get(key) == fact(inputs[6])[key] for key in ('bytes', 'sha256')),
        'Python barrier cannot claim official RDS deserialization')
    require(receipt.get('output_sha256') == {name: fact(output / name)['sha256'] for name in (OUTPUTS[0], OUTPUTS[1], OUTPUTS[3])},
        'The gate request, projection and log must match the complete producer receipt')
    return dict(request_has_no_estimates=True, projection_rows=564, raw_missing_preserved=True,
        family_denominators=helper.COUNTS, MR_products_bound_separately=True,
        standalone_family_result_does_not_contain_MR_lineage=True)


def changed_table(payload, column, value):
    reader = csv.DictReader(io.StringIO(payload.decode()), delimiter='\t')
    rows = list(reader)
    require(rows and column in reader.fieldnames, 'Existing full table column required for a targeted negative control')
    rows[0][column] = value
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def refusal_inputs(directory, original):
    directory.mkdir(mode=0o700)
    cases = []
    def add(name, port, payload, diagnostic):
        path = directory / (name + '.input')
        path.write_bytes(payload)
        paths = list(original)
        paths[port] = path
        cases.append((name, paths, diagnostic))
    add('primary-upgrade', 0, changed_table(original[0].read_bytes(), 'p_primary', '0.01'),
        'Primary upgrade forbidden: O2 requires raw NA and family one')
    provenance = strict_json(original[8].read_bytes())
    provenance['scientific_authorization_granted'] = True
    add('authority-upgrade', 8, (json.dumps(provenance) + '\n').encode(), 'Scientific authority upgrade forbidden')
    provenance = strict_json(original[8].read_bytes())
    provenance['adapter_sha256'] = '0' * 64
    add('stale-adapter', 8, (json.dumps(provenance) + '\n').encode(), 'Stale MR adapter SHA forbidden')
    leave_one_out = original[3].read_bytes().splitlines(keepends=True)
    require(len(leave_one_out) == 41, 'Full original header plus forty LOO rows required')
    add('incomplete-loo', 3, b''.join(leave_one_out[:-1]), 'Complete LOO membership requires 39 SNPs and All')
    add('qualified-identity', 5, original[5].read_bytes() + b'\n', 'Frozen qualified input SHA differs')
    registry = original[13].read_bytes()
    add('registry-identity', 13, bytes([registry[0] ^ 1]) + registry[1:], 'Frozen source identity differs')
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mr-session', required=True)
    parser.add_argument('--mr-seal', required=True)
    parser.add_argument('--runtime-backend', choices=('default', 'owner-canonical'), required=True)
    arguments = parser.parse_args()
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'frozen-a-legacy-family-gate'
    output.mkdir(mode=0o700)
    before_sources = observed_sources()
    own_before = fact(Path(__file__))
    shutil.copyfile(Path(__file__), output / 'driver.py')
    for name in before_sources:
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    helper, node = family_helper(), definition()
    archive_root = Path.home() / '.local/state/autonomics/validation-archives'
    mr_inputs, mr_receipt = checked_mr_archive(archive_root, arguments.mr_session, arguments.mr_seal)
    inputs = [*mr_inputs, *frozen_inputs(helper)]
    before_inputs = [fact(path) for path in inputs]
    for name in ('pre-verifier', 'post-verifier', 'backend-before', 'backend-after', 'images'):
        (output / name).mkdir(mode=0o700)
    pre = qualification.original_postcheck(output / 'pre-verifier')
    require(shutil.disk_usage(output).free >= 1024**3, 'At least 1 GiB archive/scratch reserve required')
    cgroup = runtime.cgroup_observation()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3, 'At least four GiB host available memory required for a serial bounded container')
    write(output / 'resource-admission.json', dict(parent=cgroup, container_memory_bytes=1073741824,
        container_cpus=1, max_concurrent_containers=1, available_host_memory_bytes=available))
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    shim_before = fact(shim)
    prerequisites = []
    if arguments.runtime_backend == 'default':
        prefix = [str(shim), '--cgroup-manager=cgroupfs']
        backend = runtime.default_backend(prefix, output / 'backend-before')
        image = installed.inspect_image(prefix, output / 'images', 'before', IMAGE)
    else:
        python_runtime, prerequisites = raw.prerequisite_archives(archive_root)
        prefix = raw.backend(output / 'backend-before', python_runtime)
        backend = dict(kind='EXPLICIT_OWNER_BOUND_CANONICAL_ALTERNATE_NOT_DEFAULT', argv=prefix[1:],
            owner_sha256=raw.OWNER_SHA)
        image = dict(reference=IMAGE, config_sha256=raw.CONFIG,
            ordered_diff_ids=python_runtime['installed_diff_ids'])
    attempted = 0
    cases = ['positive']
    try:
        attempted += 1
        execute(prefix, node, inputs, output / 'positive', 0)
        positive = validate_positive(output / 'positive', helper, inputs)
        attempted += 1
        execute(prefix, node, inputs, output / 'foreign-output', 2,
            'Existing or foreign output must never be overwritten', foreign=b'UNRELATED_OUTPUT_MUST_NOT_CHANGE\n')
        cases.append('foreign-output')
        for name, changed, diagnostic in refusal_inputs(output / 'refusal-inputs', inputs):
            attempted += 1
            execute(prefix, node, changed, output / name, 2, diagnostic)
            cases.append(name)
    finally:
        observations = stopped(prefix, permanent, output, attempted)
    post = qualification.original_postcheck(output / 'post-verifier')
    require(before_inputs == [fact(path) for path in inputs] and observed_sources() == before_sources and
        fact(Path(__file__)) == own_before and fact(shim) == shim_before,
        'Frozen contracts, producer archives or reviewed sources changed')
    if arguments.runtime_backend == 'default':
        require(backend == runtime.default_backend(prefix, output / 'backend-after') and
            image == installed.inspect_image(prefix, output / 'images', 'after', IMAGE), 'Actual fixed backend/image changed')
    else:
        require(prefix == raw.backend(output / 'backend-after', python_runtime), 'Actual owner-bound backend/image changed')
    write(output / 'verification.json', dict(status='SCOPED_LEGACY_MR_LINEAGE_BARRIER_DIRECT_NOT_CONNECTED_DAG_OR_G0',
        mr_replay=mr_receipt, sources=before_sources, input_identities=before_inputs, positive=positive,
        actual_container_entries=attempted, stopped_container_intents=len(observations),
        cases=cases, pre_verifier=pre, post_verifier=post,
        backend=backend, runtime_backend=arguments.runtime_backend, runtime_prerequisites=prerequisites,
        default_backend_availability_proved=arguments.runtime_backend == 'default',
        image=image, statistical_estimates_computed=False,
        actual_connected_DAG_executed=False, production_changed=False,
        scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
