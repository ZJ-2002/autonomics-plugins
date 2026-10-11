input <- Sys.getenv("AUTONOMICS_INPUT0")
result_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
if (any(!nzchar(c(input, result_path, log_path)))) stop("Input and both declared output paths are required")
if (result_path == log_path || input %in% c(result_path, log_path)) stop("Input and output paths must be distinct")
if (file.exists(result_path) || file.exists(log_path)) stop("Refusing to overwrite existing result or log")
log_connection <- file(log_path, open = "wx")
sink(log_connection, split = TRUE)

columns <- function(text) {
  if (!nzchar(text)) stop("Lossless R-array environment value is required")
  expressions <- parse(text = text, keep.source = FALSE)
  if (length(expressions) != 1L || !is.call(expressions[[1L]]) ||
      !identical(expressions[[1L]][[1L]], as.name("c"))) stop("Invalid R-array encoding")
  members <- as.list(expressions[[1L]])[-1L]
  if (!is.null(names(members)) && any(nzchar(names(members)))) stop("Named R-array entries are not supported")
  if (!all(vapply(members, function(member) is.character(member) && length(member) == 1L && !is.na(member), logical(1)))) {
    stop("R-array entries must be character literals; expressions are not evaluated")
  }
  vapply(members, identity, character(1), USE.NAMES = FALSE)
}

flag <- function(name) {
  text <- Sys.getenv(name)
  if (!text %in% c("true", "false")) stop(paste("Invalid boolean", name))
  text == "true"
}

validate_correlation <- function(correlation, size, description) {
  tolerance <- 1e-10
  if (!identical(dim(correlation), c(size, size))) stop(paste(description, "dimension must match exposures"))
  if (any(!is.finite(correlation))) stop(paste(description, "must be finite"))
  if (any(abs(correlation) > 1 + tolerance)) stop(paste(description, "correlation outside [-1,1]"))
  if (max(abs(correlation - t(correlation))) > tolerance) stop(paste(description, "must be symmetric"))
  if (max(abs(diag(correlation) - 1)) > tolerance) stop(paste(description, "diagonal must equal 1"))
  if (min(eigen(correlation, symmetric = TRUE, only.values = TRUE)$values) < -tolerance * size) {
    stop(paste(description, "must be positive semidefinite"))
  }
}

validate_output <- function(value, location) {
  if (is.numeric(value) && any(!is.finite(value))) stop(paste("Official result contains nonfinite values:", location))
  if (is.list(value)) {
    for (member in seq_along(value)) validate_output(value[[member]], paste(location, member, sep = "."))
  }
}

