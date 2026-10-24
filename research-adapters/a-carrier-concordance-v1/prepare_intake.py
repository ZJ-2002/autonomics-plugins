import copy
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path


BASE = Path(__file__).resolve().parent
ADAPTERS = BASE.parent
SCHEMA = 'A_X01_M06_PRECISE_INTAKE_DERIVATION_V1'
METHOD = 'Inverse variance weighted'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_rows(payload, exposure, outcome):
    reader = csv.DictReader(io.StringIO(payload.decode()), delimiter='\t', strict=True)
    fields = reader.fieldnames
    require(fields and len(fields) == len(set(fields)) and not {'analysis_id', 'execution_status'} & set(fields), 'Unmodified precise source columns required')
    rows = list(reader)
    require(rows and all(None not in row and all(value is not None for value in row.values()) for row in rows), 'Rectangular complete precise source required')
    require(all(row.get('id.exposure') == exposure and row.get('id.outcome') == outcome and
        row.get('role') == 'EXPLORATORY_OVERLAP_UNRESOLVED' and row.get('p_primary') == 'NA'
        for row in rows), 'Source trait/role identity cannot be reassigned')
    require(sum(row.get('method') == METHOD for row in rows) == 1, 'Exactly one predefined IVW method required')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=[*fields, 'analysis_id', 'execution_status'], delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(dict(row, analysis_id='A_X01_M06', execution_status='ESTIMATED') for row in rows)
    return output.getvalue().encode()


def prepare(study, tsv, rds, export_request, previous_seen_request, output):
    study, output, rds = Path(study).absolute(), Path(output).absolute(), Path(rds).absolute()
    require(output.parent.resolve(strict=True) == output.parent and not output.exists(), 'New canonical output required')
    exporter = load_module('precise_export_for_intake', BASE / 'export_precise.py')
    lock_path = ADAPTERS / 'frozen-a-real-intake-dag-v1/source-lock.json'
    lock_bytes = exporter.source_bytes(lock_path)
    require(sha(lock_bytes) == '1d81133d3ba63e1a156e977c9f1c9cccfa6f25bda59b4559bc4c06ba78b393b3', 'Exact reviewed File bridge source lock required')
    lock = json.loads(lock_bytes)
    for name, record in lock['implementation_files'].items():
        raw = exporter.source_bytes(ADAPTERS / name)
        require(sha(raw) == record['sha256'] and len(raw) == record['bytes'], 'Reviewed intake implementation changed')
    intake = load_module('precise_intake_unchanged', ADAPTERS / 'frozen-a-family-assembly/real-intake-v1/intake.py')
    frozen_paths = [study / name for name, size, digest in intake.family.SOURCES]
    intake.family.source_inputs(frozen_paths)
    decision_files = {}
    for record in lock['decision_files']:
        raw = exporter.source_bytes(study / record['path'])
        require(len(raw) == record['bytes'] and sha(raw) == record['sha256'], 'Frozen decision evidence changed')
        decision_files[record['path']] = dict(bytes=len(raw), sha256=sha(raw))
    card = json.loads(exporter.source_bytes(study / '03_AUDIT/G0_v4.3.2_2026-10-11/A_MINIMUM_INPUT_CARD.json'))
    require(card['X01']['accession'] == 'GCST90652391' and card['M06']['accession'] == 'GCST90002393'
        and card['overlap_class'] == 'O2', 'Exact frozen X01/M06 unresolved-overlap mapping required')
    previous_bytes = exporter.source_bytes(previous_seen_request)
    previous = intake.family.strict_json(previous_bytes)
    require(set(previous) == {'schema', 'scope', 'sources', 'seen_history', 'edges'} and
        previous['schema'] == 'SEEN_REAL_A_FAMILY_REPLAY_REQUEST_V1' and
        previous['scope'] == 'SEEN_REAL_TECHNICAL_REPLAY_V1_NOT_RESEARCH' and
        len(previous['sources']) == len(previous['seen_history']) == len(previous['edges']) == 1,
        'One existing seen technical replay edge required')
    source = previous['sources'][0]
    edge = previous['edges'][0]
    selector = {'id.exposure':card['X01']['accession'], 'id.outcome':card['M06']['accession'], 'method':METHOD}
    require(set(edge) == {'analysis_id', 'status', 'source_id', 'selector', 'p_column', 'estimator'} and
        edge['analysis_id'] == 'A_X01_M06' and edge['status'] == 'ESTIMATED' and edge['selector'] == selector
        and edge['source_id'] == source['source_id'] and edge['p_column'] == 'p_raw_exploratory', 'Explicit historical IVW identity required')
    require(Path(source['path']) == Path(tsv) and source['sha256'] == export_request['tsv_sha256'], 'Prior seen source must be the original export input')
    intake.seen.source_tables(previous)
    precise, export_receipt = exporter.extract(tsv, rds, export_request)
    normalized = normalize_rows(precise, card['X01']['accession'], card['M06']['accession'])
    new_id = 'derived-lossless-X01-M06'
    history = copy.deepcopy(previous['seen_history'][0])
    history.update(source_id=new_id, sha256=sha(normalized))
    require(history.get('analysis_ids') == ['A_X01_M06'] and history.get('precision') == 'ON_OR_BEFORE_DATE', 'Original analysis-level bounded-date history required')
    request = dict(schema=intake.REQUEST, scope=intake.SCOPE,
        sources=[dict(source_id=new_id, path=str(output / 'normalized.tsv'), sha256=sha(normalized))],
        seen_history=[history], edges=[dict(analysis_id='A_X01_M06', status='ESTIMATED', source_id=new_id,
            selector=selector, estimator=METHOD, analysis_id_column='analysis_id', method_column='method',
            status_column='execution_status', p_column='p_raw_exploratory', failure_reason_column=None,
            rds=dict(path=str(Path(rds)), sha256=export_request['rds_sha256']))])
    receipt = dict(schema=SCHEMA, scope='KNOWN_SEEN_O2_TECHNICAL_INTAKE_ONLY',
        created_at=datetime.now(timezone.utc).isoformat(), original_seen_request_sha256=sha(previous_bytes),
        original_seen_request_path=str(previous_seen_request), original_analysis_history=previous['seen_history'][0],
        history_bound_is_analysis_identity_not_new_bytes_creation=True,
        exact_source_lock_sha256=sha(lock_bytes), frozen_decision_files=decision_files,
        conversion=export_receipt, normalized_sha256=sha(normalized), selected_method=METHOD,
        technical_status_basis='SUCCESSFUL_BOUND_OFFICIAL_RESULT_OBJECT_NOT_SIGNIFICANCE_OR_PRIMARY_ELIGIBILITY',
        primary_qualification_granted=False, new_MR_computed=False, scientific_release_granted=False, G0=False)
    output.mkdir(mode=0o700)
    (output / 'precise.tsv').write_bytes(precise)
    (output / 'normalized.tsv').write_bytes(normalized)
    (output / 'request.json').write_bytes(intake.family.json_bytes(request))
    (output / 'derivation.json').write_bytes(intake.family.json_bytes(receipt))
    return intake, frozen_paths, request, receipt
