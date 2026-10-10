stopifnot(as.character(utils::packageVersion("MVMR")) == "0.4.8")
split_columns <- function(name) strsplit(trimws(Sys.getenv(name)), " +")[[1]]
beta_columns <- split_columns("MVMR_BETA_COLUMNS")
se_columns <- split_columns("MVMR_SE_COLUMNS")
mode <- Sys.getenv("MVMR_COVARIANCE_MODE")
justification <- trimws(Sys.getenv("MVMR_COVARIANCE_JUSTIFICATION"))
if (!mode %in% c("gencov", "justified_zero") || !nzchar(justification)) {
  stop("COV-U or missing covariance evidence; no silent zero fallback")
}
if (length(beta_columns) < 2 || length(beta_columns) != length(se_columns) ||
    anyDuplicated(c(beta_columns, se_columns)) || any(!nzchar(c(beta_columns, se_columns)))) {
  stop("Exposure column identities/order invalid")
}
data <- read.delim(Sys.getenv("AUTONOMICS_INPUT0"), check.names = FALSE, stringsAsFactors = FALSE)
covariance <- read.delim(Sys.getenv("AUTONOMICS_INPUT1"), check.names = FALSE, stringsAsFactors = FALSE)
required <- c("snp", "beta_y", "se_y", beta_columns, se_columns)
if (anyDuplicated(names(data)) || !all(required %in% names(data)) ||
    nrow(data) <= length(beta_columns) + 1 || anyNA(data$snp) ||
    any(!nzchar(data$snp)) || anyDuplicated(data$snp)) stop("Instrument schema/identity/count invalid")
numeric_columns <- data[, setdiff(required, "snp"), drop = FALSE]
if (!all(vapply(numeric_columns, is.numeric, logical(1))) ||
    any(!is.finite(as.matrix(numeric_columns))) || any(as.matrix(data[, c("se_y", se_columns)]) <= 0)) {
  stop("Effects must be finite and standard errors positive")
}
exposure_beta <- as.matrix(data[, beta_columns, drop = FALSE])
exposure_se <- as.matrix(data[, se_columns, drop = FALSE])
if (qr(exposure_beta)$rank != length(beta_columns)) stop("Exposure design is rank deficient")
if (!identical(names(covariance), c("snp", "exposure_i", "exposure_j", "covariance"))) {
  stop("Covariance schema must be snp/exposure_i/exposure_j/covariance")
}
gencov <- 0
if (mode == "justified_zero") {
  if (nrow(covariance)) stop("Zero mode cannot discard supplied covariances")
} else {
  expected_count <- nrow(data) * length(beta_columns)^2
  if (nrow(covariance) != expected_count || !is.numeric(covariance$covariance) ||
      anyNA(covariance) || any(!is.finite(covariance$covariance)) ||
      !setequal(covariance$snp, data$snp) ||
      !setequal(covariance$exposure_i, beta_columns) ||
      !setequal(covariance$exposure_j, beta_columns) ||
      anyDuplicated(covariance[, c("snp", "exposure_i", "exposure_j")])) {
    stop("Covariance identities are incomplete, duplicated, nonfinite or unknown")
  }
  gencov <- lapply(seq_len(nrow(data)), function(index) {
    rows <- covariance[covariance$snp == data$snp[index], ]
    matrix_value <- matrix(NA_real_, length(beta_columns), length(beta_columns))
    matrix_value[cbind(match(rows$exposure_i, beta_columns), match(rows$exposure_j, beta_columns))] <- rows$covariance
    scale <- max(exposure_se[index, ]^2)
    if (anyNA(matrix_value) || max(abs(matrix_value - t(matrix_value))) > scale * 1e-10 ||
        max(abs(diag(matrix_value) - exposure_se[index, ]^2)) > scale * 1e-10 ||
        min(eigen(matrix_value, symmetric = TRUE, only.values = TRUE)$values) < -scale * 1e-10) {
      stop("Covariance must be symmetric PSD with SE-squared diagonal")
    }
    matrix_value
  })
}
sink(Sys.getenv("AUTONOMICS_OUTPUT2"), split = TRUE)
cat("MVMR", as.character(utils::packageVersion("MVMR")), "mode", mode, "evidence", justification, "\n")
formatted <- MVMR::format_mvmr(BXGs = exposure_beta, BYG = data$beta_y,
  seBXGs = exposure_se, seBYG = data$se_y, RSID = data$snp)
ivw <- MVMR::ivw_mvmr(formatted, gencov = gencov)
strength <- MVMR::strength_mvmr(formatted, gencov = gencov)
pleiotropy <- MVMR::pleiotropy_mvmr(formatted, gencov = gencov)
result <- list(input = formatted, gencov = gencov, ivw = ivw, strength = strength,
               pleiotropy = pleiotropy, covariance_mode = mode, evidence = justification)
output <- data.frame(exposure = beta_columns, beta = ivw[, 1], se = ivw[, 2],
                     statistic = ivw[, 3], p = ivw[, 4], conditional_F = as.numeric(strength[1, ]))
if (any(!is.finite(as.matrix(output[, -1])))) stop("Official result contains nonfinite values")
write.table(output, Sys.getenv("AUTONOMICS_OUTPUT0"), sep = "\t", quote = FALSE, row.names = FALSE)
saveRDS(result, Sys.getenv("AUTONOMICS_OUTPUT1"))
print(sessionInfo())
sink()