run <- function() {
  if (as.character(packageVersion("MVMR")) != "0.4.8") stop("Expected official MVMR 0.4.8")
  beta_yg <- Sys.getenv("MVMR_BETA_YG")
  sebeta_yg <- Sys.getenv("MVMR_SEBETA_YG")
  beta_xg <- columns(Sys.getenv("MVMR_BETA_XG_R"))
  sebeta_xg <- columns(Sys.getenv("MVMR_SEBETA_XG_R"))
  covariance_columns <- columns(Sys.getenv("MVMR_GENCOV_COLUMNS_R"))
  label_column <- Sys.getenv("MVMR_LABEL_COLUMN")
  strength <- flag("MVMR_STRENGTH")
  strhet <- flag("MVMR_STRHET")
  pleiotropy <- flag("MVMR_PLEIOTROPY")
  qhet <- flag("MVMR_QHET")
  pcor_text <- Sys.getenv("MVMR_PCOR")
  exposure_count <- length(beta_xg)
  if (exposure_count < 2L || length(sebeta_xg) != exposure_count) stop("At least two exposure effect/SE pairs are required")
  selected <- c(beta_yg, sebeta_yg, beta_xg, sebeta_xg, covariance_columns)
  if (any(!nzchar(selected)) || anyDuplicated(selected)) stop("Selected numeric columns must be nonempty and distinct")
  if (nzchar(label_column) && label_column %in% selected) stop("Instrument label column cannot also be a numeric column")
  field_counts <- count.fields(input, sep = "\t", quote = "", comment.char = "", blank.lines.skip = FALSE)
  if (length(field_counts) < 2L || anyNA(field_counts) || any(field_counts != field_counts[[1L]])) {
    stop("Instrument TSV must be rectangular, unquoted and contain data rows")
  }
  data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character",
                     na.strings = character(0), quote = "", comment.char = "", fill = FALSE, row.names = NULL)
  if (any(!nzchar(names(data))) || anyDuplicated(names(data))) stop("Instrument TSV headers must be nonempty and unique")
  if (!all(c(selected, if (nzchar(label_column)) label_column) %in% names(data))) stop("Selected column is missing from instrument TSV")
  for (column in selected) {
    values <- suppressWarnings(as.numeric(data[[column]]))
    if (any(!is.finite(values))) stop(paste("Numeric column must contain finite values:", column))
    data[[column]] <- values
  }
  if (any(as.matrix(data[, c(sebeta_yg, sebeta_xg), drop = FALSE]) <= 0)) stop("All standard errors must be positive")
  instruments <- if (nzchar(label_column)) data[[label_column]] else rownames(data)
  if (any(!nzchar(trimws(instruments))) || anyDuplicated(instruments)) stop("Instrument labels must be nonempty and unique")
  if (nrow(data) <= exposure_count) stop("Positive residual degrees of freedom are required")
  exposure_effects <- as.matrix(data[, beta_xg, drop = FALSE])
  exposure_errors <- as.matrix(data[, sebeta_xg, drop = FALSE])
  if (qr(exposure_effects / data[[sebeta_yg]])$rank != exposure_count) stop("Exposure design is rank deficient")
  pcor <- NULL
  if (nzchar(pcor_text)) {
    components <- strsplit(pcor_text, ";", fixed = TRUE)[[1L]]
    cells <- lapply(components, function(component) strsplit(component, ",", fixed = TRUE)[[1L]])
    if (length(cells) != exposure_count || any(lengths(cells) != exposure_count) ||
        grepl("[;,]$", pcor_text) || any(vapply(components, function(component) grepl(",$", component), logical(1)))) {
      stop("pcor dimension must match exposures")
    }
    pcor <- matrix(suppressWarnings(as.numeric(unlist(cells))), nrow = exposure_count, byrow = TRUE)
    validate_correlation(pcor, exposure_count, "pcor")
  }
  if (!is.null(pcor) && length(covariance_columns)) stop("pcor and gencov_columns are mutually exclusive")
  if (qhet && is.null(pcor)) stop("qhet requires pcor; arbitrary per-SNP covariance is not substituted")
  if (length(covariance_columns)) {
    if (length(covariance_columns) != exposure_count ^ 2) stop("gencov_columns must provide a full row-major exposure covariance matrix")
    covariance_values <- as.matrix(data[, covariance_columns, drop = FALSE])
    gencov <- lapply(seq_len(nrow(data)), function(row) {
      covariance <- matrix(covariance_values[row, ], nrow = exposure_count, byrow = TRUE)
      scaled <- covariance / outer(exposure_errors[row, ], exposure_errors[row, ])
      validate_correlation(scaled, exposure_count, paste("SNP covariance", instruments[[row]]))
      covariance
    })
    covariance_source <- "provided_per_snp"
  } else if (!is.null(pcor)) {
    gencov <- MVMR::phenocov_mvmr(pcor, exposure_errors)
    covariance_source <- "phenocov_mvmr"
  } else {
    gencov <- 0
    covariance_source <- "zero"
    warning("Official gencov=0 default requested; this is not approval of zero covariance for a research design")
  }
  mvmr_input <- MVMR::format_mvmr(BXGs = exposure_effects, BYG = data[[beta_yg]],
                                seBXGs = exposure_errors, seBYG = data[[sebeta_yg]], RSID = instruments)
  result <- list(input = mvmr_input, ivw = MVMR::ivw_mvmr(mvmr_input, gencov = gencov))
  result$strength <- if (strength) MVMR::strength_mvmr(mvmr_input, gencov) else NULL
  result$strhet <- if (strhet) MVMR::strhet_mvmr(mvmr_input, gencov) else NULL
  result$pleiotropy <- if (pleiotropy) MVMR::pleiotropy_mvmr(mvmr_input, gencov) else NULL
  result$qhet <- if (qhet) MVMR::qhet_mvmr(mvmr_input, pcor, CI = FALSE, ncores = 1L) else NULL
  validate_output(result, "result")
  result$covariance <- list(pcor = pcor, source = covariance_source, gencov = gencov,
                           beta_columns = beta_xg, se_columns = sebeta_xg,
                           covariance_columns = covariance_columns)
  print(result)
  staged_result <- tempfile(".mvmr-", dirname(result_path))
  on.exit(unlink(staged_result), add = TRUE)
  saveRDS(result, staged_result)
  if (!file.link(staged_result, result_path)) stop("Could not publish result without overwriting an existing file")
}

status <- tryCatch({
  withCallingHandlers(run(), warning = function(warning) cat("WARNING:", conditionMessage(warning), "\n"))
  0L
}, error = function(error) {
  cat("ERROR:", conditionMessage(error), "\n")
  message(conditionMessage(error))
  1L
})
sink()
close(log_connection)
quit(save = "no", status = status)
