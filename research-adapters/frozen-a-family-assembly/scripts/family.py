import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import types


SOURCES = [
    ('01_REGISTRIES/GENETIC_EDGE_UNIVERSE.tsv', 58452, '1952fd61e3404364b6bef12334e9743e97f418f80f16ffabd93b4b244473afb4'),
    ('01_REGISTRIES/GENETIC_PATH_UNIVERSE.tsv', 56329, 'bdb85f7ab874d2f2d913c75a2eeb60e56bc0b6049472eeb7f45c764b6eaaa1f2'),
    ('01_REGISTRIES/G0_LOCKED_HYPOTHESIS_UNIVERSE.tsv', 11740332, 'b8d7116aea0640f3677b72eb653b097c7ff2a7d4e7815819d9927b61790b782a'),
    ('01_REGISTRIES/PRIMARY_P_DECISION_REGISTER.tsv', 21306, '92a49ae782060a6eb51fcc2d2bde65629f599714facbcb0ebefa53ea155f9f6a'),
    ('01_REGISTRIES/FAMILY_LOCK_REGISTER.tsv', 1907, 'd7d1a89589fba8f8d115c0eefc9cfd4d270f2216181c70f9c528c4c1da9209c3'),
    ('01_REGISTRIES/MULTIPLICITY_REGISTER.tsv', 6325, 'b66a8b849068a695d65d90decad99229d8a10fe49213d4445d0dfe356f47fee6'),
    ('02_EXECUTION/EXECUTION_RULES_v4.3.2.json', 13853, '1ff187d5672c0448db193db4acb17ee78012ed2588f94bac580075b1cef2245b'),
    ('02_EXECUTION/execution_utils.py', 5243, '2dd34cf6887e829334c2b3ba49f58be5c81b503333dc9183474208ebab49f08d'),
    ('02_EXECUTION/g0_v432_methods.R', 20329, 'f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd'),
]
COUNTS = dict(A_PRIMARY_EDGES=88, A_EXPANDED_EDGES=188, A_PRIMARY_PATHS=36, A_EXPANDED_PATHS=252)
SYNTHETIC = 'SYNTHETIC_NOT_RESEARCH'
LEDGER = 'FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH'
FUNCTIONS = ['primary_p', 'strict_conjunction', 'assert_locked_ids']
ASSEMBLY_COLUMNS = ['analysis_id', 'family_id', 'scope', 'scenario', 'p_raw', 'primary_method', 'reason']
VECTOR_COLUMNS = ['vector_id', 'analysis_id', 'p_raw', 'method']
ASSEMBLE_OUTPUTS = ['assembly.tsv', 'vectors.tsv', 'assembly-receipt.json', 'assembly.log']
PUBLISH_OUTPUTS = ['family.tsv', 'family-vectors.tsv', 'family-audit.json', 'family.log']
DEFINITION_SHA = '2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd'
AUTHORITY = dict(MR_estimates_computed=False, scientific_authorization_granted=False, g0_granted=False)
REQUEST_MAX_BYTES = 4 * 1024**2
PUBLISH_MAX_BYTES = [8 * 1024**2, 8 * 1024**2, 4 * 1024**2, 8 * 1024**2,
    32 * 1024**2, 4 * 1024**2, 8 * 1024**2, 8 * 1024**2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(payload):
    return hashlib.sha256(payload).hexdigest()


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    def real(value):
        number = float(value)
        require(math.isfinite(number), 'Nonfinite JSON number')
        return number
    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant, parse_float=real)


def ordinary(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in [path, *path.parents]) and
        stat.S_ISREG(path.lstat().st_mode), 'Unaliased regular input required')
    return path


def identity(path):
    value = ordinary(path).stat()
    return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def read(path, expected_size=None, max_bytes=32 * 1024**2):
    before = identity(path)
    require(type(max_bytes) is int and max_bytes > 0 and before[3] <= max_bytes,
        'Input exceeds its bounded byte budget')
    require(expected_size is None or (type(expected_size) is int and expected_size >= 0 and before[3] == expected_size),
        'Frozen input size differs before reading payload')
    limit = max_bytes if expected_size is None else expected_size
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    with path.open('rb') as handle:
        require(signature(os.fstat(handle.fileno())) == before, 'Input changed before reading payload')
        data = handle.read(limit + 1)
        require(signature(os.fstat(handle.fileno())) == before, 'Input changed while reading')
    require(identity(path) == before and len(data) == before[3], 'Input changed while reading')
    return data


