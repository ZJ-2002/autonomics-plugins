options(stringsAsFactors = FALSE, digits = 17)

OFFICIAL_REFERENCE_SHA256 <- "53c3bd5d1ffaa254ad1161a3d325f722f99c7816753c7ebdb4bc02e5416e7001"
OFFICIAL_REFERENCE_SOURCE <- r"---(args <- commandArgs(trailingOnly = TRUE)
configuration <- jsonlite::fromJSON(args[[1]], simplifyVector = TRUE)$spec
raw <- read.delim(args[[2]], colClasses = "character", check.names = FALSE,
                 na.strings = character(), quote = "", fileEncoding = "UTF-8")
donors <- sort(unique(raw[[configuration$donor_col]]))
observed_types <- sort(unique(raw[[configuration$cell_type_col]]))
family <- if (is.null(configuration$cell_types)) observed_types else configuration$cell_types
minimum_group <- if (is.null(configuration$min_donors_per_condition)) 1 else configuration$min_donors_per_condition
composition <- do.call(rbind, lapply(donors, function(donor) {
  rows <- raw[raw[[configuration$donor_col]] == donor, , drop = FALSE]
  totals <- nrow(rows)
  types <- sort(unique(c(observed_types, family)))
  counts <- vapply(types, function(cell_type) sum(rows[[configuration$cell_type_col]] == cell_type), numeric(1))
  data.frame(donor_id = donor, condition = unique(rows[[configuration$condition_col]]),
             cell_type = types, count = counts, donor_total = totals,
             proportion = counts / totals, eligible_by_cell_count = totals >= configuration$min_donor_cells,
             stringsAsFactors = FALSE)
}))
rownames(composition) <- NULL
models <- list()
tests <- do.call(rbind, lapply(family, function(cell_type) {
  observations <- composition[composition$cell_type == cell_type & composition$eligible_by_cell_count, , drop = FALSE]
  reference <- observations[observations$condition == configuration$reference, , drop = FALSE]
  test <- observations[observations$condition == configuration$test, , drop = FALSE]
  result <- data.frame(cell_type = cell_type, donors = nrow(observations), cells = sum(observations$count),
                       reference_proportion = if (nrow(reference)) mean(reference$proportion) else NA_real_,
                       test_proportion = if (nrow(test)) mean(test$proportion) else NA_real_,
                       log_odds_ratio = NA_real_, standard_error = NA_real_, z = NA_real_,
                       p_raw = NA_real_, p_adj = NA_real_, family_size = length(family),
                       reference_donors = nrow(reference), test_donors = nrow(test),
                       fit_status = "INSUFFICIENT_DONORS", stringsAsFactors = FALSE)
  if (nrow(reference) < minimum_group || nrow(test) < minimum_group) return(result)
  result$fit_status <- "NON_FINITE_MLE"
  group_counts <- c(sum(reference$count), sum(test$count))
  group_totals <- c(sum(reference$donor_total), sum(test$donor_total))
  if (any(group_counts == 0 | group_counts == group_totals)) return(result)
  observations$condition <- factor(observations$condition, levels = c(configuration$reference, configuration$test))
  model <- stats::glm(cbind(count, donor_total - count) ~ condition, data = observations,
                      family = stats::binomial(), control = stats::glm.control(epsilon = 1e-14, maxit = 100))
  stopifnot(model$converged, !model$boundary, model$rank == 2)
  coefficients <- summary(model)$coefficients[2, ]
  stopifnot(all(is.finite(coefficients)))
  result$log_odds_ratio <- unname(coefficients[[1]])
  result$standard_error <- unname(coefficients[[2]])
  result$z <- unname(coefficients[[3]])
  result$p_raw <- unname(coefficients[[4]])
  result$fit_status <- "ESTIMABLE"
  models[[cell_type]] <<- model
  result
}))
tests$p_adj <- stats::p.adjust(tests$p_raw, method = configuration$correction, n = length(family))
saveRDS(list(models = models, composition = composition, raw = raw, configuration = configuration,
             tests = tests, runtime = sessionInfo()), args[[4]])
