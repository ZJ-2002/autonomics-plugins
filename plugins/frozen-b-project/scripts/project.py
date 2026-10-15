"""Frozen v4.3.2 B LEGACY source intake and complete-family transport.

No fit, normalization, clinical label inference or scientific authorization.
"""
import csv
import copy
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path

INPUTS = ['config', 'manifest', 'samples', 'features', 'scope', 'design_certificate',
          'software_lock', 'r_dependencies', 'r_session', 'scientific_code',
          'scientific_rules', 'scope_decision', 'matrix', 'source_metadata',
          'g0_certificate', 'family_lock', 'restore_acceptance', 'runtime_manifest', 'byte_verifier']
OUTPUTS = ['config.json', 'expression.tsv', 'genes.tsv', 'samples.tsv', 'decisions.tsv', 'intake.json',
           'unadjusted-config.json', 'unadjusted-intake.json',
           'therapy_sensitivity-config.json', 'therapy_sensitivity-intake.json']
MODELS = {
    'primary': dict(formula='~group+age+sex', columns=['(Intercept)', 'groupcase', 'age', 'sexM'],
                    covariates=[dict(name='age', type='NUMERIC', levels=[]), dict(name='sex', type='CATEGORICAL', levels=['F', 'M'])],
                    role='LEGACY_EXPLORATORY_PRIMARY_MODEL'),
    'unadjusted': dict(formula='~group', columns=['(Intercept)', 'groupcase'], covariates=[], role='PRESPECIFIED_SENSITIVITY_ONLY'),
    'therapy_sensitivity': dict(formula='~group+age+sex+treatment', columns=['(Intercept)', 'groupcase', 'age', 'sexM', 'treatmentY'],
                    covariates=[dict(name='age', type='NUMERIC', levels=[]), dict(name='sex', type='CATEGORICAL', levels=['F', 'M']),
                                dict(name='treatment', type='CATEGORICAL', levels=['N', 'Y'])], role='PRESPECIFIED_SENSITIVITY_ONLY'),
}
SAMPLES = ('resource_id patient_id independent_unit_id independent_unit_basis sample_id assay_id group '
           'weight_loss_6mo_pct sex age diagnosis treatment tissue sampling_time measurement_date '
           'outcome_start_date outcome_end_date include reason source_metadata_file source_metadata_sha256').split()
FEATURES = ('feature_id source_probe_id identifier_type assay tissue cell_type contrast_id family_id included '
            'variable_in_selected_assay measurement_filter role').split()
GENES = 'matrix_row gene_id analysis_id family_id contrast_id estimand_id'.split()


def require(ok, message):
    if not ok:
        raise ValueError('Frozen B project: ' + message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    def bad(value):
        raise ValueError('nonfinite JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def identity(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def regular(path):
    path = Path(path).absolute()
    require(path.is_file() and not any(p.is_symlink() for p in [path, *path.parents]), 'regular file without symlink ancestors required')
    require(0 < path.stat().st_size <= 64 * 1024 ** 2, 'input byte budget exceeded')
    return path


def rows(raw, columns=None):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), delimiter='\t')
    require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames), 'duplicate/absent TSV headers')
    if columns is not None:
        require(reader.fieldnames == columns, 'TSV schema differs')
    result = list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in result), 'ragged TSV')
    return result


def table(columns, data):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, columns, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(data)
    return stream.getvalue().encode()


def model_record(lock, model):
    require(model in MODELS, 'only the three prespecified frozen models are permitted')
    spec = MODELS[model]
    rank = len(spec['columns'])
    return dict(model_id=model, model_formula=spec['formula'], family_role=spec['role'],
                model_columns=spec['columns'], rank=rank, residual_df=lock['primary_samples'] - rank)


