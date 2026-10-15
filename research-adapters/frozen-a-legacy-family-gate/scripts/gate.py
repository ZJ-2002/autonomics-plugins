import csv
import hashlib
import importlib.util
import io
import math
import os
from pathlib import Path
import stat
import sys
import tempfile


HELPER_SHA = '338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a'
HELPER_BYTES = 26620
ADAPTER_SHA = '33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe'
QUALIFIED_SHA = '9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa'
DESCRIPTION_SHA = '911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531'
IVW_FUNCTION_SHA = '8b16d02b9aa1ac43a6538e3e296a3d7eaade937bb12edf37597c44ab3da11e38'
FROZEN = [
    ('A_ANALYSIS_CONFIG.json', 3499, '8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f'),
    ('G0_V432_CERTIFICATE.json', 2324, 'aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2'),
    ('R_DEPENDENCY_LOCK.tsv', 11542, '8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56'),
    ('frozen-method-proof.json', 577, 'a79c4469321bcef7ffabb9f94ad557ca185409bd9177868a3c158d8debb484c2'),
]
MR_NAMES = ['ALL_METHODS_EXPLORATORY.tsv', 'HETEROGENEITY.tsv', 'EGGER_INTERCEPT.tsv',
    'ALL_LEAVE_ONE_OUT.tsv', 'ALL_REGION_SENSITIVITIES.tsv', 'QUALIFIED_INPUT.tsv',
    'twosamplemr_v432_a.RDS', 'twosamplemr_v432_a.log', 'INPUT_METHOD_PROVENANCE.json']
OUTPUT_NAMES = ['family-request.json', 'eligibility-projection.tsv', 'gate-receipt.json', 'gate.log']
METHODS = ['Inverse variance weighted', 'MR Egger', 'Weighted median']
TRAIT = {'id.exposure': 'GCST90652391', 'id.outcome': 'GCST90002393',
    'exposure': 'X01_BMFF_residual_INT', 'outcome': 'M06_monocyte_transformed'}
PREFIX = ['id.exposure', 'id.outcome', 'outcome', 'exposure']
MR_COLUMNS = PREFIX + ['method', 'nsnp', 'b', 'se', 'pval', 'role', 'p_primary',
    'p_for_family', 'p_raw_exploratory']
HET_COLUMNS = PREFIX + ['method', 'Q', 'Q_df', 'Q_pval']
INTERCEPT_COLUMNS = PREFIX + ['egger_intercept', 'se', 'pval']
LOO_COLUMNS = ['exposure', 'outcome', 'id.exposure', 'id.outcome', 'samplesize', 'SNP', 'b', 'se', 'p']
REGION_COLUMNS = PREFIX + ['method', 'nsnp', 'b', 'se', 'pval', 'p_primary', 'role', 'sensitivity']
REGIONS = ['exclude_MHC', 'exclude_TERT_vicinity', 'exclude_both']
LEDGER_COLUMNS = ['analysis_id', 'family_id', 'resource_id', 'contrast_id', 'program_or_candidate_id',
    'cell_type', 'statistic', 'estimand_id', 'independent_unit', 'role', 'selection_source',
    'followup_result_exposure', 'config_path', 'config_sha256', 'status', 'p_raw',
    'p_for_adjustment', 'exploratory_execution']
REQUEST = {'schema': 'FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1',
    'scope': 'FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH', 'scenario': 'REAL_FROZEN_NA_LEDGER', 'edges': []}
PROVENANCE_KEYS = {'scope', 'input_sha256', 'adapter_sha256', 'frozen_scientific_code_sha256',
    'R', 'TwoSampleMR', 'method_function_sha256', 'package_description', 'package_description_sha256',
    'dependency_lock_sha256', 'seed', 'bootstrap_n', 'n_independent_IV', 'exposure_role',
    'certificate_role', 'overlap_class', 'primary_p_source', 'scientific_authorization_granted',
    'formal_scientific_pass_granted'}
