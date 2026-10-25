options(digits = 17, width = 200)
require_true <- function(value, message) if (!isTRUE(value)) stop(message, call. = FALSE)
sha256_file <- function(path) digest::digest(file = path, algo = "sha256")
scalar <- function(value, type) length(value) == 1L && !is.na(value) && typeof(value) %in% type
number <- function(value) scalar(value, c("double", "integer")) && is.finite(value)
exact_keys <- function(value, keys) {
  require_true(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) &&
                 setequal(names(value), keys), "Missing, duplicate or unknown contract keys")
}
check_duplicate_keys <- function(value) {
  if (!is.list(value)) return(invisible(NULL))
  if (!is.null(names(value))) require_true(!anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
  lapply(value, check_duplicate_keys)
  invisible(NULL)
}
read_json <- function(path) {
  require_true(file.info(path)$size <= 2 * 1024^2, "JSON byte budget exceeded")
  value <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  check_duplicate_keys(value)
  value
}
valid_id <- function(value) scalar(value, "character") && nzchar(value) && identical(value, trimws(value)) && !grepl("[\t\r\n]", value)
numeric_values <- function(result, test_id) {
  entries <- list()
  add <- function(path, value) {
    if (is.numeric(value)) {
      for (index in seq_along(value)) {
        current <- as.double(value[[index]])
        kind <- if (is.nan(current)) "NAN" else if (is.na(current)) "MISSING" else if (is.infinite(current)) {
          if (current > 0) "POS_INF" else "NEG_INF"
        } else "FINITE"
        text <- if (kind %in% c("NAN", "MISSING")) "NA" else if (kind == "POS_INF") "Inf" else if (kind == "NEG_INF") "-Inf" else sprintf("%.17g", current)
        field <- paste0(path, "/", sprintf("%05d", index))
        entries[[length(entries) + 1L]] <<- data.frame(test_id = test_id, row_id = "0001", field = field,
                                                     value = text, value_kind = kind, stringsAsFactors = FALSE)
      }
    } else if (is.list(value)) {
      require_true(!is.null(names(value)) && !anyDuplicated(names(value)), "Numeric official object has an ambiguous named axis")
      for (name in names(value)) add(paste(path, name, sep = "."), value[[name]])
    }
  }
  if (is.matrix(result)) {
    for (column in colnames(result)) for (row in rownames(result)) add(paste(row, column, sep = "."), result[row, column])
  } else add("result", result)
  require_true(length(entries) > 0L, "Official result contains no numeric fields")
  do.call(rbind, entries)
}
main <- function() {
  outputs <- vapply(0:4, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1))
  require_true(all(nzchar(outputs)) && !anyDuplicated(outputs) && !any(file.exists(outputs)), "Five distinct fresh declared output ports required")
  audit <- list(status = "RUNNING", G0_granted = FALSE, resident_deployment_granted = FALSE,
                scientific_qualification = "NOT_GRANTED")
  save_audit <- function() jsonlite::write_json(audit, outputs[[3]], auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = TRUE)
  save_audit()
  writeLines("RUNNING official sensitivity calculation; not G0", outputs[[4]])
  state <- NULL
  append_log <- function(text) cat(text, "\n", file = outputs[[4]], append = TRUE)
  tryCatch({
    require_true(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "2", "Exactly two file inputs required")
    require_true(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("EValue")) == "4.1.4" &&
                   as.character(packageVersion("metap")) == "1.14", "Frozen official runtime mismatch")
    inputs <- vapply(0:1, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), character(1))
    require_true(all(file.exists(inputs)) && file.info(inputs[[1]])$size <= 64 * 1024^2, "Input missing or byte budget exceeded")
    request <- read_json(inputs[[2]])
    exact_keys(request, c("schema_version", "operation", "scope", "analysis_role", "scientific_qualification", "test_id",
                          "input0_sha256", "expected_input_ids", "family_size", "params"))
    operation <- Sys.getenv("CACHEXIA_SENSITIVITY_OPERATION")
    require_true(operation %in% c("evalue", "combine") && identical(request$operation, operation), "Manifest operation and request differ")
    role <- if (operation == "evalue") "AUXILIARY_SENSITIVITY_NOT_CAUSAL_PROOF" else "AUXILIARY_INDEPENDENT_OMNIBUS_NOT_PRIMARY_IUT"
    require_true(number(request$schema_version) && request$schema_version == 1L && identical(request$scope, "TECHNICAL_ONLY_NOT_G0") &&
                   identical(request$analysis_role, role) && identical(request$scientific_qualification, "NOT_GRANTED"), "Scientific or primary-IUT role escalation forbidden")
    require_true(valid_id(request$test_id), "Canonical lexical test ID required")
    require_true(identical(request$input0_sha256, sha256_file(inputs[[1]])), "Input content hash mismatch")
    expected_ids <- unlist(request$expected_input_ids, use.names = FALSE)
    require_true(is.list(request$expected_input_ids) && is.null(names(request$expected_input_ids)) &&
                   is.character(expected_ids) && length(expected_ids) > 0L && !anyDuplicated(expected_ids) &&
                   all(vapply(as.list(expected_ids), valid_id, logical(1))) &&
                   number(request$family_size) && request$family_size == length(expected_ids), "Frozen complete input family required")
    messages <- warnings <- character()
    invoke <- function(expression) withCallingHandlers(expression,
      warning = function(condition) { warnings <<- c(warnings, conditionMessage(condition)); append_log(paste("WARNING", conditionMessage(condition))); invokeRestart("muffleWarning") },
      message = function(condition) { messages <<- c(messages, conditionMessage(condition)); append_log(paste("MESSAGE", conditionMessage(condition))); invokeRestart("muffleMessage") })
    official_result <- NULL
    result_status <- "ESTIMABLE"
    called <- FALSE
    if (operation == "evalue") {
      exact_keys(request$params, "method_contract")
      require_true(identical(request$params$method_contract, "FROZEN_EFFECT_FILE_ONLY") && length(expected_ids) == 1L, "EValue method is frozen in the effect file, not duplicated parameters")
      effect <- read_json(inputs[[1]])
      exact_keys(effect, c("effect_id", "measure", "est", "lo", "hi", "se", "sd", "delta", "true_val", "rare"))
      require_true(valid_id(effect$effect_id) && identical(effect$effect_id, expected_ids[[1]]), "Effect identity differs from frozen input")
      require_true(effect$measure %in% c("RR", "OR", "HR", "OLS", "MD") && number(effect$est) && number(effect$true_val), "Explicit finite effect measure and target required")
      for (name in c("lo", "hi", "se", "sd", "delta")) require_true(is.null(effect[[name]]) || number(effect[[name]]), "Nonfinite or wrong typed effect parameter")
      ratio <- effect$measure %in% c("RR", "OR", "HR")
      if (ratio) {
        require_true(effect$est >= 0 && effect$true_val >= 0 && (is.null(effect$lo) || effect$lo >= 0) &&
                       (is.null(effect$hi) || effect$hi >= 0), "Ratio estimates and confidence limits cannot be negative")
        require_true((is.null(effect$lo) || effect$lo <= effect$est) &&
                       (is.null(effect$hi) || effect$hi >= effect$est), "Estimate must lie inside confidence interval")
        require_true(is.null(effect$se) && is.null(effect$sd) && is.null(effect$delta), "Inapplicable ratio se/sd/contrast forbidden")
        arguments <- list(est = effect$est, lo = if (is.null(effect$lo)) NA_real_ else effect$lo,
                          hi = if (is.null(effect$hi)) NA_real_ else effect$hi, true = effect$true_val)
        if (effect$measure == "RR") require_true(is.null(effect$rare), "RR does not use rare") else {
          require_true(scalar(effect$rare, "logical"), "OR/HR require an explicit rare-outcome assumption")
          arguments$rare <- effect$rare
        }
      } else {
        require_true(is.null(effect$lo) && is.null(effect$hi) && is.null(effect$rare) &&
                       (is.null(effect$se) || effect$se >= 0), "MD/OLS use nonnegative se, not ratio limits or rare")
        arguments <- list(est = effect$est, se = if (is.null(effect$se)) NA_real_ else effect$se, true = effect$true_val)
        if (effect$measure == "OLS") {
          require_true(number(effect$sd) && effect$sd > 0 && number(effect$delta), "OLS requires positive outcome sd and explicit contrast")
          arguments$sd <- effect$sd
          arguments$delta <- effect$delta
        } else require_true(is.null(effect$sd) && is.null(effect$delta), "Standardized MD cannot be silently rescaled")
      }
      ledger <- data.frame(input_id = effect$effect_id, parameter = names(effect),
                           source_value = vapply(effect, function(value) as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = 17)), character(1)), stringsAsFactors = FALSE)
      rownames(ledger) <- NULL
      state <- list(request = request, input = effect, arguments = arguments, input_ledger = ledger, official_result = NULL)
      called_function <- paste0("evalues.", effect$measure)
      called <- TRUE
      official_result <- invoke(do.call(getExportedValue("EValue", called_function), arguments))
    } else {
      exact_keys(request$params, c("method", "weights", "r", "alpha", "log_p", "log_input", "null_assumptions"))
      parameters <- request$params
      require_true(identical(parameters$null_assumptions, "INDEPENDENT_CONTINUOUS_UNIFORM_NULL") &&
                     scalar(parameters$log_p, "logical") && scalar(parameters$log_input, "logical"), "Independent continuous-null assumption and explicit probability scales required")
      require_true(parameters$method %in% c("fisher", "stouffer", "tippett", "tippett_min", "tippett_max", "wilkinson"), "Unsupported combination method")
      components <- read.delim(inputs[[1]], colClasses = "character", na.strings = character(), check.names = FALSE, quote = "", fileEncoding = "UTF-8")
      require_true(identical(names(components), c("test_id", "p_value", "estimability_status")) &&
                     identical(components$test_id, expected_ids) && nrow(components) == request$family_size, "Component family identities, order or cardinality changed")
      require_true(all(components$estimability_status %in% c("ESTIMABLE", "UNESTIMABLE")), "Explicit component estimability states required")
      missing <- components$estimability_status == "UNESTIMABLE"
      require_true(all(components$p_value[missing] == "") && all(nzchar(components$p_value[!missing])), "Component missing mask disagrees with eligibility")
      probabilities <- suppressWarnings(as.numeric(components$p_value))
      require_true(all(is.finite(probabilities[!missing])), "Nonfinite component p value")
      if (parameters$log_input) require_true(parameters$method %in% c("fisher", "stouffer") && all(probabilities[!missing] <= 0), "Log input is allowed only for Fisher/Stouffer and cannot be positive")
      else require_true(all(probabilities[!missing] >= 0 & probabilities[!missing] <= 1), "Component p value outside [0,1]")
      if (parameters$method != "stouffer") require_true(is.null(parameters$weights), "Weights apply only to Stouffer")
      if (parameters$method == "wilkinson") require_true(number(parameters$r) && parameters$r == floor(parameters$r) &&
                                                          parameters$r >= 1 && parameters$r <= length(probabilities), "Frozen Wilkinson rank outside full component family")
      else require_true(is.null(parameters$r), "Wilkinson rank is inapplicable to this method")
      order_method <- parameters$method %in% c("tippett", "tippett_min", "tippett_max", "wilkinson")
      if (order_method) require_true(number(parameters$alpha), "Explicit official alpha convention required")
      else require_true(is.null(parameters$alpha), "Alpha is inapplicable to Fisher/Stouffer")
      arguments <- list(p = probabilities)
      if (parameters$method == "stouffer" && !is.null(parameters$weights)) {
        weights <- unlist(parameters$weights, use.names = FALSE)
        require_true(is.list(parameters$weights) && is.null(names(parameters$weights)) &&
                       is.numeric(weights) && length(weights) == length(probabilities) && all(is.finite(weights)), "Frozen Stouffer weight vector must cover every input")
        arguments$weights <- weights
      }
      arguments$log.p <- parameters$log_p
      if (order_method) arguments$alpha <- parameters$alpha else arguments$log.input <- parameters$log_input
      if (parameters$method == "wilkinson") arguments$r <- parameters$r
      called_function <- switch(parameters$method, fisher = "sumlog", stouffer = "sumz", tippett = "minimump",
                                tippett_min = "minimump", tippett_max = "maximump", wilkinson = "wilkinsonp")
      ledger <- data.frame(source_position = seq_len(nrow(components)) - 1L, components, check.names = FALSE, stringsAsFactors = FALSE)
      state <- list(request = request, input = components, arguments = arguments, input_ledger = ledger, official_result = NULL)
      if (any(missing)) result_status <- "UNESTIMABLE_COMPONENT" else {
        called <- TRUE
        official_result <- invoke(do.call(getExportedValue("metap", called_function), arguments))
        state$official_result <- official_result
        require_true(length(official_result$validp) == length(probabilities), "Official method omitted components; frozen family cannot shrink")
        if (any(grepl("Illegal r|Some studies omitted|Weights omitted", warnings))) stop("Official method changed frozen components or rank", call. = FALSE)
      }
    }
    state$official_result <- official_result
    values <- numeric_values(if (is.null(official_result)) list(combined_p = NA_real_) else official_result, request$test_id)
    if (result_status == "ESTIMABLE" && any(values$value_kind %in% c("MISSING", "NAN", "POS_INF", "NEG_INF"))) result_status <- "NONFINITE_OFFICIAL_RESULT"
    state$result_status <- result_status
    state$called_function <- called_function
    state$official_called <- called
    state$warnings <- warnings
    state$messages <- messages
    state$runtime <- sessionInfo()
    state$input0_sha256 <- sha256_file(inputs[[1]])
    state$request_json <- readChar(inputs[[2]], file.info(inputs[[2]])$size, useBytes = TRUE)
    saveRDS(state, outputs[[2]])
    write.table(values, outputs[[1]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    write.table(ledger, outputs[[5]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    audit <- c(audit[setdiff(names(audit), "status")], list(status = "TECHNICAL_PASS_NOT_SCIENTIFIC", result_status = result_status,
                operation = operation, called_function = called_function, official_called = called, warnings = warnings, messages = messages,
                request_json = state$request_json, input0_sha256 = state$input0_sha256, input1_sha256 = sha256_file(inputs[[2]]),
                output0_sha256 = sha256_file(outputs[[1]]), output1_sha256 = sha256_file(outputs[[2]]),
                input_ledger_sha256 = sha256_file(outputs[[5]]), rows = nrow(values), input_family_size = request$family_size))
    save_audit()
    append_log("PASS official result retained; no scientific release")
    0L
  }, error = function(condition) {
    if (!is.null(state)) saveRDS(state, file.path(dirname(outputs[[1]]), "failed_official_state.rds"))
    unlink(outputs[c(1, 2, 5)])
    audit$status <<- "BLOCKED"
    audit$error <<- conditionMessage(condition)
    save_audit()
    append_log(paste("BLOCKED", conditionMessage(condition)))
    message(conditionMessage(condition))
    2L
  })
}
quit(status = main())
