options(digits = 17, width = 200, contrasts = c("contr.treatment", "contr.poly"))

ROLE <- "SYNTHETIC_MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION"
ROOT_KEYS <- c("schema_version", "mode", "scope", "input_role", "scientific_qualification", "analysis_role", "test_id", "input0_sha256", "input2_sha256", "expected_row_ids", "expected_columns", "max_input_bytes", "max_rows", "params")
METHOD_KEYS <- list(
  mice = c("schema", "methods", "predictor_matrix", "visit_sequence", "where", "ignore", "m", "maxit", "seed", "rng_kind", "donors", "matchtype", "ridge", "ls_meth", "allow_overimputation", "include_original", "remove_constant", "remove_collinear", "logged_events_policy"),
  complete = c("action", "include", "mild", "order"),
  pmm = c("schema", "target", "predictors", "ry", "wy", "seed", "rng_kind", "donors", "matchtype", "ridge", "ls_meth", "exclude", "quantify", "trim", "use_matcher", "allow_overimputation"),
  logreg = c("schema", "target", "predictors", "ry", "wy", "seed", "rng_kind", "allow_overimputation")
)
require_value <- function(value, message) if (!isTRUE(value)) stop(message, call. = FALSE)
exact_keys <- function(value, keys) require_value(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) && setequal(names(value), keys), "Exact frozen keys required")
unique_json <- function(value) {
  if (is.list(value)) {
    require_value(is.null(names(value)) || !anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
    invisible(lapply(value, unique_json))
  }
}
text_value <- function(value, empty = FALSE) {
  require_value(is.character(value) && length(value) == 1L && !is.na(value) && (empty || nzchar(value)) && identical(value, trimws(value)) && !grepl("[[:cntrl:]]", value), "Exact lexical value required")
  value
}
strings <- function(value, unique = TRUE, empty = FALSE) {
  require_value(is.list(value) && is.null(names(value)), "Explicit string array required")
  output <- unname(vapply(value, text_value, "", empty = empty))
  require_value((empty || length(output) > 0L) && (!unique || !anyDuplicated(output)), "Empty/duplicate sequence")
  output
}
boolean <- function(value) {
  require_value(is.logical(value) && length(value) == 1L && !is.na(value), "Explicit boolean required")
  value
}
number <- function(value, low = -Inf, high = Inf) {
  require_value(is.numeric(value) && length(value) == 1L && is.finite(value) && value >= low && value <= high, "Finite bounded number required")
  as.numeric(value)
}
integer_value <- function(value, low, high) {
  output <- number(value, low, high)
  require_value(output == floor(output), "Exact integer required")
  as.integer(output)
}
mask <- function(value, size) {
  require_value(is.list(value) && is.null(names(value)) && length(value) == size, "Exact frozen mask axis required")
  unname(vapply(value, boolean, TRUE))
}
checksum <- function(filename) {
  output <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_value(is.null(attr(output, "status")) && length(output) == 1L && grepl("^[0-9a-f]{64} ", output), "Input SHA unavailable")
  substr(output, 1L, 64L)
}
lexical_table <- function(filename) {
  widths <- count.fields(filename, sep = "\t", quote = '"', comment.char = "", blank.lines.skip = FALSE)
  require_value(length(widths) > 1L && !anyNA(widths) && all(widths == widths[1]), "Empty/ragged TSV")
  output <- read.delim(filename, colClasses = "character", check.names = FALSE, na.strings = NULL, quote = '"', comment.char = "", fill = FALSE, blank.lines.skip = FALSE)
  require_value(!anyDuplicated(names(output)), "Duplicate TSV header")
  output
}
typed_data <- function(filename, request) {
  data <- lexical_table(filename)
  require_value(identical(names(data), c("row_id", strings(request$expected_columns))) && identical(data$row_id, strings(request$expected_row_ids)), "Frozen lexical input axes differ")
  columns <- strings(request$expected_columns)
  schema <- request$params$schema
  exact_keys(schema, columns)
  for (column in columns) {
    require_value(grepl("^[A-Za-z][A-Za-z0-9_]*$", column) && !column %in% c("row_id", "imp_num", "id_num"), "Unsafe/reserved model column")
    specification <- schema[[column]]
    exact_keys(specification, c("type", "levels"))
    levels <- strings(specification$levels, empty = TRUE)
    value <- data[[column]]
    absent <- value %in% c("", "NA")
    if (specification$type %in% c("numeric", "integer")) {
      require_value(length(levels) == 0L, "Numeric columns cannot have factor levels")
      if (specification$type == "integer") require_value(all(grepl("^[+-]?[0-9]+$", value[!absent])), "Integer tokens must be lexical integers")
      output <- suppressWarnings(as.numeric(value))
      require_value(all(is.finite(output[!absent])), "Nonfinite/malformed numeric input")
      output[absent] <- NA_real_
      if (specification$type == "integer") require_value(all(abs(output[!absent]) <= 2^31-1), "Integer overflow")
      data[[column]] <- output
    } else {
      require_value(specification$type %in% c("factor", "ordered") && length(levels) >= 2 && !any(levels %in% c("", "NA")) && all(value[!absent] %in% levels), "Explicit unambiguous factor levels required")
      data[[column]] <- factor(ifelse(absent, NA_character_, value), levels = levels, ordered = specification$type == "ordered")
    }
  }
  rownames(data) <- data$row_id
  data[columns]
}
receipt <- function(filename, data, request) {
  status <- lexical_table(filename)
  require_value(identical(names(status), c("row_id", "variable", "status", "imputation_allowed")), "Exact missingness receipt columns required")
  expected <- expand.grid(row_id = rownames(data), variable = names(data), KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
  require_value(identical(status$row_id, expected$row_id) && identical(status$variable, expected$variable) && all(status$imputation_allowed %in% c("TRUE", "FALSE")), "Complete ordered missingness receipt axis required")
  allowed_status <- c("OBSERVED", "ITEM_MISSING", "LOST_TO_FOLLOWUP", "REFUSED", "MEDICAL_CONTRAINDICATION", "NOT_APPLICABLE", "DECEASED", "STRUCTURAL_MISSING")
  require_value(all(status$status %in% allowed_status), "Unknown missingness state")
  absent <- as.vector(is.na(data))
  require_value(identical(status$status == "OBSERVED", !absent), "Missingness receipt contradicts data")
  protected <- status$status %in% c("MEDICAL_CONTRAINDICATION", "NOT_APPLICABLE", "DECEASED", "STRUCTURAL_MISSING")
  allowed <- status$imputation_allowed == "TRUE"
  require_value(!any(protected & allowed), "Protected/death/structural cells cannot be imputed")
  list(table = status, allowed = matrix(allowed, nrow(data), ncol(data), dimnames = dimnames(data)), protected = matrix(protected, nrow(data), ncol(data), dimnames = dimnames(data)))
}
set_rng <- function(params) {
  require_value(identical(strings(params$rng_kind), c("Mersenne-Twister", "Inversion", "Rejection")), "Frozen three-part official RNG kind required")
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  set.seed(integer_value(params$seed, 0, 2^31-1))
}
check_target_type <- function(target, method) {
  if (method %in% c("norm", "mean")) require_value(is.numeric(target), "Normal/mean methods require numeric target")
  if (method == "logreg") require_value(if (is.factor(target)) nlevels(target) == 2L else is.numeric(target) && all(na.omit(target) %in% c(0, 1)), "Logreg requires explicit binary target")
  if (method == "polyreg") require_value(is.factor(target) && !is.ordered(target) && nlevels(target) > 2, "Polyreg requires unordered factor target")
  if (method == "polr") require_value(is.ordered(target) && nlevels(target) > 2, "Polr requires ordered factor target")
}
value_kind <- function(value) if (is.nan(value)) "NAN" else if (is.na(value)) "MISSING" else if (is.infinite(value)) if (value > 0) "POS_INF" else "NEG_INF" else "FINITE"
values_table <- function(data, rows, imputations, test_id) {
  require_value(nrow(data) == length(rows) && nrow(data) == length(imputations), "Completed output axis differs")
  tables <- lapply(names(data), function(column) {
    original <- data[[column]]
    require_value(is.numeric(original) || is.factor(original) || is.logical(original), "Unsupported official output column type")
    value <- as.numeric(original)
    data.frame(test_id = test_id, row_id = rows, imputation = as.character(imputations), variable = column, value = value,
      value_kind = vapply(value, value_kind, ""), label = if (is.factor(original)) ifelse(is.na(original), "", as.character(original)) else "", stringsAsFactors = FALSE)
  })
  do.call(rbind, tables)
}
completion_values <- function(result, mids, params, test_id) {
  rows <- rownames(mids$data)
  if (inherits(result, "mild")) return(do.call(rbind, lapply(names(result), function(index) values_table(result[[index]], rows, rep(index, length(rows)), test_id))))
  action <- params$action
  if (is.character(action) && action %in% c("broad", "repeated")) {
    tables <- lapply(names(result), function(column) {
      index <- sub("^.*\\.", "", column)
      variable <- sub("\\.[0-9]+$", "", column)
      require_value(variable %in% names(mids$data), "Unexpected official broad/repeated column")
      values_table(setNames(data.frame(result[[column]]), variable), rows, rep(index, length(rows)), test_id)
    })
    return(do.call(rbind, tables))
  }
  if (is.character(action) && action == "long") return(values_table(result[names(mids$data)], as.character(result$.id), result$.imp, test_id))
  indices <- if (is.character(action)) if (params$include) 0:mids$m else seq_len(mids$m) else unlist(action, use.names = FALSE)
  if (params$include && !0 %in% indices) indices <- c(0L, indices)
  values_table(result, rep(rows, length(indices)), rep(indices, each = length(rows)), test_id)
}
complete_params <- function(params, mids) {
  exact_keys(params, METHOD_KEYS$complete)
  boolean(params$include); boolean(params$mild)
  require_value(params$order %in% c("first", "last"), "Frozen completion order required")
  if (is.character(params$action)) {
    require_value(length(params$action) == 1L && params$action %in% c("all", "long", "broad", "repeated", "stacked"), "Unknown official completion action")
    action <- params$action
  } else {
    require_value(is.list(params$action) && is.null(names(params$action)) && length(params$action) > 0, "Explicit action array required")
    action <- vapply(params$action, integer_value, 0L, low = 0, high = mids$m)
    require_value(!anyDuplicated(action), "Duplicate completion indices forbidden")
  }
  mice::complete(mids, action = action, include = params$include, mild = params$mild, order = params$order)
}
run_method <- function(data, status, params, mode, request) {
  if (mode == "mice") {
    exact_keys(params$methods, names(data))
    methods <- vapply(params$methods[names(data)], text_value, "", empty = TRUE)
    require_value(all(methods %in% c("", "pmm", "logreg", "norm", "mean", "sample", "polyreg", "polr")), "Explicit supported official method required; no inferred/passive/custom method")
    exact_keys(params$predictor_matrix, names(data))
    predictors <- t(vapply(params$predictor_matrix[names(data)], function(row) {
      require_value(is.list(row) && is.null(names(row)) && length(row) == ncol(data), "Exact predictor matrix axis required")
      vapply(row, integer_value, 0L, low = 0, high = 1)
    }, rep(0L, ncol(data))))
    dimnames(predictors) <- list(names(data), names(data))
    storage.mode(predictors) <- "double"
    require_value(all(diag(predictors) == 0), "Self predictors forbidden")
    exact_keys(params$where, names(data))
    where <- vapply(params$where[names(data)], mask, rep(TRUE, nrow(data)), size = nrow(data))
    dimnames(where) <- dimnames(data)
    ignore <- mask(params$ignore, nrow(data))
    allow_over <- boolean(params$allow_overimputation)
    require_value(!any(where & !status$allowed) && (allow_over || !any(where & !is.na(data))), "Frozen where mask violates eligibility/overimputation contract")
    protected_rows <- rowSums(status$protected) > 0
    require_value(all(ignore[protected_rows]) && !any(where[protected_rows, , drop = FALSE]), "Protected/death rows must be ignored and never imputed")
    visit <- strings(params$visit_sequence)
    targets <- names(methods)[nzchar(methods)]
    require_value(setequal(visit, targets) && all(colSums(where)[!nzchar(methods)] == 0), "Exact explicit visit/target/where contract required")
    require_value(!boolean(params$remove_constant) && !boolean(params$remove_collinear) && params$logged_events_policy == "FORBID", "No silent model/predictor alteration permitted")
    imputations <- integer_value(params$m, 1, 20)
    iterations <- integer_value(params$maxit, 1, 100)
    donors <- integer_value(params$donors, 1, nrow(data))
    matching <- integer_value(params$matchtype, 0, 2)
    ridge <- number(params$ridge, 1e-12, 1)
    require_value(params$ls_meth %in% c("qr", "svd", "ridge"), "Explicit least-squares method required")
    include_original <- boolean(params$include_original)
    for (target in targets) check_target_type(data[[target]], methods[[target]])
    set_rng(params)
    result <- mice::mice(data, m = imputations, maxit = iterations, method = methods,
      predictorMatrix = predictors, visitSequence = visit, where = where, ignore = ignore, printFlag = FALSE, seed = integer_value(params$seed, 0, 2^31-1),
      donors = donors, matchtype = matching, ridge = ridge, ls.meth = params$ls_meth, remove.constant = FALSE, remove.collinear = FALSE)
    require_value(is.null(result$loggedEvents) && identical(result$predictorMatrix, predictors) && identical(result$method, methods), "Official sampler altered frozen model or logged events")
    completion <- mice::complete(result, action = "long", include = include_original, order = "first")
    for (index in seq_len(result$m)) require_value(!anyNA(mice::complete(result, action = index)[where]), "Requested cells remained missing; no silent partial imputation")
    table <- values_table(completion[names(data)], as.character(completion$.id), completion$.imp, request$test_id)
    return(list(result = result, values = table, requested = where, diagnostics = list(chainMean = result$chainMean, chainVar = result$chainVar)))
  }
  target <- text_value(params$target)
  predictors <- strings(params$predictors, empty = TRUE)
  require_value(target %in% names(data) && all(predictors %in% names(data)) && !target %in% predictors, "Unknown/self predictor")
  observed <- mask(params$ry, nrow(data))
  requested <- mask(params$wy, nrow(data))
  protected_rows <- rowSums(status$protected) > 0
  require_value(!any(observed & is.na(data[[target]])) && !any(observed & protected_rows) && !any(requested & !status$allowed[, target]) && !any(requested & protected_rows), "Observed/imputation masks violate data/eligibility")
  require_value(boolean(params$allow_overimputation) || !any(requested & !is.na(data[[target]])), "Observed overimputation not frozen")
  require_value(any(requested), "No requested imputations")
  model <- stats::model.matrix(if (length(predictors)) reformulate(predictors) else ~1, data = data, na.action = stats::na.pass)
  require_value(nrow(model) == nrow(data) && all(is.finite(model)), "Complete finite frozen predictors required")
  model <- model[, colnames(model) != "(Intercept)", drop = FALSE]
  fit_matrix <- cbind(1, model[observed, , drop = FALSE])
  require_value(sum(observed) > ncol(fit_matrix) + 1L && qr(fit_matrix)$rank == ncol(fit_matrix), "Full-rank observed model and residual degrees of freedom required")
  check_target_type(data[[target]], mode)
  set_rng(params)
  if (mode == "pmm") {
    exclude <- if (length(params$exclude)) if (is.factor(data[[target]])) strings(params$exclude) else vapply(params$exclude, number, 0) else NULL
    require_value(is.numeric(data[[target]]) || is.factor(data[[target]]), "PMM target must be numeric/factor")
    require_value(params$ls_meth %in% c("qr", "svd", "ridge"), "Explicit least-squares method required")
    donors <- integer_value(params$donors, 1, sum(observed))
    matching <- integer_value(params$matchtype, 0, 2)
    ridge <- number(params$ridge, 1e-12, 1)
    quantify <- boolean(params$quantify)
    trim <- integer_value(params$trim, 1, sum(observed))
    use_matcher <- boolean(params$use_matcher)
    result <- mice::mice.impute.pmm(data[[target]], ry = observed, x = model, wy = requested, donors = donors,
      matchtype = matching, ridge = ridge, ls.meth = params$ls_meth, exclude = exclude, quantify = quantify, trim = trim, use.matcher = use_matcher)
  } else result <- mice::mice.impute.logreg(data[[target]], ry = observed, x = model, wy = requested)
  require_value(length(result) == sum(requested) && !anyNA(result), "Official imputation cardinality/missingness differs")
  emitted <- setNames(data.frame(result), target)
  where <- matrix(FALSE, nrow(data), ncol(data), dimnames = dimnames(data))
  where[, target] <- requested
  list(result = result, values = values_table(emitted, rownames(data)[requested], rep("1", sum(requested)), request$test_id), requested = where,
    diagnostics = list(observed_rows = sum(observed), requested_rows = sum(requested), predictor_columns = ncol(model)))
}
flatten_numeric <- function(value, prefix = "diagnostics") {
  if (is.numeric(value) || is.logical(value)) {
    labels <- if (is.null(names(value))) seq_along(value) else names(value)
    return(data.frame(field = paste(prefix, labels, sep = "/"), value = as.numeric(value), stringsAsFactors = FALSE))
  }
  if (is.list(value)) return(do.call(rbind, lapply(names(value), function(name) flatten_numeric(value[[name]], paste(prefix, name, sep = "/")))))
  NULL
}
run_mice <- function(outputs, audit) {
  require_value(requireNamespace("mice", quietly = TRUE) && as.character(packageVersion("mice")) == "3.19.0" && as.character(getRversion()) == "4.6.1", "Pinned official MICE runtime required")
  require_value(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "3", "Three exact input ports required")
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  contract <- Sys.getenv("AUTONOMICS_INPUT1")
  status_file <- Sys.getenv("AUTONOMICS_INPUT2")
  require_value(file.info(contract)$size <= 1024^2 && file.info(status_file)$size <= 4 * 1024^2, "Contract/status byte budget exceeded")
  request <- jsonlite::fromJSON(contract, simplifyVector = FALSE)
  unique_json(request); exact_keys(request, ROOT_KEYS)
  mode <- Sys.getenv("CACHEXIA_MICE_MODE")
  require_value(is.integer(request$schema_version) && identical(request$schema_version, 1L) && request$mode == mode && mode %in% names(METHOD_KEYS), "Exact method/schema required")
  require_value(request$scope == "TECHNICAL_ONLY_NOT_G0" && request$input_role == "SYNTHETIC_TECHNICAL_INPUT" && request$scientific_qualification == "NOT_GRANTED" && request$analysis_role == ROLE, "No scientific/longitudinal eligibility or G0 granted")
  text_value(request$test_id)
  rows <- strings(request$expected_row_ids)
  columns <- strings(request$expected_columns)
  require_value(length(rows) <= integer_value(request$max_rows, 2, 10000) && file.info(input)$size <= integer_value(request$max_input_bytes, 1, 16 * 1024^2) && checksum(input) == request$input0_sha256 && checksum(status_file) == request$input2_sha256, "Frozen source SHA/row/byte budgets differ")
  exact_keys(request$params, METHOD_KEYS[[mode]])
  warnings <- character()
  computed <- withCallingHandlers({
    if (mode == "complete") {
      bundle <- readRDS(input)
      require_value(identical(bundle$schema_version, 1L) && bundle$scope == request$scope && bundle$analysis_role == ROLE && identical(bundle$original_row_ids, rows) && identical(bundle$expected_columns, columns) && bundle$status_sha256 == request$input2_sha256 && mice::is.mids(bundle$result), "Complete official technical mids state required; long table is not mids")
      data <- bundle$original_data
      status <- receipt(status_file, data, request)
      result <- complete_params(request$params, bundle$result)
      computed <- list(result = result, values = completion_values(result, bundle$result, request$params, request$test_id), requested = bundle$requested,
        diagnostics = list(imputations = bundle$result$m, original_rows = nrow(data)))
      parent <- bundle
    } else {
      data <- typed_data(input, request)
      status <- receipt(status_file, data, request)
      computed <- run_method(data, status, request$params, mode, request)
      parent <- NULL
    }
    list(data = data, status = status, computed = computed, parent = parent)
  }, warning = function(notice) { warnings <<- c(warnings, conditionMessage(notice)); invokeRestart("muffleWarning") })
  require_value(!any(grepl("converg|failed|rank.deficien|logged events|not achieved|algorithm did not", warnings, ignore.case = TRUE)), "Official imputation failed/changed model; no force/fallback")
  values <- computed$computed$values
  require_value(nrow(values) > 0L && nrow(values) <= 1000000L && !any(values$value_kind %in% c("POS_INF", "NEG_INF", "NAN")), "Empty/oversized/nonfinite official imputation output")
  bundle <- list(schema_version = 1L, scope = request$scope, analysis_role = ROLE, original_row_ids = rows, expected_columns = columns, original_data = computed$data,
    missingness_receipt = computed$status$table, status_sha256 = request$input2_sha256, requested = computed$computed$requested, result = computed$computed$result,
    request = request, rng_state = if (mode == "complete") computed$parent$rng_state else if (exists(".Random.seed", .GlobalEnv)) get(".Random.seed", .GlobalEnv) else NULL, parent = computed$parent)
  saveRDS(bundle, outputs[2], version = 3, compress = "gzip")
  write.table(values, outputs[1], sep = "\t", quote = TRUE, row.names = FALSE, na = "NA")
  ledger <- computed$status$table
  ledger$requested_imputation <- as.vector(computed$computed$requested)
  ledger$original_missing <- as.vector(is.na(computed$data))
  write.table(ledger, outputs[5], sep = "\t", quote = TRUE, row.names = FALSE)
  diagnostics <- flatten_numeric(computed$computed$diagnostics)
  diagnostics$value_kind <- vapply(diagnostics$value, value_kind, "")
  write.table(diagnostics, outputs[6], sep = "\t", quote = TRUE, row.names = FALSE, na = "NA")
  audit$request_json <- rawToChar(readBin(contract, "raw", n = file.info(contract)$size))
  audit$contract_sha256 <- checksum(contract)
  audit$warnings <- warnings
  audit$output0_sha256 <- checksum(outputs[1])
  audit$output1_sha256 <- checksum(outputs[2])
  audit$original_rows <- length(rows)
  audit$result_rows <- nrow(values)
  audit$MICE_stationarity_MAR_MNAR_or_longitudinal_eligibility_proven <- FALSE
  audit$status <- "TECHNICAL_PASS_NOT_SCIENTIFIC"
  audit
}
main <- function() {
  outputs <- vapply(0:5, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), "")
  require_value(all(nzchar(outputs)) && !anyDuplicated(normalizePath(outputs, mustWork = FALSE)) && !any(file.exists(outputs)), "Refusing missing/aliased/overwritten output ports")
  audit <- list(status = "RUNNING", G0_granted = FALSE, scientific_qualification_granted = FALSE, resident_deployment_granted = FALSE)
  save_audit <- function() jsonlite::write_json(audit, outputs[3], auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
  save_audit()
  cat("RUNNING official MICE technical input\n", file = outputs[4])
  exit <- tryCatch({audit <- run_mice(outputs, audit); save_audit(); cat("PASS\n", file = outputs[4], append = TRUE); 0L}, error = function(error) {
    unlink(outputs[c(1, 2, 5, 6)])
    audit$status <<- "BLOCKED"; audit$error <<- conditionMessage(error)
    save_audit(); cat("BLOCKED ", conditionMessage(error), "\n", file = outputs[4], append = TRUE); message(conditionMessage(error)); 2L
  })
  quit(status = exit)
}
main()