LOG = b'Frozen exploratory MR lineage checked; 564 original NA rows retained. No primary estimate or scientific release.\n'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_helper(path):
    require(path.is_absolute() and not any(item.is_symlink() for item in [path, *path.parents]) and
        stat.S_ISREG(path.lstat().st_mode), 'Exact regular frozen family helper required')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    before = path.stat()
    require(before.st_size == HELPER_BYTES, 'Frozen family helper size differs before reading')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        require(signature(os.fstat(handle.fileno())) == signature(before), 'Frozen family helper changed')
        payload = handle.read(HELPER_BYTES + 1)
        require(signature(os.fstat(handle.fileno())) == signature(before), 'Frozen family helper changed')
    require(signature(path.stat()) == signature(before) and len(payload) == HELPER_BYTES and
        hashlib.sha256(payload).hexdigest() == HELPER_SHA, 'Frozen family helper SHA differs')
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('locked_family_gate_helper', loader=None))
    module.__file__ = str(path)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    return module


def number(value, label, *, probability=False, positive=False, integer=False):
    require(isinstance(value, str) and value not in {'', 'NA', 'NaN', 'Inf', '-Inf'}, 'Finite numeric value required: ' + label)
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError('Finite numeric value required: ' + label) from None
    require(math.isfinite(parsed) and (not probability or 0 <= parsed <= 1) and
        (not positive or parsed > 0) and (not integer or parsed == int(parsed)),
        'Finite valid numeric value required: ' + label)
    return parsed


def trait_rows(rows):
    require(all(all(row.get(key) == value for key, value in TRAIT.items()) for row in rows),
        'Frozen X01 to M06 trait identity differs')