def table(payload, columns=None):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8'), newline=''), delimiter='\t', strict=True)
    rows = list(reader)
    require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
        (columns is None or reader.fieldnames == columns) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows),
        'Complete rectangular TSV with exact columns required')
    return rows


def tsv(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def probability(value):
    require(value is None or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1),
        'Probability must be null or a finite numeric value in [0,1], never boolean')
    return value


def scope_scenario(scope, scenario):
    require((scope == SYNTHETIC and scenario in {'BOUNDARY', 'INTERIOR'}) or
        (scope == LEDGER and scenario == 'REAL_FROZEN_NA_LEDGER'), 'Explicit compatible technical scope and scenario required')


def hypotheses(edges, paths):
    return [dict(analysis_id=row['edge_id'], family_id=row['family']) for row in edges] + [
        dict(analysis_id=row['path_id'], family_id=row['family']) for row in paths]


def family_ids(edges, paths):
    rows = hypotheses(edges, paths)
    require(len(rows) == sum(COUNTS.values()) and len({row['analysis_id'] for row in rows}) == len(rows),
        'Complete unique frozen hypothesis universe required')
    result = {family: [row['analysis_id'] for row in rows if row['family_id'] == family] for family in COUNTS}
    require({family: len(values) for family, values in result.items()} == COUNTS and
        all(row['family_id'] in COUNTS for row in rows), 'Four complete frozen family denominators required')
    return result


def helpers(path):
    path = ordinary(path)
    payload = read(path, expected_size=SOURCES[7][1])
    require(checksum(payload) == SOURCES[7][2], 'Frozen original helper source identity differs')
    module = types.ModuleType('frozen_a_family_original_helpers')
    module.__file__ = str(path)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    return {name: getattr(module, name) for name in FUNCTIONS}


def source_inputs(paths):
    require(len(paths) == 9, 'Exactly nine frozen source roles required')
    records, payloads = [], []
    for port, (path, (name, size, sha)) in enumerate(zip(paths, SOURCES, strict=True)):
        payload = read(path, expected_size=size)
        require(len(payload) == size and checksum(payload) == sha, 'Frozen source identity differs: ' + name)
        records.append(dict(port=port, name=name, bytes=size, sha256=sha))
        payloads.append(payload)
    return records, payloads


def validate_universe(tables, rules, original):
    edges, paths, ledger, decisions, locks, multiplicity = tables
    ids = family_ids(edges, paths)
    edge_ids = [row['edge_id'] for row in edges]
    original['assert_locked_ids'](edge_ids, [row['edge_id'] for row in decisions])
    for family in COUNTS:
        original['assert_locked_ids'](ids[family], [row['analysis_id'] for row in ledger if row['family_id'] == family])
        locked = [row for row in locks if row['family_id'] == family]
        corrected = [row for row in multiplicity if row['family_id'] == family]
        require(len(locked) == len(corrected) == 1 and locked[0]['status'] == 'LOCKED' and
            int(locked[0]['n_tests']) == int(corrected[0]['locked_count']) == COUNTS[family], 'Frozen family lock differs')
    known = set(edge_ids)
    require(all(all(row[key] in known for key in ['xm_edge_id', 'my_edge_id', 'xy_edge_id']) and
        row['test'] == 'max(p_XM,p_MY)' and row['correction'] == 'BY' and
        row['select_by_pairwise_significance'] == row['product_p_can_promote'] == 'NO' for row in paths),
        'Unselected strict-IUT frozen dependency contract required')
    require({family: rules['planned_counts'][family] for family in COUNTS} == COUNTS and
        rules['planned_counts']['A_MVP_BRIDGE'] == 11, 'Frozen counts including disabled separate MVP scope required')
    return ids


def vector_rows(rows):
    result = []
    for family in COUNTS:
        selected = [row for row in rows if row['family_id'] == family]
        for method in ['BH', 'BY'] if family.endswith('EDGES') else ['BY']:
            for row in selected:
                result.append(dict(vector_id='/'.join([row['scope'], row['scenario'], family, method]),
                    analysis_id=row['analysis_id'], p_raw=row['p_raw'], method=method))
    return result


