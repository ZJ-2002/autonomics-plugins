options(warn = 1, digits = 17)
outputs <- vapply(0:4, function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)), character(1))
analytic <- outputs[c(1, 2, 4)]
unlink(analytic)
writeLines("status\tRUNNING\nscope\tTECHNICAL_ONLY_NOT_G0", outputs[3])
audit <- list(status = "RUNNING", scientific_G0_granted = "false", primary_IVW_result = "false")
record <- function(...) cat(..., "\n", file = outputs[3], append = TRUE)
require_true <- function(condition, message) if (!isTRUE(condition)) stop(message, call. = FALSE)
write_tsv <- function(value, filename) write.table(value, filename, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
save_audit <- function(value = audit) write_tsv(data.frame(key = names(value), value = vapply(value, as.character, character(1))), outputs[5])
hash <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_true(is.null(attr(result, "status")) && length(result) == 1 && grepl("^[a-f0-9]{64} ", result), "Content hash unavailable")
  substr(result, 1, 64)
}
integer_value <- function(raw, maximum) {
  require_true(grepl("^[1-9][0-9]*$", raw) && nchar(raw) <= nchar(as.character(maximum)), "Canonical positive integer required")
  value <- as.numeric(raw)
  require_true(is.finite(value) && value <= maximum, "Integer outside accepted domain")
  as.integer(value)
}
boolean_value <- function(raw) {
  require_true(raw %in% c("true", "false"), "Canonical boolean required")
  raw == "true"
}
column_list <- function(raw) {
  columns <- strsplit(raw, ",", fixed = TRUE)[[1]]
  require_true(length(columns) >= 1 && length(columns) <= 4 && all(grepl("^[A-Za-z][A-Za-z0-9_]*$", columns)) && !anyDuplicated(columns), "Safe unique formula columns required")
  columns
}
flatten <- function(object, prefix = "result") {
  records <- list()
  walk <- function(value, path) {
    if (is.data.frame(value)) {
      for (column in names(value)) for (index in seq_len(nrow(value))) walk(value[[column]][index], paste(path, column, rownames(value)[index], sep = "/"))
    } else if (is.list(value)) {
      for (index in seq_along(value)) walk(value[[index]], paste(path, if (is.null(names(value))) index else names(value)[index], sep = "/"))
    } else {
      for (index in seq_along(value)) {
        item <- value[index]
        field <- if (length(value) == 1) path else paste(path, index, sep = "/")
        missing <- is.na(item)
        text <- if (missing) "NA" else as.character(item)
        numeric_value <- NA_real_
        limit <- NA_real_
        kind <- if (missing) "MISSING_OFFICIAL" else if (is.numeric(item)) "NUMERIC" else "TEXT"
        if (!missing && is.numeric(item)) {
          numeric_value <- item
          if (!is.finite(item)) kind <- if (item > 0) "POSITIVE_INFINITY" else "NEGATIVE_INFINITY"
        } else if (!missing && grepl("^<[0-9.eE+-]+$", text)) {
          limit <- suppressWarnings(as.numeric(substring(text, 2)))
          require_true(is.finite(limit) && limit > 0 && limit <= 1, "Invalid official censoring bound")
          kind <- "CENSORED_P_NOT_EXACT"
        }
        records[[length(records) + 1L]] <<- data.frame(field = field, value_type = kind, numeric_value = numeric_value, text_value = text, censor_limit = limit)
      }
    }
  }
  walk(object, prefix)
  result <- do.call(rbind, records)
  require_true(nrow(result) > 0 && !anyDuplicated(result$field), "Official result field identities are ambiguous")
  result
}