def validate_mr(payloads, helper):
    require(helper.checksum(payloads[5]) == QUALIFIED_SHA, 'Frozen qualified input SHA differs')
    qualified = helper.table(payloads[5])
    require(len(qualified) == 39 and len({row['SNP'] for row in qualified}) == 39, 'Complete 39 qualified variants required')
    trait_rows(qualified)
    snps = {row['SNP'] for row in qualified}
    tables = [helper.table(payloads[index], columns) for index, columns in enumerate(
        [MR_COLUMNS, HET_COLUMNS, INTERCEPT_COLUMNS, LOO_COLUMNS, REGION_COLUMNS])]
    for rows in tables:
        trait_rows(rows)
    estimates, heterogeneity, intercept, leave_one_out, sensitivities = tables
    require(len(estimates) == 3 and {row['method'] for row in estimates} == set(METHODS),
        'Exactly three original exploratory methods required')
    for row in estimates:
        require(row['role'] == 'EXPLORATORY_OVERLAP_UNRESOLVED' and row['p_primary'] == 'NA' and
            row['p_for_family'] == '1', 'Primary upgrade forbidden: O2 requires raw NA and family one')
        require(number(row['nsnp'], 'MR nsnp', integer=True) == 39, 'Complete MR variant count required')
        number(row['b'], 'MR b')
        number(row['se'], 'MR se', positive=True)
        require(number(row['p_raw_exploratory'], 'exploratory P', probability=True) ==
            number(row['pval'], 'MR P', probability=True), 'Exploratory probability must retain official pval')
    require(len(heterogeneity) == 2 and {row['method'] for row in heterogeneity} == set(METHODS[:2]),
        'Complete two-method heterogeneity required')
    for row in heterogeneity:
        require(number(row['Q'], 'Q') >= 0 and number(row['Q_df'], 'Q df', integer=True) ==
            (37 if row['method'] == 'MR Egger' else 38), 'Valid heterogeneity statistic and degrees required')
        number(row['Q_pval'], 'Q probability', probability=True)
    require(len(intercept) == 1, 'Exactly one Egger intercept required')
    number(intercept[0]['egger_intercept'], 'Egger intercept')
    number(intercept[0]['se'], 'Egger intercept se', positive=True)
    number(intercept[0]['pval'], 'Egger probability', probability=True)
    require(len(leave_one_out) == 40 and len({row['SNP'] for row in leave_one_out}) == 40 and
        {row['SNP'] for row in leave_one_out} == snps | {'All'}, 'Complete LOO membership requires 39 SNPs and All')
    for row in leave_one_out:
        require(row['samplesize'] == 'NA', 'Unknown original LOO sample size must remain NA')
        number(row['b'], 'LOO b')
        number(row['se'], 'LOO se', positive=True)
        number(row['p'], 'LOO probability', probability=True)
    memberships = {region: 0 for region in REGIONS}
    for row in qualified:
        chromosome = number(row['chr37'], 'chr37', integer=True)
        position = number(row['pos37'], 'pos37', integer=True, positive=True)
        mhc = chromosome == 6 and 25000000 <= position <= 34000000
        tert = chromosome == 5 and 1 <= position <= 2000000
        for region, keep in zip(REGIONS, [not mhc, not tert, not (mhc or tert)], strict=True):
            memberships[region] += int(keep)
    require(len(sensitivities) == 9 and {(row['sensitivity'], row['method']) for row in sensitivities} ==
        {(region, method) for region in REGIONS for method in METHODS}, 'Complete three-region three-method sensitivity grid required')
    for row in sensitivities:
        require(row['role'] == 'REGISTERED_SENSITIVITY_ONLY' and row['p_primary'] == 'NA',
            'Primary upgrade forbidden in registered sensitivity')
        require(number(row['nsnp'], 'Sensitivity nsnp', integer=True) == memberships[row['sensitivity']],
            'Registered region variant membership differs')
        number(row['b'], 'Sensitivity b')
        number(row['se'], 'Sensitivity se', positive=True)
        number(row['pval'], 'Sensitivity probability', probability=True)
    require(payloads[6], 'Opaque RDS artifact must not be empty')
    log = payloads[7].decode('utf-8')
    require(log.strip() and 'Scope: FROZEN_V432_A_LEGACY' in log and
        'seed=432202610; bootstrap_n=1000; overlap=O2; LEGACY_EXPLORATORY; primary_p=NA; family_p=1' in log,
        'Original exploratory log declaration missing')
    return dict(qualified_variants=39, exploratory_methods=3, heterogeneity_rows=2, intercept_rows=1,
        leave_one_out_rows=40, region_rows=9, region_variant_counts=memberships,
        missing_sample_size_preserved=True, numerical_recomputation_performed=False)


