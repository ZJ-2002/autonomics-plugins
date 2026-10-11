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

run_score <- function() {
  inputs <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:2))
  outputs <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:2))
  if (any(!nzchar(inputs)) || any(!nzchar(outputs))) {
    stop("All three declared input and output ports are required", call. = FALSE)
  }
  if (any(!dir.exists(dirname(outputs))) || anyDuplicated(outputs)) {
    stop("Output parents must exist and declared output paths must be distinct", call. = FALSE)
  }
  if (file.exists(outputs[3])) {
    stop("Refuse to overwrite an existing run log", call. = FALSE)
  }
  sink(outputs[3], split = TRUE)
  on.exit(sink(), add = TRUE)
  staged <- character()
  published <- character()
  complete <- FALSE
  on.exit({
    unlink(staged)
    if (!complete) unlink(published)
  }, add = TRUE)
  tryCatch({
    if (any(file.exists(outputs[1:2]))) {
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
    staged <- vapply(outputs[1:2], function(path) tempfile(".singscore-", tmpdir = dirname(path)), character(1))
    write.table(scores, staged[1], sep = "\t", row.names = FALSE, quote = FALSE)
    saveRDS(list(rank_data = rank_data, simple = simple, scores = scores), staged[2])
    for (position in seq_along(staged)) {
      if (!suppressWarnings(file.link(staged[position], outputs[position]))) {
        stop("Fresh output publication failed; existing artifacts are never replaced", call. = FALSE)
      }
      published <- c(published, outputs[position])
    }
    complete <- TRUE
    cat("\n== singscore_bspec summary ==\n")
    print(head(scores, 5))
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
