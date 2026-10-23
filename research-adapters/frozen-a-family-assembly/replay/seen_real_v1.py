"""Hash-bound already-seen A-family replay, never a primary-result publisher."""

import argparse
import csv
from datetime import date, datetime, timezone
import importlib.util
import json
import io
import os
from pathlib import Path


SPEC = importlib.util.spec_from_file_location('replay_frozen_family', Path(__file__).resolve().parents[1] / 'scripts/family.py')
family = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(family)
SCOPE = 'SEEN_REAL_TECHNICAL_REPLAY_V1_NOT_RESEARCH'
REQUEST = 'SEEN_REAL_A_FAMILY_REPLAY_REQUEST_V1'
STATUSES = {'ESTIMATED', 'NOT_RUN', 'FAILED', 'NOT_ESTIMABLE'}
COLUMNS = ['analysis_id', 'family_id', 'kind', 'scope', 'technical_status', 'replay_p_raw',
    'replay_p_for_adjustment', 'p_primary', 'primary_qualification', 'estimator', 'source_id']
VECTOR_COLUMNS = ['vector_id', 'analysis_id', 'family_id', 'method', 'replay_p_raw', 'replay_p_for_adjustment']


def require(condition, message):
    family.require(condition, message)


def text(value):
    require(isinstance(value, str) and value and len(value) <= 256
            and not any(character in value for character in '\t\r\n\x00'), 'Bounded explicit lexical label required')
    return value


def source_tables(request):
    sources, histories = request['sources'], request['seen_history']
    require(isinstance(sources, list) and 1 <= len(sources) <= 3 and isinstance(histories, list)
            and len(histories) == len(sources), 'One to three explicit seen source identities required')
    by_id, history_by_id = {}, {}
    for history in histories:
        common = {'source_id', 'sha256', 'declaration'}
        exact = common | {'seen_at'}
        bounded = common | {'precision', 'upper_bound_date', 'exact_first_view_known', 'history_file', 'analysis_ids'}
        require(isinstance(history, dict) and set(history) in (exact, bounded)
                and history['declaration'] == 'ALREADY_SEEN_NOT_INDEPENDENT', 'Explicit XOR exact-time or bounded-date prior-view history required')
        identifier = text(history['source_id'])
        require(identifier not in history_by_id, 'Duplicate view history identity')
        evidence = dict(history)
        if set(history) == exact:
            viewed = datetime.fromisoformat(history['seen_at'])
            require(viewed.tzinfo is not None and viewed <= datetime.now(timezone.utc),
                'Prior-view timestamp must have an explicit timezone and cannot be in the future')
        else:
            require(history['precision'] == 'ON_OR_BEFORE_DATE' and history['exact_first_view_known'] is False,
                'Unknown exact first-view time must retain explicit upper-bound precision')
            upper = date.fromisoformat(history['upper_bound_date'])
            require(upper.isoformat() == history['upper_bound_date'] and upper <= datetime.now(timezone.utc).date(),
                'Prior-view upper-bound date cannot be in the future')
            binding = history['history_file']
            require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}, 'Exact original history file identity required')
            history_bytes = family.read(family.ordinary(binding['path']), max_bytes=4 * 1024 * 1024)
            require(family.checksum(history_bytes) == binding['sha256'], 'Original history file bytes changed')
            identifiers = history['analysis_ids']
            require(isinstance(identifiers, list) and identifiers and len(set(identifiers)) == len(identifiers)
                    and all(isinstance(value, str) for value in identifiers), 'Explicit unique history-to-analysis identity mapping required')
            reader = csv.DictReader(io.StringIO(history_bytes.decode(), newline=''), delimiter='\t', strict=True)
            raw_lines = history_bytes.decode().splitlines(keepends=True)
            require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)), 'Unique history column identities required')
            previous = reader.line_num
            originals = []
            for row in reader:
                raw_row = ''.join(raw_lines[previous:reader.line_num])
                previous = reader.line_num
                if row.get('analysis_id') not in identifiers:
                    continue
                require(None not in row and all(value is not None for value in row.values())
                        and row.get('first_result_viewed_at') == 'ON_OR_BEFORE_' + upper.isoformat() + '_EXACT_FIRST_VIEW_UNKNOWN'
                        and row.get('status') == 'LEGACY_PIPELINE_ANALYZED'
                        and row.get('allowed_identity') == 'LEGACY_EXPLORATORY_TECHNICAL_REANALYSIS',
                        'Original history row must explicitly support legacy upper-bound replay identity')
                originals.append(dict(analysis_id=row['analysis_id'], original_row=row,
                    raw_row_utf8=raw_row, raw_row_sha256=family.checksum(raw_row.encode())))
            require(len(originals) == len(identifiers) and {row['analysis_id'] for row in originals} == set(identifiers),
                'Every requested history analysis must have exactly one original row')
            evidence['original_history_rows'] = originals
            evidence['upper_bound_basis'] = 'ANALYSIS_ID_HISTORY_NOT_RESULT_BYTE_FIRST_VIEW'
        history_by_id[identifier] = evidence
    records = []
    for source in sources:
        require(isinstance(source, dict) and set(source) == {'source_id', 'path', 'sha256'}, 'Exact seen source fields required')
        identifier = text(source['source_id'])
        require(identifier not in by_id and identifier in history_by_id
                and history_by_id[identifier]['sha256'] == source['sha256'], 'Source and view-history hashes must agree')
        path = family.ordinary(source['path'])
        payload = family.read(path, max_bytes=4 * 1024 * 1024)
        require(family.checksum(payload) == source['sha256'], 'Already-seen result source bytes changed')
        by_id[identifier] = family.table(payload)
        records.append(dict(source_id=identifier, bytes=len(payload), sha256=source['sha256'],
            history=history_by_id[identifier], declaration='ALREADY_SEEN_NOT_INDEPENDENT'))
    require(set(by_id) == set(history_by_id), 'Every prior-view identity must name an input source')
    return by_id, records