def assemble(paths):
    require(len(paths) == 10, 'Assemble requires nine frozen sources and one technical request')
    sources, payloads = source_inputs(paths[:9])
    request_payload = read(paths[9], max_bytes=REQUEST_MAX_BYTES)
    request = strict_json(request_payload)
    require(isinstance(request, dict) and set(request) == {'schema', 'scope', 'scenario', 'edges'} and
        request['schema'] == 'FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1', 'Exact technical request schema and keys required')
    scope, scenario = request['scope'], request['scenario']
    scope_scenario(scope, scenario)
    tables = [table(payloads[index]) for index in range(6)]
    edges, paths_table, ledger, decisions, locks, multiplicity = tables
    rules = strict_json(payloads[6])
    original = helpers(paths[7])
    ids = validate_universe(tables, rules, original)
    rows = []
    if scope == LEDGER:
        require(request['edges'] == [], 'Frozen ledger transport cannot accept invented edge eligibility or P values')
        selected = {row['analysis_id']: row for row in ledger if row['family_id'] in COUNTS}
        for hypothesis in hypotheses(edges, paths_table):
            row = selected[hypothesis['analysis_id']]
            require(row['status'] == 'NOT_ESTIMABLE' and row['p_raw'] == 'NA' and row['p_for_adjustment'] == '1',
                'Only frozen NOT_ESTIMABLE/NA/1 mechanical ledger transport allowed')
            rows.append(dict(**hypothesis, scope=scope, scenario=scenario, p_raw='NA', primary_method='NA', reason='NOT_ESTIMABLE'))
    else:
        supplied = request['edges']
        require(isinstance(supplied, list), 'Explicit complete synthetic edge records required')
        original['assert_locked_ids']([row['analysis_id'] for row in supplied], [row['edge_id'] for row in edges])
        by_id = {row['analysis_id']: row for row in supplied}
        for edge in edges:
            row = by_id[edge['edge_id']]
            require(set(row) == {'analysis_id', 'family_id', 'scope', 'scenario', 'overlap_class', 'usual_eligible',
                'mrlap_eligible', 'ivw_p', 'mrlap_p'} and row['family_id'] == edge['family'] and
                row['scope'] == scope and row['scenario'] == scenario and row['overlap_class'] in {'O0', 'O1', 'O2', 'O3'} and
                type(row['usual_eligible']) is bool and type(row['mrlap_eligible']) is bool,
                'Exact synthetic eligibility, scope, family and scenario required')
            probability(row['ivw_p'])
            probability(row['mrlap_p'])
            selected = original['primary_p'](row['overlap_class'], row['ivw_p'], row['mrlap_p'],
                usual_eligible=row['usual_eligible'], mrlap_eligible=row['mrlap_eligible'], rules=rules)
            value = probability(selected['p'])
            rows.append(dict(analysis_id=edge['edge_id'], family_id=edge['family'], scope=scope, scenario=scenario,
                p_raw='NA' if value is None else repr(value), primary_method=selected['method'], reason=selected['reason']))
        by_id = {row['analysis_id']: row for row in rows}
        for path in paths_table:
            first = by_id[path['xm_edge_id']]['p_raw']
            second = by_id[path['my_edge_id']]['p_raw']
            first, second = [None if value == 'NA' else float(value) for value in [first, second]]
            value = probability(original['strict_conjunction'](first, second))
            require(value == (None if first is None or second is None else max(first, second)), 'Strict IUT must propagate missing components')
            rows.append(dict(analysis_id=path['path_id'], family_id=path['family'], scope=scope, scenario=scenario,
                p_raw='NA' if value is None else repr(value), primary_method='STRICT_IUT',
                reason='MISSING_COMPONENT' if value is None else 'COMPLETE_COMPONENTS'))
    vectors = vector_rows(rows)
    assembly_payload, vectors_payload = tsv(rows, ASSEMBLY_COLUMNS), tsv(vectors, VECTOR_COLUMNS)
    receipt = dict(schema='FROZEN_A_FAMILY_ASSEMBLY_RECEIPT_V1', scope=scope, scenario=scenario,
        source_inputs=sources, family_counts=COUNTS, family_ids=ids,
        output_sha256={'assembly.tsv': checksum(assembly_payload), 'vectors.tsv': checksum(vectors_payload)},
        assembly_rows=len(rows), vector_rows=len(vectors), vector_count=6, raw_missing_preserved=True,
        original_python_functions=FUNCTIONS, original_python_sha256=SOURCES[7][2], request_sha256=checksum(request_payload),
        official_adjustment_performed=False, **AUTHORITY)
    return dict(zip(ASSEMBLE_OUTPUTS, [assembly_payload, vectors_payload, json_bytes(receipt),
        b'Technical assembly only; no adjustment, MR, scientific authorization or G0.\n'], strict=True))


