arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 2) stop("Expected pairs TSV and mutation directory")
pairs <- read.delim(arguments[1], colClasses = "character", na.strings = character(),
                    check.names = FALSE, quote = "", comment.char = "")
stopifnot(nrow(pairs) == 10, !anyDuplicated(pairs$case))
verify_pair <- function(pair, actual_path = pair$actual_rds) {
  actual <- readRDS(actual_path)
  expected <- readRDS(pair$reference_rds)
  metadata <- read.delim(pair$metadata_tsv, colClasses = "character",
                         na.strings = character(), check.names = FALSE,
                         quote = "", comment.char = "")
  sample_ids <- colnames(expected$rank)
  stopifnot(!anyDuplicated(metadata$sample), setequal(metadata$sample, sample_ids))
  joined <- data.frame(sample = sample_ids, TotalScore = expected$simple$TotalScore,
                       group = metadata$group[match(sample_ids, metadata$sample)],
                       check.names = FALSE, stringsAsFactors = FALSE)
  complete <- list(rank_data = expected$rank, simple = expected$simple, scores = joined)
  if (!identical(actual, complete)) stop("COMPLETE_RDS_MISMATCH", call. = FALSE)
  scores <- read.delim(pair$scores_tsv, colClasses = "character",
                       na.strings = character(), check.names = FALSE,
                       quote = "", comment.char = "")
  stopifnot(identical(names(scores), names(joined)), identical(scores$sample, joined$sample),
            identical(scores$group, joined$group))
  values <- as.double(scores$TotalScore)
  stopifnot(all(is.finite(values)), all(is.finite(joined$TotalScore)),
            all(abs(values - joined$TotalScore) <= 1e-12))
  invisible(TRUE)
}
for (position in seq_len(nrow(pairs))) {
  verify_pair(pairs[position, ])
  cat(pairs$case[position], "COMPLETE_RDS_IDENTICAL_JOINED_FIELDS_AND_ATTRIBUTES_PASS\n")
}
dir.create(arguments[2], showWarnings = FALSE)
pair <- pairs[pairs$case == "test_bidirectional_official_rank_and_all_scores", ]
stopifnot(nrow(pair) == 1)
mutations <- c("group", "TotalScore", "extra_field", "class", "row_names", "nonfinite")
for (mutation in mutations) {
  changed <- readRDS(pair$actual_rds)
  if (mutation == "group") changed$scores$group[1] <- "deliberately_wrong_group"
  if (mutation == "TotalScore") changed$scores$TotalScore[1] <- changed$scores$TotalScore[1] + 1
  if (mutation == "extra_field") changed$unexpected <- "not_declared"
  if (mutation == "class") class(changed$scores) <- c("undeclared_class", "data.frame")
  if (mutation == "row_names") rownames(changed$scores)[1] <- "wrong_row_name"
  if (mutation == "nonfinite") changed$scores$TotalScore[1] <- NaN
  destination <- file.path(arguments[2], paste0(mutation, ".RDS"))
  saveRDS(changed, destination)
  rejection <- tryCatch({verify_pair(pair, destination); "NOT_REJECTED"},
                        error = function(error) conditionMessage(error))
  stopifnot(identical(rejection, "COMPLETE_RDS_MISMATCH"))
  cat(mutation, "MUTATED_COMPLETE_RDS_REJECTED\n")
}
cat("VERIFIED_COMPLETE_PAIRS", nrow(pairs), "REJECTED_MUTATIONS", length(mutations), "\n")
