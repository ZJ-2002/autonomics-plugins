import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SESSION = '6c469b6c101c472ba60a8b5df077d780'
REFERENCE_SEAL = 'dca66ac064d61286b5aa1519247113aa40ee720aaa64dc6a76e0c63de0b1f536'
PREFIX = 'permanent/official-r-stats-publication/'


R_DRIVER = r'''
root <- commandArgs(TRUE)[1]
evidence <- commandArgs(TRUE)[2]
stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("stats")) == "4.6.1")
functions <- c("t.test.default", "cor.test.default", "var.test.default", "wilcox.test.default", "prop.test", "p.adjust")
saveRDS(setNames(lapply(functions, function(name) {
  method <- get(name, asNamespace("stats"))
  list(body = deparse(body(method)), formals = deparse(formals(method)))
}), functions), file.path(evidence, "host-stats-function-bodies.RDS"), version=3)
strict_numeric <- function(actual, expected) {
  if (is.numeric(expected)) {
    stopifnot(is.numeric(actual), length(actual) == length(expected),
      identical(is.na(actual), is.na(expected)), identical(is.nan(actual), is.nan(expected)),
      identical(is.infinite(actual), is.infinite(expected)))
    infinite <- is.infinite(expected)
    stopifnot(all(actual[infinite] == expected[infinite]))
    finite <- is.finite(expected)
    zero <- finite & expected == 0
    stopifnot(all(actual[zero] == 0))
    nonzero <- finite & expected != 0
    stopifnot(all(sign(actual[nonzero]) == sign(expected[nonzero])))
    tolerance <- pmax(abs(expected[nonzero]) * 1e-12, .Machine$double.xmin * .Machine$double.eps)
    stopifnot(all(abs(actual[nonzero] - expected[nonzero]) <= tolerance))
    return(length(expected))
  }
  if (is.list(expected)) {
    stopifnot(is.list(actual), identical(names(actual), names(expected)), length(actual) == length(expected))
    return(sum(vapply(seq_along(expected), function(index) strict_numeric(actual[[index]], expected[[index]]), numeric(1))))
  }
  0
}
cases <- read.delim(file.path(root,"cases.tsv"), colClasses="character", na.strings=NULL)
answers <- list()
checks_file <- file.path(evidence,"method-checks.tsv")
for (index in seq_len(nrow(cases))) {
  record <- cases[index,]
  directory <- file.path(root,"cases",record$id)
  retained <- file.path(evidence,"cases",record$id)
  dir.create(retained,recursive=TRUE)
  cat(paste(index,record$id,"STARTED",sep="\t"),"\n",file=file.path(evidence,"case-progress.tsv"),append=TRUE,sep="")
  fixture <- expected <- NULL
  warnings <- character()
  reference_error <- NULL
  negative <- record$negative == "true"
  if (!negative || record$oracle_policy != "UNCHANGED_REFUSAL") {
    fixture <- dget(file.path(directory,"reference-fixture.R"))
    expected <- tryCatch(withCallingHandlers(do.call(get(fixture$function_name,asNamespace("stats")),fixture$args),
      warning=function(condition) {
        warnings <<- c(warnings,conditionMessage(condition))
        invokeRestart("muffleWarning")
      }),error=function(condition) { reference_error <<- conditionMessage(condition); NULL })
    if (record$oracle_policy != "UNCHANGED_REFUSAL") {
      negative <- !is.null(reference_error) ||
        any(grepl("cannot compute exact",warnings,ignore.case=TRUE)) ||
        is.null(expected$p.value) || !is.finite(expected$p.value)
    } else stopifnot(is.null(reference_error))
    saveRDS(list(fit=expected,arguments=fixture$args,warnings=warnings,error=reference_error),
      file.path(retained,"independent-current-R-reference.RDS"),version=3)
  }
  writeLines(c(paste0("legacy_negative=",record$negative),paste0("expected_negative=",negative),
    paste0("policy=",record$oracle_policy),paste0("reference_error=",reference_error),
    paste0("reference_warning=",warnings)),file.path(retained,"reference-decision.txt"))
  Sys.setenv(STATISTICS_OPERATION=record$operation,
    AUTONOMICS_INPUT0=file.path(directory,"input0.tsv"),
    AUTONOMICS_INPUT1=file.path(directory,"input1.tsv"))
  outputs <- file.path(retained,c("statistics.tsv","parameters.tsv","statistics.RDS","statistics.log","audit.tsv"))
  do.call(Sys.setenv,as.list(setNames(outputs,paste0("AUTONOMICS_OUTPUT",0:4))))
  status <- suppressWarnings(system2("Rscript",c("--vanilla",shQuote(file.path(root,"statistics.R"))),
    stdout=file.path(retained,"child.stdout"),stderr=file.path(retained,"child.stderr")))
  cat(paste(index,record$id,paste0("EXIT_",status),sep="\t"),"\n",file=file.path(evidence,"case-progress.tsv"),append=TRUE,sep="")
  compared <- 0
  if (negative) {
    stopifnot(status != 0L, !any(file.exists(outputs[1:3])), all(file.exists(outputs[4:5])))
    audit <- read.delim(outputs[5],colClasses="character",na.strings=NULL)
    stopifnot(audit$value[audit$key == "status"] == "BLOCKED")
    if (record$id == "adjust-over-current-row-limit") {
      stopifnot(grepl("operation row limit",audit$value[audit$key == "message"],fixed=TRUE))
    }
  } else {
    stopifnot(status == 0L, all(file.exists(outputs)))
    actual <- readRDS(outputs[3])
    stopifnot(isTRUE(all.equal(actual$fit,expected,tolerance=1e-12,check.attributes=TRUE)),
      isTRUE(all.equal(actual$arguments[sort(names(actual$arguments))],fixture$args[sort(names(fixture$args))],tolerance=1e-12)),
      identical(actual$row_id,fixture$row_ids),identical(actual$warnings,warnings))
    compared <- strict_numeric(actual$fit,expected)
    summary <- read.delim(outputs[1],colClasses="character",na.strings=NULL,check.names=FALSE)
    if (record$operation == "adjust") {
      stopifnot(identical(names(summary),c("test_id","p_value","p_adj","reject","family_n","method","status")),
        identical(summary$test_id,fixture$row_ids),nrow(summary) == length(expected))
      strict_numeric(as.numeric(summary$p_adj),as.numeric(expected))
    }
    audit <- read.delim(outputs[5],colClasses="character",na.strings=NULL)
    stopifnot(audit$value[audit$key == "status"] == "COMPLETED",
      audit$value[audit$key == "stats_version"] == "4.6.1")
  }
  answers[[index]] <- data.frame(id=record$id,operation=record$operation,legacy_negative=record$negative,
    negative=if (negative) "true" else "false", oracle_policy=record$oracle_policy,
    actual_exit=status,full_reference_compared=!negative,numeric_values_compared=compared)
  write.table(answers[[index]],checks_file,sep="\t",row.names=FALSE,quote=FALSE,
    append=index > 1L,col.names=index == 1L)
}
'''


