arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 4L) stop("Expected fresh library, trusted test configuration, node result and reference output")
.libPaths(c(arguments[[1L]], .libPaths()))
source(arguments[[2L]], local = TRUE)
data <- read.delim(configuration$input, check.names = FALSE, colClasses = "character", na.strings = character(0), quote = "", comment.char = "")
selected <- c(configuration$beta, configuration$se, "SBP_beta", "SBP_se", configuration$covariance)
for (column in selected) data[[column]] <- as.numeric(data[[column]])
formatted <- MVMR::format_mvmr(as.matrix(data[, configuration$beta, drop = FALSE]), data$SBP_beta,
                              as.matrix(data[, configuration$se, drop = FALSE]), data$SBP_se, data$SNP)
covariance <- if (length(configuration$covariance)) {
  lapply(seq_len(nrow(data)), function(row) matrix(as.numeric(unlist(data[row, configuration$covariance], use.names = FALSE)), nrow = length(configuration$beta), byrow = TRUE))
} else if (!is.null(configuration$pcor)) {
  MVMR::phenocov_mvmr(configuration$pcor, as.matrix(data[, configuration$se, drop = FALSE]))
} else 0
reference <- list(input = formatted, ivw = MVMR::ivw_mvmr(formatted, covariance))
if (configuration$strength) reference$strength <- MVMR::strength_mvmr(formatted, covariance)
if (configuration$strhet) reference$strhet <- MVMR::strhet_mvmr(formatted, covariance)
if (configuration$pleiotropy) reference$pleiotropy <- MVMR::pleiotropy_mvmr(formatted, covariance)
if (configuration$qhet) reference$qhet <- MVMR::qhet_mvmr(formatted, configuration$pcor, CI = FALSE, ncores = 1L)
saveRDS(reference, arguments[[4L]])
actual <- readRDS(arguments[[3L]])
if (!identical(names(actual), c(names(reference), "covariance"))) stop("Result slots differ from the frozen enabled method set")
if (!identical(actual$input, reference$input)) stop("Formatted input, SNP identities or ordering differ")
maximum <- 0
numbers <- 0L
for (slot in names(reference)) {
  if (!isTRUE(all.equal(actual[[slot]], reference[[slot]], tolerance = 1e-12, check.attributes = TRUE))) stop(paste("Official object differs:", slot))
  for (column in seq_along(reference[[slot]])) {
    expected <- reference[[slot]][[column]]
    observed <- actual[[slot]][[column]]
    if (is.numeric(expected)) {
      if (any(!is.finite(expected)) || any(!is.finite(observed))) stop("Nonfinite official or node numeric result is not a passing comparison")
      maximum <- max(maximum, abs(expected - observed))
      numbers <- numbers + length(expected)
    }
  }
}
if (!identical(actual$covariance$gencov, covariance)) stop("Per-SNP covariance or its ordering differs")
if (!identical(actual$covariance$beta_columns, configuration$beta) || !identical(actual$covariance$se_columns, configuration$se)) stop("Exposure order audit differs")
cat("OFFICIAL_COMPLETE_OBJECTS_PASS", "slots", length(reference), "numeric_values", numbers, "max_absolute_difference", format(maximum, digits = 17), "\n")
