"""Actual R outer-wrapper publication controls without UCell/package execution."""

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'plugins/ucell/scripts/ucell.R'
BASELINE_SOURCE_SHA = '0ee592ccb766d784451a8d429f13d4cda3d7d2ea774ad7397b3ba6915ed582fd'
BASELINE_EXECUTE = 'execute_ucell <- function() {\n  input_values <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:1), unset = "")\n  output_values <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:3), unset = "")\n  if (any(!nzchar(c(input_values, output_values)))) stop("All declared input and output paths are required")\n  inputs <- unname(normalizePath(input_values, mustWork = TRUE))\n  if (any(!file.exists(inputs)) || any(file.info(inputs)$isdir)) stop("Inputs must be readable files")\n  parents <- normalizePath(dirname(output_values), mustWork = TRUE)\n  if (any(!dir.exists(parents))) stop("Output parents must be existing directories")\n  outputs <- unname(file.path(parents, basename(output_values)))\n  if (anyDuplicated(outputs) || any(outputs %in% inputs)) stop("Input and output paths must be distinct")\n  links <- Sys.readlink(outputs)\n  if (any(file.exists(outputs)) || any(!is.na(links) & nzchar(links))) stop("Refusing to overwrite any existing output")\n  stat_program <- Sys.which("stat")\n  if (!nzchar(stat_program)) stop("File ownership inspection requires stat")\n  inode <- function(filename) {\n    information <- suppressWarnings(system2(stat_program, c("-c", "%d:%i", "--", shQuote(filename)),\n                                             stdout = TRUE, stderr = TRUE))\n    if (!is.null(attr(information, "status")) || length(information) != 1 ||\n        !grepl("^[0-9]+:[0-9]+$", information)) stop("Cannot prove artifact file ownership")\n    information\n  }\n  staging_directories <- character()\n  published <- list()\n  completed <- FALSE\n  log_connection <- NULL\n  sink_level <- sink.number()\n  close_log <- function() {\n    while (sink.number() > sink_level) sink()\n    if (!is.null(log_connection)) {\n      close(log_connection)\n      log_connection <<- NULL\n    }\n  }\n  on.exit({\n    try(close_log(), silent = TRUE)\n    if (!completed) {\n      for (record in rev(published)) {\n        current <- tryCatch(inode(record$path), error = function(error) NA_character_)\n        if (identical(current, record$identity)) unlink(record$path)\n      }\n    }\n    for (directory in staging_directories) unlink(directory, recursive = TRUE)\n  }, add = TRUE)\n  staged <- vapply(seq_along(outputs), function(position) {\n    directory <- tempfile(".ucell-stage-", tmpdir = parents[position])\n    if (!dir.create(directory, mode = "0700")) stop("Cannot create owned staging directory")\n    staging_directories <<- c(staging_directories, directory)\n    file.path(directory, basename(outputs[position]))\n  }, character(1))\n  tryCatch({\n    log_connection <- file(staged[3], open = "wt")\n    if (!isTRUE(suppressWarnings(file.link(staged[3], outputs[3])))) stop("Fresh log publication refused")\n    sink(log_connection, split = TRUE)\n    run_ucell(inputs, staged)\n    close_log()\n    for (position in c(1, 2, 4)) {\n      identity <- inode(staged[position])\n      if (!isTRUE(suppressWarnings(file.link(staged[position], outputs[position])))) stop("Fresh result publication refused")\n      published[[length(published) + 1]] <- list(path = outputs[position], identity = identity)\n    }\n    completed <- TRUE\n  }, error = function(error) {\n    try(close_log(), silent = TRUE)\n    cat("BLOCKED:", conditionMessage(error), "\\n", file = staged[3], append = TRUE)\n    stop(error)\n  })\n}\n'
METHOD_PREFIX_SHA = '45f730a98592346382993f4f4ff580d08e818048c896af36e36a2e577bdcb916'
BASELINE_EXECUTE_SHA = '2292f179dda23e8f82a9d11a3d594e70c9df8f3c658124447a6d2da561a5909f'