jsonlite::write_json(list(tests = tests, composition = composition,
                          reference = list(version = as.character(getRversion()),
                                           url = "https://stat.ethz.ch/R-manual/R-devel/library/stats/html/glm.html",
                                           independent_entrypoint = TRUE)), args[[3]],
                     dataframe = "rows", auto_unbox = TRUE, na = "null", digits = NA, pretty = TRUE)
)---"

require_value <- function(value, message) {
  if (!isTRUE(value)) stop(message, call. = FALSE)
}

exact <- function(value, fields, label) {
  require_value(is.list(value) && !is.null(names(value)) && !anyDuplicated(names(value)) &&
    setequal(names(value), fields), paste(label, "fields differ"))
}

lexical <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
    identical(value, trimws(value)) && !grepl("[[:cntrl:]]", value)
}

strings <- function(value) {
  require_value(is.list(value) && is.null(names(value)) && length(value) > 0L &&
    all(vapply(value, lexical, logical(1))), "nonempty explicit string array required")
  result <- unlist(value, use.names = FALSE)
  require_value(!anyDuplicated(result), "duplicate explicit string identity")
  result
}

positive_integer <- function(value) {
  require_value(is.numeric(value) && length(value) == 1L && !is.na(value) &&
    is.finite(value) && value >= 1 && value <= 2147483647 && value == floor(value),
    "positive exact integer parameter required")
  value
}

has_link <- function(path) {
  link <- Sys.readlink(path)
  !is.na(link) && nzchar(link)
}

checked_path <- function(path, existing) {
  require_value(lexical(path) && startsWith(path, "/") &&
    !grepl("(^|/)([.]|[.][.])(/|$)", path), "absolute nontraversing path required")
  ancestors <- path
  while (tail(ancestors, 1L) != "/") ancestors <- c(ancestors, dirname(tail(ancestors, 1L)))
  require_value(!any(vapply(ancestors, has_link, logical(1))), "symlink path forbidden")
  if (existing) {
    require_value(file.exists(path) && !dir.exists(path) &&
      system2("/usr/bin/test", c("-f", shQuote(path))) == 0L &&
      file.info(path)$size <= 64 * 1024^2, "bounded regular input required")
  } else {
    require_value(!file.exists(path) && !has_link(path) && dir.exists(dirname(path)),
      "refusing to overwrite existing output")
  }
  path
}

checksum <- function(path) {
  result <- system2("/usr/bin/sha256sum", c("--", shQuote(path)), stdout = TRUE, stderr = TRUE)
  require_value(is.null(attr(result, "status")) && length(result) == 1L &&
    grepl("^[0-9a-f]{64} ", result), "SHA256 unavailable")
  substr(result, 1L, 64L)
}

