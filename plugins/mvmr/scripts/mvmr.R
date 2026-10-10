# MVMR plugin node: the R program of the legacy mvmr_container wrapper with
# every parameter moved from Rust codegen into MVMR_* environment variables.
# Conventions (same as the ldsc plugin scripts):
#   - optional params render as empty strings; nzchar() is the [ -n ] test
#   - booleans render as "true"/"false" and convert with as.logical()
#   - string arrays render space-joined and rebuild with strsplit()
# The validation block reproduces the message set of the legacy Rust
# validate() function; it runs inside the container instead of at DAG
# build time.

input <- Sys.getenv("AUTONOMICS_INPUT0")
result_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")

# Space-joined column list -> R character vector (empty text -> length 0).
columns <- function(text)
  if (nzchar(text)) strsplit(text, " ", fixed = TRUE)[[1]] else character(0)

beta_yg <- Sys.getenv("MVMR_BETA_YG")
sebeta_yg <- Sys.getenv("MVMR_SEBETA_YG")
beta_xg <- columns(Sys.getenv("MVMR_BETA_XG"))
sebeta_xg <- columns(Sys.getenv("MVMR_SEBETA_XG"))
label_column <- Sys.getenv("MVMR_LABEL_COLUMN")
strength <- as.logical(Sys.getenv("MVMR_STRENGTH"))
strhet <- as.logical(Sys.getenv("MVMR_STRHET"))
pleiotropy <- as.logical(Sys.getenv("MVMR_PLEIOTROPY"))
qhet <- as.logical(Sys.getenv("MVMR_QHET"))
pcor_text <- Sys.getenv("MVMR_PCOR")

# Legacy validate(): required columns, non-empty equal-length exposures.
if (!nzchar(beta_yg) || !nzchar(sebeta_yg)) {
  stop("beta_yg and sebeta_yg cannot be empty")
}
if (length(beta_xg) == 0 || length(beta_xg) != length(sebeta_xg)) {
  stop("beta_xg and sebeta_xg must be non-empty and equal-length")
}

# Serialized pcor -> matrix, with the legacy shape/finiteness/symmetry checks.
# The DSL has no number-matrix param yet, so the matrix travels row-major:
# rows separated by ';' and entries by ',' (example: 1,0.25;0.25,1).
pcor <- NULL
if (nzchar(pcor_text)) {
  pcor_rows <- strsplit(pcor_text, ";", fixed = TRUE)[[1]]
  pcor_cells <- lapply(pcor_rows, function(row) strsplit(row, ",", fixed = TRUE)[[1]])
  p <- length(pcor_rows)
  if (any(lengths(pcor_cells) != p)) {
    stop(sprintf("pcor must be a %dx%d matrix", p, p))
  }
  pcor <- matrix(as.numeric(unlist(pcor_cells)), nrow = p, ncol = p, byrow = TRUE)
  if (any(!is.finite(pcor))) {
    stop(sprintf("pcor must contain only finite values (%dx%d)", p, p))
  }
  for (i in seq_len(p)) {
    if (abs(pcor[i, i] - 1) > 1e-6) {
      stop(sprintf("pcor diagonal entry [%d][%d] must equal 1", i, i))
    }
    for (j in i + seq_len(p - i)) {
      if (abs(pcor[i, j] - pcor[j, i]) > 1e-6) {
        stop("pcor must be symmetric")
      }
    }
  }
}
if (qhet && is.null(pcor)) {
  stop("qhet requires a pcor matrix")
}

data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE)
mvmr_input <- MVMR::format_mvmr(
  BXGs = as.matrix(data[, beta_xg, drop = FALSE]),
  BYG = data[[beta_yg]],
  seBXGs = as.matrix(data[, sebeta_xg, drop = FALSE]),
  seBYG = data[[sebeta_yg]],
  RSID = if (nzchar(label_column)) data[[label_column]] else rownames(data)
)
if (is.null(pcor)) {
  gencov <- 0
} else {
  gencov <- MVMR::phenocov_mvmr(pcor, as.matrix(data[, sebeta_xg, drop = FALSE]))
}
result <- list(input = mvmr_input, ivw = MVMR::ivw_mvmr(mvmr_input, gencov = gencov))
result$strength <- if (strength) MVMR::strength_mvmr(mvmr_input, gencov) else NULL
result$strhet <- if (strhet) MVMR::strhet_mvmr(mvmr_input, gencov) else NULL
result$pleiotropy <- if (pleiotropy) MVMR::pleiotropy_mvmr(mvmr_input, gencov) else NULL
result$qhet <- if (qhet) MVMR::qhet_mvmr(mvmr_input, pcor, CI = FALSE) else NULL
result$covariance <- list(pcor = pcor, source = if (is.null(pcor)) "zero" else "phenocov_mvmr")
sink(log_path, split = TRUE)
print(result)
sink()
saveRDS(result, result_path)