def validate_provenance(payloads, helper):
    config, certificate, method = [helper.strict_json(payloads[index]) for index in [9, 10, 12]]
    provenance = helper.strict_json(payloads[8])
    require(isinstance(provenance, dict) and set(provenance) == PROVENANCE_KEYS, 'Exact MR provenance schema required')
    require(all(provenance[key] is False for key in ['scientific_authorization_granted', 'formal_scientific_pass_granted']),
        'Scientific authority upgrade forbidden')
    require(provenance['adapter_sha256'] == ADAPTER_SHA, 'Stale MR adapter SHA forbidden')
    expected_inputs = [QUALIFIED_SHA, *[record[2] for record in FROZEN]]
    require(provenance['input_sha256'] == expected_inputs and method['input_sha256'] == expected_inputs[:4] and
        method['scope'] == provenance['scope'] == 'FROZEN_V432_A_LEGACY', 'Exact frozen legacy MR input lineage required')
    scientific_sha = helper.SOURCES[8][2]
    require(method['scientific_code_sha256'] == provenance['frozen_scientific_code_sha256'] == scientific_sha and
        method['R'] == provenance['R'] == '4.6.1' and method['TwoSampleMR'] == provenance['TwoSampleMR'] == '0.7.11' and
        all(method[key] is False for key in ['scientific_authorization_granted', 'formal_scientific_pass_granted']),
        'Frozen method identity and false authority required')
    require(provenance['package_description_sha256'] == DESCRIPTION_SHA and provenance['method_function_sha256'] == IVW_FUNCTION_SHA and
        provenance['dependency_lock_sha256'] == FROZEN[2][2] and
        isinstance(provenance['package_description'], dict) and provenance['package_description'].get('Package') == 'TwoSampleMR' and
        provenance['package_description'].get('Version') == '0.7.11', 'Official frozen package provenance differs')
    for name, expected in [('seed', 432202610), ('bootstrap_n', 1000), ('n_independent_IV', 39)]:
        require(type(provenance[name]) is int and provenance[name] == expected, 'Frozen MR scalar identity differs: ' + name)
    require(provenance['exposure_role'] == 'LEGACY_EXPLORATORY' and
        provenance['certificate_role'] == 'LEGACY_EXPLORATORY_O2_PRIMARY_NA' and
        provenance['overlap_class'] == 'O2' and provenance['primary_p_source'] == 'NA', 'Primary upgrade forbidden in MR provenance')
    require(config['status'] == 'LOCKED' and config['version'] == '4.3.2' and config['enabled_edge'] == 'A_X01_M06' and
        config['analysis_id'] == 'G0_V432_A_X01_M06' and config['program_sha256'] == QUALIFIED_SHA and
        config['overlap_class'] == 'O2' and config['primary_p_source'] == 'NA' and
        config['exposure_role'] == 'LEGACY_EXPLORATORY' and config['ordinary_ivw_parallel'] == 'EXPLORATORY_ONLY' and
        config['seed'] == 432202610 and config['bootstrap_n'] == 1000,
        'Frozen exploratory configuration differs')
    require(certificate['status'] == 'G0_V432_MINIMUM_COMPLETE' and certificate['version'] == '4.3.2' and
        certificate['A']['allowed'] is True and certificate['A']['confirmatory_allowed'] is False and
        certificate['A']['analysis_id'] == config['analysis_id'] and
        certificate['A']['role'] == 'LEGACY_EXPLORATORY_O2_PRIMARY_NA', 'Frozen certificate role differs')
    packages = helper.table(payloads[11])
    require([row['version'] for row in packages if row['package'] == 'TwoSampleMR'] == ['0.7.11'],
        'Frozen R dependency version differs')
    return provenance


