"""Bounded official Bs preflight; never repairs an old response or author score."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_opentargets_direct_files import read_json, sealed_archive, reader_command
from tools.opentargets_direct_reader import CONTROL


ENDPOINT = 'https://api.platform.opentargets.org/api/v4/graphql'
READER_SESSION = 'fa795578fbbd4a66a5baa37706015064'
READER_SEAL = '569157164c1380bbdcdba63f5ede96053dd877de5c83e34cf97c9378a9c9fbc5'
INDEX_SESSION = '74489fc92b9e41418f0d30edfeb9c6a0'
INDEX_SEAL = 'ea9d2981ab1133a2c10c94f3ccc9ddf2a45e454b01a2aae23ba6c6292b694f64'
MAX_RESPONSE = 16 * 1024**2
MAX_REQUESTS = 4
BATCH_SIZE = 3000
GUARD_COUNT = 12918
META = 'meta { name apiVersion { x y z suffix } dataVersion { year month iteration } }'
FIELDS = 'score novelty target { id approvedSymbol approvedName biotype } datasourceScores { id score } datatypeScores { id score }'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, handle, code, message, headers, new_url):
        return None


def urlopen(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


@contextmanager
def request_deadline():
    if signal.getitimer(signal.ITIMER_REAL) != (0.0,0.0):
        raise RuntimeError('An existing timer cannot be replaced for this technical request')
    def expired(signum, frame):
        raise TimeoutError('Official POST exceeded its 60-second total deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL,60)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def validate_ids(ids, maximum=3000):
    if (not isinstance(ids, list) or not ids or len(ids) > maximum
            or any(not isinstance(identity, str) or len(identity) > 256
                or not re.fullmatch('[A-Za-z0-9_.:-]+', identity) for identity in ids)
            or len(set(ids)) != len(ids)):
        raise RuntimeError('Nonempty bounded unique literal counterpart IDs required')
    return ids


def operation(ids):
    if ids is not None:
        validate_ids(ids)
    declaration = ', $ids: [String!]' if ids is not None else ''
    restriction = 'Bs: $ids, ' if ids is not None else ''
    query = ('query($id: String!, $size: Int!' + declaration + ') { ' + META
        + ' disease(efoId: $id) { id associatedTargets(' + restriction
        + 'enableIndirect: false, page: { index: 0, size: $size }) {'
        + ' count datasources { id weight propagate required } rows { ' + FIELDS + ' } } } }')
    variables = dict(id=CONTROL, size=3000 if ids is not None else 0)
    if ids is not None:
        variables['ids'] = ids
    return dict(query=query, variables=variables)


def settings_identity(values):
    if not isinstance(values, list) or not values:
        raise RuntimeError('Actual nonempty datasource settings required')
    identities = set()
    for value in values:
        identity = value.get('id')
        weight = value.get('weight')
        if (not isinstance(identity, str) or not identity or identity in identities
                or isinstance(weight, bool) or not isinstance(weight, (float, int))
                or not math.isfinite(weight) or not 0 <= weight <= 1
                or type(value.get('propagate')) is not bool or type(value.get('required')) is not bool):
            raise RuntimeError('Datasource setting type, identity or range differs')
        identities.add(identity)
    return sorted(values, key=lambda value: value['id'])


def check_page(response, ids):
    if response.get('errors') or not isinstance(response.get('data'), dict):
        raise RuntimeError('GraphQL success required')
    data = response['data']
    metadata = data['meta']
    if (metadata['apiVersion'] != dict(x='26', y='9', z='0', suffix=None)
            or metadata['dataVersion'] != dict(year='26', month='09', iteration=None)):
        raise RuntimeError('API or data release differs from declared 26.9.0/26.09')
    disease = data['disease']
    if disease['id'] != CONTROL:
        raise RuntimeError('Exact previously seen disease identity required')
    page = disease['associatedTargets']
    count = page['count']
    rows = page['rows']
    if type(count) is not int or count < 0 or not isinstance(rows, list):
        raise RuntimeError('Present nonnegative integer count and rows required')
    settings = settings_identity(page['datasources'])
    if ids is None:
        if count != GUARD_COUNT or rows:
            raise RuntimeError('Unfiltered count changed or zero-size page returned rows')
    else:
        validate_ids(ids)
        if count != len(rows) or count > len(ids):
            raise RuntimeError('Single filtered page not demonstrably complete')
        seen = set()
        for row in rows:
            identity = row['target']['id']
            if identity not in ids or identity in seen:
                raise RuntimeError('Returned target leaked outside Bs or repeated')
            seen.add(identity)
            score, novelty = row['score'], row['novelty']
            if (isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score) or not 0 <= score <= 1):
                raise RuntimeError('Original finite API score required')
            if novelty is not None and (isinstance(novelty, bool) or not isinstance(novelty, (int, float)) or not math.isfinite(novelty)):
                raise RuntimeError('Original nullable novelty required')
            for field in ['approvedSymbol', 'approvedName', 'biotype']:
                if not isinstance(row['target'].get(field), str):
                    raise RuntimeError('Original annotation strings required')
            for field in ['datasourceScores', 'datatypeScores']:
                components = row[field]
                if not isinstance(components, list):
                    raise RuntimeError('Original component score array required')
                component_ids = set()
                for component in components:
                    value = component['score']
                    if (not isinstance(component.get('id'), str) or not component['id']
                            or component['id'] in component_ids or isinstance(value, bool)
                            or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1):
                        raise RuntimeError('Component identity or score differs from contract')
                    component_ids.add(component['id'])
    return metadata, settings, rows


def post(output, position, request):
    write(output / f'request-{position}.json', request)
    time.sleep(2)
    body = json.dumps(request).encode()
    with request_deadline(), urlopen(Request(ENDPOINT, data=body, headers={'Content-Type': 'application/json',
            'Accept-Encoding': 'identity', 'User-Agent': 'autonomics-bounded-official-Bs-preflight/1.0'}), timeout=60) as response:
        payload = response.read(MAX_RESPONSE + 1)
        if (response.status != 200 or response.url != ENDPOINT or len(payload) > MAX_RESPONSE
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise RuntimeError('Exact bounded uncompressed official response required; no retry')
        (output / f'response-{position}.json').write_bytes(payload)
        write(output / f'http-{position}.json', dict(status=response.status, received_url=response.url,
            bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), retries=0))
    result = read_json(output / f'response-{position}.json', MAX_RESPONSE)
    return check_page(result, request['variables'].get('ids'))


def complete_collection(output, candidates):
    validate_ids(candidates, maximum=100000)
    pools = [candidates[start:start+BATCH_SIZE] for start in range(0, len(candidates), BATCH_SIZE)]
    if len(pools) != 5 or len(candidates) != GUARD_COUNT:
        raise RuntimeError('Exactly five predeclared candidate pools for this previously seen control required')
    requests = [operation(None), *[operation(pool) for pool in pools], operation(None)]
    if len(requests) != 7:
        raise RuntimeError('Exactly seven declared POST requests required; no fallback')
    write(output / 'predeclared.json', dict(control=CONTROL, expected_unfiltered_count=GUARD_COUNT,
        candidate_ids_are_not_presumed_exhaustive=True, candidate_ids=candidates,
        candidate_ids_sha256=hashlib.sha256(json.dumps(candidates,separators=(',',':')).encode()).hexdigest(),
        pool_sizes=[len(pool) for pool in pools], maximum_posts=7, minimum_gap_seconds=2,
        maximum_response_bytes=MAX_RESPONSE, request_timeout_seconds=60, stage_deadline_seconds=600,
        retries=0, bulk_scores_not_used=True, frozen_configuration_changed=False, g0_granted=False))
    started = time.monotonic()
    observations, rows, identities = [], [], set()
    for position, request in enumerate(requests):
        if time.monotonic() - started > 600:
            raise RuntimeError('Complete-reference stage deadline exceeded')
        observation = post(output, position, request)
        if observations and observation[:2] != observations[0][:2]:
            raise RuntimeError('Metadata or actual default datasource settings changed')
        observations.append(observation)
        if position not in {0,6}:
            pool = pools[position-1]
            for row in observation[2]:
                identity = row['target']['id']
                if identity not in pool or identity in identities:
                    raise RuntimeError('Original filtered rows leaked or repeated; no deduplication')
                identities.add(identity)
                rows.append(row)
    if len(identities) != GUARD_COUNT or len(rows) != GUARD_COUNT or time.monotonic() - started > 600:
        raise RuntimeError('Independent API filtered union did not close against unfiltered count')
    write(output / 'complete-api-rows.json', rows)
    verification = dict(status='REFERENCE_COMPLETE_NOT_NODE_QUALIFIED', control=CONTROL,
        metadata=observations[0][0], datasource_settings=observations[0][1], requests=7,
        initial_unfiltered_count=GUARD_COUNT, final_unfiltered_count=GUARD_COUNT,
        filtered_counts=[len(observation[2]) for observation in observations[1:6]],
        returned_rows=len(rows), unique_targets=len(identities), original_api_rows_removed=0,
        completeness_established_by_filtered_subset_and_cardinality_not_bulk_prior=True,
        bulk_scores_not_used=True, metadata_and_settings_equal_in_all_seven_responses=True,
        original_offset_failure_or_unknown_worker_success_rewritten=False,
        sdk_or_dag_or_deployment_or_scientific_release_granted=False, g0_granted=False)
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--collect', action='store_true')
    arguments = parser.parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed technical session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / ('opentargets-bs-complete-reference' if arguments.collect else 'opentargets-bs-preflight')
    output.mkdir()
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    sealed = sealed_archive(arguments.archives / READER_SESSION, READER_SEAL, successful=True)
    packet = sealed['archive'] / 'artifacts/permanent/opentargets-direct-membership'
    control = read_json(packet / 'control-members.json', MAX_RESPONSE)
    if arguments.collect:
        verification = complete_collection(output, sorted(control['targets']))
        sealed_archive(arguments.archives / READER_SESSION, READER_SEAL, successful=True)
        verification['sealed_bulk_key_reference_rehashed_before_and_after'] = True
        write(output / 'verification.json', verification)
        print('SEVEN_POST_REFERENCE_COMPLETE; ORIGINAL_API_VALUES_PRESERVED; NODE_NOT_QUALIFIED; G0=false')
        return
    index_archive = sealed_archive(arguments.archives / INDEX_SESSION, INDEX_SEAL, successful=True)
    index = read_json(index_archive['archive'] / 'artifacts/permanent/opentargets-direct-continuation/complete-file-index.json')
    sources = {}
    target_records = [row for row in index['files'] if row['dataset'] == 'target']
    for row in target_records:
        session = row['source_session']
        if session not in sources:
            sources[session] = sealed_archive(arguments.archives / session, row['source_manifest_sha256'])
    write(output / 'target-input.json', target_records)
    code = '''import json,pathlib,pyarrow.parquet as pq
root=pathlib.Path('/work');ids=[]
for record in json.loads((root/'target-input.json').read_text()):
 source=pq.ParquetFile(pathlib.Path('/sources')/record['source_session']/record['relative_path'])
 for batch in source.iter_batches(columns=['id'],use_threads=False):ids.extend(batch.column('id').to_pylist())
assert len(ids)==78733 and len(set(ids))==len(ids)
(root/'target-universe.json').write_text(json.dumps(sorted(ids)))
'''
    (output / 'reader.py').write_text(code)
    command = reader_command(output, sources)
    with (output / 'reader.stdout').open('x') as stdout, (output / 'reader.stderr').open('x') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120)
    if result.returncode:
        raise RuntimeError('Sealed full target-ID universe could not be read')
    universe = read_json(output / 'target-universe.json', MAX_RESPONSE)
    positives = sorted(control['targets'])
    negative = next(identity for identity in universe if identity not in control['targets'])
    pools = [[positives[0], positives[1], negative], [positives[0], negative]]
    for pool in pools:
        validate_ids(pool)
    write(output / 'predeclared.json', dict(control=CONTROL, maximum_posts=MAX_REQUESTS,
        maximum_response_bytes=MAX_RESPONSE, minimum_gap_seconds=2, per_request_seconds=60,
        stage_deadline_seconds=600, expected_unfiltered_count=GUARD_COUNT,
        expected_api_version='26.9.0', expected_data_version='26.09', pools=pools,
        negative_is_absent_from_bulk_not_presumed_absent_from_api=True,
        nonempty_filter_required=True, retries=0, freeze_or_default_weights_changed=False,
        old_api_failure_not_rewritten=True, g0_granted=False))
    started = time.monotonic()
    requests = [operation(None), *[operation(pool) for pool in pools], operation(None)]
    observations = []
    for position, request in enumerate(requests):
        if time.monotonic() - started > 600:
            raise RuntimeError('Predeclared stage deadline exceeded')
        observations.append(post(output, position, request))
    if any(observation[:2] != observations[0][:2] for observation in observations[1:]):
        raise RuntimeError('API metadata or actual datasource settings changed')
    shared = positives[0]
    pair = [next(row for row in observation[2] if row['target']['id'] == shared) for observation in observations[1:3]]
    def normalized(row):
        value = dict(row)
        for field in ['datasourceScores', 'datatypeScores']:
            value[field] = sorted(row[field], key=lambda component: component['id'])
        return value
    exact = normalized(pair[0]) == normalized(pair[1])
    verification = dict(status='BOUNDED_BS_PREFLIGHT_OBSERVED_NOT_COMPLETE_COLLECTION',
        requests=len(requests), metadata=observations[0][0], datasource_settings=observations[0][1],
        filtered_counts=[len(observation[2]) for observation in observations[1:3]],
        overlapping_target=shared, overlapping_original_row_exact=exact,
        overlapping_score_exact=pair[0]['score'] == pair[1]['score'],
        overlapping_score_absolute_difference=abs(pair[0]['score'] - pair[1]['score']),
        overlapping_novelty_exact=pair[0]['novelty'] == pair[1]['novelty'],
        raw_api_rows_preserved=True, no_bulk_scores_used=True,
        source_completeness_or_dag_or_production_certified=False, g0_granted=False)
    write(output / 'verification.json', verification)
    for session, source in sources.items():
        sealed_archive(arguments.archives / session, source['session']['manifest_sha256'])
    sealed_archive(arguments.archives / READER_SESSION, READER_SEAL, successful=True)
    sealed_archive(arguments.archives / INDEX_SESSION, INDEX_SEAL, successful=True)
    if not exact:
        raise RuntimeError('Original API numerical/control row changed across nonempty Bs pools')
    print('FOUR_POST_BS_PREFLIGHT_COMPLETE; FULL_COLLECTION_NOT_RUN; G0=false')


if __name__ == '__main__':
    main()
