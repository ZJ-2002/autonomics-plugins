#!/usr/bin/env python3
"""Bounded synthetic method check using an existing locked R library."""
import argparse
import csv
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import importlib.util

PLUGIN = Path(__file__).resolve().parents[1]
LOCK = json.loads((PLUGIN / 'reuse-lock.json').read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path, columns, rows):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, columns, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def solve(matrix, rhs):
    rows = [list(row) + [y] for row, y in zip(matrix, rhs, strict=True)]
    for i in range(len(rows)):
        pivot = max(range(i, len(rows)), key=lambda j: abs(rows[j][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        assert abs(rows[i][i]) > 1e-10
        rows[i] = [v / rows[i][i] for v in rows[i]]
        for j in range(len(rows)):
            if i != j:
                factor = rows[j][i]
                rows[j] = [a - factor * b for a, b in zip(rows[j], rows[i], strict=True)]
    return [row[-1] for row in rows]


def run(library, output, frozen_code, *, execution_scope='HOST'):
    assert execution_scope in ['HOST', 'OCI']
    output.mkdir()
    env = {**os.environ, 'R_LIBS_USER': str(library), 'R_PROFILE_USER': '/dev/null',
           'R_ENVIRON_USER': '/dev/null'}
    versions = subprocess.run(['Rscript', '--vanilla', '-e',
        'cat(jsonlite::toJSON(c(list(R=as.character(getRversion())),setNames(lapply(c("limma","statmod","jsonlite","digest","stats"),function(p) as.character(packageVersion(p))),c("limma","statmod","jsonlite","digest","stats"))),auto_unbox=TRUE))'],
        env=env, capture_output=True, text=True, check=True)
    assert json.loads(versions.stdout) == LOCK['software_lock'], 'actual package lock differs'
    ids = ['SYN_A' + str(i) for i in range(8)]
    ages = [25, 31, 29, 43, 28, 37, 35, 46]
    sample_columns = ('resource_id patient_id independent_unit_id independent_unit_basis sample_id assay_id group '
        'weight_loss_6mo_pct sex age diagnosis treatment tissue sampling_time measurement_date outcome_start_date '
        'outcome_end_date include reason source_metadata_file source_metadata_sha256').split()
    samples = []
    for i, sample in enumerate(ids):
        row = dict.fromkeys(sample_columns, 'SYNTHETIC')
        row.update(resource_id='SYN_RESOURCE', sample_id=sample, assay_id=sample,
                   independent_unit_id=sample, group='case' if i < 4 else 'control',
                   sex='F' if i % 2 == 0 else 'M', age=str(ages[i]), include='YES',
                   treatment='N' if (i // 2) % 2 == 0 else 'Y')
        samples.append(row)
    genes, expression = [], []
    for i in range(25):
        gene = 'SYN_G' + str(i)
        genes.append(dict(matrix_row=str(i + 1), gene_id=gene, analysis_id='SYN_CONTRAST:' + gene,
                          family_id='B_TRANSCRIPTOME', contrast_id='SYN_CONTRAST', estimand_id='E_B_DIS'))
        expression.append({'gene_id': gene, **{sample: ('5' if i == 24 else repr(
            5 + i * .025 + (i % 7 - 3) * .35 * (j < 4) + .015 * ages[j] + .12 * (j % 2)
            + math.sin(i * 2 + j) * .15 + ((j * i) % 11) * .02)) for j, sample in enumerate(ids)}})
    table(output / 'samples.tsv', sample_columns, samples)
    table(output / 'genes.tsv', list(genes[0]), genes)
    table(output / 'expression.tsv', ['gene_id', *ids], expression)
    table(output / 'decisions.tsv', ['sample_id', 'independent_unit_id', 'include', 'reason'],
          [dict(sample_id=s, independent_unit_id=s, include='YES', reason='SYNTHETIC') for s in ids])
    inputs = [output / (name + '.tsv') for name in ('expression', 'genes', 'samples', 'decisions')]
    project_dir = PLUGIN.parent / 'frozen-b-project'
    project_lock = json.loads((project_dir / 'project-lock.json').read_bytes())
    spec = importlib.util.spec_from_file_location('frozen_b_family', project_dir / 'scripts/project.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    toy_lock = copy.deepcopy(project_lock)
    toy_lock.update(gene_count=25, primary_samples=8, case_n=4, control_n=4, residual_df=4, contrast_id='SYN_CONTRAST')
    toy_lock['files']['manifest']['sha256'] = 'a' * 64
    hashes = {name: sha(path) for name, path in zip(('expression','genes','samples','decisions'), inputs, strict=True)}
    configurations = {model: module.method_config(toy_lock, hashes, model) for model in module.MODELS}
    config_path = output / 'config.json'
    inputs.insert(0, config_path)

    def entry(stage, target, actual_inputs, expected=0):
        target.mkdir()
        names = ['audit.json'] if stage == 'design' else ['results.tsv', 'audit.json', 'official.rds']
        local = {**env, **{f'AUTONOMICS_INPUT{i}': str(p) for i, p in enumerate(actual_inputs)},
                 **{f'AUTONOMICS_OUTPUT{i}': str(target / n) for i, n in enumerate(names)}}
        result = subprocess.run(['Rscript', '--vanilla', str(PLUGIN / 'scripts' / ('run-' + stage + '.R'))],
                                env=local, capture_output=True, text=True)
        (target / 'stderr.txt').write_text(result.stderr)
        assert result.returncode == expected, result.stderr
        return target

    # Evaluate the verbatim frozen numerical block on SYN inputs in a separate
    # R process. The original run-B source/authorization guards are not run.
    assert sha(frozen_code) == project_lock['files']['scientific_code']['sha256']
    frozen = frozen_code.read_text()
    start = frozen.index('  for(model in c("primary","unadjusted","therapy_sensitivity")) {')
    end = frozen.index('\n} else stop(', start)
    block = frozen[start:end]
    frozen_copy = output / 'frozen-scientific-code.R'
    frozen_copy.write_bytes(frozen_code.read_bytes())
    parity_dir = output / 'frozen-numeric-block'
    parity_dir.mkdir()
    parity_script = output / 'frozen-numeric-parity.R'
    parity_script.write_text('library(limma)\nargs<-commandArgs(TRUE)\n'
        'tab<-read.delim(args[1],check.names=FALSE);expr<-as.matrix(tab[,-1]);rownames(expr)<-tab$gene_id\n'
        'meta<-read.delim(args[2],check.names=FALSE);meta$group<-factor(meta$group,levels=c("control","case"));'
        'meta$sex<-factor(meta$sex,levels=c("F","M"));meta$treatment<-factor(meta$treatment,levels=c("N","Y"))\n'
        'variable<-apply(expr,1,function(x)length(unique(x))>1);dest<-args[3]\n'
        'adjust_full<-function(p,method="BH") p.adjust(ifelse(is.finite(p),p,1),method=method)\n' + block + '\n')
    parity = subprocess.run(['Rscript', '--vanilla', str(parity_script), str(output / 'expression.tsv'),
        str(output / 'samples.tsv'), str(parity_dir)], env=env, capture_output=True, text=True)
    (output / 'frozen-numeric-parity-stderr.txt').write_text(parity.stderr)
    assert parity.returncode == 0, parity.stderr
    model_checks = {}
    for model in module.MODELS:
        config = configurations[model]
        config_path = output / (model + '-config.json')
        inputs[0] = config_path
        config_path.write_bytes(canonical(config))
        design = entry('design', output / (model + '-design'), inputs)
        design_audit = json.loads((design / 'audit.json').read_text())
        expected_design = module.model_record(toy_lock, model)
        assert design_audit['design']['rank'] == expected_design['rank']
        assert design_audit['design']['residual_df'] == expected_design['residual_df']
        fit = entry('limma', output / (model + '-fit'), [*inputs, design / 'audit.json'])
        rows = list(csv.DictReader(io.StringIO((fit / 'results.tsv').read_text()), delimiter='\t'))
        assert [r['gene_id'] for r in rows] == [r['gene_id'] for r in genes]
        x = [[1., float(j < 4)] for j in range(8)]
        if model != 'unadjusted':
            x = [row + [float(ages[j]), float(j % 2)] for j,row in enumerate(x)]
        if model == 'therapy_sensitivity':
            x = [row + [float((j // 2) % 2)] for j,row in enumerate(x)]
        width = len(x[0])
        gram = [[math.fsum(v[a] * v[b] for v in x) for b in range(width)] for a in range(width)]
        for source, row in zip(expression[:-1], rows[:-1], strict=True):
            y = [float(source[s]) for s in ids]
            beta = solve(gram, [math.fsum(v[j] * value for v,value in zip(x,y,strict=True)) for j in range(width)])
            assert abs(beta[1] - float(row['log2_expression_difference'])) < 1e-10
            assert row['status'] == 'ESTIMATED' and row['family_p'] == row['raw_p']
        assert rows[-1]['raw_p'] == rows[-1]['family_p'] == 'NA'
        assert rows[-1]['reason'] == 'CONSTANT_EXPRESSION'
        audit = json.loads((fit / 'audit.json').read_text())
        assert audit['design_receipt_sha256'] == sha(design / 'audit.json')
        assert audit['method_executed'] is True and audit['formal_authorized'] is False
        rds = subprocess.run(['Rscript','--vanilla','-e',
            'x<-readRDS(commandArgs(TRUE)[1]);stopifnot(length(x$full_gene_ids)==25L,length(x$variable_gene_ids)==24L,is.list(x$fit),length(x$fit$s2.post)==24L);cat("RDS_OK")',
            str(fit / 'official.rds')], env=env, capture_output=True, text=True, check=True)
        assert rds.stdout == 'RDS_OK'
        reference = list(csv.DictReader(io.StringIO((parity_dir / ('FULL_TRANSCRIPTOME_' + model + '.tsv')).read_text()), delimiter='\t'))
        synthetic_intake = dict(**expected_design, result_exposure='SEEN',
            project_lock=module.identity(module.canonical(toy_lock)), gene_count=25,
            input_sha256=config['input_sha256'], config_sha256=sha(config_path))
        (output / (model + '-intake.json')).write_bytes(module.canonical(synthetic_intake))
        family_inputs = dict(results=(fit / 'results.tsv').read_bytes(), genes=(output / 'genes.tsv').read_bytes(),
            intake=module.canonical(synthetic_intake), limma_audit=(fit / 'audit.json').read_bytes())
        family = module.family(family_inputs, toy_lock)
        completed = module.rows(family['family.tsv'])
        target = output / (model + '-family'); target.mkdir()
        for name,content in family.items(): (target / name).write_bytes(content)
        for expected,actual in zip(reference,completed,strict=True):
            assert expected['gene_id'] == actual['gene_id'] and expected['status'] == actual['status'] and expected['role'] == actual['role']
            for name in ['beta','moderated_se','df','lo','hi','p_raw','q_BH','q_BY']:
                if expected[name] == 'NA': assert actual[name] == 'NA'
                else: assert math.isclose(float(expected[name]),float(actual[name]),rel_tol=1e-11,abs_tol=1e-12), (model,name)
        bad_receipt = {**synthetic_intake, 'model_id':'unadjusted' if model != 'unadjusted' else 'primary'}
        bad_role = {**synthetic_intake, 'family_role':'PRESPECIFIED_SENSITIVITY_ONLY' if model == 'primary' else 'LEGACY_EXPLORATORY_PRIMARY_MODEL'}
        for bad in [bad_receipt,bad_role]:
            try: module.family({**family_inputs,'intake':module.canonical(bad)},toy_lock)
            except ValueError: pass
            else: raise AssertionError('mutated model/role accepted')
        model_checks[model] = dict(rank=expected_design['rank'], residual_df=expected_design['residual_df'],
            config_sha256=sha(config_path), intake_sha256=sha(output / (model + '-intake.json')),
            independent_ols_coefficients_verified=True, actual_design_binding_verified=True, official_rds_readback_verified=True,
            beta_se_df_ci_p_complete_bh_by_parity_verified=True, complete_gene_rows=25, constant_na_as_one_verified=True,
            mutated_model_role_rejected=True)
        if model == 'primary': primary_audit = design_audit
    config_path = output / 'config.json'; inputs[0] = config_path
    config = configurations['primary']; config_path.write_bytes(canonical(config)); design_audit = primary_audit
    for key, value in [('expression_scale', 'raw_integer_counts'), ('software_lock', {**LOCK['software_lock'], 'limma': '3.66.0'})]:
        config_path.write_bytes(canonical({**config, key: value}))
        target = entry('design', output / ('reject-' + key), inputs, 2)
        assert not (target / 'audit.json').exists()
    config_path.write_bytes(canonical(config))
    bad = output / 'bad-design.json'
    bad.write_bytes(canonical({**design_audit, 'config_sha256': '0' * 64}))
    target = entry('limma', output / 'reject-stale-design', [*inputs, bad], 2)
    assert not (target / 'results.tsv').exists()
    evidence = dict(scope='SYNTHETIC_' + execution_scope + '_NORMALIZED_LIMMA_METHOD_TRANSPORT_ONLY',
        software_lock=json.loads(versions.stdout), gene_rows=25, estimated_rows=24, constant_rows=1,
        independent_ols_coefficients_verified=True, actual_design_binding_verified=True,
        official_rds_readback_verified=True, scale_software_stale_design_rejections_verified=True,
        frozen_numerical_block_sha256=hashlib.sha256(block.encode()).hexdigest(),
        frozen_scientific_code_sha256=sha(frozen_code),
        frozen_primary_beta_se_df_ci_p_and_complete_bh_by_parity_verified=True,
        all_three_frozen_models_parity_verified=True, models=model_checks, primary_family_not_pooled=True,
        whole_frozen_scientific_program_executed=False,
        actual_oci_image_store_verified=False,
        actual_container_execution_verified=execution_scope == 'OCI',
        independent_empirical_bayes_prior_verified=False, real_source_qualified=False,
        scientific_authorization=False, G0=False,
        source_files={str(path.relative_to(PLUGIN.parent.parent)): dict(sha256=sha(path), bytes=path.stat().st_size)
                      for path in [Path(__file__), PLUGIN / 'reuse-lock.json',
                                   *sorted((PLUGIN / 'scripts').glob('*.R')),
                                   project_dir / 'scripts/project.py', project_dir / 'project-lock.json']},
        files={p.relative_to(output).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
               for p in sorted(output.rglob('*')) if p.is_file()})
    (output / 'METHOD_TOY_EVIDENCE.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--frozen-code', type=Path, required=True)
    args = parser.parse_args()
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent:
        parser.error('run via the existing managed validation session')
    with tempfile.TemporaryDirectory(prefix='normalized-limma-toy-', dir=os.environ['TMPDIR']) as scratch:
        target = Path(scratch) / 'method'
        run(args.library.resolve(strict=True), target, args.frozen_code.resolve(strict=True))
        # The real fixed ports are hard links. Mandatory archive evidence must
        # consist of independent regular files; copy bytes only after checks.
        shutil.copytree(target, Path(permanent) / 'normalized-limma-toy')