def assemble_gate(inputs, helper):
    budgets = [4 * 1024**2] * 6 + [32 * 1024**2, 1024**2, 4 * 1024**2]
    payloads = [helper.read(path, max_bytes=budget) for path, budget in zip(inputs[:9], budgets, strict=True)]
    for path, (name, size, expected) in zip(inputs[9:13], FROZEN, strict=True):
        data = helper.read(path, expected_size=size)
        require(helper.checksum(data) == expected, 'Frozen contract input SHA differs: ' + name)
        payloads.append(data)
    family_sources, family_payloads = helper.source_inputs(inputs[13:22])
    payloads.extend(family_payloads)
    require(helper.checksum(helper.read(inputs[22], expected_size=HELPER_BYTES)) == HELPER_SHA, 'Frozen family helper SHA differs')
    payloads.append(helper.read(inputs[22], expected_size=HELPER_BYTES))
    mr_summary = validate_mr(payloads, helper)
    provenance = validate_provenance(payloads, helper)
    request = helper.json_bytes(REQUEST)
    with tempfile.TemporaryDirectory(prefix='frozen-a-gate-') as directory:
        request_path = Path(directory) / 'request.json'
        request_path.write_bytes(request)
        assembly = helper.assemble([*inputs[13:22], request_path])
    validation = helper.strict_json(assembly['assembly-receipt.json'])
    ledger = helper.table(family_payloads[2], LEDGER_COLUMNS)
    projection = [row for row in ledger if row['family_id'] in helper.COUNTS]
    require(len(projection) == 564 and all(row['status'] == 'NOT_ESTIMABLE' and row['p_raw'] == 'NA' and
        row['p_for_adjustment'] == '1' for row in projection), 'Original 564 missing eligibility rows required')
    decisions = helper.table(family_payloads[3])
    require(len(decisions) == 276 and sum(row['overlap_class'] == 'PENDING' for row in decisions) == 275 and
        [row['edge_id'] for row in decisions if row['overlap_class'] == 'O2'] == ['A_X01_M06'],
        'Original 275 unresolved overlap decisions must remain unassigned')
    projection_payload = helper.tsv(projection, LEDGER_COLUMNS)
    names = [*MR_NAMES, *[row[0] for row in FROZEN], *[row[0] for row in helper.SOURCES], 'family.py']
    receipt = dict(schema='FROZEN_A_LEGACY_FAMILY_GATE_RECEIPT_V1',
        scope='FROZEN_LEGACY_A_MR_TO_MISSING_FAMILY_GATE_NOT_RESEARCH', result_exposure='SEEN',
        input_files=[dict(port=index, name=name, bytes=len(data), sha256=helper.checksum(data))
            for index, (name, data) in enumerate(zip(names, payloads, strict=True))],
        MR_lineage=provenance, MR_table_structure=mr_summary, family_source_inputs=family_sources,
        family_counts=helper.COUNTS, family_ids=validation['family_ids'], eligibility_rows=564,
        unresolved_overlap_entries_preserved=275, real_primary_p_values_filled=0, real_overlap_assignments_made=0,
        request=REQUEST, family_validation=validation,
        opaque_RDS=dict(bytes=len(payloads[6]), sha256=helper.checksum(payloads[6]), readRDS_performed=False,
            independent_official_readback_required=True),
        output_sha256={'family-request.json': helper.checksum(request),
            'eligibility-projection.tsv': helper.checksum(projection_payload), 'gate.log': helper.checksum(LOG)},
        MR_estimates_computed=False, official_MR_numerical_equivalence_certified=False,
        primary_estimates_created=False, scientific_authorization_granted=False,
        formal_scientific_pass_granted=False, g0_granted=False)
    return [request, projection_payload, helper.json_bytes(receipt), LOG]


def run(inputs, outputs):
    require(len(inputs) == 23, 'Exactly 23 declared input roles required')
    helper = load_helper(inputs[22])
    before = [helper.identity(path) for path in inputs]
    require(len({record[:2] for record in before}) == 23, 'Input aliases or repeated inodes forbidden')
    parents = helper.preflight_outputs(inputs, outputs)
    payloads = assemble_gate(inputs, helper)
    def unchanged():
        require(before == [helper.identity(path) for path in inputs], 'Gate inputs changed during execution')
    unchanged()
    helper.exclusive_publish(payloads, outputs, parents, unchanged)


def main():
    inputs, outputs = [], []
    try:
        require(len(sys.argv) == 1 and sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 14, 7),
            'Zero-parameter official CPython 3.14.7 runtime required')
        inputs = [Path(os.environ['AUTONOMICS_INPUT' + str(index)]) for index in range(23)]
        outputs = [Path(os.environ['AUTONOMICS_OUTPUT' + str(index)]) for index in range(4)]
        run(inputs, outputs)
    except Exception as error:
        message = 'Frozen A legacy family gate refused: ' + type(error).__name__ + ': ' + str(error) + '\n'
        print(message, file=sys.stderr, end='')
        if len(inputs) == 23 and len(outputs) == 4:
            try:
                helper = load_helper(inputs[22])
                log = outputs[-1]
                require(log not in inputs and not os.path.lexists(log), 'Foreign diagnostic output preserved')
                helper.exclusive_publish([message.encode()], [log], {log: helper.parent_identity(log)})
            except Exception:
                pass
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
