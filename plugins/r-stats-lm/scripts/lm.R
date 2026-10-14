options(stringsAsFactors = FALSE, digits = 17)

require_true <- function(value, message) {
  if (!isTRUE(value)) stop(message, call. = FALSE)
}

exact_keys <- function(value, keys, label) {
  require_true(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) &&
    setequal(names(value), keys), paste(label, "fields differ"))
}

scalar_text <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
    !grepl("[[:cntrl:]]", value)
}

symbol_name <- function(value) {
  scalar_text(value) && grepl("^[A-Za-z][A-Za-z0-9_]*$", value) &&
    identical(make.names(value), value) && value != "row_id"
}

has_link <- function(path) {
  link <- Sys.readlink(path)
  !is.na(link) && nzchar(link)
}

checked_path <- function(path, existing = TRUE) {
  require_true(scalar_text(path) && startsWith(path, "/") &&
    !grepl("(^|/)([.]|[.][.])(/|$)", path), "absolute non-traversing path required")
  ancestors <- path
  while (tail(ancestors, 1L) != "/") ancestors <- c(ancestors, dirname(tail(ancestors, 1L)))
  require_true(!any(vapply(ancestors, has_link, logical(1))), "symlink path forbidden")
  if (existing) {
    require_true(file.exists(path) && !dir.exists(path), "regular input required")
    require_true(system2("/usr/bin/test", c("-f", shQuote(path))) == 0L, "regular input required")
    require_true(file.info(path)$size <= 64 * 1024^2, "input exceeds byte budget")
  } else {
    require_true(!file.exists(path) && dir.exists(dirname(path)), "new output in existing directory required")
  }
  path
}

file_identity <- function(path) {
  if (!file.exists(path) || has_link(path)) return(NULL)
  value <- system2("stat", c("--printf=%d:%i", "--", shQuote(path)), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(value, "status")) || length(value) != 1L ||
      !grepl("^[0-9]+:[0-9]+$", value)) return(NULL)
  value
}

sha256 <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)

literal_tsv <- function(path) {
  connection <- file(path, "rb")
  bytes <- readBin(connection, "raw", n = file.info(path)$size)
  close(connection)
  require_true(!any(bytes == as.raw(0L)), "embedded NUL forbidden")
  lines <- readLines(path, warn = FALSE)
  require_true(length(lines) >= 2L && length(lines) <= 10001L && all(nzchar(lines)), "1..10000 nonempty rows required")
  require_true(!any(grepl('"', lines, fixed = TRUE)), "literal unquoted TSV required")
  fields <- lapply(sub("\r$", "", lines), function(line) {
    tokens <- strsplit(paste0(line, "\t__END__"), "\t", fixed = TRUE)[[1L]]
    tokens[-length(tokens)]
  })
  header <- fields[[1L]]
  require_true(length(header) <= 101L && all(nzchar(header)) && !anyDuplicated(header) &&
    all(lengths(fields) == length(header)), "unique header and rectangular TSV required")
  require_true(!any(grepl("[[:cntrl:]]", unlist(fields, use.names = FALSE))), "control characters forbidden")
  result <- as.data.frame(do.call(rbind, fields[-1L]), check.names = FALSE)
  names(result) <- header
  result
}

numeric_column <- function(value) {
  valid <- grepl("^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$", value)
  result <- suppressWarnings(as.numeric(value))
  require_true(all(valid) && all(is.finite(result)), "finite numeric model values required; no row deletion")
  result
}

value_kind <- function(value) {
  if (is.nan(value)) "NAN" else if (is.na(value)) "MISSING" else if (is.infinite(value)) {
    if (value < 0) "NEG_INF" else "POS_INF"
  } else "FINITE"
}

