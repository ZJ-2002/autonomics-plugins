run_ucell <- function() {
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
  read_input <- function(port) read.delim(Sys.getenv(paste0("AUTONOMICS_INPUT", port)),
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
  output <- data.frame(cell = rownames(scores), scores, check.names = FALSE)
  write.table(output, Sys.getenv("AUTONOMICS_OUTPUT0"), sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(list(scores = scores, features = features, maxRank = maximum_rank,
               w_neg = negative_weight, missing_genes = missing_policy), Sys.getenv("AUTONOMICS_OUTPUT1"))
  file_hash <- function(filename) digest::digest(file = filename, algo = "sha256")
  audit <- list(execution_status = "COMPLETED", method = "UCell", version = "2.16.0", ties_method = "average",
    params = list(max_rank = maximum_rank, negative_weight = negative_weight, missing_genes = missing_policy),
    matrix_sha256 = file_hash(Sys.getenv("AUTONOMICS_INPUT0")), signature_sha256 = file_hash(Sys.getenv("AUTONOMICS_INPUT1")),
    scores_sha256 = file_hash(Sys.getenv("AUTONOMICS_OUTPUT0")), cell_ids = as.list(colnames(expression)),
    gene_ids = as.list(rownames(expression)), score_columns = as.list(colnames(scores)), scientific_release = FALSE, g0_granted = FALSE)
  jsonlite::write_json(audit, Sys.getenv("AUTONOMICS_OUTPUT3"), auto_unbox = TRUE, pretty = TRUE, digits = NA)
  cat("UCell 2.16.0; maxRank", maximum_rank, "w_neg", negative_weight, "missing_genes", missing_policy, "\n")
  print(sessionInfo())
}

tryCatch({
  log_connection <- file(Sys.getenv("AUTONOMICS_OUTPUT2"), open = "wt")
  sink(log_connection, split = TRUE)
  run_ucell()
  sink()
  close(log_connection)
}, error = function(error) {
  if (sink.number() > 0) sink()
  for (port in c(0, 1, 3)) unlink(Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)))
  cat("BLOCKED:", conditionMessage(error), "\n", file = Sys.getenv("AUTONOMICS_OUTPUT2"), append = TRUE)
  quit(save = "no", status = 2)
})
