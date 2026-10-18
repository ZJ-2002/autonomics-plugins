run_ucell <- function(inputs, outputs) {
  stopifnot(as.character(utils::packageVersion("UCell")) == "2.16.0")
  stopifnot(requireNamespace("digest", quietly = TRUE), requireNamespace("jsonlite", quietly = TRUE))
  rank_text <- Sys.getenv("UCELL_MAX_RANK")
  maximum_rank <- suppressWarnings(as.integer(rank_text))
  negative_weight <- as.numeric(Sys.getenv("UCELL_NEGATIVE_WEIGHT"))
  missing_policy <- Sys.getenv("UCELL_MISSING_GENES")
  if (!grepl("^[0-9]+$", rank_text) || !is.finite(maximum_rank) || maximum_rank < 2 ||
      !is.finite(negative_weight) || negative_weight < 0 || !missing_policy %in% c("impute", "skip")) stop("Frozen UCell parameters invalid")
  lexical <- function(values) {
    !anyNA(values) && all(nzchar(values)) && all(values == trimws(values)) && !any(grepl("[\t\r\n]", values))
  }
  file_hash <- function(filename) digest::digest(file = filename, algo = "sha256")
  input_hashes <- vapply(inputs, file_hash, character(1))
  read_input <- function(port) read.delim(inputs[port + 1],
    check.names = FALSE, colClasses = "character", na.strings = NULL, quote = "", comment.char = "",
    blank.lines.skip = FALSE, fill = FALSE, stringsAsFactors = FALSE)
  table <- read_input(0)
  signatures <- read_input(1)
  if (names(table)[1] != "gene" || nrow(table) < 2 || ncol(table) < 2 || !lexical(table$gene) ||
      !lexical(names(table)) || anyDuplicated(table$gene) || anyDuplicated(names(table))) stop("Matrix gene/cell identity invalid")
  expression <- matrix(suppressWarnings(as.numeric(as.matrix(table[, -1, drop = FALSE]))),
    nrow = nrow(table), dimnames = list(table$gene, names(table)[-1]))
  if (any(!is.finite(expression)) || any(expression < 0)) stop("UCell matrix must be finite nonnegative counts/normalized expression")
  if (!identical(names(signatures), c("signature", "gene")) || !nrow(signatures) ||
      !lexical(signatures$signature) || !lexical(signatures$gene) || anyDuplicated(signatures)) stop("Frozen signature identities invalid")
  features <- split(signatures$gene, signatures$signature)
  for (members in features) {
    if (anyDuplicated(sub("[+-]$", "", members))) stop("A gene cannot be repeated or appear in both signed arms")
  }
  scores <- UCell::ScoreSignatures_UCell(expression, features = features, maxRank = maximum_rank,
    w_neg = negative_weight, missing_genes = missing_policy, ties.method = "average", name = "_UCell",
    BPPARAM = BiocParallel::SerialParam(), chunk.size = 100)
  if (nrow(scores) != ncol(expression) || !identical(rownames(scores), colnames(expression)) ||
      any(!is.finite(scores))) stop("Official score identity or finite-score contract failed")
  if (!identical(input_hashes, vapply(inputs, file_hash, character(1)))) stop("Input changed during UCell computation")
  output <- data.frame(cell = rownames(scores), scores, check.names = FALSE)
  write.table(output, outputs[1], sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(list(scores = scores, features = features, maxRank = maximum_rank,
               w_neg = negative_weight, missing_genes = missing_policy), outputs[2])
  audit <- list(execution_status = "COMPLETED", method = "UCell", version = "2.16.0", ties_method = "average",
    params = list(max_rank = maximum_rank, negative_weight = negative_weight, missing_genes = missing_policy),
    matrix_sha256 = input_hashes[1], signature_sha256 = input_hashes[2],
    scores_sha256 = file_hash(outputs[1]), cell_ids = as.list(colnames(expression)),
    gene_ids = as.list(rownames(expression)), score_columns = as.list(colnames(scores)), scientific_release = FALSE, g0_granted = FALSE)
  jsonlite::write_json(audit, outputs[4], auto_unbox = TRUE, pretty = TRUE, digits = NA)
  cat("UCell 2.16.0; maxRank", maximum_rank, "w_neg", negative_weight, "missing_genes", missing_policy, "\n")
  print(sessionInfo())
}

execute_ucell <- function() {
  input_values <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:1), unset = "")
  output_values <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:3), unset = "")
  if (any(!nzchar(c(input_values, output_values)))) stop("All declared input and output paths are required")
  inputs <- unname(normalizePath(input_values, mustWork = TRUE))
  if (any(!file.exists(inputs)) || any(file.info(inputs)$isdir)) stop("Inputs must be readable files")
  parents <- normalizePath(dirname(output_values), mustWork = TRUE)
  if (any(!dir.exists(parents))) stop("Output parents must be existing directories")
  outputs <- unname(file.path(parents, basename(output_values)))
  if (anyDuplicated(outputs) || any(outputs %in% inputs)) stop("Input and output paths must be distinct")
  links <- Sys.readlink(outputs)
  if (any(file.exists(outputs)) || any(!is.na(links) & nzchar(links))) stop("Refusing to overwrite any existing output")
  if (!all(file.exists(c("/usr/bin/stat", "/usr/bin/sha256sum", "/usr/bin/rmdir", "/usr/bin/id")))) {
    stop("File ownership inspection requires GNU stat, sha256sum, rmdir and id")
  }
  operator_uid <- suppressWarnings(system2("/usr/bin/id", "-u", stdout = TRUE, stderr = FALSE))
  if (length(operator_uid) != 1 || !grepl("^[0-9]+$", operator_uid)) stop("Cannot determine artifact owner")
  metadata <- function(filename, directory = FALSE, detailed = FALSE, owned = TRUE) {
    link <- Sys.readlink(filename)
    if (!file.exists(filename) || (!is.na(link) && nzchar(link))) return(NULL)
    format <- if (detailed) "%d:%i:%f:%u:%g:%s:%y:%z" else "%d:%i:%f:%u:%g:%s"
    information <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote(format), "--", shQuote(filename)),
      stdout = TRUE, stderr = FALSE))
    if (!is.null(attr(information, "status")) || length(information) != 1) return(NULL)
    fields <- strsplit(information, ":", fixed = TRUE)[[1]]
    if (length(fields) < 6 || (owned && !identical(fields[[4]], operator_uid)) ||
        bitwAnd(strtoi(fields[[3]], base = 16L), 61440L) != if (directory) 16384L else 32768L) return(NULL)
    if (directory) paste(fields[1:5], collapse = ":") else information
  }
  file_fact <- function(filename, detailed = FALSE, owned = TRUE) {
    before <- metadata(filename, detailed = detailed, owned = owned)
    if (is.null(before)) return(NULL)
    checksum <- tryCatch(suppressWarnings(system2("/usr/bin/sha256sum", stdin = filename,
      stdout = TRUE, stderr = FALSE)), error = function(error) character())
    if (length(checksum) != 1 || !is.null(attr(checksum, "status")) ||
        !grepl("^[0-9a-f]{64}  -$", checksum) || !identical(metadata(filename, detailed = detailed, owned = owned), before)) return(NULL)
    list(metadata = before, sha256 = substr(checksum, 1, 64))
  }
  input_facts <- lapply(inputs, file_fact, detailed = TRUE, owned = FALSE)
  if (any(vapply(input_facts, is.null, logical(1)))) stop("Cannot verify complete input identities")
  parent_identities <- lapply(parents, metadata, directory = TRUE, owned = FALSE)
  if (any(vapply(parent_identities, is.null, logical(1)))) stop("Cannot verify output parent ownership")
  stages <- list()
  published <- list()
  completed <- FALSE
  log_connection <- NULL
  original_log_identity <- NULL
  sink_level <- sink.number()
  close_log <- function() {
    while (sink.number() > sink_level) sink()
    if (!is.null(log_connection)) {
      close(log_connection)
      log_connection <<- NULL
    }
  }
  remove_owned <- function(path, expected) {
    if (!is.null(expected) && identical(file_fact(path), expected)) unlink(path)
  }
  on.exit({
    try(close_log(), silent = TRUE)
    if (!completed) {
      for (record in rev(published)) {
        if (record$position != 3L) try(remove_owned(record$path, record$fact), silent = TRUE)
      }
    }
    for (record in stages) {
      if (identical(metadata(record$directory, directory = TRUE), record$identity)) {
        try(remove_owned(record$path, record$fact), silent = TRUE)
        if (identical(metadata(record$directory, directory = TRUE), record$identity) &&
            length(list.files(record$directory, all.files = TRUE, no.. = TRUE)) == 0) {
          suppressWarnings(system2("/usr/bin/rmdir", c("--", shQuote(record$directory)), stdout = FALSE, stderr = FALSE))
        }
      }
    }
  }, add = TRUE)
  new_stage <- function(position) {
    if (!identical(metadata(parents[[position]], directory = TRUE, owned = FALSE), parent_identities[[position]])) stop("Output parent changed")
    directory <- tempfile(".ucell-stage-", tmpdir = parents[position])
    if (!dir.create(directory, mode = "0700")) stop("Cannot create owned staging directory")
    identity <- metadata(directory, directory = TRUE)
    if (is.null(identity)) stop("Cannot verify owned staging directory")
    record <- list(directory = directory, path = file.path(directory, basename(outputs[position])),
      identity = identity, fact = NULL)
    stages[[length(stages) + 1L]] <<- record
    record$path
  }
  staged <- vapply(seq_along(outputs), new_stage, character(1))
  check_stages <- function(with_contents = TRUE) {
    for (position in seq_along(outputs)) {
      record <- stages[[position]]
      if (!identical(metadata(record$directory, directory = TRUE), record$identity) ||
          !identical(metadata(parents[[position]], directory = TRUE, owned = FALSE), parent_identities[[position]]) ||
          (with_contents && (is.null(record$fact) || !identical(file_fact(record$path), record$fact)))) {
        stop("Owned staging identity or contents changed")
      }
    }
  }
  failure_log <- function(message) {
    link <- Sys.readlink(outputs[[3]])
    if (file.exists(outputs[[3]]) && (is.na(link) || !nzchar(link))) {
      positions <- which(vapply(published, function(record) {
        identical(record$position, 3L) && identical(record$path, outputs[[3]])
      }, logical(1)))
      if (length(positions) != 1L) return(invisible(FALSE))
      published_position <- positions[[1]]
      expected <- published[[published_position]]$fact
      record <- stages[[3]]
      unchanged <- function() {
        !is.null(expected) && identical(record$fact, expected) &&
          identical(metadata(record$directory, directory = TRUE), record$identity) &&
          identical(metadata(parents[[3]], directory = TRUE, owned = FALSE), parent_identities[[3]]) &&
          identical(file_fact(record$path), expected) && identical(file_fact(outputs[[3]]), expected)
      }
      if (!unchanged()) return(invisible(FALSE))
      previous <- readBin(record$path, "raw", n = file.info(record$path)$size)
      if (!unchanged()) return(invisible(FALSE))
      connection <- file(record$path, open = "ab")
      tryCatch({
        if (!unchanged()) stop("Published failure log changed before diagnostic append")
        writeBin(charToRaw(paste0("BLOCKED: ", message, "\n")), connection)
        flush(connection)
      }, finally = close(connection))
      if (!identical(metadata(record$directory, directory = TRUE), record$identity) ||
          !identical(metadata(parents[[3]], directory = TRUE, owned = FALSE), parent_identities[[3]])) {
        stop("Published failure log directory changed during diagnostic append")
      }
      updated <- file_fact(record$path)
      if (is.null(updated) ||
          !identical(strsplit(updated$metadata, ":", fixed = TRUE)[[1]][1:5],
            strsplit(expected$metadata, ":", fixed = TRUE)[[1]][1:5]) ||
          !identical(file_fact(outputs[[3]]), updated) ||
          !identical(readBin(record$path, "raw", n = file.info(record$path)$size),
            c(previous, charToRaw(paste0("BLOCKED: ", message, "\n"))))) {
        stop("Published failure log identity or contents changed during diagnostic append")
      }
      stages[[3]]$fact <<- updated
      published[[published_position]]$fact <<- updated
      return(invisible(TRUE))
    }
    if (file.exists(outputs[[3]]) || (!is.na(link) && nzchar(link)) ||
        !identical(metadata(parents[[3]], directory = TRUE, owned = FALSE), parent_identities[[3]])) return(invisible(FALSE))
    path <- new_stage(3L)
    position <- length(stages)
    link <- Sys.readlink(path)
    if (!identical(metadata(stages[[position]]$directory, directory = TRUE), stages[[position]]$identity) ||
        file.exists(path) || (!is.na(link) && nzchar(link))) return(invisible(FALSE))
    connection <- file(path, open = "wx")
    tryCatch(writeLines(paste("BLOCKED:", message), connection), finally = close(connection))
    if (!identical(metadata(stages[[position]]$directory, directory = TRUE), stages[[position]]$identity)) {
      stop("Failure log staging directory changed during writing")
    }
    expected <- file_fact(path)
    if (is.null(expected)) return(invisible(FALSE))
    if (!identical(metadata(stages[[position]]$directory, directory = TRUE), stages[[position]]$identity)) {
      stop("Failure log staging directory changed before approval")
    }
    stages[[position]]$fact <<- expected
    if (!identical(metadata(stages[[position]]$directory, directory = TRUE), stages[[position]]$identity) ||
        !identical(file_fact(path), expected)) stop("Failure log changed before exclusive publication")
    if (!isTRUE(suppressWarnings(file.link(path, outputs[[3]])))) return(invisible(FALSE))
    published[[length(published) + 1L]] <<- list(path = outputs[[3]], fact = expected, position = 3L)
    if (!identical(metadata(stages[[position]]$directory, directory = TRUE), stages[[position]]$identity) ||
        !identical(file_fact(path), expected) || !identical(file_fact(outputs[[3]]), expected)) {
      stop("Failure log changed during exclusive publication")
    }
    invisible(TRUE)
  }
  tryCatch({
    check_stages(with_contents = FALSE)
    log_connection <- file(staged[3], open = "wx")
    check_stages(with_contents = FALSE)
    initial_log <- file_fact(staged[[3]])
    if (is.null(initial_log) || !identical(strsplit(initial_log$metadata, ":", fixed = TRUE)[[1]][[6]], "0")) {
      stop("Cannot confirm exclusive empty initial log identity")
    }
    original_log_identity <- strsplit(initial_log$metadata, ":", fixed = TRUE)[[1]][1:5]
    stages[[3]]$fact <- initial_log
    sink(log_connection, split = TRUE)
    run_ucell(inputs, staged)
    close_log()
    check_stages(with_contents = FALSE)
    if (!identical(lapply(inputs, file_fact, detailed = TRUE, owned = FALSE), input_facts)) stop("Input identity changed during UCell execution")
    for (position in seq_along(outputs)) {
      expected <- file_fact(staged[[position]])
      if (is.null(expected)) stop("Cannot verify complete staged output identity")
      if (position == 3L && !identical(strsplit(expected$metadata, ":", fixed = TRUE)[[1]][1:5], original_log_identity)) {
        stop("Initial log identity changed during UCell execution")
      }
      stages[[position]]$fact <- expected
    }
    for (position in c(3L, 1L, 2L, 4L)) {
      check_stages()
      links <- Sys.readlink(outputs[[position]])
      if (file.exists(outputs[[position]]) || (!is.na(links) && nzchar(links))) stop("Fresh result publication refused")
      if (!isTRUE(suppressWarnings(file.link(staged[position], outputs[position])))) stop("Fresh result publication refused")
      expected <- stages[[position]]$fact
      published[[length(published) + 1L]] <- list(path = outputs[[position]], fact = expected, position = position)
      if (!identical(file_fact(outputs[[position]]), expected)) stop("Published output identity or contents changed")
    }
    check_stages()
    for (record in published) {
      if (!identical(file_fact(record$path), record$fact)) stop("Published output changed at final checkpoint")
    }
    completed <- TRUE
  }, error = function(error) {
    try(close_log(), silent = TRUE)
    try(failure_log(conditionMessage(error)), silent = TRUE)
    stop(error)
  })
}

tryCatch(execute_ucell(), error = function(error) {
  cat("BLOCKED:", conditionMessage(error), "\n", file = stderr())
  quit(save = "no", status = 2)
})
