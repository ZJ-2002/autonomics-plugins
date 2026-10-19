arguments <- commandArgs(trailingOnly = TRUE)
subject <- new.env(parent = globalenv())
sys.source(arguments[[1L]], envir = subject)
root <- tempfile("donor-composition-static-toy-")
stopifnot(dir.create(root))
checks <- 0L
assert <- function(value) {
  stopifnot(isTRUE(value))
  checks <<- checks + 1L
}
refuses <- function(expression) {
  rejected <- tryCatch({ force(expression); FALSE }, error = function(error) TRUE)
  assert(rejected)
}
tryCatch({
  input <- file.path(root, "cells.tsv")
  request_path <- file.path(root, "request.json")
  lines <- c("cell_id\tdonor\tcell_type\tcondition", "c1\t0001\tT\treference",
             "c2\t0001\tB\treference", "c3\tNA\tT\ttest", "c4\tNA\tB\ttest")
  writeLines(lines, input)
  request <- list(schema_version = 1L, scope = "TECHNICAL_ONLY_NOT_G0", analysis_id = "toy",
    input_sha256 = subject$checksum(input), columns = list("cell_id", "donor", "cell_type", "condition"),
    spec = list(donor_col = "donor", cell_type_col = "cell_type", condition_col = "condition",
      cell_id_col = "cell_id", reference = "reference", test = "test", cell_types = list("T", "B", "absent"),
      min_donor_cells = 1L, min_donors_per_condition = 1L, correction = "BH"))
  write_request <- function(value) jsonlite::write_json(value, request_path, auto_unbox = TRUE, null = "null")
  write_request(request)
  checked <- subject$validate_request(request_path, input)
  assert(identical(checked$cells$donor, c("0001", "0001", "NA", "NA")))
  assert(identical(checked$request$spec$cell_types, list("T", "B", "absent")))
  for (invalid in list(1L, TRUE, list("cell_id"))) {
    modified <- request
    modified$spec$cell_id_col <- invalid
    write_request(modified)
    refuses(subject$validate_request(request_path, input))
  }
  write_request(request)
  duplicated_request <- paste(readLines(request_path), collapse = "\n")
  duplicated_request <- sub('"scope":', '"scope":"TECHNICAL_ONLY_NOT_G0","scope":', duplicated_request, fixed = TRUE)
  writeLines(duplicated_request, request_path)
  refuses(subject$validate_request(request_path, input))
  core <- file.path(root, "core.R")
  writeChar(subject$OFFICIAL_REFERENCE_SOURCE, core, eos = NULL, useBytes = TRUE)
  assert(identical(subject$checksum(core), subject$OFFICIAL_REFERENCE_SHA256))
  assert(length(parse(core)) > 0L)
  for (field in c("min_donor_cells", "min_donors_per_condition")) for (invalid in list(0, 1.5, -1, TRUE)) {
    modified <- request
    modified$spec[[field]] <- invalid
    write_request(modified)
    refuses(subject$validate_request(request_path, input))
  }
  for (change in c("family_duplicate", "null_cell_id", "wrong_hash", "extra_field", "same_condition", "missing_scope")) {
    modified <- request
    if (change == "family_duplicate") modified$spec$cell_types <- list("T", "T")
    if (change == "null_cell_id") modified$spec$cell_id_col <- NULL
    if (change == "wrong_hash") modified$input_sha256 <- strrep("0", 64)
    if (change == "extra_field") modified$spec$robust <- TRUE
    if (change == "same_condition") modified$spec$test <- modified$spec$reference
    if (change == "missing_scope") modified$scope <- "FORMAL"
    write_request(modified)
    refuses(subject$validate_request(request_path, input))
  }
  for (change in c("duplicate_cell", "condition_conflict", "third_condition", "empty_identity", "padded_identity", "extra_column")) {
    modified <- lines
    if (change == "duplicate_cell") modified[[3L]] <- "c1\t0001\tB\treference"
    if (change == "condition_conflict") modified[[3L]] <- "c2\t0001\tB\ttest"
    if (change == "third_condition") modified[[3L]] <- "c2\t0001\tB\tunknown"
    if (change == "empty_identity") modified[[3L]] <- "c2\t\tB\treference"
    if (change == "padded_identity") modified[[3L]] <- "c2\t 0001\tB\treference"
    if (change == "extra_column") modified[[3L]] <- paste0(modified[[3L]], "\textra")
    writeLines(modified, input)
    updated <- request
    updated$input_sha256 <- subject$checksum(input)
    write_request(updated)
    refuses(subject$validate_request(request_path, input))
  }
  writeLines(lines, input)
  outputs <- file.path(root, paste0("output", 0:4))
  assert(identical(unname(subject$preflight_outputs(outputs, c(request_path, input))), outputs))
  for (index in seq_along(outputs)) {
    writeLines("FOREIGN", outputs[[index]])
    refuses(subject$preflight_outputs(outputs, c(request_path, input)))
    assert(identical(readLines(outputs[[index]]), "FOREIGN"))
    unlink(outputs[[index]])
  }
  assert(file.symlink(file.path(root, "absent"), outputs[[1L]]))
  refuses(subject$preflight_outputs(outputs, c(request_path, input)))
  unlink(outputs[[1L]])
  refuses(subject$preflight_outputs(c(input, outputs[-1L]), c(request_path, input)))
  owned <- file.path(root, "owned")
  writeLines("ORIGINAL", owned)
  identity <- subject$content_identity(owned)
  writeLines("FOREIGN_SAME_INODE_CHANGE", owned)
  subject$remove_owned(owned, identity)
  assert(file.exists(owned))
  identity <- subject$content_identity(owned)
  subject$remove_owned(owned, identity)
  assert(!file.exists(owned))
  writer_calls <- list()
  collect_writers <- function(expression) {
    if (!is.call(expression) && !is.expression(expression)) return(invisible(NULL))
    if (is.call(expression) && identical(expression[[1L]], as.name("write.table"))) writer_calls[[length(writer_calls) + 1L]] <<- expression
    invisible(lapply(as.list(expression), function(element) if (!missing(element)) collect_writers(element)))
  }
  collect_writers(body(subject$run_adapter))
  assert(length(writer_calls) == 2L)
  labels <- c("NA", "0001", "供者甲", 'T"quoted', 'back\\slash')
  fixture <- data.frame(label = labels, value = c(NA_real_, 1, 2, 3, 4))
  writer_environment <- new.env(parent = globalenv())
  writer_environment$result <- list(tests = fixture, composition = fixture)
  writer_environment$staged <- file.path(root, c("writer-tests.tsv", "writer-composition.tsv"))
  invisible(lapply(writer_calls, eval, envir = writer_environment))
  writer_payloads <- lapply(writer_environment$staged, function(path) paste0(paste(readLines(path, encoding = "UTF-8"), collapse = "\n"), "\n"))
  cat(jsonlite::toJSON(list(checks = checks, statistical_fits = 0L, temporary_fixture_removed_on_exit = TRUE,
    actual_writer_TSVs = writer_payloads), auto_unbox = TRUE), "\n")
}, finally = unlink(root, recursive = TRUE))