R_PROGRAM = r'''
arguments <- commandArgs(trailingOnly=TRUE)
source_path <- arguments[[1]]
root <- arguments[[2]]
mode <- arguments[[3]]
dir.create(root,mode="0700")
inputs <- file.path(root,c("matrix.input","signatures.input"))
writeLines("immutable first technical input",inputs[[1]])
writeLines("immutable second technical input",inputs[[2]])
outputs <- file.path(root,c("scores.tsv","scores.RDS","run.log","audit.json"))
for(index in seq_along(inputs)) do.call(Sys.setenv,setNames(list(inputs[[index]]),paste0("AUTONOMICS_INPUT",index-1L)))
for(index in seq_along(outputs)) do.call(Sys.setenv,setNames(list(outputs[[index]]),paste0("AUTONOMICS_OUTPUT",index-1L)))
scope <- new.env(parent=baseenv())
expressions <- parse(source_path,keep.source=FALSE)
selected <- Filter(function(expression) is.call(expression) && identical(expression[[1]],as.name("<-")) &&
    identical(expression[[2]],as.name("execute_ucell")),as.list(expressions))
stopifnot(length(selected)==1L)
eval(selected[[1]],envir=scope)
state <- new.env(parent=baseenv())
state$foreign <- NULL
state$sentinel <- NULL
state$backup <- NULL
state$first_result <- FALSE
state$hook_calls <- 0L
scope$run_ucell <- function(actual_inputs,actual_outputs) {
  if(mode=="early-computation-error") stop("early toy computation failure")
  if(mode=="early-same-inode-log-change") {
    state$foreign <- actual_outputs[[3]]
    writeLines("FOREIGN EARLY LOG CONTENT",state$foreign)
    stop("early toy computation failure")
  }
  writeLines("owned toy score",actual_outputs[[1]])
  saveRDS(list(technical=TRUE),actual_outputs[[2]])
  writeLines('{"technical":true}',actual_outputs[[4]])
  cat("owned toy UCell log\n")
  if(mode=="compute-log-replacement") {
    unlink(actual_outputs[[3]])
    writeLines("FOREIGN COMPUTE LOG",actual_outputs[[3]])
    state$foreign <- actual_outputs[[3]]
  }
  if(mode=="failure-log-directory") stop("original toy computation failure")
  if(mode %in% c("foreign-stage-directory","foreign-stage-child","foreign-log-directory","foreign-stage-success")) {
    position <- if(mode=="foreign-log-directory") 3L else 1L
    directory <- dirname(actual_outputs[[position]])
    if(mode %in% c("foreign-stage-directory","foreign-log-directory","foreign-stage-success")) {
      state$backup <- paste0(directory,"-original")
      stopifnot(file.rename(directory,state$backup),dir.create(directory,mode="0700"))
    }
    state$sentinel <- file.path(directory,"foreign-sentinel")
    writeLines("FOREIGN DIRECTORY CONTENT",state$sentinel)
    if(mode=="foreign-log-directory") {
      state$foreign <- actual_outputs[[3]]
      writeLines("FOREIGN LOG CONTENT",state$foreign)
    }
    if(mode=="foreign-stage-success") {
      state$foreign <- actual_outputs[[1]]
      writeLines("FOREIGN STAGED SCORE",state$foreign)
      return(invisible(NULL))
    }
    stop("injected failure after foreign staging mutation")
  }
}
scope$file.link <- function(from,to) {
  state$hook_calls <- state$hook_calls+1L
  if(mode=="first-result-link-failure" && identical(to,outputs[[1]])) return(FALSE)
  if(mode %in% c("published-log-same-inode","published-log-replacement") && identical(to,outputs[[1]])) {
    if(mode=="published-log-replacement") unlink(outputs[[3]])
    writeLines("FOREIGN PUBLISHED LOG",outputs[[3]])
    state$foreign <- outputs[[3]]
    return(FALSE)
  }
  if(mode=="same-inode-later-link-failure" && identical(to,outputs[[2]]) && state$first_result) return(FALSE)
  linked <- base::file.link(from,to)
  if(isTRUE(linked) && identical(to,outputs[[1]])) {
    state$first_result <- TRUE
    if(mode %in% c("same-inode-success","same-inode-later-link-failure")) {
      writeLines("FOREIGN SAME INODE CONTENT",to)
      state$foreign <- to
    }
    if(mode=="replacement-success") {
      unlink(to)
      writeLines("FOREIGN REPLACEMENT CONTENT",to)
      state$foreign <- to
    }
  }
  if(isTRUE(linked) && identical(to,outputs[[4]]) && mode=="last-link-rewrites-first") {
    writeLines("FOREIGN SAME INODE CONTENT",outputs[[1]])
    state$foreign <- outputs[[1]]
  }
  linked
}
scope$writeLines <- function(text,con=stdout(),...) {
  if(mode=="failure-log-directory" && length(text)==1L && startsWith(text,"BLOCKED:")) {
    path <- summary(con)$description
    directory <- dirname(path)
    state$backup <- paste0(directory,"-original")
    stopifnot(file.rename(directory,state$backup),dir.create(directory,mode="0700"))
    state$foreign <- path
    state$sentinel <- file.path(directory,"foreign-sentinel")
    base::writeLines("FOREIGN LOG",path)
    base::writeLines("FOREIGN DIRECTORY CONTENT",state$sentinel)
  }
  base::writeLines(text,con,...)
}
error <- NULL
success <- tryCatch({scope$execute_ucell();TRUE},error=function(condition) {error <<- conditionMessage(condition);FALSE})
foreign_exists <- !is.null(state$foreign) && file.exists(state$foreign)
sentinel_exists <- !is.null(state$sentinel) && file.exists(state$sentinel)
foreign_bytes <- if(foreign_exists) paste(readLines(state$foreign,warn=FALSE),collapse="|") else "ABSENT"
emit <- function(name,value) cat(name,"\t",value,"\n",sep="")
emit("mode",mode)
emit("success",if(success) "TRUE" else "FALSE")
emit("foreign_exists",if(foreign_exists) "TRUE" else "FALSE")
emit("sentinel_exists",if(sentinel_exists) "TRUE" else "FALSE")
emit("foreign_bytes",foreign_bytes)
emit("error",if(is.null(error)) "NONE" else gsub("[\t\r\n]"," ",error))
emit("hook_calls",state$hook_calls)
emit("scientific_computation_executed","FALSE")
emit("input_1",paste(readLines(inputs[[1]],warn=FALSE),collapse="|"))
emit("input_2",paste(readLines(inputs[[2]],warn=FALSE),collapse="|"))
emit("output_hashes",paste(unname(tools::md5sum(outputs)),collapse="|"))
emit("failure_log",if(file.exists(outputs[[3]])) paste(readLines(outputs[[3]],warn=FALSE),collapse="|") else "ABSENT")
emit("remaining_stages",length(list.files(root,pattern="^\\.ucell-stage-",all.files=TRUE)))
'''


