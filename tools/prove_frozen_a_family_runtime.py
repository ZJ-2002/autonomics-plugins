"""Exercise frozen full-family adapters against the previously sealed official oracle."""

import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_frozen_a_family_contract as contract
from tools import prove_frozen_a_input_qualification as raw
from tools.prove_frozen_a_harmonisation import inspected_backend, original_postcheck, resource_admission
from tools.prove_frozen_a_harmonisation_dag import file_identity, regular
from tools.reconcile_ab_evidence_index import verify_archive

ORACLE_SESSION = 'ab47448d3e7b49bc96610c3529d94257'
ORACLE_SEAL = '22387c3e20caecb8eaee9e671fa4a78a3e28c7d690f66bd300e5c7726095a048'
ADAPTERS = ('frozen-a-family-assembly', 'frozen-a-family-adjustment')
KINDS = ('frozen_a_family_assemble', 'frozen_a_family_adjust', 'frozen_a_family_publish')
OUTPUTS = {
    KINDS[0]: ['assembly.tsv', 'vectors.tsv', 'assembly-receipt.json', 'assembly.log'],
    KINDS[1]: ['adjusted.tsv', 'adjustment.RDS', 'adjustment-receipt.json', 'adjustment.log'],
    KINDS[2]: ['family.tsv', 'family-vectors.tsv', 'family-audit.json', 'family.log'],
}
RDS_READBACK = '''args <- commandArgs(trailingOnly=TRUE)
stopifnot(identical(as.character(getRversion()), "4.6.1"),
          identical(as.character(packageVersion("stats")), "4.6.1"))
reference <- read.delim(args[1], colClasses="character", check.names=FALSE,
                       na.strings=NULL, quote="", comment.char="")
stopifnot(nrow(reference)==2520L, !anyDuplicated(paste(reference$vector_id,reference$analysis_id,sep="/")))
checked <- 0L
seen <- character()
metadata <- read.delim(args[2], colClasses="character", check.names=FALSE,
                      na.strings=NULL, quote="", comment.char="")
stopifnot(nrow(metadata)==3L, identical(metadata$scenario,c("BOUNDARY","INTERIOR","REAL_FROZEN_NA_LEDGER")))
definition <- grep("^adjust_full <- function\\\\(", readLines(args[3],warn=FALSE),value=TRUE)
stopifnot(length(definition)==1L)
definition <- paste0(definition,"\\n")
for (index in seq_len(nrow(metadata))) {
  expected_keys <- unique(reference$vector_id[vapply(strsplit(reference$vector_id,"/",fixed=TRUE),
    function(parts) identical(parts[2],metadata$scenario[index]),logical(1))])
  expected_hashes <- as.list(setNames(vapply(c("vectors_sha","assembly_sha","receipt_sha","methods_sha"),
    function(name) metadata[[name]][index],""),
    c("vectors.tsv","assembly.tsv","assembly-receipt.json","g0_v432_methods.R")))
  payload <- readRDS(metadata$rds_path[index])
  stopifnot(is.list(payload), identical(names(payload),
    c("vectors","input_sha256","adjustment_definition","R_version","stats_version")),
    identical(payload$R_version,"4.6.1"), identical(payload$stats_version,"4.6.1"),
    is.list(payload$vectors), length(payload$vectors)==6L, identical(names(payload$vectors),expected_keys),
    identical(payload$input_sha256,expected_hashes), identical(payload$adjustment_definition,definition),
    !anyDuplicated(c(seen,names(payload$vectors))))
  seen <- c(seen,names(payload$vectors))
  for (key in names(payload$vectors)) {
    value <- payload$vectors[[key]]
    expected <- reference[reference$vector_id==key,,drop=FALSE]
    raw <- suppressWarnings(as.numeric(expected$p_raw))
    raw[expected$p_raw=="NA"] <- NA_real_
    adjusted_input <- ifelse(is.na(raw),1,raw)
    method <- unique(expected$method)
    stopifnot(is.list(value), identical(names(value),
      c("analysis_id","p_raw","p_for_adjustment","q","method","n_total")),
      nrow(expected) %in% c(88L,188L,36L,252L), identical(value$analysis_id,expected$analysis_id),
      identical(value$p_raw,raw), identical(value$p_for_adjustment,adjusted_input),
      identical(value$method,method), identical(value$n_total,nrow(expected)),
      identical(typeof(value$q),"double"), is.null(attributes(value$q)),
      identical(is.na(value$p_raw),expected$p_raw=="NA"),
      identical(value$q,stats::p.adjust(adjusted_input,method=method)),
      identical(value$q,as.numeric(expected$q)))
    checked <- checked+length(value$q)
  }
}
stopifnot(checked==2520L, length(seen)==18L, setequal(seen,unique(reference$vector_id)))
cat("OFFICIAL_RDS_READBACK_18_VECTORS_2520_VALUES_EXACT\\n")
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with regular(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def tables(path):
    with regular(path).open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t', strict=True)
        rows = list(reader)
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows),
        'Complete rectangular unique-column result required')
    return rows


def sources():
    result = {}
    for family in ADAPTERS:
        directory = ROOT / 'research-adapters' / family
        for path in sorted(directory.rglob('*')):
            require(not path.is_symlink(), 'Adapter aliases cannot enter a source proof')
            if path.is_file() and '__pycache__' not in path.parts:
                result[path.relative_to(ROOT).as_posix()] = file_identity(path)
    require(result, 'Both actual adapters must exist')
    return result


def definitions():
    result = {}
    for family in ADAPTERS:
        directory = ROOT / 'research-adapters' / family
        manifest = tomllib.loads(regular(directory / 'manifest.toml').read_text())
        require(manifest['plugin_name'] == family and not manifest.get('panels'), 'Exact panel-free family required')
        for node in manifest['nodes']:
            require(node['kind'] in KINDS and node['kind'] not in result and not node.get('params') and
                node['stage_in_mode'] == 'copy' and node['resources']['cpus'] == 1.0 and
                node['resources']['memory'] == '1Gi' and node['resources']['pull_policy'] == 'never' and
                node['resources']['network'] == 'isolated' and node['resources']['read_only_rootfs'] is True and
                [port['path'] for port in node['ports']['outputs']] == OUTPUTS[node['kind']],
                'Exact declared method, isolated resources and output ports required')
            expected_image = raw.IMAGE if family == ADAPTERS[0] else 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
            require(manifest['image']['reference'] == expected_image, 'Existing immutable official runtime required')
            result[node['kind']] = dict(node=node, directory=directory, image=expected_image)
    require(set(result) == set(KINDS), 'All three actual method definitions required')
    return result


def execute(prefix, definition, inputs, output, *, expected_exit=0, expected_diagnostic=None, foreign_outputs=None):
    node = definition['node']
    require(len(inputs) == len(node['ports']['inputs']), 'Only actual declared input ports may be populated')
    output.mkdir(mode=0o700)
    foreign = {}
    for name, payload in (foreign_outputs or {}).items():
        require(name in OUTPUTS[node['kind']][:-1], 'Only declared normal ports may hold the foreign-output control')
        path = output / name
        with path.open('xb') as handle:
            handle.write(payload)
        foreign[name] = file_identity(path)
    script = regular(definition['directory'] / node['command']['script_file'])
    command = [*prefix, 'run', '--rm', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
        '--pids-limit=64', '--pull=never', '--workdir=/work', '-v', str(output) + ':/work:rw',
        '-v', str(script) + ':/method/source:ro', '--entrypoint=' + node['command']['interpreter']]
    for key, value in node['command'].get('env', {}).items():
        command.extend(['-e', key + '=' + str(value)])
    input_records = []
    for index, path in enumerate(inputs):
        path = regular(path)
        mounted = '/inputs/' + str(index) + '/' + path.name
        command.extend(['-v', str(path) + ':' + mounted + ':ro', '-e', 'AUTONOMICS_INPUT' + str(index) + '=' + mounted])
        input_records.append(dict(port=index, path=str(path), identity=file_identity(path)))
    for index, port in enumerate(node['ports']['outputs']):
        require(port['path'] == Path(port['path']).name, 'Only declared flat output paths supported')
        command.extend(['-e', 'AUTONOMICS_OUTPUT' + str(index) + '=/work/' + port['path']])
    command.extend([definition['image'], '/method/source'])
    run = subprocess.run(command, capture_output=True, timeout=300)
    (output / 'container.stdout').write_bytes(run.stdout)
    (output / 'container.stderr').write_bytes(run.stderr)
    write(output / 'execution.json', dict(command=command, actual_exit=run.returncode, inputs=input_records,
        declared_kind=node['kind'], foreign_outputs_before=foreign, expected_diagnostic=expected_diagnostic, no_MR=True,
        scientific_authorization_granted=False, g0_granted=False))
    require(run.returncode == expected_exit, 'Actual declared method exit differs: ' + node['kind'])
    products = [output / name for name in OUTPUTS[node['kind']]]
    if expected_exit:
        require(not any(path.exists() for path in products[:-1] if path.name not in foreign),
            'Refusal published a normal method output')
        require(all(file_identity(output / name) == identity for name, identity in foreign.items()),
            'Refusal modified a foreign output')
        require(products[-1].is_file() and products[-1].stat().st_size > 0, 'Refusal must preserve its declared diagnostic')
        require(isinstance(expected_diagnostic, str) and expected_diagnostic and
            expected_diagnostic.encode() in run.stderr + products[-1].read_bytes(),
            'Method refused for a different reason than the specific injected contract violation')
        return []
    require(all(regular(path).stat().st_size > 0 for path in products), 'Every declared port must materialize')
    return products


def checked_oracle(archives):
    checked = verify_archive(archives, ORACLE_SESSION, ORACLE_SEAL)
    require(checked['positive_worker_exit_verified'], 'Prior complete official oracle must have actual exit zero')
    directory = Path(checked['artifact_root']) / 'permanent/frozen-a-family-contract'
    vectors = tables(directory / 'technical-vectors.tsv')
    reference = tables(directory / 'official-reference.tsv')
    require(len(vectors) == len(reference) == 2520, 'Entire eighteen-vector official reference required')
    return vectors, reference, dict(session=ORACLE_SESSION, seal=ORACLE_SEAL, all_members_rehashed=True)


def request_for(edges, scenario):
    return dict(schema='FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1',
        scope=contract.LEDGER if scenario == 'REAL_FROZEN_NA_LEDGER' else contract.SYNTHETIC,
        scenario=scenario, edges=[] if scenario == 'REAL_FROZEN_NA_LEDGER' else contract.synthetic_inputs(edges, scenario))


def compare_case(directory, scenario, assembled, adjusted, published, oracle_vectors, oracle_reference):
    selected_vectors = [row for row in oracle_vectors if row['vector_id'].split('/')[1] == scenario]
    selected_reference = [row for row in oracle_reference if row['vector_id'].split('/')[1] == scenario]
    observed_vectors = tables(assembled[1])
    observed_adjusted = tables(adjusted[0])
    require(len(selected_vectors) == len(selected_reference) == len(observed_vectors) == len(observed_adjusted) == 840,
        'Each actual method case must contain six complete frozen vectors')
    require(observed_vectors == selected_vectors, 'Every actual primary/IUT vector row must equal the sealed prior reference')
    for actual, reference in zip(observed_adjusted, selected_reference, strict=True):
        require(set(actual) == set(reference) and all(actual[key] == reference[key] for key in reference if key != 'q') and
            math.isfinite(float(actual['q'])) and float(actual['q']) == float(reference['q']),
            'Every official q and original identity must match the independently sealed oracle')
    full = tables(published[0])
    original = tables(assembled[0])
    require(len(full) == len(original) == 564 and len({row['analysis_id'] for row in full}) == 564,
        'Final publish must retain all 276 edges and 288 paths')
    q_lookup = {(row['analysis_id'], row['method']): row['q'] for row in observed_adjusted}
    for row, before in zip(full, original, strict=True):
        require(all(row[key] == value for key, value in before.items()) and
            float(row['p_for_adjustment']) == (1.0 if row['p_raw'] == 'NA' else float(row['p_raw'])) and
            int(row['family_n']) == contract.COUNTS[row['family_id']] and
            float(row['q_BY']) == float(q_lookup[(row['analysis_id'], 'BY')]) and
            ((row['family_id'].endswith('PATHS') and row['q_BH'] == 'NA') or
             (row['family_id'].endswith('EDGES') and float(row['q_BH']) == float(q_lookup[(row['analysis_id'], 'BH')]))),
            'Final family changes source identity, raw missingness, reason, denominator or official q')
    require(published[1].read_bytes() == adjusted[0].read_bytes(), 'Full published correction vector changed')
    write(directory / 'comparison.json', dict(scenario=scenario, full_result_rows=564, full_vector_rows=840,
        full_q_equal=840, max_absolute_difference=0, raw_missing_preserved=True,
        actual_DAG_executed=False, real_MR_results_computed=False, g0_granted=False))


def negative_controls(prefix, methods, output, original_inputs, edges, positive):
    root = output / 'refusals'
    root.mkdir()
    request = request_for(edges, 'BOUNDARY')
    cases = {}
    diagnostics = {
        'wrong-family': 'Exact synthetic eligibility, scope, family and scenario required',
        'foreign-id': 'Analysis IDs do not equal frozen family',
        'boolean-p': 'Probability must be null or a finite numeric value',
        'out-of-range-p': 'Probability must be null or a finite numeric value',
        'mixed-row-scope': 'Exact synthetic eligibility, scope, family and scenario required',
        'mixed-row-scenario': 'Exact synthetic eligibility, scope, family and scenario required',
        'research-scope': 'Explicit compatible technical scope and scenario required',
        'missing-id': 'Analysis IDs do not equal frozen family',
        'duplicate-id': 'Duplicate analysis IDs',
    }
    for label, field, value in [('wrong-family', 'family_id', 'UNKNOWN'),
            ('foreign-id', 'analysis_id', 'FOREIGN'), ('boolean-p', 'ivw_p', True),
            ('out-of-range-p', 'ivw_p', 1.01), ('mixed-row-scope', 'scope', contract.LEDGER),
            ('mixed-row-scenario', 'scenario', 'INTERIOR')]:
        altered = copy.deepcopy(request)
        altered['edges'][0][field] = value
        cases[label] = altered
    altered = copy.deepcopy(request)
    altered['scope'] = 'RESEARCH'
    cases['research-scope'] = altered
    altered = copy.deepcopy(request)
    altered['edges'] = altered['edges'][:-1]
    cases['missing-id'] = altered
    altered = copy.deepcopy(request)
    altered['edges'][-1] = copy.deepcopy(altered['edges'][0])
    cases['duplicate-id'] = altered
    observations = []
    for label, altered in cases.items():
        path = root / (label + '.json')
        write(path, altered)
        execute(prefix, methods[KINDS[0]], [*original_inputs, path], root / label, expected_exit=2,
            expected_diagnostic=diagnostics[label])
        observations.append(dict(case=label, kind=KINDS[0], actual_exit=2))
    nonfinite = root / 'nonfinite-p.json'
    altered = copy.deepcopy(request)
    altered['edges'][0]['ivw_p'] = 'NONFINITE_MARKER'
    with nonfinite.open('x') as handle:
        handle.write(json.dumps(altered).replace('"NONFINITE_MARKER"', 'Infinity'))
    execute(prefix, methods[KINDS[0]], [*original_inputs, nonfinite], root / 'nonfinite-p', expected_exit=2,
        expected_diagnostic='Nonfinite JSON number')
    observations.append(dict(case='nonfinite-p', kind=KINDS[0], actual_exit=2))
    changed_source = root / 'changed-helpers.py'
    with changed_source.open('xb') as handle:
        handle.write(original_inputs[7].read_bytes() + b'\n')
    changed_inputs = list(original_inputs)
    changed_inputs[7] = changed_source
    valid_request = output / 'BOUNDARY/request.json'
    execute(prefix, methods[KINDS[0]], [*changed_inputs, valid_request], root / 'changed-frozen-source', expected_exit=2,
        expected_diagnostic='Frozen input size differs before reading payload')
    observations.append(dict(case='changed-frozen-source', kind=KINDS[0], actual_exit=2))
    assembled, adjusted = positive
    for label in ['shortened-vector', 'wrong-path-method']:
        directory = root / (label + '-input')
        directory.mkdir()
        rows = tables(assembled[1])
        if label == 'shortened-vector':
            rows.pop()
        else:
            position = next(index for index, row in enumerate(rows) if '/A_PRIMARY_PATHS/' in row['vector_id'])
            rows[position]['method'] = 'BH'
            rows[position]['vector_id'] = rows[position]['vector_id'][:-2] + 'BH'
        vector_path = directory / 'vectors.tsv'
        contract.write_vectors(vector_path, rows)
        receipt = json.loads(assembled[2].read_text())
        receipt['output_sha256']['vectors.tsv'] = digest(vector_path)
        receipt_path = directory / 'assembly-receipt.json'
        write(receipt_path, receipt)
        execute(prefix, methods[KINDS[1]], [vector_path, assembled[0], receipt_path, original_inputs[8]], root / label,
            expected_exit=2, expected_diagnostic='Complete rectangular TSV required' if label == 'shortened-vector'
                else 'Six complete vectors must retain their fixed family, method and row order')
        observations.append(dict(case=label, kind=KINDS[1], actual_exit=2))
    wrong_version = root / 'wrong-R-version.json'
    receipt = json.loads(adjusted[2].read_text())
    receipt['stats_version'] = '4.5.1'
    write(wrong_version, receipt)
    execute(prefix, methods[KINDS[2]], [*assembled[:3], *adjusted[:2], wrong_version, *original_inputs[:2]],
        root / 'wrong-R-version', expected_exit=2, expected_diagnostic='Exact official R/stats receipt')
    observations.append(dict(case='wrong-R-version', kind=KINDS[2], actual_exit=2))
    invalid_adjustment = root / 'nonfinite-q.tsv'
    lines = adjusted[0].read_text().splitlines()
    fields = lines[1].split('\t')
    fields[-1] = 'NaN'
    lines[1] = '\t'.join(fields)
    with invalid_adjustment.open('x') as handle:
        handle.write('\n'.join(lines) + '\n')
    receipt = json.loads(adjusted[2].read_text())
    receipt['output_sha256']['adjusted.tsv'] = digest(invalid_adjustment)
    invalid_receipt = root / 'nonfinite-q-receipt.json'
    write(invalid_receipt, receipt)
    execute(prefix, methods[KINDS[2]], [*assembled[:3], invalid_adjustment, *adjusted[1:2], invalid_receipt,
        *original_inputs[:2]], root / 'nonfinite-q', expected_exit=2,
        expected_diagnostic='Probability must be null or a finite numeric value')
    observations.append(dict(case='nonfinite-q', kind=KINDS[2], actual_exit=2))
    execute(prefix, methods[KINDS[2]], [*assembled[:3], *adjusted[:3], *original_inputs[:2]],
        root / 'foreign-output', expected_exit=2, expected_diagnostic='Existing or foreign output must never be overwritten',
        foreign_outputs={'family.tsv': b'FOREIGN_OUTPUT_MUST_REMAIN\n'})
    observations.append(dict(case='foreign-output', kind=KINDS[2], actual_exit=2, foreign_file_unchanged=True))
    write(output / 'refusal-verification.json', observations)
    return observations


def official_rds_readback(output, archives, rds_paths):
    require(contract.RSCRIPT.resolve(strict=True) == contract.RSCRIPT and digest(contract.RSCRIPT) == contract.RSCRIPT_SHA,
        'Independent official Rscript executable changed; no fallback reference')
    script = output / 'official-rds-readback.R'
    with script.open('x') as handle:
        handle.write(RDS_READBACK)
    reference = archives / ORACLE_SESSION / 'artifacts/permanent/frozen-a-family-contract/official-reference.tsv'
    records = []
    for scenario, path in zip([*contract.SCENARIOS, 'REAL_FROZEN_NA_LEDGER'], rds_paths, strict=True):
        receipt = json.loads((path.parent / 'adjustment-receipt.json').read_text())
        require(receipt['scenario'] == scenario, 'Each actual RDS must be bound to its own scenario')
        inputs = receipt['input_sha256']
        records.append(dict(scenario=scenario, rds_path=str(path), vectors_sha=inputs['vectors.tsv'],
            assembly_sha=inputs['assembly.tsv'], receipt_sha=inputs['assembly-receipt.json'],
            methods_sha=inputs['g0_v432_methods.R']))
    metadata = output / 'official-rds-input-metadata.tsv'
    with metadata.open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
    method_source = contract.STUDY / contract.SOURCES[8][0]
    command = [str(contract.RSCRIPT), '--vanilla', str(script), str(reference), str(metadata), str(method_source)]
    run = subprocess.run(command, capture_output=True, timeout=60, cwd=os.environ['TMPDIR'])
    (output / 'official-rds-readback.stdout').write_bytes(run.stdout)
    (output / 'official-rds-readback.stderr').write_bytes(run.stderr)
    write(output / 'official-rds-readback-execution.json', dict(actual_exit=run.returncode, command=command,
        rscript_sha256=contract.RSCRIPT_SHA, g0_granted=False))
    require(run.returncode == 0 and b'OFFICIAL_RDS_READBACK_18_VECTORS_2520_VALUES_EXACT' in run.stdout and
        digest(contract.RSCRIPT) == contract.RSCRIPT_SHA, 'Complete official RDS readback failed')
    for label in ['repeated-scenario-object', 'changed-input-hash']:
        altered = copy.deepcopy(records)
        if label == 'repeated-scenario-object':
            altered[1]['rds_path'] = altered[0]['rds_path']
        else:
            altered[0]['vectors_sha'] = '0' * 64
        altered_path = output / ('official-rds-' + label + '.tsv')
        with altered_path.open('x', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]), delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(altered)
        control = [str(contract.RSCRIPT), '--vanilla', str(script), str(reference), str(altered_path), str(method_source)]
        refused = subprocess.run(control, capture_output=True, timeout=60, cwd=os.environ['TMPDIR'])
        (output / ('official-rds-' + label + '.stdout')).write_bytes(refused.stdout)
        (output / ('official-rds-' + label + '.stderr')).write_bytes(refused.stderr)
        write(output / ('official-rds-' + label + '-execution.json'), dict(actual_exit=refused.returncode,
            expected_reference_refusal=True, command=control, g0_granted=False))
        marker = b'names(payload$vectors)' if label == 'repeated-scenario-object' else b'payload$input_sha256'
        require(refused.returncode != 0 and marker in refused.stderr,
            'Official RDS comparator must actually reject this specific counterexample')


def stopped(prefix, permanent, output, expected):
    session = permanent.parent.name
    inventory = regular(permanent / 'container-intents.json')
    before = file_identity(inventory)
    record = json.loads(inventory.read_text())
    require(record['session'] == session and len(record['intents']) == expected and
        len({row['token'] for row in record['intents']}) == expected, 'Exact fresh managed container intents required')
    observations = []
    for row in record['intents']:
        require(row['backend'] in [prefix[1:], [*prefix[1:], '--cgroup-manager=cgroupfs']], 'Foreign container backend')
        command = [prefix[0], *row['backend'], 'ps', '-a', '--filter', 'label=autonomics.validation.session=' + session,
            '--filter', 'label=autonomics.validation.intent=' + row['token'], '--format=json']
        run = subprocess.run(command, capture_output=True, timeout=30)
        require(run.returncode == 0 and json.loads(run.stdout) == [], 'Owned method container remains or cannot be observed')
        observations.append(dict(token=row['token'], backend=row['backend'], actual_exit=run.returncode, remaining=0))
    require(file_identity(inventory) == before, 'Intent inventory changed during observation')
    write(output / 'owned-container-stops.json', observations)
    return observations


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'frozen-a-family-runtime'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    resource_admission(output)
    before = contract.source_records(contract.STUDY)
    code_before = sources()
    for name in ['r-runtime', 'python-runtime']:
        (output / name).mkdir()
    prefix = inspected_backend(output / 'r-runtime')
    runtime, prerequisites = raw.prerequisite_archives(Path.home() / '.local/state/autonomics/validation-archives')
    require(prefix == raw.backend(output / 'python-runtime', runtime), 'Both runtimes must use the same inspected owner backend')
    methods = definitions()
    vectors, reference, oracle = checked_oracle(Path.home() / '.local/state/autonomics/validation-archives')
    edges = contract.read_table(contract.STUDY / contract.SOURCES[0][0])
    original_inputs = [contract.STUDY / item[0] for item in contract.SOURCES]
    cases = []
    rds_paths = []
    first_positive = None
    for scenario in [*contract.SCENARIOS, 'REAL_FROZEN_NA_LEDGER']:
        directory = output / scenario
        directory.mkdir()
        request = directory / 'request.json'
        write(request, request_for(edges, scenario))
        assembled = execute(prefix, methods[KINDS[0]], [*original_inputs, request], directory / 'assemble')
        adjusted = execute(prefix, methods[KINDS[1]], [assembled[1], assembled[0], assembled[2], original_inputs[8]], directory / 'adjust')
        published = execute(prefix, methods[KINDS[2]], [*assembled[:3], *adjusted[:3], *original_inputs[:2]], directory / 'publish')
        compare_case(directory, scenario, assembled, adjusted, published, vectors, reference)
        rds_paths.append(adjusted[1])
        if first_positive is None:
            first_positive = (assembled, adjusted)
        cases.append(dict(scenario=scenario, methods=3, result_rows=564, correction_rows=840))
    refusals = negative_controls(prefix, methods, output, original_inputs, edges, first_positive)
    official_rds_readback(output, Path.home() / '.local/state/autonomics/validation-archives', rds_paths)
    stops = stopped(prefix, permanent, output, 9 + len(refusals))
    require(before == contract.source_records(contract.STUDY) and code_before == sources(), 'Frozen or adapter source changed')
    post = original_postcheck(output)
    write(output / 'verification.json', dict(status='SCOPED_FROZEN_FAMILY_THREE_STAGE_DIRECT_RUNTIME_PROVEN_DAG_PENDING',
        source_identities=before, code_identities=code_before, official_oracle=oracle, prerequisites=prerequisites,
        cases=cases, full_q_equal=2520, full_result_rows=1692, actual_method_containers=len(stops),
        full_official_RDS_vectors_read_back=18, full_official_RDS_values_exact=2520,
        expected_method_exit2_refusals=refusals,
        frozen_family_counts=contract.COUNTS, original_post_verifier=post, raw_GWAS_read=False,
        actual_DAG_executed=False, real_overlap_eligibility_assigned=False, MR_estimates_computed=False,
        production_restarted=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
