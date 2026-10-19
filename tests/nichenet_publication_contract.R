arguments <- commandArgs(trailingOnly = TRUE)
wrapper <- arguments[[1L]]
root <- arguments[[2L]]
baseline <- identical(arguments[[3L]], "baseline")
foreign <- "FOREIGN_NICHENET_OUTPUT_MUST_SURVIVE"
checks <- list()
literal <- function(value) paste(capture.output(dput(value)), collapse = "\n")
present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}
same <- function(filename) file.exists(filename) && identical(readLines(filename), foreign)
names <- c("values.tsv", "state.rds", "audit.json", "nichenet.log", "cells.tsv", "genes.tsv", "geneset.tsv", "family.tsv")
run_case <- function(name, setup, assess) {
  directory <- file.path(root, name)
  dir.create(directory, recursive = TRUE)
  inputs <- file.path(directory, paste0("input", 0:2))
  for (filename in inputs) writeLines("{}", filename)
  outputs <- file.path(directory, names)
  configuration <- setup(inputs, outputs, directory)
  if (!is.null(configuration$inputs)) inputs <- configuration$inputs
  environment <- c(AUTONOMICS_INPUT_COUNT = "3", setNames(inputs, paste0("AUTONOMICS_INPUT", 0:2)),
                   setNames(outputs, paste0("AUTONOMICS_OUTPUT", 0:7)))
  invocation <- file.path(directory, "invoke.R")
  writeLines(c(paste0("do.call(Sys.setenv, as.list(", literal(environment), "))"), configuration$prefix,
               paste0("source(", literal(wrapper), ")")), invocation)
  status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(invocation)),
    stdout = file.path(directory, "stdout"), stderr = file.path(directory, "stderr"))
  checks[[length(checks) + 1L]] <<- data.frame(name = name, protected = isTRUE(assess(inputs, outputs, status, directory)), exit_status = status)
}
for (position in seq_along(names)) {
  run_case(paste0("dangling-port-", position - 1L), function(inputs, outputs, directory) {
    stopifnot(file.symlink(file.path(directory, "foreign-target"), outputs[[position]]))
    list(prefix = character())
  }, function(inputs, outputs, status, directory) status != 0 &&
    identical(Sys.readlink(outputs[[position]]), file.path(directory, "foreign-target")) &&
    !file.exists(file.path(directory, "foreign-target")) && !any(vapply(outputs[-position], present, logical(1))))
}
if (!baseline) {
  for (position in seq_along(names)) {
    run_case(paste0("existing-port-", position - 1L), function(inputs, outputs, directory) {
      writeLines(foreign, outputs[[position]])
      list(prefix = character())
    }, function(inputs, outputs, status, directory) status != 0 && same(outputs[[position]]) && !any(vapply(outputs[-position], present, logical(1))))
  }
  run_case("input-output-alias", function(inputs, outputs, directory) {
    writeLines(foreign, outputs[[1L]])
    inputs[[1L]] <- outputs[[1L]]
    list(inputs = inputs, prefix = character())
  }, function(inputs, outputs, status, directory) status != 0 && same(inputs[[1L]]) && !any(vapply(outputs[-1L], present, logical(1))))
  run_case("invalid-contract-diagnostics", function(inputs, outputs, directory) list(prefix = character()),
    function(inputs, outputs, status, directory) {
      value <- if (file.exists(outputs[[3L]])) jsonlite::fromJSON(outputs[[3L]]) else list()
      status == 1L && identical(value$status, "BLOCKED") && identical(value$G0_granted, FALSE) &&
        all(file.info(outputs[c(3L, 4L)])$size > 0) && !any(vapply(outputs[-c(3L, 4L)], present, logical(1)))
    })
  run_case("racing-audit", function(inputs, outputs, directory) list(prefix = paste0(
    "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[3L]]), ")) writeLines(",
    literal(foreign), ", to); base::file.link(from, to) }")),
    function(inputs, outputs, status, directory) status != 0 && same(outputs[[3L]]) && !any(vapply(outputs[-3L], present, logical(1))))
  run_case("rollback-foreign-replacement", function(inputs, outputs, directory) list(prefix = paste0(
    "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[4L]]), ")) { unlink(",
    literal(outputs[[3L]]), "); writeLines(", literal(foreign), ", ", literal(outputs[[3L]]),
    "); writeLines(", literal(foreign), ", to) }; base::file.link(from, to) }")),
    function(inputs, outputs, status, directory) status != 0 && all(vapply(outputs[c(3L, 4L)], same, logical(1))) && !any(vapply(outputs[-c(3L, 4L)], present, logical(1))))
}
result <- do.call(rbind, checks)
write.table(result, file.path(root, "publication-checks.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
print(result)
if (baseline) stopifnot(nrow(result) == 8L, !any(result$protected)) else stopifnot(nrow(result) == 20L, all(result$protected))
