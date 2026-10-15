"""Synthetic complete-family contracts and frozen-ledger transport; never MR."""

import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys


STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')
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
SCENARIOS = ('BOUNDARY', 'INTERIOR')
RSCRIPT = Path('/usr/bin/Rscript')
RSCRIPT_SHA = '939448911dfda7b075a1e234a437cf61c09162e8a9f176269e3f9ab9f96a529b'
R_PROGRAM = '''args <- commandArgs(trailingOnly=TRUE)
stopifnot(identical(as.character(getRversion()),"4.6.1"), identical(as.character(packageVersion("stats")),"4.6.1"))
input <- read.delim(args[1],colClasses="character",check.names=FALSE,na.strings="NA")
stopifnot(!anyDuplicated(paste(input$vector_id,input$analysis_id,sep="/")))
output <- input
output$q <- NA_character_
for (key in unique(input$vector_id)) {
  selected <- which(input$vector_id==key)
  probabilities <- as.numeric(input$p_raw[selected])
  method <- unique(input$method[selected])
  stopifnot(length(method)==1,method %in% c("BH","BY"),all(is.na(probabilities) | (is.finite(probabilities) & probabilities>=0 & probabilities<=1)))
  adjusted_probabilities <- ADJUSTMENT_CALL
  stopifnot(length(adjusted_probabilities)==length(selected),all(is.finite(adjusted_probabilities)),all(adjusted_probabilities>=0 & adjusted_probabilities<=1))
  output$q[selected] <- sprintf("%.17g",adjusted_probabilities)
}
write.table(output,args[2],sep="\\t",quote=FALSE,row.names=FALSE,na="NA")
cat("R=",as.character(getRversion()),";stats=",as.character(packageVersion("stats")),";rows=",nrow(output),"\\n",sep="")
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_json(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def read_table(path):
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t', strict=True)
        rows = list(reader)
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows), 'Rectangular unique-column TSV required')
    return rows


def source_records(root):
    records = []
    for relative, size, expected in SOURCES:
        path = root / relative
        require(path.resolve(strict=True) == path and not any(parent.is_symlink() for parent in [path, *path.parents]) and
            stat.S_ISREG(path.lstat().st_mode), 'Unaliased frozen source required')
        before = path.stat()
        require(before.st_size == size and sha(path) == expected, 'Frozen source size or SHA differs: ' + relative)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Frozen source changed while reading')
        records.append(dict(path=relative, bytes=size, sha256=expected, device=before.st_dev, inode=before.st_ino,
            mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns))
    return records


def original_helpers(root):
    path = root / SOURCES[7][0]
    require(sha(path) == SOURCES[7][2], 'Original helper source changed')
    spec = importlib.util.spec_from_file_location('frozen_a_original_contract_helpers', path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def adjustment_definition(source):
    matches = [line for line in source.splitlines(keepends=True) if line.startswith('adjust_full <- function(')]
    require(len(matches) == 1 and matches[0].count('{') == matches[0].count('}') == 0,
        'One original single-expression adjustment function required')
    return matches[0]


def validate_universe(edges, paths, ledger, decisions, locks, multiplicity, helpers, *, counts=COUNTS):
    edge_ids = [row['edge_id'] for row in edges]
    path_ids = [row['path_id'] for row in paths]
    helpers.assert_locked_ids(edge_ids, [row['edge_id'] for row in decisions])
    helpers.assert_locked_ids(edge_ids + path_ids, [row['analysis_id'] for row in ledger if row['family_id'] in counts])
    require(len(edge_ids + path_ids) == len(set(edge_ids + path_ids)), 'Unique edge/path identities required')
    known = set(edge_ids)
    for row in paths:
        require(all(row[key] in known for key in ['xm_edge_id', 'my_edge_id', 'xy_edge_id']) and
            row['test'] == 'max(p_XM,p_MY)' and row['correction'] == 'BY' and
            row['select_by_pairwise_significance'] == row['product_p_can_promote'] == 'NO', 'Frozen unselected IUT dependency contract required')
    for family, count in counts.items():
        actual = [row['edge_id'] for row in edges if row['family'] == family] + [row['path_id'] for row in paths if row['family'] == family]
        require(len(actual) == count, 'Complete family denominator required: ' + family)
        helpers.assert_locked_ids(actual, [row['analysis_id'] for row in ledger if row['family_id'] == family])
        matching = [row for row in locks if row['family_id'] == family]
        correction = [row for row in multiplicity if row['family_id'] == family]
        require(len(matching) == len(correction) == 1 and matching[0]['status'] == 'LOCKED' and
            int(matching[0]['n_tests']) == int(correction[0]['locked_count']) == count, 'Exact frozen family lock required')
    require(all(row['family'] in counts for row in edges + paths), 'Unknown hypothesis family')


def synthetic_inputs(edges, scenario='BOUNDARY'):
    require(scenario in SCENARIOS, 'Explicit synthetic scenario required')
    rows = []
    for index, edge in enumerate(edges):
        case = index % 6
        first = (0. if index % 12 == 0 else 1.) if scenario == 'BOUNDARY' else .002 + (index // 6 % 5) * .001
        rows.append(dict(analysis_id=edge['edge_id'], family_id=edge['family'], scope=SYNTHETIC, scenario=scenario,
            overlap_class=['O0', 'O1', 'O1', 'O2', 'O3', 'O0'][case], usual_eligible=case != 5,
            mrlap_eligible=case == 1, ivw_p=[first, .0001, .0001, .0001, .03, None][case],
            mrlap_p=[None, [.003, .005, .007, .009, .011][index // 6 % 5], None, .00001, .03, None][case]))
    return rows


def edge_results(rows, edges, helpers, rules):
    helpers.assert_locked_ids([row['analysis_id'] for row in rows], [row['edge_id'] for row in edges])
    expected = {row['edge_id']: row['family'] for row in edges}
    require(len({row['scenario'] for row in rows}) == 1, 'Synthetic scenarios cannot be mixed within a family')
    result = {}
    for row in rows:
        require(row['scope'] == SYNTHETIC and row['scenario'] in SCENARIOS and
            row['family_id'] == expected[row['analysis_id']], 'Synthetic scenario, scope and exact family required')
        require(type(row['usual_eligible']) is bool and type(row['mrlap_eligible']) is bool, 'Explicit synthetic boolean qualification required')
        value = helpers.primary_p(row['overlap_class'], row['ivw_p'], row['mrlap_p'],
            usual_eligible=row['usual_eligible'], mrlap_eligible=row['mrlap_eligible'], rules=rules)
        result[row['analysis_id']] = dict(analysis_id=row['analysis_id'], family_id=row['family_id'],
            scope=SYNTHETIC, scenario=row['scenario'], p_raw=value['p'], primary_method=value['method'], reason=value['reason'])
    return result


def all_results(edges, paths, results, helpers):
    helpers.assert_locked_ids(results, [row['edge_id'] for row in edges])
    values = dict(results)
    scenarios = {row['scenario'] for row in results.values()}
    require(len(scenarios) == 1 and scenarios <= set(SCENARIOS), 'One synthetic scenario per IUT family required')
    scenario = next(iter(scenarios))
    for row in paths:
        first, second = results[row['xm_edge_id']]['p_raw'], results[row['my_edge_id']]['p_raw']
        observed = helpers.strict_conjunction(first, second)
        independent = None if first is None or second is None else max(first, second)
        require(observed == independent, 'Original strict IUT differs from independent conjunction contract')
        values[row['path_id']] = dict(analysis_id=row['path_id'], family_id=row['family'], scope=SYNTHETIC, scenario=scenario,
            p_raw=observed, primary_method='STRICT_IUT', reason='MISSING_COMPONENT' if observed is None else 'COMPLETE_COMPONENTS')
    return values


def ledger_results(ledger):
    rows = [row for row in ledger if row['family_id'] in COUNTS]
    require(all(row['status'] == 'NOT_ESTIMABLE' and row['p_raw'] == 'NA' and row['p_for_adjustment'] == '1' for row in rows),
        'Only the actual frozen missing-value ledger is supported')
    return {row['analysis_id']: dict(analysis_id=row['analysis_id'], family_id=row['family_id'], scope=LEDGER, scenario='REAL_FROZEN_NA_LEDGER',
        p_raw=None, primary_method='NA', reason=row['status']) for row in rows}


def vectors(results, edges, paths, helpers, *, counts=COUNTS):
    rows = []
    hypotheses = [dict(analysis_id=row['edge_id'], family_id=row['family']) for row in edges]
    hypotheses += [dict(analysis_id=row['path_id'], family_id=row['family']) for row in paths]
    helpers.assert_locked_ids(results, [row['analysis_id'] for row in hypotheses])
    for family, count in counts.items():
        selected = [results[row['analysis_id']] for row in hypotheses if row['family_id'] == family]
        require(len(selected) == count and all(row['family_id'] == family for row in selected), 'Complete family vector required')
        require(len({(row['scope'], row['scenario']) for row in selected}) == 1,
            'Each complete family must have one scope and scenario')
        for method in ['BH', 'BY'] if family.endswith('EDGES') else ['BY']:
            for row in selected:
                require(row['scope'] in {SYNTHETIC, LEDGER}, 'Only technical input scopes allowed')
                require((row['scope'] == SYNTHETIC and row['scenario'] in SCENARIOS) or
                    (row['scope'] == LEDGER and row['scenario'] == 'REAL_FROZEN_NA_LEDGER'), 'Explicit technical scenario required')
                rows.append(dict(vector_id=row['scope'] + '/' + row['scenario'] + '/' + family + '/' + method, analysis_id=row['analysis_id'],
                    p_raw='NA' if row['p_raw'] is None else repr(row['p_raw']), method=method))
    return rows


def refused_cases(inputs, edges, paths, helpers, rules):
    cases = {}
    altered = copy.deepcopy(inputs)
    altered[0]['family_id'] = 'UNKNOWN'
    cases['wrong_family'] = altered
    altered = copy.deepcopy(inputs)
    altered[0]['scope'] = 'RESEARCH'
    cases['invented_research_scope'] = altered
    cases['missing_id'] = inputs[:-1]
    cases['duplicate_id'] = [*inputs[:-1], inputs[0]]
    altered = copy.deepcopy(inputs)
    altered[0]['analysis_id'] = 'FOREIGN'
    cases['foreign_id'] = altered
    for label, value in [('boolean_p', True), ('invalid_probability', 1.01), ('infinite_p', float('inf'))]:
        altered = copy.deepcopy(inputs)
        altered[0]['ivw_p'] = value
        cases[label] = altered
    evidence = []
    for name, altered in cases.items():
        try:
            edge_results(altered, edges, helpers, rules)
        except ValueError as error:
            evidence.append(dict(case=name, rejected=True, diagnostic=str(error)))
        else:
            raise ValueError('Expected refusal accepted: ' + name)
    return evidence


def write_vectors(path, rows):
    with path.open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['vector_id', 'analysis_id', 'p_raw', 'method'], delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def adjustment_coverage(baseline, shortened, *, families=None):
    families = COUNTS if families is None else families
    require(len(baseline) == len(shortened), 'Complete shortened-family control inventory required')
    interior = sum(0 < float(row['q']) < 1 for row in baseline)
    require(interior > 0, 'Official complete-family benchmark must include interior q values')
    by_key = {(row['vector_id'], row['analysis_id']): row for row in baseline}
    differences = 0
    family_coverage = {family: dict(interior_q_values=0, shared_BH_BY_different_q=0,
        official_drop_missing_changed_nonmissing_q=0) for family in families}
    for row in baseline:
        family = row['vector_id'].split('/')[-2]
        if row['vector_id'].startswith(SYNTHETIC + '/'):
            require(family in family_coverage, 'Unknown synthetic correction family')
            family_coverage[family]['interior_q_values'] += 0 < float(row['q']) < 1
        if row['vector_id'].endswith('/BH'):
            other = by_key.get((row['vector_id'][:-3] + '/BY', row['analysis_id']))
            differences += other is not None and float(row['q']) != float(other['q'])
            if row['vector_id'].startswith(SYNTHETIC + '/') and other is not None:
                family_coverage[family]['shared_BH_BY_different_q'] += float(row['q']) != float(other['q'])
    require(differences > 0, 'Official benchmark must distinguish BH and BY for a shared scope/family/ID')
    changed = 0
    for row, control in zip(baseline, shortened, strict=True):
        require({key: value for key, value in row.items() if key != 'q'} ==
            {key: value for key, value in control.items() if key != 'q'}, 'Shortened-family control changed input identities')
        value = float(control['q'])
        require(math.isfinite(value) and 0 <= value <= 1, 'Official negative control q outside probability range')
        changed += row['p_raw'] != 'NA' and float(row['q']) != value
        if row['vector_id'].startswith(SYNTHETIC + '/'):
            family_coverage[row['vector_id'].split('/')[-2]]['official_drop_missing_changed_nonmissing_q'] += row['p_raw'] != 'NA' and float(row['q']) != value
    require(changed > 0, 'Dropping missing rows must visibly change a nonmissing official q value')
    for family, coverage in family_coverage.items():
        require(coverage['interior_q_values'] > 0 and coverage['official_drop_missing_changed_nonmissing_q'] > 0,
            'Each complete synthetic family must have interior q and a shortened-family difference: ' + family)
        require(not family.endswith('EDGES') or coverage['shared_BH_BY_different_q'] > 0,
            'Each synthetic edge family must distinguish BH and BY: ' + family)
    return dict(interior_q_values=interior, shared_BH_BY_different_q=differences,
        official_drop_missing_changed_nonmissing_q=changed, per_synthetic_family=family_coverage,
        shortened_family_control_not_a_production_algorithm=True)


def validate_vector_lengths(rows):
    grouped = {}
    for row in rows:
        parts = row['vector_id'].split('/')
        require(len(parts) == 4 and parts[2] in COUNTS and row['method'] == parts[3] and
            parts[3] in (['BH', 'BY'] if parts[2].endswith('EDGES') else ['BY']) and
            ((parts[0] == SYNTHETIC and parts[1] in SCENARIOS) or
             (parts[0] == LEDGER and parts[1] == 'REAL_FROZEN_NA_LEDGER')), 'Explicit complete-vector scope, scenario, family and method required')
        grouped.setdefault(row['vector_id'], []).append(row['analysis_id'])
    require(grouped and all(len(ids) == len(set(ids)) == COUNTS[key.split('/')[2]] for key, ids in grouped.items()),
        'Every R correction vector must retain its complete frozen family length')


def r_adjustments(output, rows, definition):
    validate_vector_lengths(rows)
    require(RSCRIPT.resolve(strict=True) == RSCRIPT and sha(RSCRIPT) == RSCRIPT_SHA, 'Frozen official Rscript executable identity required')
    input_path = output / 'technical-vectors.tsv'
    write_vectors(input_path, rows)
    results = []
    for label, function, expression in [('frozen-helper', definition, 'adjust_full(probabilities,method)'),
            ('official-reference', '', 'stats::p.adjust(ifelse(is.finite(probabilities),probabilities,1),method=method)'),
            ('official-shortened-control', '', 'local({ estimable <- is.finite(probabilities); adjusted_probabilities <- rep(1,length(probabilities)); adjusted_probabilities[estimable] <- stats::p.adjust(probabilities[estimable],method=method); adjusted_probabilities })')]:
        script = output / (label + '.R')
        script.write_text(function + R_PROGRAM.replace('ADJUSTMENT_CALL', expression))
        destination = output / (label + '.tsv')
        run = subprocess.run([str(RSCRIPT), '--vanilla', str(script), str(input_path), str(destination)],
            capture_output=True, text=True, timeout=60, cwd=os.environ['TMPDIR'])
        (output / (label + '.stdout')).write_text(run.stdout)
        (output / (label + '.stderr')).write_text(run.stderr)
        write_json(output / (label + '.execution.json'), dict(actual_exit=run.returncode, rscript_sha256=RSCRIPT_SHA,
            method_fitting=False, scientific_authorization_granted=False, g0_granted=False))
        require(run.returncode == 0 and ';stats=4.6.1;rows=' + str(len(rows)) in run.stdout, 'Exact official R/statistics runtime must actually execute')
        results.append(read_table(destination))
    require(all(len(result) == len(rows) for result in results), 'All complete-family outputs required')
    for expected, actual, reference in zip(rows, *results[:2], strict=True):
        require({key: actual[key] for key in expected} == expected and actual == reference, 'Every original/helper and independent official row must match exactly')
        value = float(actual['q'])
        require(math.isfinite(value) and 0 <= value <= 1 and
            (not actual['vector_id'].startswith(LEDGER) or value == 1), 'Valid official q and missing ledger placeholders required')
    return dict(complete_q_values=len(rows), exact_official_q_equal=len(rows), max_absolute_difference=0,
        vectors=len({row['vector_id'] for row in rows}), official_processes=3, R='4.6.1', stats='4.6.1',
        **adjustment_coverage(results[1], results[2]))


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-family-contract'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    before = source_records(STUDY)
    helpers = original_helpers(STUDY)
    tables = [read_table(STUDY / SOURCES[index][0]) for index in range(6)]
    edges, paths, ledger, decisions, locks, multiplicity = tables
    rules = json.loads((STUDY / SOURCES[6][0]).read_text())
    validate_universe(*tables, helpers)
    require({family: rules['planned_counts'][family] for family in COUNTS} == COUNTS and
        rules['planned_counts']['A_MVP_BRIDGE'] == 11, 'Four original families and separate conditional MVP scope required')
    rows = []
    path_coverage = {}
    for scenario in SCENARIOS:
        inputs = synthetic_inputs(edges, scenario)
        synthetic = all_results(edges, paths, edge_results(inputs, edges, helpers, rules), helpers)
        path_values = [synthetic[row['path_id']]['p_raw'] for row in paths]
        finite_paths = sum(value is not None and math.isfinite(value) for value in path_values)
        missing_paths = sum(value is None for value in path_values)
        require(finite_paths > 0 and missing_paths > 0 and finite_paths + missing_paths == len(paths),
            'Unselected synthetic paths must cover finite and missing component results')
        path_coverage[scenario] = dict(finite=finite_paths, missing=missing_paths)
        require(all(synthetic[row['analysis_id']]['p_raw'] is None for row in inputs if row['overlap_class'] in {'O2', 'O3'} or
            (row['overlap_class'] == 'O1' and not row['mrlap_eligible'])), 'No primary-P fallback is permitted')
        rows.extend(vectors(synthetic, edges, paths, helpers))
    frozen = ledger_results(ledger)
    rows.extend(vectors(frozen, edges, paths, helpers))
    refusals = refused_cases(synthetic_inputs(edges), edges, paths, helpers, rules)
    definition = adjustment_definition((STUDY / SOURCES[8][0]).read_text())
    comparison = r_adjustments(output, rows, definition)
    require(before == source_records(STUDY), 'Frozen sources changed during technical proof')
    write_json(output / 'verification.json', dict(scope='SYNTHETIC_COMPLETE_FROZEN_IDS_AND_LEDGER_TRANSPORT_ONLY_NOT_RESEARCH',
        source_identities=before, family_counts=COUNTS, synthetic_edge_ids=len(edges), synthetic_path_ids=len(paths),
        synthetic_scenarios=list(SCENARIOS), synthetic_path_coverage=path_coverage,
        raw_missing_preserved=True, adjustment_missing_placeholder=1,
        synthetic_qualification_not_applied_to_real_register=True, frozen_decisions_unchanged=True,
        frozen_overlap_counts={value: sum(row['overlap_class'] == value for row in decisions) for value in ['PENDING', 'O2']},
        original_python_functions=['primary_p', 'strict_conjunction', 'assert_locked_ids'],
        original_adjust_full_sha256=hashlib.sha256(definition.encode()).hexdigest(), official_comparison=comparison,
        refusals=refusals, conditional_MVP_enabled=False, raw_inputs_read=False, MR_estimates_computed=False, actual_DAG_executed=False,
        native_boolean_test_certified=False, native_adjust_pvalues_certified=False,
        current_daemon_verified=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