tryCatch({
  require_true(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "2", "Exactly two inputs required")
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  request <- read.delim(Sys.getenv("AUTONOMICS_INPUT1"), colClasses = "character", check.names = FALSE, quote = "", comment.char = "", na.strings = character())
  keys <- c("schema_version", "scope", "test_id", "input_sha256", "input_role", "effect_scale", "alignment", "beta_outcome", "sd_outcome", "beta_exposure", "sd_exposure", "outlier_test", "distortion_test", "signif_threshold", "nb_distribution", "seed", "missing_policy")
  require_true(identical(names(request), c("key", "value")) && !anyDuplicated(request$key) && setequal(request$key, keys), "Frozen contract key set differs")
  contract <- setNames(as.list(request$value), request$key)
  require_true(contract$schema_version == "1" && contract$scope == "TECHNICAL_ONLY_NOT_G0", "Invalid scientific scope or schema")
  require_true(nzchar(contract$test_id) && !grepl("[\t\r\n/]", contract$test_id), "Invalid frozen test identity")
  audit$test_id <- contract$test_id
  require_true(contract$input_role %in% c("SYNTHETIC_TECHNICAL_INPUT", "LEGACY_SEEN"), "New scientific evidence is not authorized")
  require_true(contract$effect_scale == "CONVENTIONAL_BETA_NOT_MRLAP_Z" && contract$alignment == "PREHARMONISED_REQUIRED" && contract$missing_policy == "reject", "Effect-scale/alignment/missing contract differs")
  require_true(grepl("^[a-f0-9]{64}$", contract$input_sha256) && hash(input) == contract$input_sha256, "Input content identity differs")
  require_true(as.character(packageVersion("MRPRESSO")) == "1.0" && as.character(getRversion()) == "4.5.1", "Official method/runtime version differs")
  audit$input_sha256 <- hash(input)
  audit$contract_sha256 <- hash(Sys.getenv("AUTONOMICS_INPUT1"))
  audit$method_version <- as.character(packageVersion("MRPRESSO"))
  audit$input_role <- contract$input_role
  audit$alignment_is_source_attestation_not_independent_proof <- "true"
  beta_outcome <- column_list(contract$beta_outcome)
  sd_outcome <- column_list(contract$sd_outcome)
  require_true(length(beta_outcome) == 1 && length(sd_outcome) == 1, "Outcome must have exactly one beta/SE column")
  beta_exposure <- column_list(contract$beta_exposure)
  sd_exposure <- column_list(contract$sd_exposure)
  require_true(length(beta_exposure) == length(sd_exposure), "Exposure beta/SE lengths differ")
  columns <- c(beta_outcome, beta_exposure, sd_outcome, sd_exposure)
  require_true(!anyDuplicated(columns) && !any(columns %in% c("SNP", "Weights")), "Numeric role columns must be distinct and cannot shadow SNP/Weights")
  data <- read.delim(input, colClasses = "character", check.names = FALSE, quote = "", comment.char = "", na.strings = character())
  require_true(!anyDuplicated(names(data)) && setequal(names(data), c("SNP", columns)) && nrow(data) <= 250, "Explicit SNP/effect schema or row budget differs")
  require_true(all(nzchar(data$SNP)) && !anyDuplicated(data$SNP) && !any(grepl('["\t\r\n/]', data$SNP)), "Unique unquoted lexical SNP identities required")
  for (column in columns) {
    original <- data[[column]]
    values <- suppressWarnings(as.numeric(data[[column]]))
    require_true(all(is.finite(values)), "Missing/nonfinite effect; no silent SNP deletion")
    zero_text <- grepl("^[+-]?(0+(\\.0*)?|\\.0+)([eE][+-]?[0-9]+)?$", original)
    require_true(all(values != 0 | zero_text), "Nonzero effect underflowed numeric representation")
    data[[column]] <- values
  }
  require_true(all(as.matrix(data[c(sd_outcome, sd_exposure)]) > 0), "SE must be finite positive")
  require_true(all(data[[beta_exposure[1]]] != 0), "Zero first exposure would annihilate the official sign transformation")
  rownames(data) <- data$SNP
  row_count <- nrow(data)
  require_true(row_count > length(beta_exposure) + 2, "Not enough instrumental variables for official leave-one-out fit")
  design <- as.matrix(data[beta_exposure]) / data[[sd_outcome]]
  require_true(qr(design)$rank == length(beta_exposure) && all(vapply(seq_len(row_count), function(index) qr(design[-index, , drop = FALSE])$rank == length(beta_exposure), logical(1))), "Singular full or leave-one-out exposure design")
  seed <- integer_value(contract$seed, 2147483647)
  simulations <- integer_value(contract$nb_distribution, 10000)
  require_true(simulations > row_count, "Monte Carlo distribution must exceed SNP count")
  threshold <- suppressWarnings(as.numeric(contract$signif_threshold))
  require_true(is.finite(threshold) && threshold > 0 && threshold < 1, "Threshold must be strictly within (0,1)")
  outlier <- boolean_value(contract$outlier_test)
  distortion <- boolean_value(contract$distortion_test)
  require_true(!distortion || outlier, "Distortion requires an enabled outlier test")
  require_true(!outlier || row_count / simulations <= threshold, "Monte Carlo Bonferroni resolution cannot reach requested threshold")
  audit$requested_snps <- row_count
  audit$seed <- seed
  audit$nb_distribution <- simulations
  audit$outlier_test_requested <- tolower(as.character(outlier))
  audit$distortion_test_requested <- tolower(as.character(distortion))
  audit$global_p_resolution <- 1 / simulations
  audit$outlier_p_resolution <- row_count / simulations
  record("METHOD", "MRPRESSO", as.character(packageVersion("MRPRESSO")), "R", as.character(getRversion()))
  record("CALL", "seed", seed, "NbDistribution", simulations, "OUTLIERtest", outlier, "DISTORTIONtest", distortion, "SignifThreshold", threshold)
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  warnings <- character()
  result <- withCallingHandlers(MRPRESSO::mr_presso(BetaOutcome = beta_outcome, BetaExposure = beta_exposure,
    SdOutcome = sd_outcome, SdExposure = sd_exposure, data = data, OUTLIERtest = outlier,
    DISTORTIONtest = distortion, NbDistribution = simulations, SignifThreshold = threshold, seed = seed),
    warning = function(warning) {
      warnings <<- c(warnings, conditionMessage(warning))
      record("WARNING", conditionMessage(warning))
      invokeRestart("muffleWarning")
    })
  summary <- flatten(result)
  summary$numeric_value <- vapply(summary$numeric_value, function(value) if (is.na(value)) "NA" else sprintf("%.17g", value), character(1))
  summary$censor_limit <- vapply(summary$censor_limit, function(value) if (is.na(value)) "NA" else sprintf("%.17g", value), character(1))
  write_tsv(summary, outputs[1])
  saveRDS(result, outputs[2])
  cat(paste(capture.output(print(result)), collapse = "\n"), "\n", file = outputs[3], append = TRUE)
  details <- result[["MR-PRESSO results"]]
  outlier_table <- details[["Outlier Test"]]
  ledger <- data.frame(SNP = data$SNP, input_order = seq_len(row_count), passed_input = TRUE,
                       outlier_test_returned = !is.null(outlier_table), outlier_p_text = "NA", sensitivity_outlier = NA)
  if (!is.null(outlier_table)) {
    require_true(nrow(outlier_table) == row_count && setequal(rownames(outlier_table), data$SNP), "Official outlier identities lost")
    ledger$outlier_p_text <- as.character(outlier_table[data$SNP, "Pvalue"])
    numeric_p <- suppressWarnings(as.numeric(ledger$outlier_p_text))
    ledger$sensitivity_outlier <- ifelse(is.na(numeric_p), NA, numeric_p <= threshold)
    censored <- grepl("^<", ledger$outlier_p_text)
    limits <- suppressWarnings(as.numeric(substring(ledger$outlier_p_text[censored], 2)))
    require_true(all(is.finite(limits) & limits <= threshold), "Censored outlier P does not prove the frozen threshold")
    ledger$sensitivity_outlier[censored] <- TRUE
  }
  ledger$interpretation <- if (!outlier) "OUTLIER_TEST_NOT_REQUESTED" else if (is.null(outlier_table)) "GLOBAL_GATE_DID_NOT_RETURN_OUTLIER_TEST" else "OFFICIAL_SENSITIVITY_ONLY_NO_AUTOMATIC_REMOVAL"
  write_tsv(ledger, outputs[4])
  audit$status <- "TECHNICAL_METHOD_PASS_NOT_PRIMARY_IVW"
  audit$warnings_n <- length(warnings)
  audit$outlier_test_returned <- tolower(as.character(!is.null(outlier_table)))
  audit$distortion_test_returned <- tolower(as.character(!is.null(details[["Distortion Test"]])))
  audit$automatic_snps_removed <- "0"
  audit$summary_sha256 <- hash(outputs[1])
  audit$rds_sha256 <- hash(outputs[2])
  audit$snps_sha256 <- hash(outputs[4])
  save_audit()
  record("status\tPASS", "SNPs", row_count, "full_object_retained", TRUE)
}, error = function(error) {
  unlink(analytic)
  audit$status <- "BLOCKED"
  audit$error <- conditionMessage(error)
  save_audit(audit)
  record("status\tBLOCKED", conditionMessage(error))
  message(conditionMessage(error))
  quit(status = 2)
})
