arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 1) stop("Expected comparison-pairs TSV")
pairs <- read.delim(arguments[1], colClasses = "character", na.strings = character(),
                     check.names = FALSE, quote = "", comment.char = "")
stopifnot(nrow(pairs) > 0, !anyDuplicated(pairs$case))
for (position in seq_len(nrow(pairs))) {
  actual <- readRDS(pairs$actual_rds[position])
  expected <- readRDS(pairs$reference_rds[position])
  stopifnot(identical(actual$rank_data, expected$rank))
  stopifnot(identical(actual$simple, expected$simple))
  scores <- read.delim(pairs$scores_tsv[position], colClasses = "character",
                       na.strings = character(), check.names = FALSE,
                       quote = "", comment.char = "")
  metadata <- read.delim(pairs$metadata_tsv[position], colClasses = "character",
                         na.strings = character(), check.names = FALSE,
                         quote = "", comment.char = "")
  stopifnot(identical(names(scores), c("sample", "TotalScore", "group")))
  stopifnot(identical(scores$sample, colnames(expected$rank)))
  stopifnot(identical(scores$sample, actual$scores$sample))
  stopifnot(!anyDuplicated(metadata$sample), setequal(metadata$sample, scores$sample))
  stopifnot(identical(scores$group, metadata$group[match(scores$sample, metadata$sample)]))
  values <- as.double(scores$TotalScore)
  stopifnot(all(is.finite(values)), all(is.finite(expected$simple$TotalScore)))
  stopifnot(all(abs(values - expected$simple$TotalScore) <= 1e-12))
  cat(pairs$case[position], "EXACT_RANK_AND_COMPLETE_SIMPLE_RDS_PASS TSV_MAX_ABSOLUTE_ERROR",
      max(abs(values - expected$simple$TotalScore)), "\n")
}
cat("VERIFIED_PAIRS", nrow(pairs), "\n")
