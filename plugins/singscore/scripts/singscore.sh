read_tsv <- function(path) {
  fields <- count.fields(path, sep = "\t", quote = "", comment.char = "",
                         blank.lines.skip = FALSE)
  if (length(fields) == 0 || fields[1] == 0 || any(fields != fields[1])) {
    stop("TSV must have a nonempty header and equal field counts on every row", call. = FALSE)
  }
  table <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE,
                      colClasses = "character", na.strings = character(),
                      row.names = NULL, quote = "", comment.char = "",
                      strip.white = FALSE, fill = FALSE, blank.lines.skip = FALSE)
  if (any(!nzchar(trimws(names(table)))) || anyDuplicated(names(table))) {
    stop("TSV column names must be nonempty and unique", call. = FALSE)
  }
  table
}

validate_ids <- function(values, label, unique_required = TRUE) {
  if (length(values) == 0 || anyNA(values) || any(!nzchar(trimws(values))) ||
      any(values != trimws(values))) {
    stop(paste(label, "must be nonempty literal identifiers without surrounding whitespace"), call. = FALSE)
  }
  if (unique_required && anyDuplicated(values)) {
    stop(paste(label, "must be unique"), call. = FALSE)
  }
}

singscore_publication_identity <- function(filename) {
  value <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i:%f:%u:%g"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
  status <- attr(value, "status")
  if ((!is.null(status) && status != 0L) || length(value) != 1L) return(NA_character_)
  unname(value)
}

singscore_publication_file_identity <- function(filename) {
  link <- Sys.readlink(filename)
  if (!is.na(link) && nzchar(link)) return(NA_character_)
  metadata <- function() {
    value <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i:%f:%u:%g:%s:%y"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
    status <- attr(value, "status")
    if ((!is.null(status) && status != 0L) || length(value) != 1L) return(NA_character_)
    fields <- strsplit(value, ":", fixed = TRUE)[[1]]
    if (length(fields) < 7L || is.na(strtoi(fields[[3]], base = 16L)) ||
        bitwAnd(strtoi(fields[[3]], base = 16L), 61440L) != 32768L) return(NA_character_)
    unname(value)
  }
  before <- metadata()
  if (is.na(before)) return(NA_character_)
  checksum <- tryCatch(suppressWarnings(system2("/usr/bin/sha256sum", stdin = filename, stdout = TRUE, stderr = FALSE)), error = function(error) character())
  status <- attr(checksum, "status")
  after <- metadata()
  link <- Sys.readlink(filename)
  if ((!is.null(status) && status != 0L) || length(checksum) != 1L ||
      !grepl("^[0-9a-f]{64}  -$", checksum) || is.na(after) || !identical(before, after) ||
      (!is.na(link) && nzchar(link))) return(NA_character_)
  paste0(before, ":", substr(checksum, 1L, 64L))
}

singscore_publication_remove_owned <- function(filename, expected) {
  if (is.na(expected)) return(invisible(FALSE))
  current <- singscore_publication_file_identity(filename)
  if (is.na(current) || !identical(current, expected)) return(invisible(FALSE))
  invisible(unlink(filename) == 0L)
}

