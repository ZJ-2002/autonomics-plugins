"""Observe actual R publication statements with five non-scientific toy writes."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REVISION = 'd3065953a513f5b5f07e436b8ff2da62177341cd'
SOURCES = {
    'deseq2': ('plugins/deseq2/deseq2_runner.R',
        'cb019c599face7715089df4c16157851b0403bef5f61a3166123ba913ba170f1'),
    'limma': ('plugins/bulk-rnaseq/limma_voom_runner.R',
        '4dd81e31f558b311da0fdbcc54415967d7cd237356b54d56cfed7ed284808dcf'),
}
MODES = ('control', 'same-inode-success', 'same-inode-later-link-failure', 'foreign-stage-child',
    'last-link-rewrites-first', 'staged-before-link')
FOREIGN = 'EXPLICIT FOREIGN NONSCIENTIFIC BYTES'

SCIENCE_AUDIT_PROGRAM = r'''
arguments <- commandArgs(TRUE)
functions <- function(source) {
    values <- parse(source, keep.source=FALSE)
    answer <- list()
    for(value in values) if(is.call(value) && identical(value[[1]], as.name("<-")) &&
        is.call(value[[3]]) && identical(value[[3]][[1]], as.name("function")))
        answer[[as.character(value[[2]])]] <- value[[3]]
    answer
}
original <- functions(arguments[[1]])
current <- functions(arguments[[2]])
scientific <- function(value) {
    statements <- as.list(value[[3]])[-1L]
    front <- which(vapply(statements, function(value) identical(value,
        quote(report_path <- staged_outputs[[5]])), logical(1)))
    tail <- which(vapply(statements, function(value) is.call(value) &&
        identical(value[[1]], as.name("if")) &&
        any(grepl("output appeared during execution", deparse(value), fixed=TRUE)), logical(1)))
    stopifnot(length(front)==1L,length(tail)==1L,tail>front+1L)
    previous <- statements[[tail-1L]]
    if(is.call(previous) && identical(previous[[1]],as.name("<-")) &&
        identical(previous[[2]],as.name("links"))) tail <- tail-1L
    statements[(front+1L):(tail-1L)]
}
original_science <- scientific(original$main)
current_science <- scientific(current$main)
stopifnot(identical(original_science,current_science))
original_names <- setdiff(names(original),"main")
stopifnot(all(vapply(original_names,function(name) identical(original[[name]],current[[name]]),logical(1))))
top_level <- function(source) {
    values <- as.list(parse(source,keep.source=FALSE))
    Filter(function(value) !(is.call(value) && identical(value[[1]],as.name("<-")) &&
        is.call(value[[3]]) && identical(value[[3]][[1]],as.name("function"))),values)
}
stopifnot(identical(top_level(arguments[[1]]),top_level(arguments[[2]])))
cat("main_scientific_statements\t",length(original_science),"\n",sep="")
cat("original_function_helpers\t",length(original_names),"\n",sep="")
'''

HELPER_AUDIT_PROGRAM = r'''
arguments <- commandArgs(TRUE)
scope <- new.env(parent=globalenv())
for(value in parse(arguments[[1]],keep.source=FALSE)) if(is.call(value) &&
    identical(value[[1]],as.name("<-")) && is.call(value[[3]]) &&
    identical(value[[3]][[1]],as.name("function")) && !identical(value[[2]],as.name("main"))) eval(value,scope)
stopifnot(is.function(scope$publication_file_identity),is.function(scope$publication_remove_owned_file))
directory <- arguments[[2]]
stopifnot(dir.create(directory,mode="0700"))
path <- file.path(directory,"quoted ' $; file")
writeLines("OWN",path)
expected <- scope$publication_file_identity(path)
stopifnot(!is.na(expected))
link <- file.path(directory,"link")
stopifnot(file.symlink(path,link),is.na(scope$publication_file_identity(link)),
    is.na(scope$publication_file_identity(directory)),is.na(scope$publication_file_identity(file.path(directory,"absent"))))
cat("regular_and_nonregular\tPASS\n")
Sys.chmod(path,"0600")
before <- scope$publication_identity(path)
Sys.chmod(path,"0640")
stopifnot(identical(before,scope$publication_identity(path)),
    !identical(expected,scope$publication_file_identity(path)),
    !isTRUE(scope$publication_remove_owned_file(path,expected)),file.exists(path))
cat("same_inode_metadata_changed_preserved\tPASS\n")
scope$system2 <- function(command,...) {
    if(identical(command,"/usr/bin/sha256sum")) {
        answer <- ""
        attr(answer,"status") <- 1L
        return(answer)
    }
    base::system2(command,...)
}
stopifnot(is.na(scope$publication_file_identity(path)),
    !isTRUE(scope$publication_remove_owned_file(path,expected)),file.exists(path))
cat("sha_read_failure_not_owned\tPASS\n")
scope$system2 <- function(command,...) {
    answer <- base::system2(command,...)
    if(identical(command,"/usr/bin/sha256sum")) writeLines("CHANGED AFTER HASH",path)
    answer
}
stopifnot(is.na(scope$publication_file_identity(path)))
cat("changed_during_hash_not_owned\tPASS\n")
scope$system2 <- function(command,...) {
    if(identical(command,"/usr/bin/stat")) return(character())
    base::system2(command,...)
}
stopifnot(is.na(scope$publication_file_identity(path)),
    !isTRUE(scope$publication_remove_owned_file(path,expected)),file.exists(path))
cat("metadata_read_failure_not_owned\tPASS\n")
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_fact(path):
    require(not path.is_symlink() and path.is_file(), 'Unaliased regular source required')
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    require(fields(before) == fields(after), 'Source changed during observation')
    return dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())


def audit_sources(original, current, output):
    output.mkdir(mode=0o700)
    interpreter = shutil.which('Rscript')
    require(interpreter is not None, 'Actual Rscript is required')
    facts = dict(original=file_fact(original), current=file_fact(current))
    result = subprocess.run([interpreter, '--vanilla', '-', str(original), str(current)],
        input=SCIENCE_AUDIT_PROGRAM, text=True, capture_output=True, timeout=60)
    (output / 'science.stdout.log').write_text(result.stdout)
    (output / 'science.stderr.log').write_text(result.stderr)
    require(result.returncode == 0, 'Original statistical AST/helper equality failed: ' + result.stderr)
    counts = dict(line.split('\t') for line in result.stdout.strip().splitlines())
    require(set(counts) == {'main_scientific_statements', 'original_function_helpers'},
        'Complete statistical AST audit counts required')
    with tempfile.TemporaryDirectory(prefix='r-publication-helper-', dir=os.environ.get('TMPDIR')) as scratch:
        helpers = subprocess.run([interpreter, '--vanilla', '-', str(current), str(Path(scratch) / 'case')],
            input=HELPER_AUDIT_PROGRAM, text=True, capture_output=True, timeout=60)
    (output / 'helpers.stdout.log').write_text(helpers.stdout)
    (output / 'helpers.stderr.log').write_text(helpers.stderr)
    require(helpers.returncode == 0, 'File-identity refusal controls failed: ' + helpers.stderr)
    helper_controls = dict(line.split('\t') for line in helpers.stdout.strip().splitlines())
    require(set(helper_controls) == {'regular_and_nonregular', 'same_inode_metadata_changed_preserved',
        'sha_read_failure_not_owned', 'changed_during_hash_not_owned', 'metadata_read_failure_not_owned'} and
        set(helper_controls.values()) == {'PASS'}, 'Complete actual helper controls required')
    require(facts == dict(original=file_fact(original), current=file_fact(current)), 'Audit sources changed')
    record = dict(source_facts=facts, statistical_AST_exact=True, original_helpers_AST_exact=True,
        original_top_level_nonfunction_AST_exact=True,
        counts={name: int(count) for name, count in counts.items()},
        helper_controls=helper_controls, statistical_computation_executed=False,
        atomic_publication_certified=False, g0_granted=False)
    (output / 'AUDIT.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


R_PROGRAM = r'''
arguments <- commandArgs(TRUE)
source_path <- arguments[[1]]
mode <- arguments[[2]]
directory <- arguments[[3]]
ast_path <- arguments[[4]]
source_ast <- parse(source_path, keep.source=FALSE)
is_assignment <- function(value, name) {
    is.call(value) && identical(value[[1]], as.name("<-")) &&
        identical(value[[2]], as.name(name))
}
main_matches <- which(vapply(source_ast, function(value) is_assignment(value, "main"), logical(1)))
stopifnot(length(main_matches) == 1L)
main_assignment <- source_ast[[main_matches]]
stopifnot(is.call(main_assignment[[3]]), identical(main_assignment[[3]][[1]], as.name("function")))
statements <- as.list(main_assignment[[3]][[3]])[-1]
front <- which(vapply(statements, function(value) {
    is_assignment(value, "report_path") && identical(value[[3]], quote(staged_outputs[[5]]))
}, logical(1)))
finish <- which(vapply(statements, function(value) {
    is_assignment(value, "complete") && identical(value[[3]], TRUE)
}, logical(1)))
tail_start <- which(vapply(statements, function(value) {
    is.call(value) && identical(value[[1]], as.name("if")) &&
        any(grepl("output appeared during execution", deparse(value), fixed=TRUE))
}, logical(1)))
stopifnot(length(front)==1L, length(finish)==1L, length(tail_start)==1L,
    front < tail_start, tail_start < finish)
if (is_assignment(statements[[tail_start-1L]], "links")) tail_start <- tail_start-1L
scope <- new.env(parent=globalenv())
helpers <- list()
for (value in source_ast) {
    if (is.call(value) && identical(value[[1]], as.name("<-")) &&
        is.call(value[[3]]) && identical(value[[3]][[1]], as.name("function")) &&
        !identical(value[[2]], as.name("main"))) {
        eval(value, scope)
        helpers[[length(helpers)+1L]] <- value
    }
}
toy <- quote(for (index in seq_along(staged_outputs))
    writeLines(paste0("OWN-", index), staged_outputs[[index]]))
fragment <- as.call(c(list(as.name("{")), statements[seq_len(front)],
    list(toy), statements[tail_start:finish]))
main_function <- main_assignment[[3]]
main_function[[3]] <- fragment
scope$main <- eval(main_function, scope)
writeLines(c("# Parsed helpers and exact extracted R publication statements; no fit executed",
    vapply(helpers, function(value) paste(deparse(value, width.cutoff=500L), collapse="\n"), character(1)),
    paste(deparse(fragment, width.cutoff=500L), collapse="\n")), ast_path)
stopifnot(dir.create(directory, mode="0700"))
targets <- file.path(directory, paste0("port-", seq_len(5)))
names(targets) <- paste0("AUTONOMICS_OUTPUT", 0:4)
do.call(Sys.setenv, as.list(c(AUTONOMICS_INPUT0="UNUSED_SYNTHETIC_ONLY",
    AUTONOMICS_INPUT1="UNUSED_SYNTHETIC_ONLY", targets)))
calls <- 0L
injected <- FALSE
same_inode <- NA
foreign_path <- NULL
foreign_paths <- character()
failure_injected <- FALSE
foreign <- "EXPLICIT FOREIGN NONSCIENTIFIC BYTES"
scope$file.link <- function(from, to) {
    calls <<- calls+1L
    if (mode=="same-inode-later-link-failure" && calls==3L) {
        failure_injected <<- TRUE
        return(FALSE)
    }
    if (mode=="staged-before-link" && calls==1L) {
        before <- scope$publication_identity(from)
        writeLines(foreign, from)
        same_inode <<- identical(before, scope$publication_identity(from))
        injected <<- TRUE
        foreign_path <<- from
        foreign_paths <<- c(foreign_paths, from)
    }
    answer <- base::file.link(from, to)
    if (isTRUE(answer) && calls==1L && mode=="staged-before-link")
        foreign_paths <<- c(foreign_paths, to)
    if (isTRUE(answer) && calls==1L && startsWith(mode, "same-inode-")) {
        before <- scope$publication_identity(to)
        writeLines(foreign, to)
        same_inode <<- identical(before, scope$publication_identity(to))
        injected <<- TRUE
        foreign_path <<- to
        foreign_paths <<- c(from, to)
    }
    if (isTRUE(answer) && calls==1L && mode=="foreign-stage-child") {
        foreign_path <<- file.path(dirname(from), "FOREIGN-UNREGISTERED-MEMBER")
        writeLines(foreign, foreign_path)
        injected <<- TRUE
        foreign_paths <<- foreign_path
    }
    if (isTRUE(answer) && calls==5L && mode=="last-link-rewrites-first") {
        before <- scope$publication_identity(targets[[1]])
        writeLines(foreign, targets[[1]])
        same_inode <<- identical(before, scope$publication_identity(targets[[1]]))
        injected <<- TRUE
        foreign_path <<- targets[[1]]
        foreign_paths <<- c(foreign_path)
    }
    answer
}
error <- tryCatch({suppressWarnings(scope$main()); NULL}, error=function(value) conditionMessage(value))
present <- file.exists(targets) | (!is.na(Sys.readlink(targets)) & nzchar(Sys.readlink(targets)))
foreign_preserved <- !is.null(foreign_path) && file.exists(foreign_path) &&
    identical(readLines(foreign_path, warn=FALSE), foreign)
preserved_paths <- vapply(foreign_paths, function(path) file.exists(path) &&
    identical(readLines(path, warn=FALSE), foreign), logical(1))
own_ports <- vapply(seq_along(targets), function(index) file.exists(targets[[index]]) &&
    identical(readLines(targets[[index]], warn=FALSE), paste0("OWN-", index)), logical(1))
observation <- data.frame(mode=mode, returned_success=is.null(error),
    error=if(is.null(error)) "" else error, link_calls=calls, injected=injected,
    same_inode=if(is.na(same_inode)) "NOT_APPLICABLE" else as.character(same_inode),
    failure_injected=failure_injected, foreign_preserved=foreign_preserved,
    injected_path_count=length(foreign_paths), preserved_path_count=sum(preserved_paths),
    all_injected_paths_preserved=length(foreign_paths)>0L && all(preserved_paths),
    normal_ports=sum(own_ports), present_ports=sum(present),
    foreign_path=if(is.null(foreign_path)) "" else foreign_path,
    scientific_computation_executed=FALSE, g0_granted=FALSE)
write.table(observation, stdout(), sep="\t", row.names=FALSE, quote=TRUE, qmethod="double")
'''


def parse_observation(stdout):
    rows = list(csv.DictReader(io.StringIO(stdout), delimiter='\t'))
    require(len(rows) == 1, 'Exactly one actual R observation required')
    record = rows[0]
    for name in ('returned_success', 'injected', 'failure_injected', 'foreign_preserved',
            'all_injected_paths_preserved', 'scientific_computation_executed', 'g0_granted'):
        require(record.get(name) in ('TRUE', 'FALSE'), 'Strict R boolean observation required')
        record[name] = record[name] == 'TRUE'
    for name in ('link_calls', 'normal_ports', 'present_ports', 'injected_path_count',
            'preserved_path_count'):
        require(record.get(name, '').isdigit(), 'Actual integer count required')
        record[name] = int(record[name])
    require(record['scientific_computation_executed'] is False and record['g0_granted'] is False,
        'Publication-only scope required')
    return record


def trial(source, output, mode):
    require(mode in MODES, 'Unknown explicit publication control')
    output.mkdir(parents=True, mode=0o700)
    interpreter = shutil.which('Rscript')
    require(interpreter is not None, 'Actual Rscript is required; no skipped proof')
    with tempfile.TemporaryDirectory(prefix='r-publication-', dir=os.environ.get('TMPDIR')) as scratch:
        source_before = file_fact(source)
        result = subprocess.run([interpreter, '--vanilla', '-', str(source), mode,
            str(Path(scratch) / 'case'), str(output / 'extracted-publication.R')],
            input=R_PROGRAM, text=True, capture_output=True, timeout=60,
            env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
        (output / 'stdout.tsv').write_text(result.stdout)
        (output / 'stderr.log').write_text(result.stderr)
        require(result.returncode == 0, 'R extraction/observation failed: ' + result.stderr)
        require(file_fact(source) == source_before, 'Source changed during actual R observation')
        record = parse_observation(result.stdout)
        record['host_R_exit'] = result.returncode
        record['source'] = source_before
        record['extracted_publication'] = file_fact(output / 'extracted-publication.R')
        record['foreign_path'] = Path(record['foreign_path']).name if record['foreign_path'] else ''
        (output / 'observation.json').write_text(json.dumps(record, indent=2) + '\n')
        return record


def validate_observation(record, *, baseline):
    mode = record['mode']
    if mode == 'control':
        require(record['returned_success'] and record['normal_ports'] == 5 and
            record['link_calls'] == 5 and not record['injected'], 'Actual normal publication required')
        return 'CONTROL_ACTUALLY_SUCCEEDED_NOT_NODE_CERTIFICATION'
    require(record['injected'], 'Fault injection must actually occur')
    if mode.startswith('same-inode-') or mode in ('last-link-rewrites-first', 'staged-before-link'):
        require(record['same_inode'] == 'TRUE', 'Actual unchanged dev/inode observation required')
    if baseline:
        if mode in ('same-inode-success', 'last-link-rewrites-first'):
            require(record['returned_success'] and record['foreign_preserved'] and
                record['normal_ports'] == 4, 'Expected baseline silent acceptance was not observed')
        elif mode == 'same-inode-later-link-failure':
            require(not record['returned_success'] and record['failure_injected'] and
                not record['foreign_preserved'] and record['present_ports'] == 0,
                'Expected baseline foreign deletion was not observed')
        elif mode == 'foreign-stage-child':
            require(record['returned_success'] and not record['foreign_preserved'],
                'Expected baseline recursive foreign-child deletion was not observed')
        else:
            require(record['returned_success'] and record['normal_ports'] == 4 and
                not record['foreign_preserved'],
                'Expected baseline altered-stage acceptance and cleanup were not observed')
        return 'BASELINE_DEFECT_ACTUALLY_OBSERVED_NOT_PASS'
    require(record['foreign_preserved'] and record['all_injected_paths_preserved'],
        'Fixed publication must preserve foreign bytes at all injected paths')
    if mode != 'foreign-stage-child':
        require(not record['returned_success'] and bool(record['error']),
            'Fixed publication must reject changed linked content')
    return 'SCOPED_PUBLICATION_REGRESSION_ONLY'


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),
        'Managed session is required for durable publication observations')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
        default=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'r-publication-ownership'
        if os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') else None)
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--current-root', type=Path, default=ROOT)
    options = parser.parse_args()
    require(options.output is not None, 'Explicit output or managed permanent path required')
    options.output.mkdir(parents=True, mode=0o700)
    require(not any(options.output.iterdir()), 'Evidence directory must initially be empty')
    records = []
    for family, (relative, expected) in SOURCES.items():
        payload = subprocess.run(['git', '-C', str(ROOT), 'show', BASELINE_REVISION + ':' + relative],
            check=True, capture_output=True).stdout
        require(hashlib.sha256(payload).hexdigest() == expected, 'Immutable baseline source mismatch')
        source = options.output / (family + '-baseline.R')
        with source.open('xb') as stream:
            stream.write(payload)
        for label, path in [('baseline', source)] + ([] if options.baseline_only else
                [('current', options.current_root / relative)]):
            if label == 'current':
                snapshot = options.output / (family + '-current.R')
                before = file_fact(path)
                with snapshot.open('xb') as stream:
                    stream.write(path.read_bytes())
                require(file_fact(path) == before and file_fact(snapshot) == before,
                    'Current source snapshot mismatch')
                path = snapshot
                audit_sources(source, path, options.output / (family + '-source-audit'))
            for mode in MODES:
                record = trial(path, options.output / family / label / mode, mode)
                record.update(family=family, source_class=label,
                    assessment=validate_observation(record, baseline=label == 'baseline'))
                records.append(record)
    report = dict(schema='R_PUBLICATION_OWNERSHIP_OBSERVATIONS_V1', baseline_revision=BASELINE_REVISION,
        observations=records, actual_observations=len(records), statistical_packages_loaded=False,
        scientific_computation_executed=False, isolated_DAG_proven=False, g0_granted=False,
        status='BASELINE_DEFECTS_OBSERVED_NOT_FIXED' if options.baseline_only else
            'SCOPED_CURRENT_PUBLICATION_REGRESSION_OBSERVED_NOT_METHOD_CERTIFICATION')
    (options.output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], actual_observations=len(records),
        report=str(options.output / 'REPORT.json'))))


if __name__ == '__main__':
    main()