def validate_assembly(assembly, vectors, receipt, edges, paths):
    expected_keys = {'schema', 'scope', 'scenario', 'source_inputs', 'family_counts', 'family_ids', 'output_sha256',
        'assembly_rows', 'vector_rows', 'vector_count', 'raw_missing_preserved', 'original_python_functions',
        'original_python_sha256', 'request_sha256', 'official_adjustment_performed', *AUTHORITY}
    require(isinstance(receipt, dict) and set(receipt) == expected_keys and
        receipt['schema'] == 'FROZEN_A_FAMILY_ASSEMBLY_RECEIPT_V1', 'Exact assembly receipt schema required')
    scope_scenario(receipt['scope'], receipt['scenario'])
    require(receipt['source_inputs'] == [dict(port=index, name=name, bytes=size, sha256=sha)
        for index, (name, size, sha) in enumerate(SOURCES)] and receipt['family_counts'] == COUNTS and
        receipt['family_ids'] == family_ids(edges, paths) and receipt['raw_missing_preserved'] is True and
        receipt['original_python_functions'] == FUNCTIONS and receipt['original_python_sha256'] == SOURCES[7][2] and
        receipt['official_adjustment_performed'] is False and all(receipt[key] is False for key in AUTHORITY) and
        isinstance(receipt['request_sha256'], str) and len(receipt['request_sha256']) == 64 and
        all(character in '0123456789abcdef' for character in receipt['request_sha256']), 'Assembly provenance or authority differs')
    require(receipt['output_sha256'] == {'assembly.tsv': checksum(assembly), 'vectors.tsv': checksum(vectors)},
        'Assembly or vector bytes differ from their producer receipt')
    rows = table(assembly, ASSEMBLY_COLUMNS)
    expected = hypotheses(edges, paths)
    require(len(rows) == sum(COUNTS.values()) and
        [(row['analysis_id'], row['family_id']) for row in rows] == [(row['analysis_id'], row['family_id']) for row in expected],
        'Complete frozen IDs, order and families required')
    for row in rows:
        require(row['scope'] == receipt['scope'] and row['scenario'] == receipt['scenario'], 'Mixed technical scope/scenario')
        if row['p_raw'] != 'NA':
            probability(float(row['p_raw']))
        require(row['primary_method'] and row['reason'], 'Original primary method and missing reason required')
        if receipt['scope'] == LEDGER:
            require(row['p_raw'] == 'NA' and row['primary_method'] == 'NA' and row['reason'] == 'NOT_ESTIMABLE',
                'Mechanical ledger scope must remain entirely NOT_ESTIMABLE')
    vector_values = table(vectors, VECTOR_COLUMNS)
    require(vector_values == vector_rows(rows) and type(receipt['assembly_rows']) is int and receipt['assembly_rows'] == len(rows) and
        type(receipt['vector_rows']) is int and receipt['vector_rows'] == len(vector_values) and
        type(receipt['vector_count']) is int and receipt['vector_count'] == 6, 'Every original complete correction vector required')
    return rows, vector_values