run_score <- function() {
  inputs <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:2))
  outputs <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:2))
  if (any(!nzchar(inputs)) || any(!nzchar(outputs))) {
    stop("All three declared input and output ports are required", call. = FALSE)
  }
  if (any(!dir.exists(dirname(outputs))) || anyDuplicated(outputs)) {
    stop("Output parents must exist and declared output paths must be distinct", call. = FALSE)
  }
  outputs <- vapply(outputs, function(path) file.path(normalizePath(dirname(path), mustWork = TRUE), basename(path)), character(1))
  if (anyDuplicated(outputs)) stop("Declared output paths must remain distinct after parent resolution", call. = FALSE)
  if (!all(file.exists(c("/usr/bin/stat", "/usr/bin/sha256sum", "/usr/bin/rmdir")))) {
    stop("GNU stat, sha256sum and rmdir are required for publication identity checks", call. = FALSE)
  }
  links <- Sys.readlink(outputs)
  if (file.exists(outputs[3]) || (!is.na(links[3]) && nzchar(links[3]))) {
    stop("Refuse to overwrite an existing run log", call. = FALSE)
  }
  log_connection <- file(outputs[3], open = "wx")
  log_initial_identity <- singscore_publication_identity(outputs[3])
  if (is.na(log_initial_identity)) { close(log_connection); stop("Fresh run log identity unavailable", call. = FALSE) }
  log_open <- TRUE
  log_sink_active <- FALSE
  log_final_identity <- NA_character_
  close_score_log <- function() {
    if (log_sink_active) {
      sink()
      log_sink_active <<- FALSE
    }
    if (log_open) {
      close(log_connection)
      log_open <<- FALSE
    }
    current <- singscore_publication_identity(outputs[3])
    full <- singscore_publication_file_identity(outputs[3])
    if (is.na(current) || is.na(full) || !identical(current, log_initial_identity) ||
        (!is.na(log_final_identity) && !identical(full, log_final_identity))) {
      complete <<- FALSE
      stop("Run log identity or finalized contents changed; foreign log preserved", call. = FALSE)
    }
    log_final_identity <<- full
    invisible(full)
  }
  on.exit(close_score_log(), add = TRUE)
  sink(log_connection, split = TRUE)
  log_sink_active <- TRUE
  staged <- character()
  stages <- character()
  stage_identities <- character()
  staged_identities <- rep(NA_character_, 2L)
  published <- integer()
  complete <- FALSE
  on.exit({
    if (!complete) {
      for (position in published) singscore_publication_remove_owned(outputs[position], staged_identities[position])
    }
    for (position in seq_along(stages)) {
      current <- singscore_publication_identity(stages[position])
      if (!is.na(current) && identical(current, stage_identities[position])) {
        if (length(staged) >= position) singscore_publication_remove_owned(staged[position], staged_identities[position])
        suppressWarnings(system2("/usr/bin/rmdir", c("--", shQuote(stages[position])), stdout = FALSE, stderr = FALSE))
      }
    }
  }, add = TRUE)
  tryCatch({
    links <- Sys.readlink(outputs[1:2])
    if (any(file.exists(outputs[1:2])) || any(!is.na(links) & nzchar(links))) {
      stop("Refuse to overwrite existing score or RDS artifacts", call. = FALSE)
    }
    matrix_table <- read_tsv(inputs[1])
    if (ncol(matrix_table) < 2 || nrow(matrix_table) == 0) {
      stop("Expression matrix must have genes and at least one sample", call. = FALSE)
    }
    genes <- matrix_table[[1]]
    sample_ids <- names(matrix_table)[-1]
    validate_ids(genes, "Expression gene identifiers")
    validate_ids(sample_ids, "Expression sample identifiers")
    values <- suppressWarnings(as.double(as.matrix(matrix_table[-1])))
    if (any(!is.finite(values))) {
      stop("Expression values must be numeric and finite; missing expression is not zero-filled", call. = FALSE)
    }
    expr <- matrix(values, nrow = length(genes), dimnames = list(genes, sample_ids))
    gene_set <- read_tsv(inputs[2])
    samples <- read_tsv(inputs[3])
    if (!all(c("gene", "direction") %in% names(gene_set))) {
      stop("Gene set file must carry gene and direction columns", call. = FALSE)
    }
    if (!all(c("sample", "group") %in% names(samples))) {
      stop("Samples file must carry sample and group columns", call. = FALSE)
    }
    validate_ids(gene_set$gene, "Signature gene identifiers")
    if (!all(gene_set$direction %in% c("up", "down"))) {
      stop("Gene set direction must be up/down only", call. = FALSE)
    }
    missing_genes <- setdiff(gene_set$gene, genes)
    if (length(missing_genes) > 0) {
      stop(paste0("Gene set contains ids absent from the expression matrix; mapping is upstream: ",
                  paste(head(sort(missing_genes), 8), collapse = ",")), call. = FALSE)
    }
    validate_ids(samples$sample, "Metadata sample identifiers")
    validate_ids(samples$group, "Metadata group labels", unique_required = FALSE)
    if (!setequal(samples$sample, sample_ids)) {
      stop("Metadata and expression sample identities must match exactly one-to-one", call. = FALSE)
    }
    up_set <- gene_set$gene[gene_set$direction == "up"]
    down_set <- gene_set$gene[gene_set$direction == "down"]
    if (length(up_set) == 0) {
      stop("Down-only signatures are unsupported; refuse to guess a direction", call. = FALSE)
    }
    suppressMessages(library(singscore))
    if (packageVersion("singscore") != "1.32.0") {
      stop("This method contract requires official singscore 1.32.0", call. = FALSE)
    }
    cat("singscore version:", as.character(packageVersion("singscore")), "\n")
    cat("matrix:", nrow(expr), "genes x", ncol(expr), "samples; gene set:",
        length(up_set), "up +", length(down_set), "down\n")
    rank_data <- singscore::rankGenes(expr, tiesMethod = "average", stableGenes = NULL)
    simple <- if (length(down_set) == 0) {
      singscore::simpleScore(rank_data, upSet = up_set, centerScore = TRUE,
                             knownDirection = TRUE, dispersionFun = stats::mad)
    } else {
      singscore::simpleScore(rank_data, upSet = up_set, downSet = down_set,
                             centerScore = TRUE, knownDirection = TRUE,
                             dispersionFun = stats::mad)
    }
    if (nrow(simple) != length(sample_ids) ||
        !identical(rownames(simple), sample_ids) ||
        any(!is.finite(simple$TotalScore))) {
      stop("Official scoring returned missing, nonfinite or misaligned sample scores", call. = FALSE)
    }
    scores <- data.frame(sample = sample_ids, TotalScore = simple$TotalScore,
                          group = samples$group[match(sample_ids, samples$sample)],
                          check.names = FALSE, stringsAsFactors = FALSE)
    for (position in seq_len(2L)) {
      stage <- tempfile(".singscore-", tmpdir = dirname(outputs[position]))
      if (!dir.create(stage, mode = "0700")) stop("Fresh private score staging directory required", call. = FALSE)
      stages <- c(stages, stage)
      stage_identities <- c(stage_identities, singscore_publication_identity(stage))
      if (is.na(stage_identities[position])) stop("Score staging directory identity unavailable", call. = FALSE)
    }
    staged <- file.path(stages, c("scores.tsv", "scores.RDS"))
    for (position in seq_along(staged)) {
      if (!identical(singscore_publication_identity(stages[position]), stage_identities[position])) {
        stop("Score staging directory changed before writing", call. = FALSE)
      }
      connection <- file(staged[position], open = if (position == 1L) "wx" else "wbx")
      initial <- singscore_publication_identity(staged[position])
      if (is.na(initial)) { close(connection); stop("Fresh score staging file identity unavailable", call. = FALSE) }
      tryCatch({
        if (position == 1L) {
          write.table(scores, connection, sep = "\t", row.names = FALSE, quote = FALSE)
        } else {
          connection <- gzcon(connection)
          saveRDS(list(rank_data = rank_data, simple = simple, scores = scores), connection)
        }
      }, finally = close(connection))
      if (!identical(singscore_publication_identity(stages[position]), stage_identities[position]) ||
          !identical(singscore_publication_identity(staged[position]), initial)) {
        stop("Score staging file or directory changed during writing", call. = FALSE)
      }
      staged_identities[position] <- singscore_publication_file_identity(staged[position])
      if (is.na(staged_identities[position])) stop("Complete staged score identity unavailable", call. = FALSE)
    }
    for (position in seq_along(staged)) {
      if (!identical(singscore_publication_identity(stages[position]), stage_identities[position]) ||
          is.na(staged_identities[position]) ||
          !identical(singscore_publication_file_identity(staged[position]), staged_identities[position])) {
        stop("Staged score artifact changed before publication", call. = FALSE)
      }
      if (!suppressWarnings(file.link(staged[position], outputs[position]))) {
        stop("Fresh output publication failed; existing artifacts are never replaced", call. = FALSE)
      }
      published <- c(published, position)
      if (!identical(singscore_publication_identity(stages[position]), stage_identities[position]) ||
          !identical(singscore_publication_file_identity(outputs[position]), staged_identities[position])) {
        stop("Published score artifact identity or contents changed", call. = FALSE)
      }
    }
    for (position in seq_along(staged)) {
      if (!identical(singscore_publication_identity(stages[position]), stage_identities[position]) ||
          !identical(singscore_publication_file_identity(staged[position]), staged_identities[position]) ||
          !identical(singscore_publication_file_identity(outputs[position]), staged_identities[position])) {
        stop("Score artifact changed before publication completed", call. = FALSE)
      }
    }
    cat("\n== singscore_bspec summary ==\n")
    print(head(scores, 5))
    close_score_log()
    complete <- TRUE
    0L
  }, error = function(error) {
    cat("ERROR:", conditionMessage(error), "\n")
    message("ERROR: ", conditionMessage(error))
    1L
  })
}

status <- tryCatch(run_score(), error = function(error) {
  message("ERROR: ", conditionMessage(error))
  1L
})
quit(status = status)
