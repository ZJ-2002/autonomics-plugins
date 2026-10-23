"""Real A-result intake candidate, with frozen pending primary decisions preserved."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('real_intake_seen_history', BASE / 'replay/seen_real_v1.py')
seen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seen)
family = seen.family
require = family.require
SCOPE = 'A_REAL_INPUT_CANDIDATE_V1_QUALIFICATION_PENDING'
REQUEST = 'A_REAL_INPUT_REQUEST_V1'
COLUMNS = ['analysis_id', 'family_id', 'kind', 'scope', 'execution_status', 'observed_p', 'p_primary',
           'p_for_adjustment', 'primary_method', 'primary_qualification', 'source_id', 'estimator', 'component_ids']
VECTOR_COLUMNS = ['vector_id', 'analysis_id', 'family_id', 'method', 'p_primary', 'p_for_adjustment']


def binding(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'Exact artifact path/SHA identity required')
    payload = family.read(family.ordinary(value['path']), max_bytes=32 * 1024**2)
    require(payload and family.checksum(payload) == value['sha256'], 'Result artifact bytes changed')
    return dict(path=value['path'], sha256=value['sha256'], bytes=len(payload))


def pending_decision(row):
    # 当前冻结登记未授予任何逐边资格；不能把调用者声明变成科学签署。
    expected = dict(overlap_class='PENDING', evidence_file='', usual_MR_eligible='PENDING',
        MRlap_applicability='PENDING', diagnostics_file='', primary_p_source='UNASSIGNED',
        p_primary='', ivw_parallel='IF_ESTIMABLE', method_selected_from_p='NO', status='NOT_FROZEN')
    if row.get('edge_id') == 'A_X01_M06':
        expected.update(overlap_class='O2', evidence_file='03_AUDIT/G0_v4.3.2_2026-10-11/A_MINIMUM_INPUT_CARD.json',
            usual_MR_eligible='INPUTS_QUALIFIED;OVERLAP_UNRESOLVED', MRlap_applicability='NOT_QUALIFIED_NOT_ENABLED',
            diagnostics_file='03_AUDIT/G0_v4.3.2_2026-10-11/A_HARMONIZATION_QUALIFICATION.json',
            primary_p_source='NA', p_primary='NA', ivw_parallel='EXPLORATORY_ONLY', status='LOCKED_O2_PRIMARY_NA')
    require(set(row) == {'edge_id', *expected} and all(row[key] == value for key, value in expected.items()),
        'Primary decision is outside the exact current pending register; new scientific admission requires a versioned contract')
    return 'OVERLAP_UNRESOLVED' if row['overlap_class'] == 'O2' else 'PRIMARY_QUALIFICATION_MISSING'


def assemble(frozen_paths, request_path):
    frozen, payloads = family.source_inputs(frozen_paths)
    tables = [family.table(payload) for payload in payloads[:6]]
    edges, paths, unused, decisions, unused2, unused3 = tables
    original = family.helpers(frozen_paths[7])
    ids = family.validate_universe(tables, family.strict_json(payloads[6]), original)
    decision_map = {row['edge_id']: row for row in decisions}
    for row in decisions:
        pending_decision(row)
    decision_evidence = []
    for decision in decisions:
        if decision['overlap_class'] == 'O2':
            for field in ['evidence_file', 'diagnostics_file']:
                path = Path(frozen_paths[0]).parent.parent / decision[field]
                content = family.read(family.ordinary(path), max_bytes=4 * 1024**2)
                decision_evidence.append(dict(analysis_id=decision['edge_id'], role=field, path=str(path),
                    sha256=family.checksum(content), bytes=len(content)))
            chosen = original['primary_p']('O2', 0.5, None, usual_eligible=True, mrlap_eligible=False, rules=family.strict_json(payloads[6]))
            require(chosen['p'] is None, 'Frozen O2 helper cannot promote exploratory IVW')
    request_bytes = family.read(family.ordinary(request_path), max_bytes=4 * 1024**2)
    request = family.strict_json(request_bytes)
    require(isinstance(request, dict) and set(request) == {'schema', 'scope', 'sources', 'seen_history', 'edges'}
            and request['schema'] == REQUEST and request['scope'] == SCOPE, 'Exact separate real-input v1 contract required')
    sources, histories = request['sources'], request['seen_history']
    require(isinstance(sources, list) and 1 <= len(sources) <= 276 and isinstance(histories, list)
            and len(histories) == len(sources), 'Bounded result sources and original exposure history required')
    require(all(isinstance(row, dict) for row in histories), 'History objects required')
    history_by_id = {row.get('source_id'): row for row in histories}
    require(len(history_by_id) == len(histories), 'Duplicate history identity')
    source_map, provenance = {}, []
    for source in sources:
        require(isinstance(source, dict) and set(source) == {'source_id', 'path', 'sha256'}, 'Exact result source fields required')
        identifier = seen.text(source['source_id'])
        require(identifier not in source_map and identifier in history_by_id, 'Unique source with matching exposure history required')
        # 直接复用上界精度/原始历史行核验；不把结果生成时间冒充首次查看。
        selected, records = seen.source_tables(dict(sources=[source], seen_history=[history_by_id[identifier]]))
        source_map.update(selected)
        provenance.extend(records)
    supplied = request['edges']
    require(isinstance(supplied, list) and 1 <= len(supplied) <= 276, 'One to 276 explicit executed edge records required')
    known = {row['edge_id'] for row in edges}
    values, evidence = {}, []
    fields = {'analysis_id', 'status', 'source_id', 'selector', 'p_column', 'estimator',
              'analysis_id_column', 'method_column', 'status_column', 'failure_reason_column', 'rds'}
    for record in supplied:
        require(isinstance(record, dict) and set(record) == fields, 'Exact real edge fields required; qualification overrides forbidden')
        identifier = seen.text(record['analysis_id'])
        require(identifier in known and identifier not in values, 'Unknown or duplicate frozen analysis ID')
        require(record['status'] in {'ESTIMATED', 'FAILED', 'NOT_ESTIMABLE'}, 'Executed status required; omitted edges alone are NOT_RUN')
        require(record['source_id'] in source_map and isinstance(record['selector'], dict) and record['selector']
                and all(isinstance(k, str) and isinstance(v, str) for k, v in record['selector'].items()), 'Exact lexical source selector required')
        matches = [row for row in source_map[record['source_id']] if all(row.get(k) == v for k, v in record['selector'].items())]
        require(len(matches) == 1, 'Result selector must match exactly one source row')
        row = matches[0]
        method = seen.text(record['estimator'])
        require(row.get(seen.text(record['analysis_id_column'])) == identifier, 'Source row must carry the exact frozen analysis ID')
        require(row.get(seen.text(record['method_column'])) == method and
                row.get(seen.text(record['status_column'])) == record['status'], 'Source method/status must match declared result')
        replay_record = {key: record[key] for key in ['analysis_id', 'status', 'source_id', 'selector', 'p_column', 'estimator']}
        value, unused_method = seen.replay_value(replay_record, source_map)
        if record['status'] == 'ESTIMATED':
            require(record['failure_reason_column'] is None and record['rds'] is not None, 'Estimated result requires original RDS identity and no failure reason')
        else:
            require(isinstance(record['failure_reason_column'], str) and row.get(record['failure_reason_column']), 'Failure/unestimable ledger reason required')
        rds = None if record['rds'] is None else binding(record['rds'])
        values[identifier] = dict(status=record['status'], value=value, source=record['source_id'], estimator=method)
        evidence.append(dict(analysis_id=identifier, source_id=record['source_id'], selector=record['selector'],
            original_row=row, rds=rds, decision_row=decision_map[identifier], failure_reason_column=record['failure_reason_column']))
    require({row['source_id'] for row in supplied} == set(source_map), 'Unused or omitted source identity')
    for record in provenance:
        mapped = {row['analysis_id'] for row in supplied if row['source_id'] == record['source_id']}
        declared = record['history'].get('analysis_ids')
        require(declared is None or set(declared) == mapped, 'Bounded history must match exactly the source analysis IDs')
    rows = []
    for edge in edges:
        result = values.get(edge['edge_id'], dict(status='NOT_RUN', value=None, source='NA', estimator='NA'))
        rows.append(dict(analysis_id=edge['edge_id'], family_id=edge['family'], kind='EDGE', scope=SCOPE,
            execution_status=result['status'], observed_p='NA' if result['value'] is None else repr(result['value']),
            p_primary='NA', p_for_adjustment='1', primary_method='NA',
            primary_qualification=pending_decision(decision_map[edge['edge_id']]),
            source_id=result['source'], estimator=result['estimator'], component_ids='NA'))
    by_id = {row['analysis_id']: row for row in rows}
    dependencies = []
    for path in paths:
        components = [by_id[path[key]] for key in ['xm_edge_id', 'my_edge_id']]
        raw = original['strict_conjunction'](*[None if row['p_primary'] == 'NA' else float(row['p_primary']) for row in components])
        require(raw is None, 'Current pending decisions cannot produce a finite path primary')
        statuses = [row['execution_status'] for row in components]
        status = next((candidate for candidate in ['FAILED', 'NOT_RUN', 'NOT_ESTIMABLE'] if candidate in statuses), 'ESTIMATED')
        component_ids = ','.join(row['analysis_id'] for row in components)
        rows.append(dict(analysis_id=path['path_id'], family_id=path['family'], kind='PATH', scope=SCOPE,
            execution_status=status, observed_p='NA', p_primary='NA', p_for_adjustment='1', primary_method='STRICT_IUT',
            primary_qualification='MISSING_COMPONENT_PRIMARY', source_id='NA', estimator='STRICT_IUT', component_ids=component_ids))
        dependencies.append(dict(analysis_id=path['path_id'], component_ids=component_ids.split(','),
            component_execution_status=statuses, component_primary_qualification=[row['primary_qualification'] for row in components]))
    vectors = []
    for family_id, members in ids.items():
        selected = {row['analysis_id']: row for row in rows if row['family_id'] == family_id}
        for method in ['BH', 'BY'] if family_id.endswith('EDGES') else ['BY']:
            vectors.extend(dict(vector_id=family_id + '/' + method, analysis_id=identifier, family_id=family_id,
                method=method, p_primary=selected[identifier]['p_primary'], p_for_adjustment=selected[identifier]['p_for_adjustment']) for identifier in members)
    require(len(rows) == 564 and len(vectors) == 840, 'Complete frozen families required')
    products = {'real-family.tsv': family.tsv(rows, COLUMNS), 'real-vectors.tsv': family.tsv(vectors, VECTOR_COLUMNS)}
    receipt = dict(schema='A_REAL_INPUT_ASSEMBLY_V1', scope=SCOPE, frozen_source_inputs=frozen,
        request_sha256=family.checksum(request_bytes), sources=provenance, edge_evidence=evidence,
        decision_evidence=decision_evidence, decision_state_counts={state: sum(row['overlap_class'] == state for row in decisions) for state in ['PENDING','O2']},
        path_dependencies=dependencies, family_counts=family.COUNTS, family_ids=ids,
        output_sha256={name: family.checksum(payload) for name, payload in products.items()},
        assembly_rows=564, vector_rows=840, vector_count=6, registered_total_unchanged=696,
        primary_results_published=False, eligibility_receipts_accepted=False, scientific_family_complete=False,
        independent_replication_claimed=False, MR_estimates_computed=False, official_adjustment_performed=False,
        scientific_authorization_granted=False, g0_granted=False)
    products['real-assembly.json'] = family.json_bytes(receipt)
    return products


def write_products(output, products):
    require(output.is_absolute() and not output.exists(), 'New absolute isolated output directory required')
    require(output.parent.resolve(strict=True) == output.parent, 'Canonical output parent required')
    output.mkdir(mode=0o700)
    for name, payload in products.items():
        with os.fdopen(os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as handle:
            handle.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-source', nargs=9, required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--rscript', type=Path, help='Optional official R/stats 4.6.1 executable: run complete adjustment chain')
    args = parser.parse_args()
    products = assemble(args.frozen_source, args.request)
    write_products(args.output, products)
    if args.rscript is not None:
        rscript = family.ordinary(args.rscript)
        script = BASE.parent / 'frozen-a-family-adjustment/real-intake-v1/adjust_real.R'
        command = [str(rscript), '--vanilla', str(script), str(args.output / 'real-vectors.tsv'),
            str(args.output / 'real-assembly.json'), str(args.frozen_source[8]), str(args.output / 'official')]
        result = subprocess.run(command, capture_output=True, timeout=300)
        report = dict(schema='A_REAL_INPUT_DRIVER_EXECUTION_V1', actual_exit=result.returncode,
            rscript=dict(path=str(rscript), sha256=family.checksum(family.read(rscript))),
            script_sha256=family.checksum(family.read(script)), scientific_authorization_granted=False, g0_granted=False)
        (args.output / 'official-driver.json').write_bytes(family.json_bytes(report))
        (args.output / 'official.stdout').write_bytes(result.stdout)
        (args.output / 'official.stderr').write_bytes(result.stderr)
        for name in ['official-driver.json', 'official.stdout', 'official.stderr']:
            (args.output / name).chmod(0o600)
        if result.returncode:
            raise SystemExit(result.returncode)
        adjustment = family.strict_json(family.read(args.output / 'official/real-adjustment.json'))
        require(adjustment['schema'] == 'A_REAL_INPUT_ADJUSTMENT_V1' and adjustment['scope'] == SCOPE
            and adjustment['RDS_readback_vectors'] == 6 and adjustment['RDS_readback_values'] == 840, 'Complete official R readback receipt required')
        for key, name in [('real_tsv', 'real-adjusted.tsv'), ('real_RDS', 'real-adjustment.RDS')]:
            require(adjustment['output_sha256'][key] == family.checksum(family.read(args.output / 'official' / name)), 'Official artifact identity differs')
        completed = dict(schema='A_REAL_INPUT_CHAIN_V1', scope=SCOPE, actual_exit=0,
            artifacts={str(path.relative_to(args.output)): family.checksum(family.read(path))
                for path in sorted(args.output.rglob('*')) if path.is_file()},
            primary_results_published=False, scientific_authorization_granted=False, g0_granted=False)
        destination = args.output / 'real-chain.json'
        destination.write_bytes(family.json_bytes(completed))
        destination.chmod(0o600)
    print(json.dumps(dict(scope=SCOPE, assembly_rows=564, vector_rows=840, primary_results_published=False)))


if __name__ == '__main__':
    main()