def publish(paths):
    require(len(paths) == 8, 'Publish requires exactly eight producer/R/registry inputs')
    data = [read(path, expected_size=SOURCES[port - 6][1] if port >= 6 else None, max_bytes=PUBLISH_MAX_BYTES[port])
        for port, path in enumerate(paths)]
    for port, index in [(6, 0), (7, 1)]:
        require(len(data[port]) == SOURCES[index][1] and checksum(data[port]) == SOURCES[index][2], 'Original registry identity differs')
    receipt = strict_json(data[2])
    rows, vectors = validate_assembly(data[0], data[1], receipt, table(data[6]), table(data[7]))
    official = strict_json(data[5])
    expected = dict(schema='FROZEN_A_OFFICIAL_ADJUSTMENT_RECEIPT_V1', scope=receipt['scope'], scenario=receipt['scenario'],
        input_sha256={'vectors.tsv': checksum(data[1]), 'assembly.tsv': checksum(data[0]),
            'assembly-receipt.json': checksum(data[2]), 'g0_v432_methods.R': SOURCES[8][2]},
        output_sha256={'adjusted.tsv': checksum(data[3]), 'adjustment.RDS': checksum(data[4])},
        R_version='4.6.1', stats_version='4.6.1', adjustment_definition_sha256=DEFINITION_SHA,
        vector_count=6, rows=len(vectors), family_counts=COUNTS, official_function='stats::p.adjust',
        invocation='adjust_full(p, method)', missing_for_adjustment=1, **AUTHORITY)
    require(isinstance(official, dict) and set(official) == set(expected) and official == expected and
        all(official[key] is False for key in AUTHORITY) and
        all(type(official[key]) is int for key in ['vector_count', 'rows', 'missing_for_adjustment']),
        'Exact official R/stats receipt, source definition, output hashes and false authority required')
    require(bool(data[4]), 'Official RDS artifact must not be empty')
    adjusted = table(data[3], [*VECTOR_COLUMNS, 'q'])
    require(len(adjusted) == len(vectors) and
        all({key: row[key] for key in VECTOR_COLUMNS} == original for row, original in zip(adjusted, vectors, strict=True)),
        'Official adjusted output must preserve all complete vector IDs/order/raw probabilities')
    lookup = {}
    for row in adjusted:
        probability(float(row['q']))
        require(row['p_raw'] != 'NA' or float(row['q']) == 1, 'Missing-probability adjustment placeholder must retain q=1')
        key = row['vector_id'], row['analysis_id']
        require(key not in lookup, 'Duplicate official correction row')
        lookup[key] = row['q']
    output_rows = []
    for row in rows:
        prefix = '/'.join([row['scope'], row['scenario'], row['family_id']])
        output_rows.append(dict(**row, p_for_adjustment='1' if row['p_raw'] == 'NA' else row['p_raw'],
            q_BH=lookup[(prefix + '/BH', row['analysis_id'])] if row['family_id'].endswith('EDGES') else 'NA',
            q_BY=lookup[(prefix + '/BY', row['analysis_id'])], family_n=COUNTS[row['family_id']]))
    family = tsv(output_rows, [*ASSEMBLY_COLUMNS, 'p_for_adjustment', 'q_BH', 'q_BY', 'family_n'])
    audit = dict(schema='FROZEN_A_FAMILY_PUBLICATION_AUDIT_V1', scope=receipt['scope'], scenario=receipt['scenario'],
        family_counts=COUNTS, family_ids=receipt['family_ids'], assembly_rows=len(rows), vector_rows=len(vectors), vector_count=6,
        input_sha256={name: checksum(payload) for name, payload in zip(
            ['assembly.tsv', 'vectors.tsv', 'assembly-receipt.json', 'adjusted.tsv', 'adjustment.RDS',
             'adjustment-receipt.json', 'GENETIC_EDGE_UNIVERSE.tsv', 'GENETIC_PATH_UNIVERSE.tsv'], data, strict=True)},
        output_sha256={'family.tsv': checksum(family), 'family-vectors.tsv': checksum(data[3])},
        official_adjustment_receipt=official, Python_q_recomputation_performed=False, RDS_parsed_in_Python=False,
        raw_missing_preserved=True, missing_placeholder_used_only_for_adjustment=True, **AUTHORITY)
    return dict(zip(PUBLISH_OUTPUTS, [family, data[3], json_bytes(audit),
        b'Official R q values transported without Python adjustment; technical scope only, not G0.\n'], strict=True))


def parent_identity(path):
    parent = path.parent
    require(parent.is_dir() and parent.resolve(strict=True) == parent and
        not any(item.is_symlink() for item in [parent, *parent.parents]), 'Unaliased existing output parent required')
    value = parent.stat()
    return value.st_dev, value.st_ino, value.st_mode


def preflight_outputs(inputs, outputs):
    require(len(outputs) == 4 and len(set(outputs)) == 4, 'Four distinct output ports required')
    require(all(path.is_absolute() and path not in inputs for path in outputs), 'Output aliases an input or is not absolute')
    parents = {path: parent_identity(path) for path in outputs}
    require(all(not os.path.lexists(path) for path in outputs), 'Existing or foreign output must never be overwritten')
    return parents