def trial(source, root, mode):
    result = subprocess.run(['/usr/bin/Rscript', '--vanilla', '-e', R_PROGRAM,
        str(source), str(root), mode], check=False, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError('Actual base-R wrapper control failed: ' + result.stderr)
    record = {}
    for line in result.stdout.splitlines():
        if '\t' in line:
            name, value = line.split('\t', 1)
            if name in {'mode', 'success', 'foreign_exists', 'sentinel_exists', 'foreign_bytes', 'error', 'hook_calls',
                    'scientific_computation_executed', 'input_1', 'input_2', 'output_hashes', 'failure_log', 'remaining_stages'}:
                if name in record:
                    raise AssertionError('Duplicate actual wrapper observation')
                record[name] = value
    for key in ['success', 'foreign_exists', 'sentinel_exists', 'scientific_computation_executed']:
        if record.get(key) not in {'TRUE', 'FALSE'}:
            raise AssertionError('Actual wrapper boolean observation missing')
        record[key] = record[key] == 'TRUE'
    if record['scientific_computation_executed'] or record.get('input_1') != 'immutable first technical input' or record.get('input_2') != 'immutable second technical input':
        raise AssertionError('Technical wrapper control ran science or modified an input')
    return record


class UCellTSVPublicationTests(unittest.TestCase):
    def actual(self, mode, *, baseline=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = SOURCE
            if baseline:
                source = root / 'baseline-execute.R'
                source.write_text(BASELINE_EXECUTE)
            return trial(source, root / 'case', mode)

    def test_actual_control_executes_no_scientific_method(self):
        current, baseline = self.actual('control'), self.actual('control', baseline=True)
        self.assertTrue(current['success'])
        self.assertEqual(current['output_hashes'], baseline['output_hashes'])

    def test_actual_same_inode_later_failure_preserves_modified_content(self):
        result = self.actual('same-inode-later-link-failure')
        self.assertFalse(result['success'])
        self.assertTrue(result['foreign_exists'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN SAME INODE CONTENT')

    def test_actual_foreign_stage_directory_is_never_recursively_deleted(self):
        result = self.actual('foreign-stage-directory')
        self.assertFalse(result['success'])
        self.assertTrue(result['sentinel_exists'])
        self.assertIn('BLOCKED:', result['failure_log'])

    def test_actual_replaced_stage_is_rejected_before_foreign_source_can_be_adopted(self):
        baseline = self.actual('foreign-stage-success', baseline=True)
        self.assertTrue(baseline['success'])
        current = self.actual('foreign-stage-success')
        self.assertFalse(current['success'])
        self.assertTrue(current['sentinel_exists'])
        self.assertEqual(current['foreign_bytes'], 'FOREIGN STAGED SCORE')

    def test_actual_same_inode_success_is_rejected_and_preserved(self):
        result = self.actual('same-inode-success')
        self.assertFalse(result['success'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN SAME INODE CONTENT')

    def test_actual_foreign_replacement_after_link_is_rejected_and_preserved(self):
        result = self.actual('replacement-success')
        self.assertFalse(result['success'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN REPLACEMENT CONTENT')

    def test_actual_last_link_cannot_silently_rewrite_earlier_output(self):
        result = self.actual('last-link-rewrites-first')
        self.assertFalse(result['success'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN SAME INODE CONTENT')

    def test_actual_unknown_foreign_stage_child_is_preserved(self):
        result = self.actual('foreign-stage-child')
        self.assertFalse(result['success'])
        self.assertTrue(result['sentinel_exists'])

    def test_actual_foreign_log_directory_is_not_appended_or_deleted(self):
        result = self.actual('foreign-log-directory')
        self.assertFalse(result['success'])
        self.assertTrue(result['sentinel_exists'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN LOG CONTENT')
        self.assertIn('BLOCKED:', result['failure_log'])

    def test_failure_log_writer_cannot_adopt_foreign_replacement_stage(self):
        result = self.actual('failure-log-directory')
        self.assertFalse(result['success'])
        self.assertTrue(result['sentinel_exists'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN LOG')
        self.assertEqual(result['failure_log'], 'ABSENT')
        self.assertEqual(result['error'], 'original toy computation failure')

    def test_confirmed_owned_log_retains_exact_later_publication_failure_diagnostic(self):
        result = self.actual('first-result-link-failure')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Fresh result publication refused')
        self.assertIn('BLOCKED: Fresh result publication refused', result['failure_log'])

    def test_early_error_cleans_only_confirmed_empty_initial_log_stage(self):
        result = self.actual('early-computation-error')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'early toy computation failure')
        self.assertEqual(result['remaining_stages'], '0')
        self.assertIn('BLOCKED: early toy computation failure', result['failure_log'])

    def test_compute_cannot_replace_initial_log_and_have_foreign_file_approved(self):
        result = self.actual('compute-log-replacement')
        self.assertFalse(result['success'])
        self.assertTrue(result['foreign_exists'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN COMPUTE LOG')
        self.assertNotIn('FOREIGN COMPUTE LOG', result['failure_log'])

    def test_early_same_inode_log_edit_is_not_deleted_as_empty_owned_file(self):
        result = self.actual('early-same-inode-log-change')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'early toy computation failure')
        self.assertTrue(result['foreign_exists'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN EARLY LOG CONTENT')

    def test_same_inode_foreign_published_log_is_not_appended(self):
        result = self.actual('published-log-same-inode')
        self.assertFalse(result['success'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN PUBLISHED LOG')
        self.assertEqual(result['failure_log'], 'FOREIGN PUBLISHED LOG')

    def test_replacement_foreign_published_log_is_not_appended(self):
        result = self.actual('published-log-replacement')
        self.assertFalse(result['success'])
        self.assertEqual(result['foreign_bytes'], 'FOREIGN PUBLISHED LOG')
        self.assertEqual(result['failure_log'], 'FOREIGN PUBLISHED LOG')

    def test_baseline_same_inode_rollback_counterexample_is_preserved(self):
        result = self.actual('same-inode-later-link-failure', baseline=True)
        self.assertFalse(result['success'])
        self.assertFalse(result['foreign_exists'])

    def test_baseline_foreign_stage_counterexample_is_preserved(self):
        result = self.actual('foreign-stage-directory', baseline=True)
        self.assertFalse(result['success'])
        self.assertFalse(result['sentinel_exists'])

    def test_original_official_method_source_bytes_are_unchanged(self):
        prefix = SOURCE.read_text().split('execute_ucell <- function()', 1)[0]
        self.assertEqual(hashlib.sha256(prefix.encode()).hexdigest(), METHOD_PREFIX_SHA)
        self.assertEqual(hashlib.sha256(BASELINE_EXECUTE.encode()).hexdigest(), BASELINE_EXECUTE_SHA)


if __name__ == '__main__':
    unittest.main()