def method_config(lock, hashes, model):
    model_record(lock, model)
    return dict(schema_version=1, protocol_version='4.3.2', status='FROZEN', method='LIMMA_EBAYES',
        expression_scale='log2_normalized', contrast_id=lock['contrast_id'], resource_id='GSE130563',
        source_archive_sha256=lock['files']['manifest']['sha256'], software_lock=lock['software_lock'],
        design=dict(numerator='case', denominator='control', covariates=copy.deepcopy(MODELS[model]['covariates']),
                    family_min_units=3, qr_tolerance=1e-8),
        method_parameters=dict(trend=True, robust=True, allowed_warning_messages=[]), input_sha256=hashes,
        limits=dict(max_expression_elements=10000000, max_input_file_bytes=64 * 1024 ** 2))


def intake(paths, lock):
    require(set(paths) == set(INPUTS), 'all actual project/source files required')
    paths = {name: regular(p) for name, p in paths.items()}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    refs = {name: identity(data) for name, data in raw.items()}
    require(all(refs[name]['sha256'] == lock['files'][name]['sha256'] for name in INPUTS), 'frozen source bytes differ')
    cfg = strict_json(raw['config'])
    require(cfg['status'] == 'LOCKED' and cfg['version'] == '4.3.2' and cfg['module'] == 'B', 'current frozen B configuration required')
    require(cfg['family_ids'] == ['B_TRANSCRIPTOME'] and cfg['resource_ids'] == [], 'current minimum scope differs; old ZIP registry cannot substitute')
    require(cfg['contrast_id'] == lock['contrast_id'] and cfg['estimand_id'] == 'E_B_DIS', 'contrast/estimand differs')
    require(cfg['model_formula'] == '~group+age+sex' and cfg['model_df'] == lock['residual_df'], 'primary frozen formula/df differs')
    require(cfg['sensitivities'] == ['unadjusted ~group', 'therapy ~group+age+sex+treatment'], 'prespecified frozen sensitivities differ')
    require(cfg['matrix_type'] == 'GENE_LEVEL_MICROARRAY_RMA_LOG2' and
            cfg['normalization'] == 'SOURCE_RMA_LOG2_NOT_RENORMALIZED_NO_RAW_COUNT_OR_GENE_LENGTH_MODEL', 'normalization/scale substitution')
    require(cfg['matrix_file'] == lock['files']['matrix']['relative_path'] and
            cfg['software_lock_file'] == lock['files']['software_lock']['relative_path'], 'frozen matrix/software path binding differs')
    require(cfg['transcriptome_method'] == 'limma3.68.5 lmFit+eBayes(trend=TRUE,robust=TRUE)', 'frozen official method differs')
    require(cfg['followup_exposure_at_lock'] == 'LEGACY_EXPLORATORY' and cfg['predefined_program_panel_enabled'] is False,
            'legacy history/program scope differs')
    require(cfg['correction'] == 'BH' and cfg['sensitivity_correction'] == 'BY' and cfg['q'] == .05 and
            cfg['raw_missing_p'] == 'NA' and cfg['adjustment_missing_p'] == 1, 'complete-family correction policy differs')
    bindings = [('manifest', 'input_manifest'), ('samples', 'sample_map'), ('features', 'feature_definition'),
                ('scope', 'discovery_scope'), ('scientific_code', 'scientific_code'), ('scientific_rules', 'scientific_rules')]
    require(all(cfg[prefix + '_sha256'] == refs[name]['sha256'] and
                cfg[prefix + '_file'] == lock['files'][name]['relative_path'] for name, prefix in bindings), 'config dependency identity differs')
    manifest = strict_json(raw['manifest'])
    require(isinstance(manifest, list) and all(set(r) == {'file', 'sha256'} for r in manifest), 'original input manifest schema differs')
    require(len({r['file'] for r in manifest}) == len(manifest), 'duplicate original manifest path')
    indexed = {r['file']: r['sha256'] for r in manifest}
    require(all(indexed.get(lock['files'][name]['relative_path']) == refs[name]['sha256']
                for name in ['matrix', 'source_metadata', 'samples', 'features', 'scope']), 'original manifest bytes do not bind actual files')
    scope = strict_json(raw['scope']); cert = strict_json(raw['design_certificate']); decision = strict_json(raw['scope_decision'])
    require(scope['N_primary'] == lock['primary_samples'] and scope['case_n'] == lock['case_n'] and scope['control_n'] == lock['control_n'], 'locked cohort counts differ')
    require(cert['matrix_genes'] == lock['gene_count'] and cert['source_samples'] == lock['source_samples'] and
            cert['primary_samples'] == lock['primary_samples'] and cert['case_n'] == lock['case_n'] and cert['control_n'] == lock['control_n'], 'certificate dimensions differ')
    primary = cert['designs']['primary']
    require(primary['columns'] == ['(Intercept)', 'groupcase', 'age', 'sexM'] and primary['rank'] == 4 and
            primary['residual_df'] == lock['residual_df'] and primary['identifiable'] is True, 'metadata design certificate differs')
    for model in MODELS:
        expected = model_record(lock, model)
        actual = cert['designs'][model]
        require(actual['columns'] == expected['model_columns'] and actual['rank'] == expected['rank'] and
                actual['residual_df'] == expected['residual_df'] and actual['identifiable'] is True and
                ''.join(actual['formula'].split()) == expected['model_formula'], 'prespecified model certificate differs')
    require(decision['investigator_scientific_signature'] is None, 'this entry is only the locked unsigned legacy scope')
    g0 = strict_json(raw['g0_certificate'])
    require(g0['status'] == 'G0_V432_MINIMUM_COMPLETE' and g0['B']['allowed'] is True and
            g0['B']['role'] == 'LEGACY_EXPLORATORY_FULL_FEATURE_DISEASE_ASSOCIATION' and
            g0['B']['independent_validation_allowed'] is False and g0['investigator_scientific_signature'] is None and
            g0['all_project_scientific_gates_passed'] is False and g0['full_denominators']['B_TRANSCRIPTOME'] == lock['gene_count'],
            'current B legacy permission/limitations certificate required')
    require(g0['B']['config_file'] == lock['files']['config']['relative_path'], 'certificate B configuration path differs')
    require(g0['family_lock_sha256'] == refs['family_lock']['sha256'] and
            g0['restore_evidence_sha256'] == refs['restore_acceptance']['sha256'] and
            g0['scientific_rules_sha256'] == refs['scientific_rules']['sha256'], 'certificate dependency bytes differ')
    runtime = strict_json(raw['runtime_manifest'])
    runtime_index = {r['path']: r for r in runtime['files']}
    require(len(runtime_index) == len(runtime['files']), 'duplicate runtime manifest entry')
    require(all(runtime_index[lock['files'][name]['relative_path']]['sha256'] == refs[name]['sha256'] and
                runtime_index[lock['files'][name]['relative_path']]['size_bytes'] == refs[name]['bytes']
                for name in INPUTS if name != 'runtime_manifest'), 'project runtime manifest does not bind B inputs')
    software = rows(raw['software_lock'])
    require(any(r['component'] == 'limma_edgeR_or_DESeq2' and r['version_or_commit'] == 'limma3.68.5;R4.6.1;statmod1.5.2'
                and r['status'] == 'LOCKED_V432_MINIMUM_SCOPE' for r in software), 'frozen software method lock differs')
    deps = rows(raw['r_dependencies'])
    require(all(any(r['package'] == p and r['version'] == v for r in deps) for p, v in lock['software_lock'].items() if p not in ['R', 'stats']), 'R dependency declarations differ')
    require('R version 4.6.1' in raw['r_session'].decode(), 'R session declaration differs')
    samples = rows(raw['samples'], SAMPLES); features = rows(raw['features'], FEATURES)
    require(len(samples) == lock['primary_samples'] and len({r['sample_id'] for r in samples}) == len(samples) and
            len({r['independent_unit_id'] for r in samples}) == len(samples), 'complete unique primary sample/unit axis required')
    require(sum(r['group'] == 'case' for r in samples) == lock['case_n'] and sum(r['group'] == 'control' for r in samples) == lock['control_n'], 'actual locked groups differ')
    require(all(r['include'] == 'YES' and r['sex'] in ['F', 'M'] and r['treatment'] in ['N', 'Y'] and math.isfinite(float(r['age'])) and
                r['source_metadata_sha256'] == refs['source_metadata']['sha256'] for r in samples), 'sample metadata/covariates differ')
    require(len(features) == lock['gene_count'] and len({r['feature_id'] for r in features}) == len(features) and
            len({r['source_probe_id'] for r in features}) == len(features), 'complete unique frozen gene universe required')
    require(all(r['included'] == 'YES' and r['family_id'] == 'B_TRANSCRIPTOME' and r['contrast_id'] == cfg['contrast_id'] and
                r['role'] == 'LEGACY_EXPLORATORY' and r['measurement_filter'] == 'ALL_SOURCE_ROWS_UNIQUE_ENTREZ_AND_FINITE;NO_EFFECT_OR_PROGRAM_SELECTION'
                for r in features), 'frozen feature scope/legacy roles differ')
    # Source RMA values are copied verbatim as decimal fields, never renormalized.
    with gzip.GzipFile(fileobj=io.BytesIO(raw['matrix'])) as matrix_stream:
        uncompressed = matrix_stream.read(64 * 1024 ** 2 + 1)
    require(len(uncompressed) <= 64 * 1024 ** 2, 'uncompressed matrix byte budget exceeded')
    text = uncompressed.decode()
    lines = text.splitlines()
    begin = [i for i, line in enumerate(lines) if line == '!series_matrix_table_begin']
    end = [i for i, line in enumerate(lines) if line == '!series_matrix_table_end']
    require(len(begin) == len(end) == 1 and end[0] > begin[0], 'exact GEO series matrix table required')
    reader = csv.reader(lines[begin[0] + 1:end[0]], delimiter='\t')
    header = next(reader)
    require(header[0] == 'ID_REF' and len(header) == lock['source_samples'] + 1 and len(set(header)) == len(header), 'complete source assay axis differs')
    ids = [r['sample_id'] for r in samples]
    require(set(ids) <= set(header[1:]), 'locked primary assay absent from source matrix')
    positions = [header.index(s) for s in ids]
    expression = []
    for i, row in enumerate(reader):
        require(i < len(features) and len(row) == len(header) and row[0] == features[i]['source_probe_id'], 'source probe order/universe differs')
        require(all(math.isfinite(float(v)) for v in row[1:]), 'nonfinite source expression; no imputation/deletion')
        expression.append({'gene_id': features[i]['feature_id'], **{s: row[j] for s, j in zip(ids, positions, strict=True)}})
    require(len(expression) == len(features), 'incomplete source matrix rows')
    genes = [dict(zip(GENES, [str(i + 1), r['feature_id'], cfg['contrast_id'] + ':' + r['feature_id'],
                            'B_TRANSCRIPTOME', cfg['contrast_id'], 'E_B_DIS'], strict=True)) for i, r in enumerate(features)]
    decisions = [dict(sample_id=r['sample_id'], independent_unit_id=r['independent_unit_id'], include='YES', reason=r['reason']) for r in samples]
    payloads = {'expression.tsv': table(['gene_id', *ids], expression), 'genes.tsv': table(GENES, genes),
                'samples.tsv': raw['samples'], 'decisions.tsv': table(['sample_id', 'independent_unit_id', 'include', 'reason'], decisions)}
    hashes = {name: identity(payloads[name + '.tsv'])['sha256'] for name in ['expression', 'genes', 'samples', 'decisions']}
    receipt = dict(scope='FROZEN_V432_B_LEGACY_SOURCE_INTAKE_NOT_QUALIFICATION', source_files=refs,
        project_lock=identity(canonical(lock)), frozen_scientific_code_executed=False,
        method_transport='EXISTING_NORMALIZED_LIMMA_COMPONENT_WITH_PARITY_REVIEW_REQUIRED',
        input_sha256=hashes,
        source_samples=header[1:], primary_samples=ids, gene_count=len(genes),
        result_exposure='SEEN',
        original_full_project_byte_verifier_executed=False,
        original_full_project_byte_audit_verified=False,
        metadata_certificate_is_not_full_scientific_permission=True,
        scientific_authorization=False, formal_authorized=False, G0=False)
    for model in MODELS:
        config_name = 'config.json' if model == 'primary' else model + '-config.json'
        receipt_name = 'intake.json' if model == 'primary' else model + '-intake.json'
        payloads[config_name] = canonical(method_config(lock, hashes, model))
        payloads[receipt_name] = canonical({**receipt, **model_record(lock, model),
            'config_sha256': identity(payloads[config_name])['sha256']})
    require(all(identity(p.read_bytes()) == refs[name] for name, p in paths.items()), 'input changed during intake')
    return payloads