def require(value, message):
    if not value:
        raise RuntimeError(message)


def identity(payload):
    return dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation session required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'r-stats-current-r-host'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    archive = Path.home() / '.local/state/autonomics/validation-archives' / REFERENCE_SESSION
    receipt = json.loads((archive / 'SESSION.json').read_text())
    manifest_bytes = (archive / 'artifacts/MANIFEST.json').read_bytes()
    require(receipt['state'] == 'CLEANED' and receipt['worker_exit_status'] == 0
            and receipt['manifest_sha256'] == REFERENCE_SEAL and identity(manifest_bytes)['sha256'] == REFERENCE_SEAL,
            'Exact successful legacy fixture seal required')
    manifest = json.loads(manifest_bytes)
    retained = []

    def member(name):
        relative = PREFIX + name
        payload = (archive / 'artifacts' / relative).read_bytes()
        require(identity(payload) == manifest['files'][relative], 'Selected frozen fixture identity changed')
        retained.append(dict(member=relative, **identity(payload)))
        return payload

    import io
    cases_payload = member('cases.tsv')
    cases = list(csv.DictReader(io.StringIO(cases_payload.decode()), delimiter='\t'))
    require(len(cases) == 164 and len({row['id'] for row in cases}) == 164, 'Existing fixture denominator differs')
    scratch = Path(os.environ['TMPDIR']) / 'r-stats-current-r-host'
    scratch.mkdir(mode=0o700)
    source = ROOT / 'plugins/r-stats/scripts/statistics.R'
    manifest_path = ROOT / 'plugins/r-stats/manifest.toml'
    source_payload = source.read_bytes()
    manifest_payload = manifest_path.read_bytes()
    driver_payload = Path(__file__).read_bytes()
    (scratch / 'statistics.R').write_bytes(source_payload)
    (output / 'statistics.R').write_bytes(source_payload)
    (output / 'manifest.toml').write_bytes(manifest_payload)
    requalified = []
    exact_cases = {'cor-spearman-ties-true', 'cor-kendall-ties-true', 'wilcox-true-ties-blocked', 'wilcox-true-zero-blocked'}
    allowed_requalifications = exact_cases | {'prop-missing-pair-NULL-official-error'}

    def contract_keys(identifier):
        payload = member('cases/' + identifier + '/input1.tsv')
        return {row['key']: row['value'] for row in csv.DictReader(io.StringIO(payload.decode()), delimiter='\t')}

    for row in cases:
        require(re.fullmatch(r'[A-Za-z0-9_.+-]+', row['id']), 'Unsafe fixture identity')
        directory = scratch / 'cases' / row['id']
        directory.mkdir(parents=True, mode=0o700)
        names = ['input0.tsv', 'input1.tsv'] + ([] if row['negative'] == 'true' else ['reference-fixture.R'])
        for name in names:
            (directory / name).write_bytes(member('cases/' + row['id'] + '/' + name))
        row['oracle_policy'] = 'UNCHANGED_REFUSAL'
        if row['id'] in allowed_requalifications:
            selected_keys = contract_keys(row['id'])
            peers = []
            for peer in cases:
                if peer['operation'] != row['operation'] or peer['negative'] != 'false':
                    continue
                peer_input = member('cases/' + peer['id'] + '/input0.tsv')
                if peer_input != (directory / 'input0.tsv').read_bytes():
                    continue
                peer_keys = contract_keys(peer['id'])
                different = {key for key in selected_keys.keys() | peer_keys.keys() if selected_keys.get(key) != peer_keys.get(key)}
                required_change = 'exact' if row['id'] in exact_cases else 'p'
                if required_change in different and different <= {'test_id', required_change}:
                    peers.append(peer)
            require(peers, 'An independently frozen same-input reference peer is required')
            peer = peers[0]
            fixture = member('cases/' + peer['id'] + '/reference-fixture.R').decode().strip()
            override = 'fixture$args$exact <- TRUE' if row['id'] in exact_cases else 'fixture$args$p <- NULL'
            (directory / 'reference-fixture.R').write_text('local({fixture <- ' + fixture + '; ' + override + '; fixture})\n')
            row['oracle_policy'] = 'CURRENT_AUTHOR_EXACT_TRUE' if row['id'] in exact_cases else 'CURRENT_AUTHOR_DEFAULT_P_NULL'
            requalified.append(dict(id=row['id'], independent_peer=peer['id'], explicit_argument_change=override))
    for method in ['BH', 'BY', 'holm', 'OVER_LIMIT']:
        identifier = 'adjust-full-transcriptome-' + method if method != 'OVER_LIMIT' else 'adjust-over-current-row-limit'
        directory = scratch / 'cases' / identifier
        directory.mkdir(parents=True, mode=0o700)
        count = 25000 if method != 'OVER_LIMIT' else 25001
        values = ['NA' if index % 29 == 0 else format(((index * 37) % 997) / 997, '.17g') for index in range(1, count + 1)]
        values[0:3] = ['0', '1e-300', '1e-308']
        row_ids = ['gene' + str(index).zfill(5) for index in range(1, count + 1)]
        data = ('row_id\tp_value\n' + ''.join(key + '\t' + value + '\n' for key, value in zip(row_ids, values))).encode()
        (directory / 'input0.tsv').write_bytes(data)
        keys = dict(operation='adjust', scope='TECHNICAL_ONLY_NOT_G0', test_id=identifier,
                    input_sha256=identity(data)['sha256'], missing_policy='official',
                    method=method if method != 'OVER_LIMIT' else 'BH', n_total=str(count), alpha='0.05')
        (directory / 'input1.tsv').write_text('key\tvalue\n' + ''.join(key + '\t' + value + '\n' for key, value in keys.items()))
        negative = method == 'OVER_LIMIT'
        if not negative:
            fixture = 'list(function_name="p.adjust",args=list(p=c(' + ','.join('NA_real_' if value == 'NA' else value for value in values)
            fixture += '),method=' + json.dumps(method) + ',n=' + str(count) + '),row_ids=c(' + ','.join(json.dumps(key) for key in row_ids) + '))\n'
            (directory / 'reference-fixture.R').write_text(fixture)
        cases.append(dict(id=identifier, operation='adjust', negative='true' if negative else 'false', oracle_policy='UNCHANGED_REFUSAL'))
        retained_case = output / 'cases' / identifier
        retained_case.mkdir(parents=True, mode=0o700)
        for name in ['input0.tsv', 'input1.tsv', 'reference-fixture.R']:
            if (directory / name).exists():
                shutil.copyfile(directory / name, retained_case / name)
    with (scratch / 'cases.tsv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, delimiter='\t', fieldnames=['id', 'operation', 'negative', 'oracle_policy'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(cases)
    (scratch / 'reference-current-R.R').write_text(R_DRIVER)
    (output / 'reference-current-R.R').write_text(R_DRIVER)
    shutil.copyfile(scratch / 'cases.tsv', output / 'cases.tsv')
    (output / 'original-fixture-locators.json').write_text(json.dumps(retained, indent=2) + '\n')
    (output / 'version-sensitive-reference-policies.json').write_text(json.dumps(requalified, indent=2) + '\n')
    environment = dict(os.environ, R_PROFILE_USER='/dev/null', R_ENVIRON_USER='/dev/null', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    with (output / 'host.stdout').open('wb') as stdout, (output / 'host.stderr').open('wb') as stderr:
        completed = subprocess.run(['Rscript', '--vanilla', str(scratch / 'reference-current-R.R'), str(scratch), str(output)],
                                   env=environment, stdout=stdout, stderr=stderr, timeout=600)
    require(completed.returncode == 0, 'Actual current-R wrapper/reference comparison failed; retain the original diagnostic')
    checks = list(csv.DictReader((output / 'method-checks.tsv').open(), delimiter='\t'))
    changed = [row for row in checks if row['legacy_negative'] != row['negative']]
    require(len(checks) == 168 and {row['id'] for row in checks} == {row['id'] for row in cases}
            and {row['id'] for row in changed} <= allowed_requalifications
            and all(row['legacy_negative'] == 'true' and row['negative'] == 'false' for row in changed),
            'Only independently determined author-version outcomes may differ; no case may disappear')
    require(source.read_bytes() == source_payload, 'Candidate source changed during proof')
    require(manifest_path.read_bytes() == manifest_payload and Path(__file__).read_bytes() == driver_payload,
            'Candidate manifest or driver changed during proof')
    report = dict(schema='OFFICIAL_R_STATS_4_6_1_HOST_WRAPPER_REQUALIFICATION_V1', host_pass=True,
                  status='HOST_METHOD_AND_INTERFACE_PROOF_ONLY_CONTAINER_DAG_DEPLOYMENT_PENDING',
                  original_fixture_session=REFERENCE_SESSION, original_fixture_seal=REFERENCE_SEAL,
                  original_case_inputs_reused=164, old_R_4_5_1_answers_reused=False,
                  independent_reference='Direct installed official R/stats 4.6.1 from separately frozen function arguments, not the wrapper argument parser',
                  positive_cases=sum(row['negative'] == 'false' for row in checks),
                  specific_refusal_cases=sum(row['negative'] == 'true' for row in checks),
                  full_fit_and_argument_objects_compared=sum(row['negative'] == 'false' for row in checks),
                  explicitly_changed_author_version_outcomes=changed,
                  expected_outcome_determined_from_independent_author_before_wrapper=True,
                  numeric_fit_values_compared=sum(int(row['numeric_values_compared']) for row in checks),
                  tiny_nonzero_values_cannot_match_zero=True, subnormal_tolerance='At most one representable step with same nonzero sign',
                  additional_full_transcriptome_rows=25000, full_transcriptome_methods=['BH', 'BY', 'holm'],
                  source_identity=identity(source_payload), manifest_identity=identity(manifest_payload),
                  version_upgrade_not_frozen_study_method_migration=True, declared_kinds=['t_test', 'cor_test', 'var_test', 'wilcox_test', 'prop_test', 'p_adjust'],
                  actual_container_executed=False, current_engine_DAG_proven=False, production_installed=False,
                  scientific_data_computations=0, scientific_release_granted=False, g0_granted=False)
    (output / 'original-fixture-locators.json').write_text(json.dumps(retained, indent=2) + '\n')
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
