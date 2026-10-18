arguments <- commandArgs(trailingOnly = TRUE)
family <- arguments[[1L]]
root <- arguments[[2L]]
baseline <- identical(arguments[[3L]], "baseline")
foreign <- "FOREIGN_MICE_OUTPUT_MUST_SURVIVE"
checks <- list()
literal <- function(value) paste(capture.output(dput(value)), collapse = "\n")
present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}
same <- function(filename) file.exists(filename) && identical(readLines(filename), foreign)
for (entry in c("mice", "bind")) {
  binder <- identical(entry, "bind")
  names <- if (binder) c("resolved_contract.json", "bind_audit.json", "bind.log") else
    c("values.tsv", "state.rds", "audit.json", "mice.log", "missingness_ledger.tsv", "diagnostics.tsv")
  audit <- if (binder) 2L else 3L
  log <- audit + 1L
  wrapper <- file.path(family, "scripts", if (binder) "bind_contract.R" else "mice.R")
  run_case <- function(name, setup, assess) {
    directory <- file.path(root, paste(entry, name, sep = "-"))
    dir.create(directory, recursive = TRUE)
    input_count <- if (binder) 2L else 3L
    inputs <- file.path(directory, paste0("input", seq_len(input_count) - 1L))
    for (filename in inputs) writeLines("{}", filename)
    outputs <- file.path(directory, names)
    configuration <- setup(inputs, outputs, directory)
    if (!is.null(configuration$inputs)) inputs <- configuration$inputs
    environment <- c(CACHEXIA_MICE_MODE = "pmm", AUTONOMICS_INPUT_COUNT = as.character(input_count),
      setNames(inputs, paste0("AUTONOMICS_INPUT", seq_len(input_count) - 1L)),
      setNames(outputs, paste0("AUTONOMICS_OUTPUT", seq_along(outputs) - 1L)))
    invocation <- file.path(directory, "invoke.R")
    writeLines(c(paste0("do.call(Sys.setenv, as.list(", literal(environment), "))"),
      configuration$prefix, paste0("source(", literal(wrapper), ")")), invocation)
    status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(invocation)),
      stdout = file.path(directory, "stdout"), stderr = file.path(directory, "stderr"))
    checks[[length(checks) + 1L]] <<- data.frame(entry = entry, name = name,
      protected = isTRUE(assess(inputs, outputs, status, directory)), exit_status = status)
  }
  for (position in seq_along(names)) {
    run_case(paste0("dangling-port-", position - 1L), function(inputs, outputs, directory) {
      stopifnot(file.symlink(file.path(directory, "foreign-target"), outputs[[position]]))
      list(prefix = character())
    }, function(inputs, outputs, status, directory) status != 0 &&
      identical(Sys.readlink(outputs[[position]]), file.path(directory, "foreign-target")) &&
      !file.exists(file.path(directory, "foreign-target")) &&
      !any(vapply(outputs[-position], present, logical(1))))
  }
  if (!baseline) {
    for (position in seq_along(names)) {
      run_case(paste0("existing-port-", position - 1L), function(inputs, outputs, directory) {
        writeLines(foreign, outputs[[position]])
        list(prefix = character())
      }, function(inputs, outputs, status, directory) status != 0 && same(outputs[[position]]) &&
        !any(vapply(outputs[-position], present, logical(1))))
    }
    run_case("input-output-alias", function(inputs, outputs, directory) {
      writeLines(foreign, outputs[[1L]])
      inputs[[1L]] <- outputs[[1L]]
      list(inputs = inputs, prefix = character())
    }, function(inputs, outputs, status, directory) status != 0 && same(inputs[[1L]]) &&
      !any(vapply(outputs[-1L], present, logical(1))))
    run_case("invalid-contract-diagnostics", function(inputs, outputs, directory) list(prefix = character()),
      function(inputs, outputs, status, directory) {
        value <- if (file.exists(outputs[[audit]])) jsonlite::fromJSON(outputs[[audit]]) else list()
        status == 2L && identical(value$status, "BLOCKED") && identical(value$G0_granted, FALSE) &&
          all(file.info(outputs[c(audit, log)])$size > 0) &&
          !any(vapply(outputs[-c(audit, log)], present, logical(1)))
      })
    run_case("racing-audit", function(inputs, outputs, directory) list(prefix = paste0(
      "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[audit]]), ")) writeLines(",
      literal(foreign), ", to); base::file.link(from, to) }")),
      function(inputs, outputs, status, directory) status != 0 && same(outputs[[audit]]) &&
        !any(vapply(outputs[-audit], present, logical(1))))
    run_case("rollback-foreign-replacement", function(inputs, outputs, directory) list(prefix = paste0(
      "file.link <- function(from, to) { if (identical(to, ", literal(outputs[[log]]), ")) { unlink(",
      literal(outputs[[audit]]), "); writeLines(", literal(foreign), ", ", literal(outputs[[audit]]),
      "); writeLines(", literal(foreign), ", to) }; base::file.link(from, to) }")),
      function(inputs, outputs, status, directory) status != 0 && all(vapply(outputs[c(audit, log)], same, logical(1))) &&
        !any(vapply(outputs[-c(audit, log)], present, logical(1))))
  }
}
result <- do.call(rbind, checks)
write.table(result, file.path(root, "publication-checks.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
print(result)
if (baseline) stopifnot(nrow(result) == 9L, !any(result$protected)) else
  stopifnot(nrow(result) == 26L, all(result$protected))
