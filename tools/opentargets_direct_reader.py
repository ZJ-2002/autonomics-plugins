"""Offline reader used only by the managed Open Targets direct-file audit."""

from collections import Counter
import json
import math
from pathlib import Path


CONTROL = 'MONDO_0004975'
FIELDS = ['diseaseId', 'targetId', 'aggregationType', 'aggregationValue',
          'associationScore', 'currentNovelty']


def check_control(rows, targets, diseases):
    if not rows or len(diseases) != 1 or diseases[0]['id'] != CONTROL:
        raise RuntimeError('Nonempty control membership and one exact disease annotation required')
    seen = set()
    for row in rows:
        if row['diseaseId'] != CONTROL or not isinstance(row['targetId'], str) or not row['targetId']:
            raise RuntimeError('Control member identity differs')
        identity = row['targetId']
        if identity in seen:
            raise RuntimeError('Duplicate control target must not be silently collapsed')
        seen.add(identity)
        score = row['associationScore']
        novelty = row['currentNovelty']
        if (not isinstance(score, (int, float)) or isinstance(score, bool)
                or not math.isfinite(score) or not 0 <= score <= 1):
            raise RuntimeError('Control association score invalid')
        if novelty is not None and (not isinstance(novelty, (int, float))
                or isinstance(novelty, bool) or not math.isfinite(novelty) or not 0 <= novelty <= 1):
            raise RuntimeError('Control novelty must retain its finite-or-null semantics')
    if seen != set(targets):
        raise RuntimeError('Exact control target annotation membership required')
    for identity, target in targets.items():
        if target['id'] != identity or any(not isinstance(target.get(field), str)
                for field in ['approvedSymbol', 'approvedName', 'biotype']):
            raise RuntimeError('Control target annotation row or string field missing')
    if not isinstance(diseases[0].get('name'), str):
        raise RuntimeError('Control disease name string field missing')
    return len(seen)


def annotation_quality(targets, diseases):
    result = []
    for kind, records, fields in [('target', targets.values(), ['approvedSymbol', 'approvedName', 'biotype']),
                                  ('disease', diseases, ['name'])]:
        for record in records:
            for field in fields:
                value = record[field]
                if not value.strip():
                    result.append(dict(entity=kind, id=record['id'], field=field,
                        state='EMPTY_STRING' if value == '' else 'WHITESPACE_ONLY', original_value=value))
    return result


def compare_api_rows(bulk_rows, bulk_targets, api_rows):
    bulk = {row['targetId']: row for row in bulk_rows}
    if len(bulk) != len(bulk_rows) or set(bulk) != set(bulk_targets):
        raise RuntimeError('Bulk diagnostic reference must have exact unique annotated membership')
    identities = [row['target']['id'] for row in api_rows]
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise RuntimeError('API diagnostic row has no target identity')
    counts = Counter(identities)
    comparisons = []
    for position, api in enumerate(api_rows):
        identity = identities[position]
        reference = bulk.get(identity)
        if reference is None:
            comparisons.append(dict(api_row=position, target_id=identity, in_bulk=False))
            continue
        for value in [api['score'], reference['associationScore']]:
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise RuntimeError('Only finite numeric scores can be compared')
        for value in [api['novelty'], reference['currentNovelty']]:
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)):
                raise RuntimeError('Novelty must retain finite-or-null semantics during comparison')
        for field in ['approvedSymbol', 'approvedName', 'biotype']:
            if not isinstance(api['target'].get(field), str) or not isinstance(bulk_targets[identity].get(field), str):
                raise RuntimeError('Annotation comparison requires original string fields')
        novelty_state = ('BOTH_NULL' if api['novelty'] is None and reference['currentNovelty'] is None else
            'API_NULL_BULK_FINITE' if api['novelty'] is None else
            'BULK_NULL_API_FINITE' if reference['currentNovelty'] is None else 'BOTH_FINITE')
        comparisons.append(dict(api_row=position, target_id=identity, in_bulk=True,
            score_exact=api['score'] == reference['associationScore'],
            score_delta_api_minus_bulk=api['score'] - reference['associationScore'],
            novelty_state=novelty_state, novelty_exact=api['novelty'] == reference['currentNovelty'],
            novelty_delta_api_minus_bulk=(api['novelty'] - reference['currentNovelty'] if novelty_state == 'BOTH_FINITE' else None),
            annotation_exact={field: api['target'][field] == bulk_targets[identity][field]
                for field in ['approvedSymbol', 'approvedName', 'biotype']}))
    matched = [row for row in comparisons if row['in_bulk']]
    finite_novelty = [row for row in matched if row['novelty_state'] == 'BOTH_FINITE']
    summary = dict(status='POINTWISE_BULK_API_DIAGNOSTIC_NOT_SOURCE_EQUIVALENCE',
        bulk_rows=len(bulk_rows), bulk_unique_targets=len(bulk), api_rows=len(api_rows),
        api_unique_targets=len(counts), api_duplicate_occurrences=len(api_rows) - len(counts),
        api_duplicate_target_ids={identity: count for identity, count in sorted(counts.items()) if count > 1},
        bulk_target_ids_missing_from_api=sorted(set(bulk) - set(counts)),
        api_target_ids_not_in_bulk=sorted(set(counts) - set(bulk)), matched_api_rows=len(matched),
        score_exact_rows=sum(row['score_exact'] for row in matched),
        score_maximum_absolute_difference=max((abs(row['score_delta_api_minus_bulk']) for row in matched), default=None),
        novelty_exact_rows=sum(row['novelty_exact'] for row in matched),
        novelty_maximum_absolute_difference=max((abs(row['novelty_delta_api_minus_bulk']) for row in finite_novelty), default=None),
        novelty_null_patterns=dict(Counter(row['novelty_state'] for row in matched)),
        annotation_exact_rows={field: sum(row['annotation_exact'][field] for row in matched)
            for field in ['approvedSymbol', 'approvedName', 'biotype']},
        api_rows_deduplicated_or_reordered=False, bulk_rows_rewritten=False,
        bulk_novelty_assumed_semantically_equal_to_API_novelty=False,
        numeric_tolerance_optimized_or_scientific_equivalence_granted=False,
        current_daemon_verified=False, g0_granted=False)
    return summary, comparisons