fit_model <- function(input, contract_path) {
  require_true(as.character(getRversion()) == "4.6.1" &&
    as.character(utils::packageVersion("stats")) == "4.6.1", "pinned R/stats version mismatch")
  for (package in c("jsonlite", "digest")) require_true(requireNamespace(package, quietly = TRUE), "dependency unavailable")
  checked_path(input)
  checked_path(contract_path)
  input_hash <- sha256(input)
  contract_hash <- sha256(contract_path)
  contract <- jsonlite::fromJSON(contract_path, simplifyVector = FALSE)
  exact_keys(contract, c("schema_version", "scope", "analysis_id", "input_sha256", "response",
    "columns", "terms", "intercept", "weights", "offset", "qr_tolerance", "conf_level"), "lm contract")
  require_true(identical(contract$schema_version, 1L) &&
    identical(contract$scope, "TECHNICAL_ONLY_NOT_G0") && scalar_text(contract$analysis_id), "technical contract required")
  require_true(identical(contract$input_sha256, input_hash), "input SHA256 mismatch")
  columns <- contract$columns
  require_true(is.list(columns) && length(columns) > 0L && length(columns) <= 100L &&
    !is.null(names(columns)) && !anyDuplicated(names(columns)) &&
    all(vapply(names(columns), symbol_name, logical(1))), "explicit unique model column definitions required")
  data <- literal_tsv(input)
  require_true(identical(names(data), c("row_id", names(columns))), "input column order differs from contract")
  require_true(all(nzchar(data$row_id)) && !anyDuplicated(data$row_id), "unique nonempty row identities required")
  contrasts <- list()
  for (name in names(columns)) {
    definition <- columns[[name]]
    require_true(is.list(definition) && scalar_text(definition$type), "typed column required")
    if (definition$type == "numeric") {
      exact_keys(definition, "type", "numeric column")
      data[[name]] <- numeric_column(data[[name]])
    } else {
      exact_keys(definition, c("type", "levels"), "factor column")
      require_true(identical(definition$type, "factor") && is.list(definition$levels) &&
        is.null(names(definition$levels)) && length(definition$levels) >= 2L &&
        all(vapply(definition$levels, scalar_text, logical(1))), "explicit factor levels required")
      levels <- unlist(definition$levels, use.names = FALSE)
      require_true(!anyDuplicated(levels) && setequal(data[[name]], levels), "factor levels are unknown, absent or duplicated")
      data[[name]] <- factor(data[[name]], levels = levels, ordered = FALSE)
      contrasts[[name]] <- stats::contr.treatment(levels, base = 1L)
    }
  }
  require_true(symbol_name(contract$response) && contract$response %in% names(columns) &&
    columns[[contract$response]]$type == "numeric", "numeric response required")
  require_true(is.logical(contract$intercept) && length(contract$intercept) == 1L &&
    !is.na(contract$intercept), "explicit intercept boolean required")
  optional_column <- function(value) {
    require_true(is.null(value) || (symbol_name(value) && value %in% names(columns) &&
      columns[[value]]$type == "numeric"), "numeric weight/offset column or null required")
    value
  }
  weight_name <- optional_column(contract$weights)
  offset_name <- optional_column(contract$offset)
  special <- c(contract$response, weight_name, offset_name)
  require_true(!anyDuplicated(special), "response, weights and offset must be distinct")
  require_true(is.list(contract$terms) && is.null(names(contract$terms)) && length(contract$terms) <= 100L, "explicit ordered term list required")
  labels <- vapply(contract$terms, function(term) {
    require_true(is.list(term) && is.null(names(term)) && length(term) > 0L &&
      all(vapply(term, symbol_name, logical(1))), "term must contain column symbols only")
    variables <- unlist(term, use.names = FALSE)
    require_true(!anyDuplicated(variables) && all(variables %in% setdiff(names(columns), special)), "invalid interaction variables")
    paste(variables, collapse = ":")
  }, character(1))
  canonical_terms <- vapply(contract$terms, function(term) paste(sort(unlist(term)), collapse = ":"), character(1))
  require_true(!anyDuplicated(canonical_terms) && (length(labels) > 0L || contract$intercept), "unique nonempty model required")
  used <- unique(unlist(contract$terms, use.names = FALSE))
  require_true(setequal(names(columns), c(special, used)), "unused columns forbidden")
  require_true(is.numeric(contract$qr_tolerance) && length(contract$qr_tolerance) == 1L &&
    is.finite(contract$qr_tolerance) && contract$qr_tolerance >= 1e-12 && contract$qr_tolerance <= 1e-3, "QR tolerance outside supported bounds")
  require_true(is.numeric(contract$conf_level) && length(contract$conf_level) == 1L &&
    is.finite(contract$conf_level) && contract$conf_level > 0 && contract$conf_level < 1, "confidence level outside (0,1)")
  formula <- if (length(labels)) stats::reformulate(labels, response = contract$response,
    intercept = contract$intercept, env = baseenv()) else stats::as.formula(paste(contract$response, "~ 1"), env = baseenv())
  arguments <- list(formula = formula, data = data, method = "qr", na.action = stats::na.fail,
    singular.ok = FALSE, model = TRUE, x = TRUE, y = TRUE, qr = TRUE, tol = contract$qr_tolerance)
  if (length(contrasts)) arguments$contrasts <- contrasts
  if (!is.null(weight_name)) {
    arguments$weights <- data[[weight_name]]
    require_true(all(arguments$weights >= 0) && any(arguments$weights > 0), "nonnegative weights with positive support required")
  }
  if (!is.null(offset_name)) arguments$offset <- data[[offset_name]]
  warnings <- character()
  fitted <- withCallingHandlers(do.call(stats::lm, arguments), warning = function(condition) {
    warnings <<- c(warnings, conditionMessage(condition))
    invokeRestart("muffleWarning")
  })
  require_true(fitted$df.residual > 0 && fitted$rank == ncol(fitted$x), "full rank with positive residual df required")
  summary <- withCallingHandlers(summary(fitted), warning = function(condition) {
    warnings <<- c(warnings, conditionMessage(condition))
    invokeRestart("muffleWarning")
  })
  interval <- stats::confint(fitted, level = contract$conf_level)
  coefficients <- data.frame(term = rownames(summary$coefficients),
    estimate = summary$coefficients[, 1L], std_error = summary$coefficients[, 2L],
    statistic = summary$coefficients[, 3L], p_value = summary$coefficients[, 4L],
    conf_low = interval[, 1L], conf_high = interval[, 2L], row.names = NULL)
  for (name in setdiff(names(coefficients), "term")) {
    coefficients[[paste0(name, "_kind")]] <- vapply(coefficients[[name]], value_kind, character(1))
  }
  observations <- data.frame(row_id = data$row_id, fitted = stats::fitted(fitted),
    residual = stats::residuals(fitted), weight = if (is.null(weight_name)) 1 else data[[weight_name]],
    row.names = NULL)
  require_true(identical(sha256(input), input_hash) && identical(sha256(contract_path), contract_hash), "inputs changed during fitting")
  list(contract = contract, fit = fitted, summary = summary, coefficients = coefficients,
    observations = observations, warnings = warnings, input_sha256 = input_hash, contract_sha256 = contract_hash)
}

