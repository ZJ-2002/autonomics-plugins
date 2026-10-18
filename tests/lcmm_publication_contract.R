arguments <- commandArgs(trailingOnly = TRUE)
wrapper <- arguments[[1L]]
root <- arguments[[2L]]
baseline <- identical(arguments[[3L]], "baseline")
checks <- list()
foreign <- "FOREIGN_OUTPUT_MUST_SURVIVE"
literal <- function(value) paste(capture.output(dput(value)), collapse = "\n")
present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}
same <- function(filename) file.exists(filename) && identical(readLines(filename), foreign)
for (mode in c("fit", "predict", "compare", "bind")) {
  binder <- identical(mode, "bind")
  names <- if (binder) c("resolved_contract.json", "bind_audit.json", "bind.log") else
    c("summary.tsv", "state.rds", "audit.json", "lcmm.log", "row_ledger.tsv", "subject_map.tsv")
  audit <- if (binder) 2L else 3L
  log <- audit + 1L
  run_case <- function(name, setup, assess) {
    directory <- file.path(root, paste(mode, name, sep = "-"))
    dir.create(directory, recursive = TRUE)
    inputs <- file.path(directory, c("input0", "input1", "input2"))
    for (filename in inputs) writeLines("{}", filename)
    outputs <- file.path(directory, names)
    configuration <- setup(inputs, outputs)
    if (!is.null(configuration$inputs)) inputs <- configuration$inputs
    environment <- c(CACHEXIA_LCMM_MODE = mode, AUTONOMICS_WORKDIR = directory,
                     AUTONOMICS_INPUT_COUNT = "3", setNames(inputs, paste0("AUTONOMICS_INPUT", 0:2)),
                     setNames(outputs, paste0("AUTONOMICS_OUTPUT", seq_along(outputs) - 1L)))
    invocation <- file.path(directory, "invoke.R")
    writeLines(c(paste0("do.call(Sys.setenv, as.list(", literal(environment), "))"),
      "library <- function(...) invisible(NULL)", configuration$prefix,
      paste0("source(", literal(wrapper), ")")), invocation)
    status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(invocation)),
                     stdout = file.path(directory, "stdout"), stderr = file.path(directory, "stderr"))
    checks[[length(checks) + 1L]] <<- data.frame(mode = mode, name = name,
      pass = isTRUE(assess(inputs, outputs, status)), exit_status = status)
  }
  for (position in seq_along(names)) {
    run_case(paste0("existing-port-", position - 1L), function(inputs, outputs) {
      writeLines(foreign, outputs[[position]])
      list(prefix = character())
    }, function(inputs, outputs, status) status != 0 && same(outputs[[position]]) &&
         !any(vapply(outputs[-position], present, logical(1))))
  }
  if (!baseline) {
    run_case("dangling-output", function(inputs, outputs) {
      stopifnot(file.symlink(file.path(root, "absent-target"), outputs[[1L]]))
      list(prefix = character())
    }, function(inputs, outputs, status) status != 0 &&
         identical(Sys.readlink(outputs[[1L]]), file.path(root, "absent-target")) &&
         !any(vapply(outputs[-1L], present, logical(1))))
    run_case("input-output-alias", function(inputs, outputs) {
      writeLines(foreign, outputs[[1L]])
      inputs[[1L]] <- outputs[[1L]]
      list(inputs = inputs, prefix = character())
    }, function(inputs, outputs, status) status != 0 && same(inputs[[1L]]) &&
         !any(vapply(outputs[-1L], present, logical(1))))
    run_case("invalid-contract-diagnostics", function(inputs, outputs) list(prefix = character()),
      function(inputs, outputs, status) {
        value <- if (file.exists(outputs[[audit]])) jsonlite::fromJSON(outputs[[audit]]) else list()
        status == 1L && identical(value$status, "BLOCKED") && identical(value$G0_granted, FALSE) &&
          all(file.info(outputs[c(audit, log)])$size > 0) &&
          !any(vapply(outputs[-c(audit, log)], present, logical(1)))
      })
    run_case("racing-audit", function(inputs, outputs) list(prefix = paste0(
      "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[audit]]), ")) writeLines(",
      literal(foreign), ", to); base::file.link(from, to) }")),
      function(inputs, outputs, status) status != 0 && same(outputs[[audit]]) &&
        !any(vapply(outputs[-audit], present, logical(1))))
    run_case("rollback-foreign-replacement", function(inputs, outputs) list(prefix = paste0(
      "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[log]]), ")) { unlink(",
      literal(outputs[[audit]]), "); writeLines(", literal(foreign), ", ", literal(outputs[[audit]]),
      "); writeLines(", literal(foreign), ", to) }; base::file.link(from, to) }")),
      function(inputs, outputs, status) status != 0 && all(vapply(outputs[c(audit, log)], same, logical(1))) &&
        !any(vapply(outputs[-c(audit, log)], present, logical(1))))
  }
}
result <- do.call(rbind, checks)
write.table(result, file.path(root, "publication-checks.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
print(result)
if (baseline) stopifnot(nrow(result) == 21L, !any(result$pass)) else
  stopifnot(nrow(result) == 41L, all(result$pass))
