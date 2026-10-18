main <- function() {
  binder <- identical(Sys.getenv("CACHEXIA_LCMM_MODE"), "bind")
  output_names <- if (binder) c("resolved_contract.json", "bind_audit.json", "bind.log") else
    c("summary.tsv", "state.rds", "audit.json", "lcmm.log", "row_ledger.tsv", "subject_map.tsv")
  port_names <- paste0("AUTONOMICS_OUTPUT", seq_along(output_names) - 1L)
  original_outputs <- Sys.getenv(port_names)
  if (any(!nzchar(original_outputs))) stop("Every declared output path is required")
  destinations <- vapply(original_outputs, function(filename)
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename)), character(1))
  if (anyDuplicated(destinations) || anyDuplicated(basename(destinations))) stop("Distinct output paths required")
  inputs <- vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), "")
  if (any(!nzchar(inputs))) stop("Three declared input paths are required")
  input_paths <- vapply(inputs, normalizePath, character(1), mustWork = TRUE)
  diagnostic <- file.path(dirname(destinations[[1L]]), "failed_fit.rds")
  protected <- if (binder) destinations else c(destinations, diagnostic)
  if (any(protected %in% input_paths)) stop("Input and output paths must be distinct")
  path_present <- function(filename) {
    target <- Sys.readlink(filename)
    file.exists(filename) || (!is.na(target) && nzchar(target))
  }
  if (any(vapply(protected, path_present, logical(1)))) stop("Refusing to overwrite existing output")
  stage <- tempfile(pattern = ".lcmm-owned-", tmpdir = dirname(destinations[[1L]]))
  if (!dir.create(stage, mode = "0700")) stop("Private output staging could not be created")
  created <- list()
  completed <- FALSE
  file_identity <- function(filename) {
    value <- system2("stat", c("-c", shQuote("%d:%i"), shQuote(filename)), stdout = TRUE, stderr = TRUE)
    if (!is.null(attr(value, "status")) || length(value) != 1L || !grepl("^[0-9]+:[0-9]+$", value)) {
      stop("Output file identity unavailable")
    }
    value[[1L]]
  }
  on.exit({
    do.call(Sys.setenv, as.list(original_outputs))
    if (!completed) {
      for (owned in rev(created)) {
        tryCatch({
          if (path_present(owned$path) && identical(file_identity(owned$path), owned$identity)) unlink(owned$path)
        }, error = function(error) warning(paste("Output rollback retained an unverified path:", conditionMessage(error))))
      }
    }
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  do.call(Sys.setenv, as.list(setNames(file.path(stage, basename(destinations)), port_names)))
  exit_status <- 0L
options(digits = 17, width = 200, contrasts = c("contr.treatment", "contr.poly"))
ROLE <- "SYNTHETIC_TRAJECTORY_TECHNICAL_NOT_LANDMARK_PREDICTION"
require_value <- function(value, message) if (!isTRUE(value)) stop(message, call. = FALSE)
exact <- function(value, keys) require_value(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) && setequal(names(value), keys), "Exact object keys required")
unique_json <- function(value) {
  if (is.list(value)) {
    require_value(is.null(names(value)) || !anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
    invisible(lapply(value, unique_json))
  }
}
text <- function(value) {
  require_value(is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) && identical(trimws(value), value) && !grepl("[[:cntrl:]]", value), "Exact lexical value required")
  value
}
strings <- function(value, empty = FALSE) {
  require_value(is.list(value) && is.null(names(value)), "Explicit string array required")
  result <- unname(vapply(value, text, ""))
  require_value((empty || length(result)) && !anyDuplicated(result), "Nonempty unique sequence required")
  result
}
number <- function(value, low, high, integer = FALSE) {
  require_value(is.numeric(value) && length(value) == 1L && is.finite(value) && value >= low && value <= high && (!integer || value == floor(value)), "Finite bounded number required")
  if (integer) as.integer(value) else as.numeric(value)
}
boolean <- function(value) require_value(is.logical(value) && length(value) == 1L && !is.na(value), "Boolean required")
checksum <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_value(is.null(attr(result, "status")) && length(result) == 1L && grepl("^[0-9a-f]{64} ", result), "Content SHA256 unavailable")
  substr(result, 1L, 64L)
}
read_json <- function(filename) {
  result <- jsonlite::fromJSON(filename, simplifyVector = FALSE)
  unique_json(result)
  result
}
read_data <- function(filename, schema, ids) {
  widths <- count.fields(filename, sep = "\t", quote = '"', comment.char = "", blank.lines.skip = FALSE)
  require_value(length(widths) > 1L && !anyNA(widths) && all(widths == widths[1L]), "Empty or ragged TSV")
  result <- read.delim(filename, sep = "\t", quote = '"', comment.char = "", colClasses = "character", check.names = FALSE, na.strings = NULL, fill = FALSE, blank.lines.skip = FALSE)
  require_value(is.list(schema) && identical(names(schema), names(result)) && !anyDuplicated(names(result)) && all(grepl("^[A-Za-z][A-Za-z0-9_]*$", names(result))), "Exact ordered safe schema required")
  for (name in names(schema)) {
    rule <- schema[[name]]
    exact(rule, c("type", "levels"))
    levels <- strings(rule$levels, TRUE)
    require_value(rule$type %in% c("id", "numeric", "factor") && (rule$type == "factor" || !length(levels)), "Unsupported schema type")
    if (rule$type == "numeric") {
      tokens <- result[[name]]
      converted <- suppressWarnings(as.numeric(tokens))
      require_value(all(grepl("^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$", tokens)) && all(is.finite(converted)), "This complete-observation route rejects missing/malformed/nonfinite values")
      result[[name]] <- converted
    } else {
      invisible(vapply(result[[name]], text, ""))
      if (rule$type == "factor") {
        require_value(length(levels) >= 2L && all(result[[name]] %in% levels), "Unknown factor levels")
        result[[name]] <- factor(result[[name]], levels = levels)
      }
    }
  }
  require_value("row_id" %in% names(schema) && schema$row_id$type == "id" && !anyDuplicated(result$row_id) && identical(result$row_id, ids), "Exact unique original row axis required")
  require_value(nrow(result) >= 2L && nrow(result) <= 1000L, "Bounded observation count required")
  result
}
formula_terms <- function(value, data, outcome = NULL, empty = FALSE) {
  terms <- strings(value, empty)
  if (identical(terms, "1")) return(if (is.null(outcome)) ~1 else reformulate("1", response = outcome))
  pieces <- unique(unlist(strsplit(terms, "[:*]")))
  require_value(all(pieces %in% names(data)) && all(grepl("^[A-Za-z][A-Za-z0-9_]*$", pieces)) && all(vapply(data[pieces], function(column) is.numeric(column) || is.factor(column), TRUE)), "Formula terms must name frozen numeric/factor columns")
  if (!length(terms)) return(~1)
  as.formula(paste(if (is.null(outcome)) "~" else paste(outcome, "~"), paste(terms, collapse = "+")))
}
validate_request <- function(request, mode) {
  exact(request, c("schema_version", "mode", "scope", "input_role", "scientific_qualification", "analysis_role", "test_id", "input0_sha256", "input2_sha256", "expected_row_ids", "max_input_bytes", "max_rows", "params"))
  require_value(identical(request$schema_version, 1L) && identical(request$mode, mode), "Version/mode contract mismatch")
  require_value(identical(request$scope, "TECHNICAL_ONLY_NOT_G0") && identical(request$input_role, "SYNTHETIC_TECHNICAL_INPUT") && identical(request$scientific_qualification, "NOT_GRANTED") && identical(request$analysis_role, ROLE), "Scientific qualification not granted by this technical route")
  text(request$test_id); strings(request$expected_row_ids)
  number(request$max_input_bytes, 1, 16*1024^2, TRUE); number(request$max_rows, 2, 1000, TRUE)
}
validate_bundle <- function(bundle) {
  require_value(is.list(bundle) && identical(bundle$scope, "TECHNICAL_ONLY_NOT_G0") && identical(bundle$analysis_role, ROLE) && inherits(bundle$fit, "hlme") && bundle$fit$conv == 1L && identical(bundle$mode, "fit"), "Complete converged official hlme fit bundle required")
  require_value(is.character(bundle$source_sha256) && grepl("^[0-9a-f]{64}$", bundle$source_sha256) && identical(bundle$row_ids, bundle$data$row_id), "Fit source/row identity missing")
  require_value(all(is.finite(bundle$fit$best)) && all(is.finite(bundle$fit$V)), "Nonfinite fit estimate/covariance")
  bundle
}
fit_model <- function(request, input, context) {
  params <- request$params
  exact(params, c("schema", "subject", "outcome", "time", "fixed", "mixture", "random", "classmb", "ng", "idiag", "nwg", "correlation", "maxiter", "convB", "convL", "convG", "seed", "initialization", "class_selection", "complete_observations_only"))
  require_value(identical(params$initialization, if (params$ng == 1L) "OFFICIAL_SINGLE_CLASS_DEFAULT" else "FROZEN_CONVERGED_SINGLE_CLASS_FIT") && identical(params$class_selection, "NONE_PRESPECIFIED_NG") && identical(params$complete_observations_only, TRUE), "No autonomous class selection/missingness handling")
  data <- read_data(input, params$schema, strings(request$expected_row_ids))
  require_value(nrow(data) <= request$max_rows, "Frozen row budget exceeded before fitting")
  subject <- text(params$subject); outcome <- text(params$outcome); time <- text(params$time)
  require_value(subject %in% names(data) && params$schema[[subject]]$type == "id" && outcome %in% names(data) && time %in% names(data) && is.numeric(data[[outcome]]) && is.numeric(data[[time]]), "Frozen lexical subject/numeric outcome and time required")
  require_value(!anyDuplicated(data[c(subject, time)]), "Duplicate subject-time observations")
  original_subjects <- unique(data[[subject]])
  map <- data.frame(subject_id = original_subjects, numeric_subject = seq_along(original_subjects), stringsAsFactors = FALSE)
  require_value(length(original_subjects) >= 2L && max(table(data[[subject]])) >= 2L, "Longitudinal observations for multiple subjects required")
  numeric_data <- data
  numeric_data[[subject]] <- match(data[[subject]], map$subject_id)
  ng <- number(params$ng, 1, 4, TRUE)
  number(params$seed, 0, 2147483646, TRUE)
  boolean(params$idiag); boolean(params$nwg)
  require_value(!params$nwg || length(params$random) > 0L, "nwg scales random-effect covariance, not residual variance")
  require_value(params$correlation %in% c("NONE", "BM", "AR"), "Explicit official correlation choice required")
  args <- list(fixed = formula_terms(params$fixed, data, outcome), data = numeric_data, subject = subject, ng = ng,
    idiag = params$idiag, nwg = params$nwg, maxiter = number(params$maxiter, 1, 1000, TRUE),
    convB = number(params$convB, 1e-12, 1e-3), convL = number(params$convL, 1e-12, 1e-3), convG = number(params$convG, 1e-12, 1e-3),
    na.action = 2L, verbose = FALSE, returndata = TRUE, var.time = time, partialH = FALSE, nproc = 1L)
  mixture <- strings(params$mixture, TRUE); random <- strings(params$random, TRUE); classmb <- strings(params$classmb, TRUE)
  require_value((ng == 1L && !length(mixture) && !length(classmb)) || (ng > 1L && length(mixture) > 0L), "Explicit mixture and class-membership rules required")
  if (length(mixture)) args$mixture <- formula_terms(params$mixture, data)
  if (length(random)) args$random <- formula_terms(params$random, data)
  if (length(classmb)) args$classmb <- formula_terms(params$classmb, data)
  if (params$correlation != "NONE") args$cor <- call(params$correlation, as.name(time))
  if (ng > 1L) {
    parent <- validate_bundle(readRDS(context))
    require_value(parent$fit$ng == 1L && identical(parent$source_sha256, request$input0_sha256) && identical(parent$data, data) && identical(parent$subject_map, map), "Initial fit must use exactly the same frozen data and subject bijection")
    require_value(identical(parent$request$params$fixed, params$fixed) && identical(parent$request$params$random, params$random) && identical(parent$request$params$idiag, params$idiag) && identical(parent$request$params$correlation, params$correlation), "Incompatible single-class initializer")
    args$B <- parent$fit
  } else {
    receipt <- read_json(context)
    exact(receipt, c("schema_version", "analysis_role", "source_sha256", "row_ids", "eligibility"))
    require_value(identical(receipt$schema_version, 1L) && identical(receipt$analysis_role, ROLE) && identical(receipt$source_sha256, request$input0_sha256) && identical(strings(receipt$row_ids), data$row_id) && identical(receipt$eligibility, "SYNTHETIC_COMPLETE_OBSERVATIONS_NOT_RESEARCH_PERMISSION"), "Frozen complete-observation technical receipt required")
  }
  RNGkind("Mersenne-Twister", "Inversion", "Rejection"); set.seed(params$seed)
  fit <- do.call(lcmm::hlme, args)
  if (fit$conv != 1L) {
    saveRDS(list(fit = fit, request = request, data = data, subject_map = map, status = "NONCONVERGED_NOT_ANALYTIC", rng_state = .Random.seed), file.path(dirname(Sys.getenv("AUTONOMICS_OUTPUT2")), "failed_fit.rds"), version = 3)
    stop("Official optimizer did not satisfy all convergence criteria; no fallback or analytic output", call. = FALSE)
  }
  require_value(all(is.finite(fit$best)) && all(is.finite(fit$V)) && fit$ns == nrow(map), "Fit estimates/covariance/subject universe invalid")
  list(mode = "fit", scope = "TECHNICAL_ONLY_NOT_G0", analysis_role = ROLE, fit = fit, data = data, row_ids = data$row_id,
    subject_map = map, source_sha256 = request$input0_sha256, schema = params$schema, request = request, rng_state = .Random.seed,
    result = NULL, lineage = list(list(mode = "fit", input0_sha256 = request$input0_sha256, input2_sha256 = request$input2_sha256)))
}
predict_model <- function(request, input, context) {
  params <- request$params
  exact(params, c("schema", "time", "draws", "prediction_role", "expected_fit_source_sha256"))
  require_value(identical(params$prediction_role, "CLASS_CONDITIONAL_TECHNICAL_NOT_FORECAST"), "No landmark/future prediction qualification")
  boolean(params$draws)
  parent <- validate_bundle(readRDS(input))
  require_value(identical(parent$source_sha256, params$expected_fit_source_sha256), "Wrong frozen fit source")
  data <- read_data(context, params$schema, strings(request$expected_row_ids))
  require_value(nrow(data) <= request$max_rows, "Frozen row budget exceeded before prediction")
  require_value(identical(text(params$time), parent$request$params$time) && params$time %in% names(data) && is.numeric(data[[params$time]]), "Prediction time axis differs")
  result <- lcmm::predictY(parent$fit, newdata = data, var.time = params$time, draws = params$draws, na.action = 2L)
  require_value(nrow(result$pred) == nrow(data) && all(is.finite(result$pred)), "Prediction output rows/nonfinite estimates differ")
  list(mode = "predict", scope = "TECHNICAL_ONLY_NOT_G0", analysis_role = ROLE, fit = parent$fit, result = result, data = data, row_ids = data$row_id,
    subject_map = parent$subject_map, source_sha256 = parent$source_sha256, schema = params$schema, request = request, rng_state = parent$rng_state,
    lineage = c(parent$lineage, list(list(mode = "predict", input0_sha256 = request$input0_sha256, input2_sha256 = request$input2_sha256))))
}
compare_models <- function(request, input, context) {
  params <- request$params
  exact(params, c("model_ids", "which", "expected_fit_source_sha256", "selection_role"))
  require_value(identical(params$selection_role, "DESCRIPTIVE_CRITERIA_NOT_CLASS_SELECTION_OR_BIOLOGICAL_SUBTYPE"), "Class selection/scientific claims not allowed")
  ids <- strings(params$model_ids)
  require_value(length(ids) == 2L, "Two uniquely identified complete fits required")
  first <- validate_bundle(readRDS(input)); second <- validate_bundle(readRDS(context))
  require_value(identical(first$source_sha256, params$expected_fit_source_sha256) && identical(first$source_sha256, second$source_sha256) && identical(first$data, second$data) && identical(first$row_ids, second$row_ids) && identical(first$subject_map, second$subject_map) && identical(first$row_ids, strings(request$expected_row_ids)), "Models must use the identical frozen observation universe, not merely equal sample counts")
  which <- strings(params$which)
  require_value(all(which %in% c("G", "loglik", "conv", "npm", "AIC", "BIC", "SABIC", "entropy", "ICL1", "ICL2", "%class")), "Unknown official summarytable field")
  fits <- setNames(list(first$fit, second$fit), ids)
  result <- do.call(lcmm::summarytable, c(unname(fits), list(which = which, display = FALSE)))
  require_value(nrow(result) == 2L, "Model family must remain complete")
  list(mode = "compare", scope = "TECHNICAL_ONLY_NOT_G0", analysis_role = ROLE, fits = fits, fit = first$fit, result = result,
    data = first$data, row_ids = first$row_ids, subject_map = first$subject_map, source_sha256 = first$source_sha256,
    schema = first$schema, request = request, result_model_ids = ids[order(c(first$fit$ng, second$fit$ng))], rng_state = NULL, lineage = list(first$lineage, second$lineage, list(mode = "compare", input0_sha256 = request$input0_sha256, input2_sha256 = request$input2_sha256)))
}
numeric_summary <- function(bundle) {
  records <- list()
  walk <- function(value, prefix) {
    if (is.numeric(value)) {
      labels <- names(value)
      for (index in seq_along(value)) {
        item <- value[index]
        kind <- if (is.nan(item)) "NAN" else if (is.na(item)) "MISSING" else if (is.infinite(item)) if (item > 0) "POS_INF" else "NEG_INF" else "FINITE"
        field <- paste0(prefix, "/", index, if (!is.null(labels)) paste0(":", labels[index]) else "")
        records[[length(records)+1L]] <<- data.frame(test_id = bundle$request$test_id, row_id = "0001", field = field, value = as.numeric(item), value_kind = kind, stringsAsFactors = FALSE)
      }
    } else if (is.list(value) && !is.data.frame(value) || is.data.frame(value)) {
      for (index in seq_along(value)) {
        name <- if (is.null(names(value))) as.character(index) else names(value)[index]
        if (!name %in% c("runtime", "call")) walk(value[[index]], paste0(prefix, "/", name))
      }
    }
  }
  walk(if (bundle$mode == "compare") bundle$fits else bundle$fit, "fit")
  walk(bundle$result, "result")
  require_value(length(records) > 0L, "No numeric official result")
  do.call(rbind, records)
}
run <- function() {
  suppressPackageStartupMessages(library(lcmm))
  require_value(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("lcmm")) == "2.2.2", "Pinned official runtime required")
  mode <- Sys.getenv("CACHEXIA_LCMM_MODE")
  require_value(mode %in% c("fit", "predict", "compare", "bind") && Sys.getenv("AUTONOMICS_INPUT_COUNT") == "3", "Declared mode and exactly three input ports required")
  paths <- vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), "")
  require_value(all(nzchar(paths)) && all(file.exists(paths)), "Missing declared inputs")
  require_value(all(file.info(paths)$size <= 16*1024^2), "Input hard byte budget exceeded")
  request <- read_json(paths[2L])
  validate_request(request, if (mode == "bind") text(request$mode) else mode)
  require_value(all(file.info(paths)$size <= request$max_input_bytes), "Frozen input byte budget exceeded")
  if (mode == "bind") {
    changed <- character()
    for (index in c(0L, 2L)) {
      key <- paste0("input", index, "_sha256")
      require_value(identical(request[[key]], "UPSTREAM_CONTENT_HASH"), "Binder only resolves explicit upstream placeholders, never literal hashes")
      request[[key]] <- checksum(paths[index+1L]); changed <- c(changed, key)
    }
    jsonlite::write_json(request, Sys.getenv("AUTONOMICS_OUTPUT0"), auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
    jsonlite::write_json(list(status = "TECHNICAL_BIND_PASS_NOT_SCIENTIFIC", only_source_sha256_changed = TRUE, changed_fields = changed, output0_sha256 = checksum(Sys.getenv("AUTONOMICS_OUTPUT0")), G0_granted = FALSE, resident_deployment_granted = FALSE), Sys.getenv("AUTONOMICS_OUTPUT1"), auto_unbox = TRUE, pretty = TRUE)
    cat("PASS hash-only frozen LCMM binding; no scientific permission\n", file = Sys.getenv("AUTONOMICS_OUTPUT2"))
    return(invisible(NULL))
  }
  for (index in c(0L, 2L)) require_value(identical(request[[paste0("input", index, "_sha256")]], checksum(paths[index+1L])), "Frozen input content hash differs")
  bundle <- switch(mode, fit = fit_model(request, paths[1L], paths[3L]), predict = predict_model(request, paths[1L], paths[3L]), compare = compare_models(request, paths[1L], paths[3L]))
  require_value(nrow(bundle$data) <= request$max_rows, "Frozen row budget exceeded")
  summary <- numeric_summary(bundle)
  write.table(summary, Sys.getenv("AUTONOMICS_OUTPUT0"), sep = "\t", row.names = FALSE, quote = TRUE, na = "NA")
  saveRDS(bundle, Sys.getenv("AUTONOMICS_OUTPUT1"), version = 3)
  write.table(data.frame(row_id = bundle$row_ids, status = "SYNTHETIC_COMPLETE_TECHNICAL_NOT_ELIGIBILITY"), Sys.getenv("AUTONOMICS_OUTPUT4"), sep = "\t", row.names = FALSE, quote = TRUE)
  write.table(bundle$subject_map, Sys.getenv("AUTONOMICS_OUTPUT5"), sep = "\t", row.names = FALSE, quote = TRUE)
  audit <- list(status = "TECHNICAL_PASS_NOT_SCIENTIFIC", mode = mode, request_json = jsonlite::toJSON(request, auto_unbox = TRUE, digits = NA, null = "null"),
    output0_sha256 = checksum(Sys.getenv("AUTONOMICS_OUTPUT0")), output1_sha256 = checksum(Sys.getenv("AUTONOMICS_OUTPUT1")), rows = nrow(summary), G0_granted = FALSE,
    resident_deployment_granted = FALSE, real_time_landmark_missingness_class_selection_or_biological_subtype_proven = FALSE)
  jsonlite::write_json(audit, Sys.getenv("AUTONOMICS_OUTPUT2"), auto_unbox = TRUE, pretty = TRUE, digits = NA)
  cat("PASS complete official lcmm object retained; technical only, not G0\n", file = Sys.getenv("AUTONOMICS_OUTPUT3"))
}
tryCatch(run(), error = function(error) {
  mode <- Sys.getenv("CACHEXIA_LCMM_MODE")
  binder <- identical(mode, "bind")
  for (index in if (binder) 0L else c(0L, 1L, 4L, 5L)) {
    path <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", index))
    if (nzchar(path) && file.exists(path)) unlink(path)
  }
  audit <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", if (binder) 1L else 2L))
  log <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", if (binder) 2L else 3L))
  if (nzchar(audit)) jsonlite::write_json(list(status = "BLOCKED", mode = mode, message = conditionMessage(error), G0_granted = FALSE, resident_deployment_granted = FALSE), audit, auto_unbox = TRUE, pretty = TRUE)
  if (nzchar(log)) cat(paste("BLOCKED", conditionMessage(error), "\n"), file = log)
  message(conditionMessage(error))
  exit_status <<- 1L
})
  positions <- if (exit_status == 0L) seq_along(destinations) else if (binder) c(2L, 3L) else c(3L, 4L)
  sources <- file.path(stage, basename(destinations[positions]))
  targets <- destinations[positions]
  failed_fit <- file.path(stage, "failed_fit.rds")
  if (!binder && exit_status != 0L && file.exists(failed_fit)) {
    sources <- c(sources, failed_fit)
    targets <- c(targets, diagnostic)
  }
  for (position in seq_along(sources)) {
    identity <- file_identity(sources[[position]])
    if (!file.link(sources[[position]], targets[[position]])) stop("Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(path = targets[[position]], identity = identity)
  }
  completed <- TRUE
  exit_status
}
exit_status <- main()
if (exit_status != 0L) quit(save = "no", status = exit_status)
