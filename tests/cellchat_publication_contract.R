arguments <- commandArgs(trailingOnly = TRUE)
wrapper <- arguments[[1L]]
root <- arguments[[2L]]
mode <- arguments[[3L]]
checks <- list()
names <- c("values.tsv", "cellchat.rds", "audit.json", "cellchat.log", "cells.tsv", "genes.tsv", "state.rds", "family.tsv")
foreign <- "FOREIGN_OUTPUT_MUST_SURVIVE"
present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}
same <- function(filename) file.exists(filename) && identical(readLines(filename), foreign)
literal <- function(value) paste(capture.output(dput(value)), collapse = "\n")
run_case <- function(name, setup, assess) {
  directory <- file.path(root, name)
  dir.create(directory, recursive = TRUE)
  inputs <- file.path(directory, c("input0.h5ad", "input1.json"))
  writeLines("SYNTHETIC_NOT_H5AD", inputs[[1L]])
  writeLines("{}", inputs[[2L]])
  outputs <- file.path(directory, names)
  configuration <- setup(inputs, outputs)
  if (!is.null(configuration$inputs)) inputs <- configuration$inputs
  environment <- c(AUTONOMICS_WORKDIR = directory, AUTONOMICS_INPUT0 = inputs[[1L]], AUTONOMICS_INPUT1 = inputs[[2L]])
  invocation <- file.path(directory, "invoke.R")
  writeLines(c(paste0("do.call(Sys.setenv, as.list(", literal(environment), "))"),
    "library <- function(package, ...) { if (identical(as.character(substitute(package)), 'jsonlite')) base::library(jsonlite) else invisible(NULL) }",
    configuration$prefix, paste0("source(", literal(wrapper), ")")), invocation)
  status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(invocation)),
                    stdout = file.path(directory, "stdout"), stderr = file.path(directory, "stderr"))
  checks[[length(checks) + 1L]] <<- data.frame(name = name, pass = isTRUE(assess(inputs, outputs, status)), exit_status = status)
}
for (position in seq_along(names)) {
  run_case(paste0("existing-port-", position - 1L), function(inputs, outputs) {
    writeLines(foreign, outputs[[position]])
    list(prefix = character())
  }, function(inputs, outputs, status) status != 0 && same(outputs[[position]]) &&
       !any(vapply(outputs[-position], present, logical(1))))
}
if (mode != "baseline") {
  run_case("dangling-output", function(inputs, outputs) {
    stopifnot(file.symlink(file.path(root, "absent-target"), outputs[[1L]]))
    list(prefix = character())
  }, function(inputs, outputs, status) status != 0 &&
       identical(Sys.readlink(outputs[[1L]]), file.path(root, "absent-target")) &&
       !any(vapply(outputs[-1L], present, logical(1))))
  run_case("input-output-alias", function(inputs, outputs) {
    stopifnot(file.copy(inputs[[1L]], outputs[[1L]]))
    inputs[[1L]] <- outputs[[1L]]
    list(inputs = inputs, prefix = character())
  }, function(inputs, outputs, status) status != 0 && identical(readLines(inputs[[1L]]), "SYNTHETIC_NOT_H5AD") &&
       !any(vapply(outputs[-1L], present, logical(1))))
  run_case("invalid-contract-diagnostics", function(inputs, outputs) list(prefix = character()),
    function(inputs, outputs, status) {
      audit <- if (file.exists(outputs[[3L]])) jsonlite::fromJSON(outputs[[3L]]) else list()
      status == 1L && identical(audit$status, "BLOCKED") && identical(audit$G0_granted, FALSE) &&
        all(file.info(outputs[c(3L, 4L)])$size > 0) && !any(vapply(outputs[-c(3L, 4L)], present, logical(1)))
    })
  run_case("racing-audit", function(inputs, outputs) list(prefix = paste0(
    "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[3L]]), ")) writeLines(",
    literal(foreign), ", to); base::file.link(from, to) }")),
    function(inputs, outputs, status) status != 0 && same(outputs[[3L]]) &&
      !any(vapply(outputs[-3L], present, logical(1))))
  run_case("rollback-foreign-replacement", function(inputs, outputs) list(prefix = paste0(
    "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[4L]]), ")) { unlink(",
    literal(outputs[[3L]]), "); writeLines(", literal(foreign), ", ", literal(outputs[[3L]]),
    "); writeLines(", literal(foreign), ", to) }; base::file.link(from, to) }")),
    function(inputs, outputs, status) status != 0 && all(vapply(outputs[c(3L, 4L)], same, logical(1))) &&
      !any(vapply(outputs[-c(3L, 4L)], present, logical(1))))
}
result <- do.call(rbind, checks)
write.table(result, file.path(root, "publication-checks.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
print(result)
if (mode == "baseline") {
  stopifnot(nrow(result) == 8L, !any(result$pass))
} else {
  stopifnot(nrow(result) == 13L, all(result$pass))
}