def owned_content(path, owned):
    try:
        value = path.lstat()
        require(stat.S_ISREG(value.st_mode) and (value.st_dev, value.st_ino, value.st_size) ==
            (owned['device'], owned['inode'], owned['bytes']), 'Owned inode or size differs')
        signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        with path.open('rb') as handle:
            before = os.fstat(handle.fileno())
            require(signature(before) == signature(value), 'Owned file changed before hashing')
            payload = handle.read(owned['bytes'] + 1)
            require(signature(os.fstat(handle.fileno())) == signature(before), 'Owned file changed while hashing')
        return signature(path.lstat()) == signature(value) and len(payload) == owned['bytes'] and checksum(payload) == owned['sha256']
    except (OSError, ValueError):
        return False


def unlink_owned(path, owned):
    if owned_content(path, owned):
        path.unlink()
        return True
    return False


def exclusive_publish(payloads, outputs, parents, postcheck=None):
    staged, linked = [], []
    try:
        for path, payload in zip(outputs, payloads, strict=True):
            require(parent_identity(path) == parents[path], 'Output parent identity changed')
            descriptor, filename = tempfile.mkstemp(prefix='.frozen-a-family-', dir=path.parent)
            temporary = Path(filename)
            value = os.fstat(descriptor)
            owned = dict(device=value.st_dev, inode=value.st_ino, bytes=len(payload), sha256=checksum(payload))
            staged.append((temporary, owned))
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for path, (temporary, owned) in zip(outputs, staged, strict=True):
            require(parent_identity(path) == parents[path], 'Output parent changed before publication')
            require(owned_content(temporary, owned), 'Staged output content or inode changed before publication')
            os.link(temporary, path)
            linked.append((path, owned))
            require(owned_content(path, owned), 'Published output replaced by foreign inode or content')
        for path, owned in linked:
            require(owned_content(path, owned), 'Published output changed during publication')
        if postcheck is not None:
            postcheck()
        for temporary, owned in staged:
            require(unlink_owned(temporary, owned), 'Staged output changed before owned temporary retirement')
        for path, owned in linked:
            require(owned_content(path, owned), 'Published output changed during temporary retirement')
    except BaseException:
        for path, owned in reversed(linked):
            unlink_owned(path, owned)
        raise
    finally:
        for path, owned in staged:
            unlink_owned(path, owned)


def run(mode, inputs, outputs):
    names = ASSEMBLE_OUTPUTS if mode == 'assemble' else PUBLISH_OUTPUTS
    require(mode in {'assemble', 'publish'}, 'Explicit assemble or publish mode required')
    before = [identity(path) for path in inputs]
    parents = preflight_outputs(inputs, outputs)
    result = assemble(inputs) if mode == 'assemble' else publish(inputs)
    require(set(result) == set(names) and before == [identity(path) for path in inputs], 'Input identities changed or incomplete output bundle')
    def unchanged():
        require(before == [identity(path) for path in inputs], 'Input identities changed during publication')
    exclusive_publish([result[name] for name in names], outputs, parents, unchanged)


def main():
    mode = os.environ.get('FROZEN_A_FAMILY_MODE')
    inputs, outputs = [], []
    try:
        outputs = [Path(os.environ['AUTONOMICS_OUTPUT' + str(index)]) for index in range(4)]
        require(mode in {'assemble', 'publish'} and len(sys.argv) == 1, 'Zero-parameter explicit family mode required')
        inputs = [Path(os.environ['AUTONOMICS_INPUT' + str(index)]) for index in range(10 if mode == 'assemble' else 8)]
        require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 14, 7), 'Official CPython 3.14.7 required')
        run(mode, inputs, outputs)
    except Exception as error:
        message = 'Frozen A family refused: ' + type(error).__name__ + ': ' + str(error) + '\n'
        print(message, file=sys.stderr, end='')
        if len(outputs) == 4:
            try:
                log = outputs[-1]
                require(log not in inputs and not os.path.lexists(log), 'Foreign diagnostic output preserved')
                exclusive_publish([message.encode()], [log], {log: parent_identity(log)})
            except Exception:
                pass
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