def family(raw, lock):
    require(set(raw) == {'results', 'genes', 'intake', 'limma_audit'}, 'four actual family inputs required')
    genes = rows(raw['genes'], GENES); results = rows(raw['results'])
    intake_receipt = strict_json(raw['intake']); audit = strict_json(raw['limma_audit'])
    model = intake_receipt['model_id']
    expected_model = model_record(lock, model)
    require(all(intake_receipt.get(k) == v for k, v in expected_model.items()) and intake_receipt['result_exposure'] == 'SEEN',
            'prespecified model/role/history required; old conditional roles forbidden')
    expected_config = identity(canonical(method_config(lock, intake_receipt['input_sha256'], model)))['sha256']
    require(intake_receipt['config_sha256'] == expected_config, 'model must bind its exact prespecified configuration')
    require(intake_receipt['project_lock'] == identity(canonical(lock)) and intake_receipt['gene_count'] == lock['gene_count'], 'actual frozen project identity differs')
    require(identity(raw['genes'])['sha256'] == intake_receipt['input_sha256']['genes'] and audit['input_sha256'] == intake_receipt['input_sha256'] and
            audit['config_sha256'] == intake_receipt['config_sha256'] and audit['software_lock'] == lock['software_lock'], 'same actual intake/config/software audit required')
    require(audit['stage'] == 'LIMMA' and audit['method_executed'] is True and audit['formal_authorized'] is False, 'actual official limma method receipt required')
    design = audit['design']
    require(design['model_columns'] == expected_model['model_columns'] and design['rank'] == expected_model['rank'] and
            design['residual_df'] == expected_model['residual_df'] and design['identifiable'] is True and
            ''.join(audit['model_formula'].split()) == expected_model['model_formula'], 'actual prespecified model design differs')
    require(audit['plugin_transport_output_sha256']['results'] == identity(raw['results'])['sha256'], 'actual limma output hash differs')
    require(len(results) == len(genes) == lock['gene_count'] and len({r['analysis_id'] for r in genes}) == len(genes), 'complete family denominator required')
    require(all(all(g[key] == r[key] for key in GENES) for g, r in zip(genes, results, strict=True)), 'actual full gene registry/results order differs')
    adjustment = audit.get('family_adjustment')
    expected_adjustment = dict(backend='stats::p.adjust', R=lock['software_lock']['R'],
        stats=lock['software_lock']['stats'], methods=['BH', 'BY'], n_total=lock['gene_count'],
        missing_p_denominator_value=1)
    require(adjustment == expected_adjustment and type(adjustment['n_total']) is int and
            type(adjustment['missing_p_denominator_value']) is int,
            'actual complete official R adjustment receipt required; no native fallback')
    for row in results:
        if row['status'] == 'ESTIMATED':
            p = float(row['raw_p']); require(math.isfinite(p) and 0 <= p <= 1, 'invalid estimated p')
            require(row['family_p'] == row['raw_p'], 'estimated gene p unavailable to complete family')
        else:
            require(row['status'] == 'NOT_ESTIMABLE' and row['raw_p'] == row['family_p'] == 'NA', 'non-estimable rows must retain missing raw p')
            p = 1.
        require('q_BH' in row and 'q_BY' in row, 'official adjusted columns required')
        qbh, qby = float(row['q_BH']), float(row['q_BY'])
        require(math.isfinite(qbh) and math.isfinite(qby) and 0 <= p <= qbh <= qby <= 1,
                'official adjusted values must preserve the complete family and missing-as-one policy')
        row.update(role=expected_model['family_role'], model_id=model,
                   status='ESTIMATED_LEGACY_ASSOCIATION' if row['status'] == 'ESTIMATED' else row['status'])
        # Retain component columns and expose every original f7 full-result field.
        for name, component in {'beta': 'log2_expression_difference', 'moderated_se': 'standard_error',
                                'df': 'moderated_df', 'lo': 'ci_lower', 'hi': 'ci_upper', 'p_raw': 'raw_p'}.items():
            row[name] = row[component]
    receipt = dict(scope='COMPLETE_FROZEN_B_LEGACY_FAMILY_BH_BY_NOT_SCIENTIFIC_AUTHORIZATION',
        gene_count=len(results), missing_p_denominator_value=1, **expected_model,
        primary_family_denominator=lock['gene_count'], adjustment_scope='ONE_MODEL_FULL_GENE_UNIVERSE_NOT_POOLED_ACROSS_MODELS',
        family_adjustment=adjustment,
        source_files={name: identity(data) for name, data in raw.items()}, project_lock=identity(canonical(lock)),
        frozen_scientific_code_executed=False, scientific_authorization=False, formal_authorized=False, G0=False)
    return {'family.tsv': table(list(results[0]), results), 'family-audit.json': canonical(receipt)}


