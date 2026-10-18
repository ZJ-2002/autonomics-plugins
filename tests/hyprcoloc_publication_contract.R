arguments <- commandArgs(trailingOnly = TRUE)
wrapper <- arguments[[1L]]
root <- arguments[[2L]]
mode <- arguments[[3L]]
checks <- list()
run_case <- function(name, setup, assess) {
  directory <- file.path(root, name)
  dir.create(directory, recursive = TRUE)
  inputs <- file.path(directory, paste0("input", 0:5, ".tsv"))
  outputs <- file.path(directory, c("hyprcoloc_summary.tsv", "hyprcoloc.RDS", "hyprcoloc.log", "snps.tsv", "audit.tsv", "traits.tsv"))
  for (filename in inputs) writeLines("TOY_INPUT", filename)
  configuration <- setup(inputs, outputs)
  outputs <- configuration$outputs
  environment <- c(AUTONOMICS_INPUT_COUNT = "0", setNames(inputs, paste0("AUTONOMICS_INPUT", 0:5)),
                   setNames(outputs, paste0("AUTONOMICS_OUTPUT", 0:5)))
  script <- file.path(directory, "invoke.R")
  literal <- function(value) paste(capture.output(dput(value)), collapse = "\n")
  writeLines(c(paste0("do.call(Sys.setenv, as.list(", literal(environment), "))"),
               configuration$prefix, paste0("source(", literal(wrapper), ")")), script)
  status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(script)),
                    stdout = file.path(directory, "stdout"), stderr = file.path(directory, "stderr"))
  outcome <- assess(inputs, outputs, status)
  checks[[length(checks) + 1L]] <<- data.frame(name = name, pass = isTRUE(outcome), exit_status = status)
}
present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}
foreign <- "FOREIGN_OUTPUT_MUST_SURVIVE"
same_foreign <- function(filename) file.exists(filename) && identical(readLines(filename), foreign)
for (position in 1:6) {
  run_case(paste0("existing-port-", position - 1L), function(inputs, outputs) {
    writeLines(foreign, outputs[[position]])
    list(outputs = outputs, prefix = character())
  }, function(inputs, outputs, status) status != 0 && same_foreign(outputs[[position]]) &&
       !any(vapply(outputs[-position], present, logical(1))))
}
if (mode != "baseline") {
  run_case("dangling-output", function(inputs, outputs) {
    stopifnot(file.symlink(file.path(root, "absent"), outputs[[1L]]))
    list(outputs = outputs, prefix = character())
  }, function(inputs, outputs, status) status != 0 &&
       identical(Sys.readlink(outputs[[1L]]), file.path(root, "absent")) &&
       !any(vapply(outputs[-1L], present, logical(1))))
  run_case("input-output-alias", function(inputs, outputs) {
    outputs[[1L]] <- inputs[[1L]]
    list(outputs = outputs, prefix = character())
  }, function(inputs, outputs, status) status != 0 && identical(readLines(inputs[[1L]]), "TOY_INPUT") &&
       !any(vapply(outputs[-1L], present, logical(1))))
  run_case("duplicate-output", function(inputs, outputs) {
    outputs[[2L]] <- outputs[[1L]]
    list(outputs = outputs, prefix = character())
  }, function(inputs, outputs, status) status != 0 && !any(vapply(outputs, present, logical(1))))
  run_case("invalid-input-diagnostics", function(inputs, outputs) {
    list(outputs = outputs, prefix = character())
  }, function(inputs, outputs, status) status == 2 &&
       !any(vapply(outputs[c(1L, 2L, 4L, 6L)], present, logical(1))) &&
       all(file.info(outputs[c(3L, 5L)])$size > 0) &&
       any(grepl("BLOCKED", readLines(outputs[[5L]]))))
  for (variant in c("second-link-failure", "foreign-replacement", "foreign-publication-race")) {
    run_case(variant, function(inputs, outputs) {
      log_literal <- paste(capture.output(dput(outputs[[3L]])), collapse = "\n")
      audit_literal <- paste(capture.output(dput(outputs[[5L]])), collapse = "\n")
      marker_literal <- paste(capture.output(dput(foreign)), collapse = "\n")
      action <- switch(variant,
        "second-link-failure" = "return(FALSE)",
        "foreign-replacement" = paste0("unlink(", log_literal, "); writeLines(", marker_literal, ", ", log_literal, "); return(FALSE)"),
        "foreign-publication-race" = paste0("writeLines(", marker_literal, ", ", audit_literal, "); return(base::file.link(from, to))"))
      prefix <- paste0("file.link <- function(from, to) { if (identical(to, ", audit_literal, ")) { ",
                       action, " }; base::file.link(from, to) }")
      list(outputs = outputs, prefix = prefix)
    }, function(inputs, outputs, status) {
      expected <- switch(variant, "second-link-failure" = integer(), "foreign-replacement" = 3L,
                         "foreign-publication-race" = 5L)
      status != 0 && all(vapply(outputs[expected], same_foreign, logical(1))) &&
        !any(vapply(outputs[setdiff(seq_along(outputs), expected)], present, logical(1)))
    })
  }
}
result <- do.call(rbind, checks)
write.table(result, file.path(root, "checks.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
print(result)
if (mode == "baseline") stopifnot(nrow(result) == 6L, !any(result$pass)) else stopifnot(nrow(result) == 13L, all(result$pass))
