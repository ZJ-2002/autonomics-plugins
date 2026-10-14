arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 3, arguments[1] %in% c("reference", "compare"))
root <- arguments[2]
.libPaths(c(arguments[3], .libPaths()))
library(UCell)
stopifnot(as.character(packageVersion("UCell")) == "2.16.0",
          normalizePath(find.package("UCell")) == normalizePath(file.path(arguments[3], "UCell")))
cases <- jsonlite::read_json(file.path(root, "positive-cases.json"), simplifyVector = FALSE)
readbacks <- list()
for (configuration in cases) {
  work <- file.path(root, configuration$name)
  parameters <- configuration$parameters
  table <- read.delim(file.path(work, "matrix.tsv"), colClasses = "character", na.strings = NULL,
                      quote = "", comment.char = "", check.names = FALSE)
  members <- read.delim(file.path(work, "signatures.tsv"), colClasses = "character", na.strings = NULL,
                        quote = "", comment.char = "", check.names = FALSE)
  expression <- matrix(as.numeric(as.matrix(table[, -1, drop = FALSE])), nrow = nrow(table),
                        dimnames = list(table[[1]], names(table)[-1]))
  features <- split(members$gene, members$signature)
  if (arguments[1] == "reference") {
    reference <- UCell::ScoreSignatures_UCell(expression, features = features,
      maxRank = as.integer(parameters$max_rank), w_neg = as.numeric(parameters$negative_weight),
      missing_genes = parameters$missing_genes, ties.method = "average", name = "_UCell",
      BPPARAM = BiocParallel::SerialParam(), chunk.size = 100)
    stopifnot(all(is.finite(reference)), identical(rownames(reference), colnames(expression)))
    saveRDS(list(scores = reference, features = features, maxRank = as.integer(parameters$max_rank),
                 w_neg = as.numeric(parameters$negative_weight), missing_genes = parameters$missing_genes),
            file.path(work, "author-reference.RDS"))
  } else {
    expected <- readRDS(file.path(work, "author-reference.RDS"))
    actual <- readRDS(file.path(work, "ucell.RDS"))
    reference_weight_type <- typeof(expected$w_neg)
    stopifnot(reference_weight_type %in% c("integer", "double"), typeof(actual$w_neg) == "double",
              identical(as.numeric(expected$w_neg), as.numeric(parameters$negative_weight)))
    expected$w_neg <- as.numeric(parameters$negative_weight)
    stopifnot(identical(actual, expected))
    scores <- read.delim(file.path(work, "ucell_scores.tsv"), colClasses = "character", na.strings = NULL,
                         quote = "", comment.char = "", check.names = FALSE)
    stopifnot(identical(names(scores), c("cell", colnames(expected$scores))),
              identical(scores$cell, colnames(expression)))
    values <- matrix(as.numeric(as.matrix(scores[, -1, drop = FALSE])), nrow = nrow(scores))
    stopifnot(all(is.finite(values)), all(abs(values - unname(expected$scores)) <= 1e-12))
    audit <- jsonlite::read_json(file.path(work, "audit.json"), simplifyVector = FALSE)
    checksum <- function(filename) digest::digest(file = file.path(work, filename), algo = "sha256")
    stopifnot(setequal(names(audit), c("execution_status", "method", "version", "ties_method", "params",
      "matrix_sha256", "signature_sha256", "scores_sha256", "cell_ids", "gene_ids", "score_columns",
      "scientific_release", "g0_granted")))
    stopifnot(identical(audit$execution_status, "COMPLETED"), identical(audit$method, "UCell"),
      identical(audit$version, "2.16.0"), identical(audit$ties_method, "average"),
      identical(unlist(audit$cell_ids, use.names = FALSE), colnames(expression)),
      identical(unlist(audit$gene_ids, use.names = FALSE), rownames(expression)),
      identical(unlist(audit$score_columns, use.names = FALSE), colnames(expected$scores)),
      identical(audit$matrix_sha256, checksum("matrix.tsv")),
      identical(audit$signature_sha256, checksum("signatures.tsv")),
      identical(audit$scores_sha256, checksum("ucell_scores.tsv")),
      identical(audit$scientific_release, FALSE), identical(audit$g0_granted, FALSE))
    stopifnot(identical(audit$params, parameters), file.info(file.path(work, "ucell.log"))$size > 0)
    readbacks[[length(readbacks) + 1]] <- list(case = configuration$name,
      original_reference_weight_type = reference_weight_type, schema_weight_type = "double",
      complete_RDS_identical_with_declared_numeric_metadata_type = TRUE,
      official_score_object_not_modified = TRUE, score_values = length(actual$scores))
    cat(configuration$name, "EXACT_COMPLETE_RDS_TSV_AUDIT_AND_IDENTITIES_PASS\n")
  }
}
if (arguments[1] == "compare") jsonlite::write_json(readbacks,
  file.path(root, "readback-verification.json"), auto_unbox = TRUE, pretty = TRUE)
cat(toupper(arguments[1]), "CASES", length(cases), "FRESH_AUTHOR_NAMESPACE", find.package("UCell"), "\n")
