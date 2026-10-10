options(digits = 17, width = 200)

ROLE <- "SURVEY_TECHNICAL_BACKGROUND_ASSOCIATION_NOT_CANCER_MECHANISM"
METHOD_KEYS <- list(
  design = c("schema", "design", "domain"),
  mean = c("variables", "na_rm", "deff", "conf_level", "ci_df"),
  var = c("variables", "na_rm", "conf_level", "ci_df"),
  quantile = c("variables", "quantiles", "alpha", "interval_type", "na_rm", "ci", "se", "qrule", "df"),
  glm = c("response", "terms", "intercept", "family", "link", "rescale", "std_errors", "na_action", "maxit", "epsilon", "conf_level"),
  ttest = c("response", "group", "na_rm", "alternative", "mu", "conf_level"),
  post = c("columns", "population", "partial", "population_role"),
  rake = c("margins", "maxit", "epsilon", "population_role"),
  calibrate = c("terms", "intercept", "population", "calfun", "bounds", "maxit", "epsilon", "force", "population_role"),
  trim = c("lower", "upper", "strict")
)

require_value <- function(value, message) if (!isTRUE(value)) stop(message, call. = FALSE)
exact_keys <- function(value, keys) require_value(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) && setequal(names(value), keys), "Exact frozen object keys required")
unique_json <- function(value) {
  if (is.list(value)) {
    require_value(is.null(names(value)) || !anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
    invisible(lapply(value, unique_json))
  }
  invisible(value)
}
text_value <- function(value) {
  require_value(is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) && identical(trimws(value), value) && !grepl("[[:cntrl:]]", value), "Exact lexical value required")
  value
}
strings <- function(value, empty = FALSE) {
  require_value(is.list(value) && is.null(names(value)), "Explicit JSON string array required")
  result <- vapply(value, text_value, "")
  require_value((empty || length(result) > 0L) && !anyDuplicated(result), "Empty or duplicate frozen sequence")
  unname(result)
}
boolean <- function(value) {
  require_value(is.logical(value) && length(value) == 1L && !is.na(value), "Frozen boolean required")
  value
}
number <- function(value, low = -Inf, high = Inf) {
  require_value(is.numeric(value) && length(value) == 1L && is.finite(value) && value >= low && value <= high, "Finite bounded method number required")
  as.numeric(value)
}
integer_value <- function(value, low, high) {
  result <- number(value, low, high)
  require_value(result == floor(result), "Frozen integer required")
  as.integer(result)
}
checksum <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_value(is.null(attr(result, "status")) && length(result) == 1L && grepl("^[0-9a-f]{64} ", result), "Input SHA256 unavailable")
  substr(result, 1L, 64L)
}
lexical_table <- function(filename) {
  widths <- count.fields(filename, sep = "\t", quote = '"', comment.char = "", blank.lines.skip = FALSE)
  require_value(length(widths) > 1L && !anyNA(widths) && all(widths == widths[1]), "Empty or ragged TSV")
  result <- read.delim(filename, colClasses = "character", check.names = FALSE, na.strings = NULL, quote = '"', comment.char = "", fill = FALSE, blank.lines.skip = FALSE)
  require_value(!anyDuplicated(names(result)), "Duplicate TSV header")
  result
}
safe_columns <- function(value, data, empty = FALSE) {
  result <- strings(value, empty)
  require_value(all(result %in% names(data)) && all(grepl("^[A-Za-z][A-Za-z0-9_]*$", result)), "Unknown or unsafe column")
  result
}
safe_terms <- function(value, data) {
  result <- strings(value)
  require_value(all(vapply(strsplit(result, ":", fixed = TRUE), function(parts) all(grepl("^[A-Za-z][A-Za-z0-9_]*$", parts) & parts %in% names(data)), TRUE)), "Only frozen column/interaction terms allowed")
  result
}
numeric_column <- function(value) {
  absent <- value %in% c("", "NA")
  result <- suppressWarnings(as.numeric(value))
  require_value(all(is.finite(result[!absent])), "Nonfinite or malformed numeric data")
  result[absent] <- NA_real_
  result
}
typed_data <- function(filename, schema) {
  data <- lexical_table(filename)
  require_value(is.list(schema) && !is.null(names(schema)) && identical(names(schema), names(data)) && "row_id" %in% names(data), "Exact ordered data schema required")
  require_value(all(grepl("^[A-Za-z][A-Za-z0-9_]*$", names(data))), "Unsafe input header")
  for (column in names(schema)) {
    rule <- schema[[column]]
    exact_keys(rule, c("type", "levels"))
    type <- text_value(rule$type)
    levels <- strings(rule$levels, TRUE)
    require_value(type %in% c("numeric", "integer", "id", "factor") && (type == "factor" || !length(levels)), "Unknown schema type/levels")
    if (type %in% c("numeric", "integer")) {
      if (type == "integer") require_value(all(data[[column]] %in% c("", "NA") | grepl("^[+-]?[0-9]+$", data[[column]])), "Integer schema requires exact decimal integer tokens before float conversion")
      data[[column]] <- numeric_column(data[[column]])
      if (type == "integer") require_value(all(is.na(data[[column]]) | (abs(data[[column]]) <= 2147483647 & data[[column]] == floor(data[[column]]))), "Integer schema rejects fractional/out-of-range values")
    } else {
      invisible(vapply(data[[column]], text_value, ""))
      if (type == "factor") {
        require_value(length(levels) > 0L && all(data[[column]] %in% levels), "Factor level outside frozen schema")
        data[[column]] <- factor(data[[column]], levels = levels)
      }
    }
  }
  require_value(schema$row_id$type == "id" && !anyDuplicated(data$row_id), "Unique lexical row identities required")
  data
}
design_formula <- function(columns) if (!length(columns)) ~1 else reformulate(columns)
set_design_options <- function(spec) options(survey.lonely.psu = spec$lonely_psu, survey.adjust.domain.lonely = spec$adjust_domain_lonely)
build_design <- function(request, input) {
  params <- request$params
  data <- typed_data(input, params$schema)
  require_value(identical(data$row_id, strings(request$expected_row_ids)), "Frozen complete row axis/order differs")
  spec <- params$design
  exact_keys(spec, c("ids", "strata", "weights", "probs", "fpc", "nest", "check_strata", "pps", "variance", "lonely_psu", "adjust_domain_lonely"))
  ids <- safe_columns(spec$ids, data, TRUE)
  strata <- safe_columns(spec$strata, data, TRUE)
  probs <- safe_columns(spec$probs, data, TRUE)
  fpc <- safe_columns(spec$fpc, data, TRUE)
  weights <- if (is.null(spec$weights)) NULL else text_value(spec$weights)
  require_value(length(ids) <= 3L && length(strata) <= max(1L, length(ids)) && length(fpc) %in% c(0L, max(1L, length(ids))), "Frozen design stage counts differ")
  require_value(xor(!is.null(weights), length(probs) > 0L), "Exactly weights or probabilities required")
  for (column in unique(c(ids, strata, probs, fpc, weights))) require_value(column %in% names(data) && !anyNA(data[[column]]), "Missing design column/value")
  if (!is.null(weights)) require_value(is.numeric(data[[weights]]) && all(data[[weights]] >= 0) && sum(data[[weights]]) > 0, "Finite nonnegative sampling weights required")
  if (length(probs)) require_value(length(probs) == max(1L, length(ids)) && all(vapply(data[probs], function(value) is.numeric(value) && all(value > 0 & value <= 1), TRUE)), "Sampling probabilities must be in (0,1]")
  if (length(fpc)) require_value(all(vapply(data[fpc], function(value) is.numeric(value) && all(value > 0), TRUE)), "Positive finite FPC required")
  require_value(spec$pps %in% c("FALSE", "brewer", "overton") && spec$variance %in% c("HT", "YG") && spec$lonely_psu %in% c("fail", "adjust", "remove", "certainty", "average"), "Unknown PPS/variance/lonely-PSU policy")
  boolean(spec$nest); boolean(spec$check_strata); boolean(spec$adjust_domain_lonely)
  set_design_options(spec)
  design <- survey::svydesign(ids = design_formula(ids), strata = if (length(strata)) design_formula(strata) else NULL,
    weights = if (is.null(weights)) NULL else reformulate(weights), probs = if (length(probs)) design_formula(probs) else NULL,
    fpc = if (length(fpc)) design_formula(fpc) else NULL, data = data, nest = spec$nest, check.strata = spec$check_strata,
    pps = if (spec$pps == "FALSE") FALSE else spec$pps, variance = spec$variance, na_weights = "fail")
  domain <- params$domain
  exact_keys(domain, c("column", "values"))
  values <- strings(domain$values, TRUE)
  if (is.null(domain$column)) require_value(!length(values), "Absent domain cannot contain levels") else {
    column <- text_value(domain$column)
    require_value(column %in% names(data) && length(values) > 0L && all(values %in% as.character(data[[column]])), "Unknown/empty domain")
    design <- design[as.character(data[[column]]) %in% values, ]
  }
  require_value(nrow(design$variables) >= 2L, "Survey domain too small")
  list(schema_version = 1L, scope = "TECHNICAL_ONLY_NOT_G0", analysis_role = ROLE, original_row_ids = data$row_id,
    design_options = spec, design = design, result = NULL, lineage = list(list(mode = "design", request = request, parent_sha256 = request$input0_sha256)))
}
population_frame <- function(records, columns, data) {
  require_value(is.list(records) && is.null(names(records)) && length(records) > 0L, "Explicit population cells required")
  rows <- lapply(records, function(row) {
    exact_keys(row, c(columns, "Freq"))
    result <- lapply(columns, function(column) text_value(row[[column]]))
    names(result) <- columns
    result$Freq <- number(row$Freq, 0)
    result
  })
  population <- do.call(rbind, lapply(rows, as.data.frame, stringsAsFactors = FALSE))
  require_value(!anyDuplicated(population[columns]) && sum(population$Freq) > 0, "Duplicate/empty population cells")
  for (column in columns) if (is.factor(data[[column]])) {
    require_value(all(population[[column]] %in% levels(data[[column]])), "Unknown population level")
    population[[column]] <- factor(population[[column]], levels = levels(data[[column]]))
  }
  population
}
analyse <- function(bundle, request, mode) {
  params <- request$params
  design <- bundle$design
  data <- design$variables
  set_design_options(bundle$design_options)
  result <- NULL
  summary <- NULL
  if (mode %in% c("mean", "var", "quantile")) {
    variables <- safe_columns(params$variables, data)
    formula <- reformulate(variables)
    boolean(params$na_rm)
    if (mode == "quantile") {
      require_value(is.list(params$quantiles) && is.null(names(params$quantiles)) && length(params$quantiles) > 0, "Frozen quantile probabilities required")
      quantiles <- vapply(params$quantiles, number, 0, low = 0, high = 1)
      require_value(!anyDuplicated(quantiles) && params$interval_type %in% c("mean", "beta", "xlogit", "asin", "score") && params$qrule %in% c("math", "school", "shahvaish", paste0("hf", 1:9)), "Explicit quantile rule/interval required")
      boolean(params$ci); boolean(params$se)
      require_value(params$ci || !params$se, "Quantile SE requires official CI")
      alpha <- number(params$alpha, 1e-6, .999)
      df <- if (identical(params$df, "DESIGN")) NULL else number(params$df, 1)
      result <- survey::svyquantile(formula, design, quantiles = quantiles, alpha = alpha, interval.type = params$interval_type,
        na.rm = params$na_rm, ci = params$ci, se = params$se, qrule = params$qrule, df = df)
      summary <- list(result = unclass(result), dof = survey::degf(design))
    } else {
      level <- number(params$conf_level, 1e-6, .999999)
      require_value(params$ci_df %in% c("DESIGN", "INFINITY"), "Explicit confidence-interval degrees of freedom required")
      df <- if (params$ci_df == "DESIGN") survey::degf(design) else Inf
      result <- if (mode == "mean") survey::svymean(formula, design, na.rm = params$na_rm, deff = boolean(params$deff), influence = FALSE) else survey::svyvar(formula, design, na.rm = params$na_rm)
      summary <- list(coef = stats::coef(result), vcov = stats::vcov(result), confint = stats::confint(result, level = level, df = df), dof = survey::degf(design))
    }
  } else if (mode == "glm") {
    response <- text_value(params$response)
    require_value(response %in% names(data), "Unknown response")
    terms <- safe_terms(params$terms, data)
    formula <- reformulate(terms, response = response, intercept = boolean(params$intercept))
    require_value(params$family %in% c("gaussian", "binomial", "quasibinomial", "poisson", "quasipoisson", "Gamma", "inverse.gaussian") && params$std_errors %in% c("linearized", "Bell-McCaffrey", "Bell-McCaffrey-2") && params$na_action %in% c("na.fail", "na.omit"), "Unknown frozen GLM family/inference/missing policy")
    family <- get(params$family, asNamespace("stats"))(link = text_value(params$link))
    na_action <- get(params$na_action, asNamespace("stats"))
    frame <- stats::model.frame(formula, data, na.action = na_action)
    matrix <- stats::model.matrix(formula, frame)
    require_value(nrow(matrix) > ncol(matrix) && qr(matrix)$rank == ncol(matrix), "Rank-deficient/underdetermined model")
    result <- do.call(survey::svyglm, list(formula = formula, design = design, family = family, rescale = boolean(params$rescale), std.errors = params$std_errors,
      na.action = na_action, control = stats::glm.control(maxit = integer_value(params$maxit, 1, 1000), epsilon = number(params$epsilon, 1e-12, .01), trace = FALSE), influence = FALSE, deff = FALSE))
    require_value(isTRUE(result$converged) && !anyNA(stats::coef(result)), "Official GLM failed to converge/estimate all coefficients")
    summary <- list(coef = summary(result)$coefficients, vcov = stats::vcov(result), confint = stats::confint(result, level = number(params$conf_level, 1e-6, .999999)), residual_df = result$df.residual, design_df = survey::degf(design))
  } else if (mode == "ttest") {
    response <- text_value(params$response)
    require_value(response %in% names(data) && params$alternative == "two.sided" && number(params$mu) == 0 && number(params$conf_level) == .95, "Official svyttest exposes two-sided zero-null 95% CI only")
    boolean(params$na_rm)
    group <- if (is.null(params$group)) NULL else text_value(params$group)
    if (!is.null(group)) {
      require_value(group %in% names(data) && is.factor(data[[group]]) && length(unique(data[[group]])) == 2L, "Two frozen factor groups required")
      require_value(!params$na_rm && !anyNA(data[[response]]), "Two-group svyttest does not honor na.rm; complete response and explicit FALSE required")
    }
    formula <- if (is.null(group)) reformulate("1", response = response) else reformulate(group, response = response)
    result <- survey::svyttest(formula, design, na.rm = params$na_rm)
    summary <- unclass(result)
  } else if (mode == "post") {
    require_value(params$population_role == "SYNTHETIC_KNOWN_POPULATION_NOT_STUDY", "External population scientific qualification not granted")
    columns <- safe_columns(params$columns, data)
    population <- population_frame(params$population, columns, data)
    design <- survey::postStratify(design, reformulate(columns), population, partial = boolean(params$partial))
  } else if (mode == "rake") {
    require_value(params$population_role == "SYNTHETIC_KNOWN_POPULATION_NOT_STUDY" && is.list(params$margins) && is.null(names(params$margins)) && length(params$margins) > 0L, "Frozen population margins required")
    formulas <- populations <- list()
    for (margin in params$margins) {
      exact_keys(margin, c("columns", "population"))
      columns <- safe_columns(margin$columns, data)
      formulas[[length(formulas) + 1L]] <- reformulate(columns)
      populations[[length(populations) + 1L]] <- population_frame(margin$population, columns, data)
    }
    totals <- vapply(populations, function(population) sum(population$Freq), 0)
    require_value(max(totals) - min(totals) <= 1e-10 * max(totals), "Incompatible population margin totals")
    design <- survey::rake(design, sample.margins = formulas, population.margins = populations, control = list(maxit = integer_value(params$maxit, 1, 10000), epsilon = number(params$epsilon, 1e-12, .01), verbose = FALSE), compress = FALSE)
  } else if (mode == "calibrate") {
    require_value(params$population_role == "SYNTHETIC_KNOWN_POPULATION_NOT_STUDY" && !boolean(params$force), "Frozen synthetic population; force=FALSE required")
    terms <- safe_terms(params$terms, data)
    formula <- reformulate(terms, intercept = boolean(params$intercept))
    matrix <- stats::model.matrix(formula, data)
    require_value(qr(matrix)$rank == ncol(matrix) && is.list(params$population) && !anyDuplicated(names(params$population)) && setequal(names(params$population), colnames(matrix)), "Full-rank calibration and exact named population totals required")
    population <- vapply(params$population[colnames(matrix)], number, 0)
    require_value(params$calfun %in% c("linear", "raking", "logit") && is.list(params$bounds) && length(params$bounds) == 2L, "Frozen calibration method/bounds required")
    bounds <- vapply(params$bounds, number, 0)
    require_value(bounds[1] >= 0 && bounds[1] < bounds[2], "Ordered nonnegative calibration bounds required")
    design <- survey::calibrate(design, formula = formula, population = population, calfun = params$calfun, bounds = bounds,
      maxit = integer_value(params$maxit, 1, 10000), epsilon = number(params$epsilon, 1e-12, .01), force = FALSE, verbose = FALSE, bounds.const = FALSE, sparse = FALSE)
  } else if (mode == "trim") {
    lower <- number(params$lower, 0)
    upper <- number(params$upper, lower)
    require_value(lower < upper, "Ordered trimming bounds required")
    strict <- boolean(params$strict)
    average <- mean(stats::weights(design, "sampling"))
    require_value(!strict || (lower < average && average < upper), "Strict trimming must have feasible preserved weight total")
    design <- survey::trimWeights(design, upper = upper, lower = lower, strict = strict)
  } else stop("Unknown operation")
  if (mode %in% c("post", "rake", "calibrate", "trim")) {
    require_value(all(is.finite(stats::weights(design))) && all(stats::weights(design) >= 0), "Calibrated weights invalid")
    result <- design
    summary <- list(weights = setNames(stats::weights(design), design$variables$row_id), design_df = survey::degf(design))
  }
  bundle$design <- design
  bundle$result <- result
  bundle$lineage[[length(bundle$lineage) + 1L]] <- list(mode = mode, request = request, parent_sha256 = request$input0_sha256)
  list(bundle = bundle, summary = summary)
}
flatten_numeric <- function(value, prefix = "result") {
  if (is.numeric(value) || is.logical(value)) {
    labels <- if (is.null(names(value))) as.character(seq_along(value)) else names(value)
    if (is.matrix(value)) labels <- as.vector(outer(if (is.null(rownames(value))) seq_len(nrow(value)) else rownames(value), if (is.null(colnames(value))) seq_len(ncol(value)) else colnames(value), paste, sep = ":"))
    return(data.frame(field = paste(prefix, labels, sep = "/"), value = as.numeric(value), stringsAsFactors = FALSE))
  }
  if (is.list(value)) {
    labels <- if (is.null(names(value))) as.character(seq_along(value)) else names(value)
    pieces <- lapply(seq_along(value), function(index) flatten_numeric(value[[index]], paste(prefix, labels[index], sep = "/")))
    return(do.call(rbind, pieces))
  }
  NULL
}
value_kind <- function(value) if (is.nan(value)) "NAN" else if (is.na(value)) "MISSING" else if (is.infinite(value)) if (value > 0) "POS_INF" else "NEG_INF" else "FINITE"
run_survey <- function(outputs, audit) {
  require_value(requireNamespace("survey", quietly = TRUE), "Pinned official survey namespace unavailable")
  require_value(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("survey")) == "4.5", "Pinned R/survey versions differ")
  mode <- Sys.getenv("CACHEXIA_SURVEY_MODE")
  require_value(mode %in% names(METHOD_KEYS) && Sys.getenv("AUTONOMICS_INPUT_COUNT") == "2", "Mode/input count differs")
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  contract <- Sys.getenv("AUTONOMICS_INPUT1")
  require_value(file.info(contract)$size <= 1024^2, "Contract byte budget exceeded")
  request <- jsonlite::fromJSON(contract, simplifyVector = FALSE)
  unique_json(request)
  exact_keys(request, c("schema_version", "mode", "scope", "input_role", "scientific_qualification", "analysis_role", "test_id", "input0_sha256", "expected_row_ids", "max_input_bytes", "max_rows", "params"))
  require_value(is.integer(request$schema_version) && identical(request$schema_version, 1L) && request$mode == mode && request$scope == "TECHNICAL_ONLY_NOT_G0" && request$scientific_qualification == "NOT_GRANTED" && request$analysis_role == ROLE && request$input_role == "SYNTHETIC_TECHNICAL_INPUT", "Frozen technical-only scope required")
  test_id <- text_value(request$test_id)
  rows <- strings(request$expected_row_ids)
  integer_value(request$max_rows, 2, 10000)
  integer_value(request$max_input_bytes, 1, 16 * 1024^2)
  require_value(length(rows) <= request$max_rows && file.info(input)$size <= request$max_input_bytes && checksum(input) == request$input0_sha256, "Input SHA256/row/byte budget differs")
  exact_keys(request$params, METHOD_KEYS[[mode]])
  warnings <- character()
  computed <- withCallingHandlers({
    if (mode == "design") {
      bundle <- build_design(request, input)
      list(bundle = bundle, summary = list(weights = setNames(stats::weights(bundle$design), bundle$design$variables$row_id), design_df = survey::degf(bundle$design)))
    } else {
      bundle <- readRDS(input)
      exact_keys(bundle, c("schema_version", "scope", "analysis_role", "original_row_ids", "design_options", "design", "result", "lineage"))
      require_value(identical(bundle$schema_version, 1L) && bundle$scope == "TECHNICAL_ONLY_NOT_G0" && bundle$analysis_role == ROLE && inherits(bundle$design, "survey.design2") && identical(bundle$original_row_ids, rows), "Frozen official survey state differs; weights-only reconstruction forbidden")
      analyse(bundle, request, mode)
    }
  }, warning = function(notice) { warnings <<- c(warnings, conditionMessage(notice)); invokeRestart("muffleWarning") })
  require_value(!any(grepl("converg|failed|rank.deficien|iteration limit|not achieved", warnings, ignore.case = TRUE)), "Official operation did not converge/estimate; no force/fallback")
  table <- flatten_numeric(computed$summary)
  require_value(!is.null(table) && nrow(table) > 0L && nrow(table) <= 100000L, "Empty/oversized official summary")
  table$test_id <- test_id
  table$row_id <- paste0("field_", seq_len(nrow(table)))
  table$value_kind <- vapply(table$value, value_kind, "")
  table <- table[c("test_id", "row_id", "field", "value", "value_kind")]
  saveRDS(computed$bundle, outputs[2], compress = "gzip", version = 3)
  write.table(table, outputs[1], sep = "\t", row.names = FALSE, quote = TRUE, na = "NA")
  ledger <- data.frame(row_id = rows, status = ifelse(rows %in% computed$bundle$design$variables$row_id, "IN_DESIGN", "NOT_IN_DOMAIN"))
  write.table(ledger, outputs[5], sep = "\t", row.names = FALSE, quote = TRUE)
  audit$request_json <- rawToChar(readBin(contract, "raw", n = file.info(contract)$size))
  audit$contract_sha256 <- checksum(contract)
  audit$warnings <- warnings
  audit$output0_sha256 <- checksum(outputs[1])
  audit$output1_sha256 <- checksum(outputs[2])
  audit$summary_rows <- nrow(table)
  audit$active_rows <- nrow(computed$bundle$design$variables)
  audit$design_df <- survey::degf(computed$bundle$design)
  audit$design_class <- class(computed$bundle$design)
  audit$has_calibration <- !is.null(computed$bundle$design$postStrata)
  audit$status <- "TECHNICAL_PASS_NOT_SCIENTIFIC"
  audit
}
main <- function() {
  outputs <- vapply(0:4, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), "")
  require_value(all(nzchar(outputs)) && !anyDuplicated(normalizePath(outputs, mustWork = FALSE)) && !any(file.exists(outputs)), "Refusing missing/aliased/overwritten output ports")
  audit <- list(status = "RUNNING", G0_granted = FALSE, scientific_qualification_granted = FALSE, resident_deployment_granted = FALSE)
  save_audit <- function() jsonlite::write_json(audit, outputs[3], auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
  save_audit()
  cat("RUNNING ", ROLE, "\n", file = outputs[4])
  status <- tryCatch({
    audit <- run_survey(outputs, audit)
    save_audit()
    cat("PASS\n", file = outputs[4], append = TRUE)
    0L
  }, error = function(error) {
    unlink(outputs[c(1, 2, 5)])
    audit$status <<- "BLOCKED"
    audit$error <<- conditionMessage(error)
    save_audit()
    cat("BLOCKED ", conditionMessage(error), "\n", file = outputs[4], append = TRUE)
    message(conditionMessage(error))
    2L
  })
  quit(status = status)
}

main()