def main():
    import pyarrow
    import pyarrow.compute as compute
    import pyarrow.parquet as parquet

    root = Path('/work')
    records = json.loads((root / 'reader-input.json').read_text())
    schemas, census, partitions, rows, targets, diseases = {}, Counter(), [], [], {}, []
    target_ids, disease_ids = set(), set()
    for dataset in ['association_overall_direct', 'target', 'disease']:
        for record in records:
            if record['dataset'] != dataset:
                continue
            source = parquet.ParquetFile(Path('/sources') / record['source_session'] / record['relative_path'])
            schema = source.schema_arrow
            if dataset in schemas and not schema.equals(schemas[dataset], check_metadata=True):
                raise RuntimeError('Partition schema differs within dataset')
            schemas[dataset] = schema
            columns = FIELDS if dataset == 'association_overall_direct' else (
                ['id', 'approvedSymbol', 'approvedName', 'biotype'] if dataset == 'target' else ['id', 'name'])
            observed = 0
            wanted = {row['targetId'] for row in rows}
            for batch in source.iter_batches(batch_size=8192, columns=columns, use_threads=False):
                observed += batch.num_rows
                if dataset == 'association_overall_direct':
                    for field in ['diseaseId', 'targetId', 'aggregationType', 'aggregationValue']:
                        values = batch.column(field)
                        if (not pyarrow.types.is_string(values.type) or values.null_count
                                or compute.any(compute.equal(values, '')).as_py()):
                            raise RuntimeError('Association or aggregation identity missing')
                    grouped = pyarrow.Table.from_batches([batch]).group_by(
                        ['aggregationType', 'aggregationValue'], use_threads=False).aggregate([('targetId', 'count')])
                    for group in grouped.to_pylist():
                        census[(group['aggregationType'], group['aggregationValue'])] += group['targetId_count']
                    rows.extend(batch.filter(compute.equal(batch.column('diseaseId'), CONTROL)).to_pylist())
                else:
                    for row in batch.to_pylist():
                        identities = target_ids if dataset == 'target' else disease_ids
                        identity = row['id']
                        if not isinstance(identity, str) or not identity or identity in identities:
                            raise RuntimeError('Missing or duplicate annotation ID')
                        identities.add(identity)
                        if dataset == 'target' and identity in wanted:
                            targets[identity] = row
                        elif dataset == 'disease' and identity == CONTROL:
                            diseases.append(row)
            if observed != source.metadata.num_rows:
                raise RuntimeError('Complete partition scan differs from Parquet metadata')
            partitions.append(dict(path=record['relative_path'], source_session=record['source_session'],
                                   source_manifest_sha256=record['source_manifest_sha256'],
                                   sha256=record['sha256'], bytes=record['bytes'], rows=observed,
                                   row_groups=source.metadata.num_row_groups))
            source.close()
    with (root / 'scan-observations.json').open('x') as handle:
        json.dump(dict(partitions=partitions,
            aggregation_census=[dict(aggregationType=key[0], aggregationValue=key[1], rows=value)
                for key, value in sorted(census.items())],
            schemas={name: str(schema) for name, schema in schemas.items()},
            control_raw_rows=len(rows), control_annotation_rows=len(targets),
            control_disease_rows=len(diseases), g0_granted=False), handle, indent=2, allow_nan=False)
        handle.write('\n')
    with (root / 'raw-control-observations.json').open('x') as handle:
        json.dump(dict(rows=rows, targets=targets, diseases=diseases), handle, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    count = check_control(rows, targets, diseases)
    control = dict(disease=diseases[0], rows=rows, targets=targets)
    with (root / 'control-members.json').open('x') as handle:
        json.dump(control, handle, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    result = dict(status='ALL_ACQUIRED_PARTITIONS_READ_CONTROL_MEMBERSHIP_AUDITED_NOT_API_EQUIVALENCE',
        pyarrow_version=pyarrow.__version__, control=CONTROL, control_members=count,
        control_target_annotations=len(targets), unique_target_annotations=len(target_ids),
        unique_disease_annotations=len(disease_ids), partitions=partitions,
        control_annotation_quality_observations=annotation_quality(targets, diseases),
        blank_annotation_values_preserved_without_imputation=True,
        scientific_annotation_completeness_or_acceptability_certified=False,
        aggregation_census=[dict(aggregationType=key[0], aggregationValue=key[1], rows=value)
                            for key, value in sorted(census.items())],
        schemas={name: str(schema) for name, schema in schemas.items()},
        schema_equality_checked_for_every_partition=True,
        all_projected_rows_in_every_partition_materialized=True,
        control_duplicate_rows_removed=False, bulk_novelty_assumed_equal_to_API_novelty=False,
        complete_generic_API_or_indirect_or_component_scores_certified=False,
        frozen_source_changed=False, scientific_authorization_granted=False, g0_granted=False)
    with (root / 'reader-verification.json').open('x') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    main()