main <- function() {
  outputs <- vapply(0:4, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1))
  invisible(lapply(outputs, checked_path, existing = FALSE))
  require_true(!anyDuplicated(outputs) && length(unique(dirname(outputs))) == 1L, "distinct outputs in one directory required")
  parent <- dirname(outputs[[1L]])
  stage <- tempfile(".r-stats-lm-", tmpdir = parent)
  require_true(dir.create(stage, mode = "0700"), "owned staging directory unavailable")
  stage_identity <- file_identity(stage)
  require_true(!is.null(stage_identity), "staging identity unavailable")
  staged <- file.path(stage, basename(outputs))
  published <- integer()
  identities <- rep(list(NULL), length(outputs))
  complete <- FALSE
  on.exit({
    if (!complete) for (index in published) {
      if (identical(file_identity(outputs[[index]]), identities[[index]])) unlink(outputs[[index]])
    }
    if (identical(file_identity(stage), stage_identity)) unlink(stage, recursive = TRUE)
  }, add = TRUE)
  result <- fit_model(Sys.getenv("AUTONOMICS_INPUT0"), Sys.getenv("AUTONOMICS_INPUT1"))
  utils::write.table(result$coefficients, staged[[1L]], sep = "\t", quote = TRUE, row.names = FALSE, na = "NA")
  utils::write.table(result$observations, staged[[2L]], sep = "\t", quote = TRUE, row.names = FALSE, na = "NA")
  saveRDS(list(fit = result$fit, summary = result$summary, covariance = stats::vcov(result$fit),
    contract = result$contract, row_id = result$observations$row_id, warnings = result$warnings), staged[[3L]], version = 3)
  writeLines(c(capture.output(print(result$summary)), result$warnings, capture.output(sessionInfo())), staged[[4L]])
  audit <- list(schema_version = 1L, analysis_id = result$contract$analysis_id,
    method = "stats::lm", R_version = as.character(getRversion()), stats_version = as.character(utils::packageVersion("stats")),
    input_sha256 = result$input_sha256, contract_sha256 = result$contract_sha256,
    rank = result$fit$rank, residual_df = result$fit$df.residual, input_rows = nrow(result$observations),
    nobs = stats::nobs(result$fit), zero_weight_rows = sum(result$observations$weight == 0),
    r_squared = result$summary$r.squared, r_squared_kind = value_kind(result$summary$r.squared),
    adjusted_r_squared = result$summary$adj.r.squared, warnings = as.list(result$warnings),
    scope = result$contract$scope, formal_authorized = FALSE, g0_granted = FALSE,
    outputs = lapply(seq_len(4L), function(index) list(port = index - 1L, sha256 = sha256(staged[[index]]))))
  jsonlite::write_json(audit, staged[[5L]], auto_unbox = TRUE, pretty = TRUE, digits = 17, na = "null")
  invisible(lapply(outputs, checked_path, existing = FALSE))
  for (index in seq_along(outputs)) {
    identities[[index]] <- file_identity(staged[[index]])
    require_true(!is.null(identities[[index]]), "staged output identity unavailable")
    require_true(file.link(staged[[index]], outputs[[index]]), "no-clobber publication failed")
    published <- c(published, index)
    require_true(identical(file_identity(outputs[[index]]), identities[[index]]), "published output identity changed")
  }
  complete <- TRUE
}

if (sys.nframe() == 0L) tryCatch(main(), error = function(condition) {
  message("BLOCKED: ", conditionMessage(condition))
  quit(status = 2L)
})