def entry(stage, lock):
    names = INPUTS if stage == 'INTAKE' else ['results', 'genes', 'intake', 'limma_audit']
    paths = {names[0]: regular(os.environ['AUTONOMICS_INPUT0'])}
    paths.update({name: regular(os.environ['AUTONOMICS_INPUT' + str(i)]) for i, name in enumerate(names) if i})
    payloads = intake(paths, lock) if stage == 'INTAKE' else family({n: p.read_bytes() for n, p in paths.items()}, lock)
    outputs = OUTPUTS if stage == 'INTAKE' else ['family.tsv', 'family-audit.json']
    targets = [Path(os.environ['AUTONOMICS_OUTPUT0']).absolute()]
    targets.extend(Path(os.environ['AUTONOMICS_OUTPUT' + str(i)]).absolute() for i in range(1, len(outputs)))
    require([p.name for p in targets] == outputs and len({p.parent for p in targets}) == 1, 'exact output set required')
    require(not any(p.exists() or p.is_symlink() for p in targets) and not any(p.is_symlink() for p in targets[0].parents), 'output already exists/symlink')
    parent = targets[0].parent; parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / ('.frozen-b-' + stage.lower() + '-complete'); bundle.mkdir()
    for name, data in payloads.items():
        (bundle / name).write_bytes(data)
    published = {}
    success = False
    try:
        for name, target in zip(outputs, targets, strict=True):
            source = bundle / name
            expected = source.stat()
            os.link(source, target)
            published[target] = (expected.st_dev, expected.st_ino)
            actual = target.lstat()
            require((actual.st_dev, actual.st_ino) == published[target], 'published output was replaced')
        for name, target in zip(outputs, targets, strict=True):
            actual = target.lstat()
            require((actual.st_dev, actual.st_ino) == published[target] and
                    target.read_bytes() == payloads[name], 'complete published output was replaced or modified')
        success = True
    finally:
        if not success:
            for target, expected in published.items():
                try:
                    actual = target.lstat()
                    if ((actual.st_dev, actual.st_ino) == expected and
                            target.read_bytes() == payloads[target.name]):
                        target.unlink()
                except FileNotFoundError:
                    pass

