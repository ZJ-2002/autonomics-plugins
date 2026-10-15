"""Bounded replay of the already-seen frozen 39-IV O2 exploratory MR input."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_h5ad_subset_official_runtime as runtime
from tools import prove_r_publication_runtime as installed
from tools import prove_frozen_a_harmonisation as qualification
from tools.prove_frozen_a_family_runtime import stopped
from tools.prove_frozen_a_package_identity import FUNCTION_IDENTITY_R
from tools.reconcile_ab_evidence_index import verify_archive

STUDY = qualification.STUDY
AUDIT = qualification.AUDIT
PLUGIN = 'plugins/twosamplemr-v432-a/'
IMAGE = qualification.IMAGE
INNER = 'tools/check_frozen_a_legacy_mr_runtime.R'
INNER_SHA = '9b656c39926c6fdaeecafba8df8dc2c5216cba81c891255e00f36ad328a688d8'
METHOD_SHA = qualification.SOURCE_SHA
BLOCK_SHA = '0fe5cac9fff04351897ef3eca682ecb212e144b6e52604bc827ed141805bdc34'
CANARY_SESSION = 'b4d736c808d24d149d49be608d81440f'
CANARY_SEAL = 'fc6e2ba706ef5679716160ddfca4ff6a12fa7ea3f79edfe4c03d641e81e6ef77'
OLD_RESULT = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/results/v4.3.2/A_LEGACY_TUI/autonomics-container-command-154916-1791977616091097592')
INPUTS = [
    (AUDIT + 'A_FROZEN_EXPLORATORY_INPUT.tsv', '9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa'),
    (AUDIT + 'A_ANALYSIS_CONFIG.json', '8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f'),
    (AUDIT + 'G0_V432_CERTIFICATE.json', 'aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2'),
    (AUDIT + 'R_DEPENDENCY_LOCK.tsv', '8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56'),
]
OUTPUTS = ['ALL_METHODS_EXPLORATORY.tsv', 'HETEROGENEITY.tsv', 'EGGER_INTERCEPT.tsv',
    'ALL_LEAVE_ONE_OUT.tsv', 'ALL_REGION_SENSITIVITIES.tsv', 'QUALIFIED_INPUT.tsv',
    'twosamplemr_v432_a.RDS', 'twosamplemr_v432_a.log', 'INPUT_METHOD_PROVENANCE.json']
OLD_HASHES = [
    '37e0ec7b76a09579e64dfa9eeaa2ff224b7ef66556d8655c456014b78e3f66b7',
    '692f6ee4fa4b67d31c8e504cd210010796d0297e838922581a40bf2f980d2f95',
    '4a1ce8facdc2c3de237bc2f4b44ad499ecee87558153acdcebc5efd5fdcd3d4e',
    '5a93e796c11144b8616d1286c63a47eca4f4481670bb9bd7295e0c2af5e7bc2d',
    '9d61daecc0200f5438e1e0d0f1f4abc37d3f95afea1f424dd4baa02f50e5256d',
    INPUTS[0][1], 'cef4061a3c78a07c930486209c883fca42b3d66e624d2ccfbd487e9af783b8b6',
    '3926158f78d0e38551185e17b97c4f8bfd436b4f21a41c15722cc3a3ac9846c7',
    '432fb25a357be004baa29bab7d4432d7b8c9ffb0b6df1c5188ba4baf359c80b0',
]
PINS = {
    PLUGIN + 'manifest.toml': '661e12b231f7b38540d5cba2fca8a31ee3d5d0831305998f00fa0e898d980324',
    PLUGIN + 'scripts/mr.R': '33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe',
    PLUGIN + 'contracts/frozen-method-proof.json': 'a79c4469321bcef7ffabb9f94ad557ca185409bd9177868a3c158d8debb484c2',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_r_publication_runtime.py': 'db91460fb9875bad822e15dfa4abbc7283b1e5121455c5447eab47c76c7578c9',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
    'tools/prove_frozen_a_harmonisation.py': '79b36d2f5a64409f0b8b87735b7773f29dd3dedeaa3809ddb14a4c7a97685018',
    'tools/prove_frozen_a_package_identity.py': '31283d23240d176d15cf041872d34ae6a4a3cd841aa5abfd97e3b96170a89e93',
}
require, fact, write, strict_json = runtime.require, runtime.fact, runtime.write, runtime.strict_json


def run_a_block(text):
    begin, end = '} else if(mode=="run-A") {\n', '\n} else if(mode=="run-B") {'
    require(text.count(begin) == text.count(end) == 1 and text.index(begin) < text.index(end),
        'Unique ordered original run-A branch required')
    value = text.split(begin, 1)[1].split(end, 1)[0]
    require(hashlib.sha256(value.encode()).hexdigest() == BLOCK_SHA, 'Exact frozen original run-A branch required')
    return value


def source_facts():
    pins = {**PINS, INNER: INNER_SHA}
    require(all(len(value) == 64 and set(value) <= set('0123456789abcdef') for value in pins.values()),
        'Reviewed checker source is not frozen')
    records = {name: fact(ROOT / name) for name in pins}
    require(all(records[name]['sha256'] == expected for name, expected in pins.items()), 'Reviewed technical source changed')
    return records


def frozen_facts():
    records = {name: fact(STUDY / name) for name, expected in INPUTS}
    require(all(records[name]['sha256'] == expected for name, expected in INPUTS), 'Frozen MR input identity changed')
    name = '02_EXECUTION/g0_v432_methods.R'
    records[name] = fact(STUDY / name)
    require(records[name]['sha256'] == METHOD_SHA, 'Original frozen scientific source changed')
    run_a_block((STUDY / name).read_text())
    return records


def old_reference_facts():
    records = {name: fact(OLD_RESULT / name) for name in OUTPUTS}
    require(all(records[name]['sha256'] == expected for name, expected in zip(OUTPUTS, OLD_HASHES, strict=True)),
        'Already-seen canonical nine-port reference changed')
    return records


def checked_prior():
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    canary = verify_archive(archives, CANARY_SESSION, CANARY_SEAL)
    require(canary['positive_worker_exit_verified'], 'Recorded completed prior real legacy canary required')
    package = verify_archive(archives, qualification.PACKAGE_SESSION, qualification.PACKAGE_SEAL)
    require(package['positive_worker_exit_verified'], 'Complete official package identity proof required')
    proof = strict_json((Path(package['artifact_root']) / 'permanent/frozen-a-package-identity/verification.json').read_text())
    require(proof['exact_image'] == IMAGE and proof['function_identity']['function_count'] == 171 and
        proof['function_identity']['aggregate_sha256'] == qualification.PACKAGE_FUNCTIONS_SHA,
        'Official package-owned function reference identity differs')
    return dict(prior_canary_session=CANARY_SESSION, prior_canary_seal=CANARY_SEAL,
        prior_canary_is_not_independent_oracle=True, package_identity_session=qualification.PACKAGE_SESSION,
        package_identity_seal=qualification.PACKAGE_SEAL)


def snapshot(output, observed, frozen, old):
    source = output / 'source'
    source.mkdir(mode=0o700)
    for name, identity in observed.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        require(fact(target)['sha256'] == identity['sha256'], 'Technical source copy changed')
    inputs = output / 'inputs'
    inputs.mkdir(mode=0o700)
    for index, (name, expected) in enumerate(INPUTS):
        shutil.copyfile(STUDY / name, inputs / ('input' + str(index)))
        require(fact(inputs / ('input' + str(index)))['sha256'] == expected, 'Exact transported frozen input required')
    shutil.copyfile(ROOT / (PLUGIN + 'contracts/frozen-method-proof.json'), inputs / 'input4')
    shutil.copyfile(STUDY / '02_EXECUTION/g0_v432_methods.R', source / 'g0_v432_methods.R')
    require(fact(source / 'g0_v432_methods.R')['sha256'] == frozen['02_EXECUTION/g0_v432_methods.R']['sha256'],
        'Unchanged original method source snapshot required')
    (source / 'namespace-identity.R').write_text(FUNCTION_IDENTITY_R)
    prior = output / 'prior-seen'
    prior.mkdir(mode=0o700)
    for name in OUTPUTS:
        shutil.copyfile(OLD_RESULT / name, prior / name)
        require(fact(prior / name)['sha256'] == old[name]['sha256'], 'Already-seen artifact copy changed')
    return source, inputs


def command(prefix, source, inputs, output, reference):
    arguments = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=1073741824', '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-e', 'TMPDIR=/tmp', '-e', 'R_LIBS_USER=/nonexistent',
        '-v', str(source) + ':/source:ro', '-v', str(inputs) + ':/inputs:ro', '-v', str(output) + ':/proof:rw']
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS'):
        arguments.extend(['-e', name + '=1'])
    if not reference:
        for index in range(5):
            arguments.extend(['-e', 'AUTONOMICS_INPUT' + str(index) + '=/inputs/input' + str(index)])
        for index, name in enumerate(OUTPUTS):
            arguments.extend(['-e', 'AUTONOMICS_OUTPUT' + str(index) + '=/proof/current/' + name])
    script = '/source/' + INNER if reference else '/source/' + PLUGIN + 'scripts/mr.R'
    arguments.extend(['--entrypoint=Rscript', IMAGE, '--vanilla', script])
    return arguments


def execute(prefix, source, inputs, output, reference):
    label = 'independent-original-reference' if reference else 'current'
    arguments = command(prefix, source, inputs, output, reference)
    write(output / (label + '-command.json'), arguments)
    process = subprocess.run(arguments, capture_output=True, text=True, timeout=1200)
    (output / (label + '.stdout')).write_text(process.stdout)
    (output / (label + '.stderr')).write_text(process.stderr)
    write(output / (label + '-execution.json'), dict(actual_exit=process.returncode, image=IMAGE,
        container_memory_bytes=1024**3, container_cpus=1, no_network=True, no_pull=True, no_build=True))
    require(type(process.returncode) is int and process.returncode == 0, 'Actual ' + label + ' official execution failed')


def validate_summary(value):
    require(value.get('schema') == 'FROZEN_A_REAL_39_LEGACY_OFFICIAL_REFERENCE_V1' and
        type(value.get('variants')) is int and value['variants'] == 39 and
        type(value.get('seed')) is int and value['seed'] == 432202610 and
        value.get('R') == '4.6.1' and value.get('TwoSampleMR') == '0.7.11', 'Exact frozen real legacy method scope required')
    for name in ('actual_DAG_executed', 'new_independent_scientific_evidence', 'MRlap_executed',
            'other_275_edges_executed', 'production_changed', 'scientific_authorization_granted', 'g0_granted'):
        require(value.get(name) is False, 'Direct legacy replay cannot grant additional authority')
    require(value.get('original_run_A_block_sha256') == BLOCK_SHA and value.get('original_scientific_source_sha256') == METHOD_SHA and
        value.get('original_scientific_statements_unchanged') is True and value.get('whole_original_cli_executed') is False and
        value.get('original_verifier_not_faked') is True and value.get('outer_whole_project_verifier_required') is True,
        'Original unmodified scientific statements and explicit technical envelope required')
    require(value.get('overlap_class') == 'O2' and value.get('primary_p_source') == 'NA' and
        value.get('all_main_primary_missing') is True and value.get('all_main_adjustment_one') is True,
        'O2 primary cannot be replaced by exploratory IVW or MRlap')
    require(value.get('six_complete_TSVs_byte_equal') is True and value.get('six_complete_TSVs_readback_equal') is True and
        value.get('complete_RDS_object_identical') is True and value.get('RDS_numeric_tolerance') == 0 and
        type(value.get('RDS_numeric_tolerance')) is int and value.get('input_harmonised_object_identical') is True,
        'Complete serialized/readback tables and exact full official objects required')
    require(value.get('independent_official_call_sequence') == ['mr', 'mr_heterogeneity', 'mr_pleiotropy_test',
        'mr_leaveoneout', 'mr', 'mr', 'mr'] and value.get('methods') == ['mr_ivw', 'mr_egger_regression', 'mr_weighted_median'],
        'Full original global RNG/call order and all fixed methods required')
    require(value.get('official_namespace_function_count') == 171 and
        type(value['official_namespace_function_count']) is int and
        value.get('official_namespace_aggregate_sha256') == qualification.PACKAGE_FUNCTIONS_SHA and
        value.get('package_description_sha256') == qualification.PACKAGE_DESCRIPTION_SHA and
        value.get('observed_RemoteSha') is None, 'Actual image package identity must be observed, not invented')
    require(value.get('all_nine_current_ports_checked') is True and value.get('full_provenance_contract_checked') is True and
        value.get('complete_log_checked') is True and value.get('log_byte_equal_to_original_cli_claimed') is False and
        value.get('adapter_added_fields_disclosed') == ['p_raw_exploratory', 'contract', 'qualified_input_serialization',
            'RDS', 'diagnostic_log', 'provenance'], 'Every port and adapter-only field must be disclosed')
    comparisons = value.get('tables')
    require(isinstance(comparisons, list) and len(comparisons) == 6 and
        [row.get('port') for row in comparisons] == list(range(6)) and
        all(type(row.get('port')) is int for row in comparisons) and
        [row.get('name') for row in comparisons] == OUTPUTS[:6] and
        all(row.get('complete_bytes_equal') is True and row.get('complete_readback_equal') is True and
            type(row.get('rows')) is int and row['rows'] > 0 for row in comparisons), 'All six complete table inventories required')
    return value


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Explicitly execute the already-seen real legacy technical replay')
    options = parser.parse_args(arguments)
    require(options.execute is True, 'Explicit --execute required; no automatic real legacy fitting')
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'frozen-a-legacy-mr-runtime'
    output.mkdir(mode=0o700)
    own_before, sources_before, frozen_before, old_before = fact(Path(__file__)), source_facts(), frozen_facts(), old_reference_facts()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    prior = checked_prior()
    for name in ('pre-verifier', 'post-verifier', 'backend-before', 'backend-after', 'images'):
        (output / name).mkdir(mode=0o700)
    pre = qualification.original_postcheck(output / 'pre-verifier')
    cgroup = runtime.cgroup_observation()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3,
        'Bounded serial official replay requires host memory reserve and scratch capacity')
    write(output / 'resource-admission.json', dict(parent=cgroup, parent_memory_max_bytes=2 * 1024**3,
        container_memory_bytes=1024**3, container_cpus=1, max_concurrent_containers=1))
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    shim_before = fact(shim)
    prefix = [str(shim), '--cgroup-manager=cgroupfs']
    backend_before = runtime.default_backend(prefix, output / 'backend-before')
    image_before = installed.inspect_image(prefix, output / 'images', 'before', IMAGE)
    source, inputs = snapshot(output, sources_before, frozen_before, old_before)
    manifest = tomllib.loads((source / (PLUGIN + 'manifest.toml')).read_text())
    require(manifest['image']['reference'] == IMAGE and len(manifest['nodes']) == 1 and
        manifest['nodes'][0]['kind'] == 'twosamplemr_v432_a_exploratory' and
        manifest['nodes'][0]['ports']['outputs'] == [dict(path=name, format=kind) for name, kind in
            zip(OUTPUTS, ['tsv'] * 6 + ['r_rds', 'twosamplemr_log', 'json'], strict=True)], 'Declared exact method ports differ')
    (output / 'current').mkdir(mode=0o700)
    attempted = 0
    try:
        attempted += 1
        execute(prefix, source, inputs, output, False)
        attempted += 1
        execute(prefix, source, inputs, output, True)
    finally:
        stops = stopped(prefix, permanent, output, attempted)
    summary = validate_summary(strict_json((output / 'reference-verification.json').read_text()))
    for index, name in enumerate(OUTPUTS):
        fact(output / 'current' / name)
    require(backend_before == runtime.default_backend(prefix, output / 'backend-after') and
        image_before == installed.inspect_image(prefix, output / 'images', 'after', IMAGE), 'Actual backend/image changed')
    post = qualification.original_postcheck(output / 'post-verifier')
    require(source_facts() == sources_before and frozen_facts() == frozen_before and old_reference_facts() == old_before and
        fact(Path(__file__)) == own_before and fact(shim) == shim_before, 'Canonical frozen inputs, old results or reviewed code changed')
    write(output / 'verification.json', dict(status='SCOPED_REAL_ALREADY_SEEN_39_IV_DIRECT_OFFICIAL_REPLAY_NOT_DAG_OR_G0',
        scope='FROZEN_V432_A_LEGACY', original_sources=sources_before, frozen_inputs=frozen_before,
        already_seen_reference_ports=old_before, prerequisites=prior, reference=summary, image=image_before,
        backend=backend_before, pre_verifier=pre, post_verifier=post, current_ports=[dict(port=index, name=name,
            **fact(output / 'current' / name)) for index, name in enumerate(OUTPUTS)],
        stopped_container_intents=len(stops), original_manifest_resource_certified=False,
        actual_DAG_executed=False, production_changed=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