def replay_value(record, sources):
    require(isinstance(record, dict) and set(record) == {'analysis_id', 'status', 'source_id', 'selector', 'p_column', 'estimator'},
        'Exact replay edge fields required; eligibility or primary overrides are forbidden')
    require(record['status'] in STATUSES and record['status'] != 'NOT_RUN', 'Supplied result must distinguish estimated, failed or not estimable')
    identifier = record['source_id']
    require(identifier in sources and isinstance(record['selector'], dict) and record['selector'], 'Explicit source and unique lexical row selector required')
    require(all(isinstance(key, str) and isinstance(value, str) for key, value in record['selector'].items()), 'Selector must use exact lexical cells')
    matches = [row for row in sources[identifier] if all(row.get(key) == value for key, value in record['selector'].items())]
    require(len(matches) == 1, 'Result row selector must match exactly one source row')
    estimator = text(record['estimator'])
    if record['status'] != 'ESTIMATED':
        require(record['p_column'] is None, 'Failed or unestimable rows cannot supply a P column')
        return None, estimator
    column = text(record['p_column'])
    require(column in matches[0] and matches[0][column] not in {'', 'NA', 'NaN', 'nan'}, 'Estimated source probability is missing')
    return family.probability(float(matches[0][column])), estimator


def assemble(frozen_paths, request_path):
    require(len(frozen_paths) == 9, 'Nine frozen source roles required')
    frozen_sources, payloads = family.source_inputs(frozen_paths)
    request_bytes = family.read(family.ordinary(request_path), max_bytes=4 * 1024 * 1024)
    request = family.strict_json(request_bytes)
    require(isinstance(request, dict) and set(request) == {'schema', 'scope', 'sources', 'seen_history', 'edges'}
            and request['schema'] == REQUEST and request['scope'] == SCOPE, 'Exact separate versioned technical replay contract required')
    tables = [family.table(payload) for payload in payloads[:6]]
    edges, paths = tables[:2]
    original = family.helpers(frozen_paths[7])
    ids = family.validate_universe(tables, family.strict_json(payloads[6]), original)
    sources, provenance = source_tables(request)
    supplied = request['edges']
    require(isinstance(supplied, list) and 1 <= len(supplied) <= 3, 'One to three explicitly selected already-seen edge records required')
    by_id = {}
    known = {row['edge_id'] for row in edges}
    for record in supplied:
        identifier = text(record['analysis_id'])
        require(identifier in known and identifier not in by_id, 'Unknown or duplicate frozen edge identity')
        value, estimator = replay_value(record, sources)
        by_id[identifier] = dict(status=record['status'], value=value, estimator=estimator, source_id=record['source_id'])
    require({row['source_id'] for row in supplied} == set(sources), 'Unused or omitted result source identity')
    for provenance_row in provenance:
        declared = provenance_row['history'].get('analysis_ids')
        require(declared is None or set(declared) == {row['analysis_id'] for row in supplied
            if row['source_id'] == provenance_row['source_id']}, 'History analysis identities must exactly match selected source edges')
    rows = []

    def append(identifier, family_id, kind, status, value, estimator, source_id):
        require(status in STATUSES and (status == 'ESTIMATED') == (value is not None), 'Replay status and missingness disagree')
        rows.append(dict(analysis_id=identifier, family_id=family_id, kind=kind, scope=SCOPE,
            technical_status=status, replay_p_raw='NA' if value is None else repr(value),
            replay_p_for_adjustment='1' if value is None else repr(value), p_primary='NA',
            primary_qualification='NOT_EVALUATED_NOT_GRANTED', estimator=estimator, source_id=source_id))

    for edge in edges:
        result = by_id.get(edge['edge_id'], dict(status='NOT_RUN', value=None, estimator='NA', source_id='NA'))
        append(edge['edge_id'], edge['family'], 'EDGE', result['status'], result['value'], result['estimator'], result['source_id'])
    assembled = {row['analysis_id']: row for row in rows}
    for path in paths:
        components = [assembled[path[key]] for key in ['xm_edge_id', 'my_edge_id']]
        values = [None if row['replay_p_raw'] == 'NA' else float(row['replay_p_raw']) for row in components]
        value = family.probability(original['strict_conjunction'](*values))
        require(value == (None if any(item is None for item in values) else max(values)), 'Frozen strict IUT must propagate a missing component')
        statuses = {row['technical_status'] for row in components}
        status = next((candidate for candidate in ['FAILED', 'NOT_RUN', 'NOT_ESTIMABLE'] if candidate in statuses), 'ESTIMATED')
        append(path['path_id'], path['family'], 'PATH', status, value, 'STRICT_IUT_REPLAY', 'NA')
    vectors = []
    for family_id, members in ids.items():
        selected = {row['analysis_id']: row for row in rows if row['family_id'] == family_id}
        for method in ['BH', 'BY'] if family_id.endswith('EDGES') else ['BY']:
            for identifier in members:
                row = selected[identifier]
                vectors.append(dict(vector_id=family_id + '/' + method, analysis_id=identifier, family_id=family_id,
                    method=method, replay_p_raw=row['replay_p_raw'], replay_p_for_adjustment=row['replay_p_for_adjustment']))
    require(len(rows) == 564 and len(vectors) == 840, 'Complete frozen denominators and six correction vectors required')
    assembly_bytes, vector_bytes = family.tsv(rows, COLUMNS), family.tsv(vectors, VECTOR_COLUMNS)
    receipt = dict(schema='SEEN_REAL_A_FAMILY_REPLAY_ASSEMBLY_V1', scope=SCOPE, frozen_source_inputs=frozen_sources,
        family_counts=family.COUNTS, family_ids=ids, sources=provenance, request_sha256=family.checksum(request_bytes),
        output_sha256={'replay-family.tsv': family.checksum(assembly_bytes), 'replay-vectors.tsv': family.checksum(vector_bytes)},
        assembly_rows=564, vector_rows=840, vector_count=6, registered_total_unchanged=696,
        primary_results_published=False, eligibility_receipts_accepted=False, scientific_family_complete=False,
        independent_replication_claimed=False, MR_estimates_computed=False, official_adjustment_performed=False,
        scientific_authorization_granted=False, g0_granted=False)
    return {'replay-family.tsv': assembly_bytes, 'replay-vectors.tsv': vector_bytes,
        'replay-assembly.json': family.json_bytes(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-source', nargs=9, required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    products = assemble(arguments.frozen_source, arguments.request)
    require(arguments.output.is_absolute() and not arguments.output.exists(), 'New isolated replay output directory required')
    arguments.output.mkdir(mode=0o700)
    for name, payload in products.items():
        with os.fdopen(os.open(arguments.output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as handle:
            handle.write(payload)
    print(json.dumps(dict(scope=SCOPE, products=sorted(products), primary_results_published=False, g0_granted=False)))


if __name__ == '__main__':
    main()