inode <- function(path) {
  if (!file.exists(path) || has_link(path)) return(NULL)
  result <- system2("/usr/bin/stat", c("-c", "%d:%i:%f:%u:%g", "--", shQuote(path)), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status")) || length(result) != 1L) return(NULL)
  result
}

content_identity <- function(path) {
  before <- inode(path)
  if (is.null(before) || dir.exists(path)) return(NULL)
  digest <- tryCatch(checksum(path), error = function(error) NULL)
  if (is.null(digest) || !identical(before, inode(path))) return(NULL)
  list(inode = before, sha256 = digest)
}

remove_owned <- function(path, identity) {
  if (!is.null(identity) && identical(content_identity(path), identity)) unlink(path)
}

read_cells <- function(path, columns) {
  connection <- file(path, "rb")
  on.exit(close(connection), add = TRUE)
  payload <- readBin(connection, "raw", n = file.info(path)$size)
  require_value(!any(payload == as.raw(0L)), "NUL in cell TSV")
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  require_value(length(lines) >= 2L && length(lines) <= 1000001L && all(nzchar(lines)),
    "cell TSV requires1..1000000 complete nonblank rows")
  require_value(all(validUTF8(lines)), "invalid UTF8 cell TSV")
  fields <- lapply(sub("\r$", "", lines), function(line) {
    values <- strsplit(paste0(line, "\t__END__"), "\t", fixed = TRUE)[[1L]]
    values[-length(values)]
  })
  require_value(identical(fields[[1L]], columns) && all(lengths(fields) == length(columns)),
    "exact declared TSV column order and rectangular rows required")
  cells <- as.data.frame(do.call(rbind, fields[-1L]), check.names = FALSE)
  names(cells) <- columns
  require_value(all(vapply(unlist(cells, use.names = FALSE), lexical, logical(1))),
    "cell identities cannot be missing, empty, control or whitespace padded")
  cells
}

validate_request <- function(request_path, input_path) {
  checked_path(request_path, TRUE)
  checked_path(input_path, TRUE)
  input_hash <- checksum(input_path)
  request <- jsonlite::fromJSON(request_path, simplifyVector = FALSE)
  exact(request, c("schema_version", "scope", "analysis_id", "input_sha256", "columns", "spec"), "request")
  require_value(identical(request$schema_version, 1L) && identical(request$scope, "TECHNICAL_ONLY_NOT_G0") &&
    lexical(request$analysis_id) && identical(request$input_sha256, input_hash), "technical request/input identity mismatch")
  spec <- request$spec
  exact(spec, c("donor_col", "cell_type_col", "condition_col", "cell_id_col", "reference", "test",
    "cell_types", "min_donor_cells", "min_donors_per_condition", "correction"), "composition spec")
  raw_bindings <- spec[c("cell_id_col", "donor_col", "cell_type_col", "condition_col")]
  require_value(all(vapply(raw_bindings, lexical, logical(1))), "column bindings must be literal strings,not coerced IDs")
  bindings <- unlist(raw_bindings, use.names = FALSE)
  require_value(length(bindings) == 4L && all(vapply(bindings, lexical, logical(1))) && !anyDuplicated(bindings),
    "four distinct literal cell-column bindings required;cell_id is mandatory")
  columns <- strings(request$columns)
  require_value(length(columns) == 4L && setequal(columns, bindings), "exact four bound input columns required")
  require_value(lexical(spec$reference) && lexical(spec$test) && spec$reference != spec$test,
    "distinct literal reference/test required")
  family <- strings(spec$cell_types)
  require_value(length(family) <= 1000L && lexical(spec$correction) &&
    spec$correction %in% stats::p.adjust.methods, "explicit frozen family and official correction required")
  positive_integer(spec$min_donor_cells)
  positive_integer(spec$min_donors_per_condition)
  cells <- read_cells(input_path, columns)
  require_value(!anyDuplicated(cells[[spec$cell_id_col]]), "duplicate globally unique cell_id")
  require_value(all(cells[[spec$condition_col]] %in% c(spec$reference, spec$test)), "unexpected condition")
  donor_conditions <- split(cells[[spec$condition_col]], cells[[spec$donor_col]])
  require_value(all(lengths(lapply(donor_conditions, unique)) == 1L), "donor maps to multiple conditions")
  require_value(length(donor_conditions) >= 2L && all(c(spec$reference, spec$test) %in% cells[[spec$condition_col]]),
    "at least two donors and both conditions required")
  require_value(length(donor_conditions) <= 10000L &&
    length(donor_conditions) * length(union(unique(cells[[spec$cell_type_col]]), family)) <= 1000000L,
    "complete donor-by-type table exceeds fixed engineering budget;no truncation")
  list(request = request, cells = cells, input_sha256 = input_hash,
       request_sha256 = checksum(request_path), donor_count = length(donor_conditions))
}

preflight_outputs <- function(paths, inputs) {
  require_value(length(paths) == 5L && !anyDuplicated(paths), "five distinct declared outputs required")
  invisible(lapply(paths, checked_path, existing = FALSE))
  normalized <- vapply(paths, function(path) file.path(normalizePath(dirname(path), mustWork = TRUE), basename(path)), character(1))
  require_value(!anyDuplicated(normalized) && !any(normalized %in% vapply(inputs, normalizePath, character(1), mustWork = TRUE)),
    "output aliases another output or input")
  normalized
}

run_adapter <- function(environment = Sys.getenv()) {
  require_value(identical(unname(environment[["AUTONOMICS_INPUT_COUNT"]]), "2"), "exactly two declared input Files required")
  inputs <- unname(environment[paste0("AUTONOMICS_INPUT", 0:1)])
  outputs <- unname(environment[paste0("AUTONOMICS_OUTPUT", 0:4)])
  require_value(length(inputs) == 2L && all(nzchar(inputs)) && all(nzchar(outputs)), "declared input/output bindings missing")
  invisible(lapply(inputs, checked_path, existing = TRUE))
  outputs <- preflight_outputs(outputs, inputs)
  stage_inode <- NULL
  log <- NULL
  log_open <- FALSE
  log_inode <- NULL
  published <- list()
  staged_owned <- list()
  success <- FALSE
  stage <- tempfile(".donor-composition-", tmpdir = dirname(outputs[[1L]]))
  require_value(dir.create(stage, mode = "0700"), "owned staging directory unavailable")
  on.exit({
    if (!success) for (path in names(published)) remove_owned(path, published[[path]])
    if (log_open) close(log)
    for (path in names(staged_owned)) remove_owned(path, staged_owned[[path]])
    if (!is.null(stage_inode) && identical(inode(stage), stage_inode)) system2("/usr/bin/rmdir", c("--", shQuote(stage)), stdout = FALSE, stderr = FALSE)
  }, add = TRUE)
  stage_inode <- inode(stage)
  require_value(!is.null(stage_inode), "owned staging identity unavailable")
  log <- file(outputs[[5L]], open = "wx", encoding = "UTF-8")
  log_inode <- inode(outputs[[5L]])
  log_open <- TRUE
  tryCatch({
    require_value(!is.null(log_inode), "owned log identity unavailable")
    require_value(as.character(getRversion()) == "4.6.1" && as.character(utils::packageVersion("stats")) == "4.6.1",
      "pinned R/stats4.6.1 required")
    require_value(requireNamespace("jsonlite", quietly = TRUE), "jsonlite unavailable")
    checked <- validate_request(inputs[[1L]], inputs[[2L]])
    core <- file.path(stage, "official-reference.R")
    writeChar(OFFICIAL_REFERENCE_SOURCE, core, eos = NULL, useBytes = TRUE)
    staged_owned[[core]] <- content_identity(core)
    require_value(identical(checksum(core), OFFICIAL_REFERENCE_SHA256), "unchanged official-reference core identity mismatch")
    original_result <- file.path(stage, "reference.json")
    model <- file.path(stage, "models.RDS")
    core_log <- file.path(stage, "core.log")
    status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", shQuote(core), shQuote(inputs[[1L]]),
      shQuote(inputs[[2L]]), shQuote(original_result), shQuote(model)), stdout = core_log, stderr = core_log)
    for (path in c(original_result, model, core_log)) staged_owned[[path]] <- content_identity(path)
    if (file.exists(core_log)) writeLines(readLines(core_log, warn = FALSE), log)
    require_value(identical(status, 0L), "official grouped-binomial core failed;no normal output publication")
    result <- readRDS(model)
    family <- unlist(checked$request$spec$cell_types, use.names = FALSE)
    require_value(identical(result$tests$cell_type, family) && all(result$tests$family_size == length(family)) &&
      identical(names(result), c("models", "composition", "raw", "configuration", "tests", "runtime")) &&
      identical(result$raw, checked$cells), "complete official result or literal input identity differs")
    require_value(all(result$tests$fit_status %in% c("ESTIMABLE", "NON_FINITE_MLE", "INSUFFICIENT_DONORS")), "unknown fit status")
    for (column in c("p_raw", "p_adj")) require_value(all(is.na(result$tests[[column]]) |
      is.finite(result$tests[[column]]) & result$tests[[column]] >= 0 & result$tests[[column]] <= 1), "invalid official probability")
    staged <- c(file.path(stage, "tests.tsv"), file.path(stage, "composition.tsv"), model, file.path(stage, "audit.json"))
    write.table(result$tests, staged[[1L]], sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE, na = "", fileEncoding = "UTF-8")
    write.table(result$composition, staged[[2L]], sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE, na = "", fileEncoding = "UTF-8")
    audit <- list(schema_version = 1L, analysis_id = checked$request$analysis_id, scope = checked$request$scope,
      method = "stats::glm grouped-binomial two-condition dispersion1 Wald;stats::p.adjust full family",
      R_version = as.character(getRversion()), stats_version = as.character(utils::packageVersion("stats")),
      jsonlite_version = as.character(utils::packageVersion("jsonlite")), reference_core_sha256 = OFFICIAL_REFERENCE_SHA256,
      locale = Sys.getlocale(), locale_changed_by_adapter = FALSE,
      input_sha256 = checked$input_sha256, request_sha256 = checked$request_sha256,
      input_rows = nrow(checked$cells), donors = checked$donor_count, family = as.list(family), family_n = length(family),
      statuses = as.list(table(result$tests$fit_status)), all_family_nonestimable = all(result$tests$fit_status != "ESTIMABLE"),
      table_numeric_missing = "empty TSV field;literal NA string IDs remain lexical;use explicit schema,not broad NA token coercion",
      statistical_unit_warning = "Donor-aggregated grouped-binomial likelihood pools counts;NOT donor-overdispersion/robust SE/random effects/permutation",
      descriptive_estimand = "equal-donor mean proportions", fitted_estimand = "condition pooled binomial log odds",
      scientific_eligibility_verified = FALSE, g0_granted = FALSE)
    jsonlite::write_json(audit, staged[[4L]], auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null")
    for (path in staged) staged_owned[[path]] <- content_identity(path)
    require_value(identical(checksum(inputs[[1L]]), checked$request_sha256) &&
      identical(checksum(inputs[[2L]]), checked$input_sha256), "inputs changed during official fit")
    for (index in seq_along(staged)) {
      checked_path(outputs[[index]], FALSE)
      expected <- content_identity(staged[[index]])
      require_value(!is.null(expected) && file.link(staged[[index]], outputs[[index]]), "no-clobber publication failed")
      published[[outputs[[index]]]] <- expected
      require_value(identical(content_identity(outputs[[index]]), expected), "published output content/identity changed")
    }
    require_value(identical(inode(outputs[[5L]]), log_inode), "owned log replaced")
    writeLines(c("status\tPASS_TECHNICAL_ONLY_NOT_G0", paste0("family_n\t", length(family)),
      "method\tOFFICIAL_GROUPED_BINOMIAL_NOT_DONOR_ROBUST"), log)
    flush(log)
    for (path in names(published)) require_value(identical(content_identity(path), published[[path]]), "published output changed before completion")
    close(log)
    log_open <- FALSE
    success <- TRUE
    invisible(0L)
  }, error = function(error) {
    if (log_open) {
      writeLines(c("status\tBLOCKED", paste0("error\t", conditionMessage(error))), log)
      flush(log)
    }
    stop(error)
  })
}

if (sys.nframe() == 0L) tryCatch(run_adapter(), error = function(error) {
  message("BLOCKED: ", conditionMessage(error))
  quit(status = 2L)
})
