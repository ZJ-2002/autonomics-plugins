options(digits = 17, width = 200)

port <- function(direction, index) Sys.getenv(paste0("AUTONOMICS_", direction, index))
write_tsv <- function(value, filename) write.table(value, filename, sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
lexical_table <- function(filename) {
  widths <- count.fields(filename, sep = "\t", quote = '"', comment.char = "", blank.lines.skip = FALSE)
  if (!length(widths) || anyNA(widths) || any(widths != widths[1])) stop("Ragged TSV is forbidden")
  value <- read.delim(filename, colClasses = "character", check.names = FALSE,
                      na.strings = NULL, quote = '"', comment.char = "", fill = FALSE,
                      blank.lines.skip = FALSE, stringsAsFactors = FALSE)
  if (anyDuplicated(names(value))) stop("Duplicate columns")
  value
}
check_id <- function(value) {
  if (!length(value) || anyNA(value) || any(!grepl("^[A-Za-z0-9_.:+-]+$", value)) || anyDuplicated(value)) stop("Unique lexical identities required")
}
numeric_vector <- function(value, missing = TRUE) {
  absent <- value %in% c("", "NA")
  result <- suppressWarnings(as.numeric(value))
  if ((!missing && any(absent)) || any(!is.finite(result[!absent]))) stop("Numeric values must be finite, with only explicit empty/NA missing")
  result[absent] <- NA_real_
  result
}
checksum <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status")) || length(result) != 1L || !grepl("^[0-9a-f]{64} ", result)) stop("Input identity could not be verified")
  substr(result, 1L, 64L)
}
value_kind <- function(value) {
  if (is.nan(value)) "NAN" else if (is.na(value)) "MISSING" else if (is.infinite(value)) {
    if (value < 0) "NEG_INF" else "POS_INF"
  } else "FINITE"
}
finite_slot <- function(value) if (!length(value) || !is.finite(value[1])) NA_real_ else unname(value[1])
run_statistics <- function() {
  if (as.character(getRversion()) != "4.5.1" || as.character(packageVersion("stats")) != "4.5.1") stop("Pinned official R/stats version mismatch")
  operation <- Sys.getenv("STATISTICS_OPERATION")
  keys <- lexical_table(port("INPUT", 1))
  if (!identical(names(keys), c("key", "value")) || !nrow(keys) || anyDuplicated(keys$key)) stop("Unique key/value contract required")
  contract <- setNames(as.list(keys$value), keys$key)
  required <- function(key) {
    value <- contract[[key]]
    if (is.null(value) || length(value) != 1L || !nzchar(value)) stop("Missing frozen method key: ", key)
    value
  }
  number <- function(key, low = -Inf, high = Inf) {
    value <- numeric_vector(required(key), FALSE)
    if (length(value) != 1L || value < low || value > high) stop("Method value outside contract bounds: ", key)
    value
  }
  logical_key <- function(key) {
    value <- required(key)
    if (!value %in% c("true", "false")) stop("Frozen true/false required: ", key)
    value == "true"
  }
  common <- c("operation", "scope", "test_id", "input_sha256", "missing_policy")
  method_keys <- switch(operation,
    t = c("mode", "mu", "alternative", "var_equal", "conf_level"),
    cor = c("method", "alternative", "exact", "continuity", "conf_level"),
    var = c("mode", "ratio", "alternative", "conf_level"),
    wilcox = c("mode", "mu", "alternative", "exact", "correct", "conf_int", "conf_level", "digits_rank", "tol_root"),
    prop = c("p", "alternative", "correct", "conf_level", "require_integer_counts"),
    adjust = c("method", "n_total", "alpha"), stop("Unknown statistics operation"))
  if (operation %in% c("t", "var", "wilcox") && required("mode") == "groups") method_keys <- c(method_keys, "group1", "group2")
  if (length(setdiff(names(contract), c(common, method_keys)))) stop("Unknown or irrelevant frozen method key")
  invisible(lapply(c(common, method_keys), required))
  if (required("operation") != operation || required("scope") != "TECHNICAL_ONLY_NOT_G0" || required("missing_policy") != "official") stop("Operation, scope or missing policy mismatch")
  check_id(required("test_id"))
  if (required("input_sha256") != checksum(port("INPUT", 0))) stop("Input SHA256 mismatch")
  data <- lexical_table(port("INPUT", 0))
  if (!"row_id" %in% names(data) || nrow(data) < 1L || nrow(data) > 10000L) stop("Data needs 1..10000 explicit row identities")
  check_id(data$row_id)
  args <- list()
  first_values <- second_values <- NULL
  if (operation %in% c("t", "cor", "var", "wilcox")) {
    mode <- if (operation == "cor") "paired" else required("mode")
    allowed <- if (operation == "var") c("wide", "groups") else if (operation == "cor") "paired" else c("one", "wide", "paired", "groups")
    if (!mode %in% allowed) stop("Unsupported data mode")
    columns <- switch(mode, one = c("row_id", "x"), groups = c("row_id", "x", "group"), c("row_id", "x", "y"))
    if (!identical(names(data), columns)) stop("Data columns differ from frozen mode")
    first_values <- numeric_vector(data$x)
    if (mode == "groups") {
      labels <- c(required("group1"), required("group2"))
      check_id(labels)
      if (!setequal(unique(data$group[nzchar(data$group)]), labels)) stop("Exactly the two frozen groups required")
      first_values <- first_values[data$group == labels[1]]
      second_values <- numeric_vector(data$x[data$group == labels[2]])
    } else if (mode %in% c("wide", "paired")) second_values <- numeric_vector(data$y)
    args <- list(x = first_values)
    if (!is.null(second_values)) args$y <- second_values
    if (operation %in% c("t", "wilcox")) args$paired <- mode == "paired"
  }
  if (operation != "adjust") {
    alt <- required("alternative")
    if (!alt %in% c("two.sided", "less", "greater")) stop("Unsupported alternative")
    level <- number("conf_level", 0, 1)
    if (level <= 0 || level >= 1) stop("Confidence level must be strictly within (0,1)")
    args$alternative <- alt
    args$conf.level <- level
  }
  if (operation %in% c("t", "wilcox")) args$mu <- number("mu")
  if (operation == "t") args$var.equal <- logical_key("var_equal")
  if (operation == "var") {
    args$ratio <- number("ratio", 0)
    if (args$ratio == 0) stop("Variance ratio must be positive")
  }
  if (operation %in% c("cor", "wilcox")) {
    exact <- required("exact")
    if (!exact %in% c("auto", "true", "false")) stop("Exact policy must be auto/true/false")
    if (exact != "auto") args$exact <- exact == "true"
  }
  if (operation == "cor") {
    args$method <- required("method")
    if (!args$method %in% c("pearson", "spearman", "kendall")) stop("Unknown correlation method")
    args$continuity <- logical_key("continuity")
  }
  if (operation == "wilcox") {
    args$correct <- logical_key("correct")
    args$conf.int <- logical_key("conf_int")
    args$tol.root <- number("tol_root", 1e-12, .1)
    args$digits.rank <- if (required("digits_rank") == "Inf") Inf else number("digits_rank", 1, 16)
    if (is.finite(args$digits.rank) && args$digits.rank != floor(args$digits.rank)) stop("digits_rank needs a positive integer or Inf")
  }
  if (operation == "prop") {
    if (!identical(names(data), c("row_id", "count", "total"))) stop("Proportion data columns differ")
    args$x <- numeric_vector(data$count)
    args$n <- numeric_vector(data$total)
    if (logical_key("require_integer_counts") && any(c(args$x, args$n) %% 1 != 0, na.rm = TRUE)) stop("Frozen integer counts required")
    if (required("p") != "NULL") args$p <- numeric_vector(strsplit(required("p"), ",", fixed = TRUE)[[1]], FALSE)
    args$correct <- logical_key("correct")
  }
  if (operation == "adjust") {
    if (!identical(names(data), c("row_id", "p_value"))) stop("Adjustment data columns differ")
    args$p <- numeric_vector(data$p_value)
    if (any(args$p < 0 | args$p > 1, na.rm = TRUE)) stop("P-values must be in [0,1]")
    args$method <- required("method")
    if (!args$method %in% c("bonferroni", "holm", "hochberg", "hommel", "BH", "BY", "fdr", "none")) stop("Unknown adjustment method")
    args$n <- number("n_total", nrow(data), 1e9)
    if (args$n != floor(args$n)) stop("Family n must be an integer")
    alpha <- number("alpha", 0, 1)
    if (alpha <= 0) stop("Alpha must be positive")
  }
  method <- switch(operation, t = stats::t.test, cor = stats::cor.test,
                   var = stats::var.test, wilcox = stats::wilcox.test,
                   prop = stats::prop.test, adjust = stats::p.adjust)
  warnings <- character()
  fit <- withCallingHandlers(do.call(method, args), warning = function(condition) {
    warnings <<- c(warnings, conditionMessage(condition))
    message("OFFICIAL_WARNING: ", conditionMessage(condition))
    invokeRestart("muffleWarning")
  })
  if (operation %in% c("cor", "wilcox") && required("exact") == "true" &&
      any(grepl("cannot compute exact", warnings, ignore.case = TRUE))) stop("Frozen exact=true would fall back; blocked")
  if (operation == "adjust") {
    summary <- data.frame(test_id = data$row_id, p_value = args$p, p_adj = as.numeric(fit),
                          reject = fit < alpha, family_n = args$n, method = args$method,
                          status = ifelse(is.na(fit), "NOT_ESTIMABLE", "ESTIMABLE"), check.names = FALSE)
    parameters <- data.frame(field = "adjusted_p", index = seq_along(fit), label = data$row_id,
                             value_kind = vapply(fit, value_kind, character(1)),
                             value = vapply(fit, function(value) format(value, digits = 17, trim = TRUE), character(1)))
  } else {
    bounds <- if (length(fit$conf.int)) unname(fit$conf.int) else c(NA_real_, NA_real_)
    parameters <- lapply(c("statistic", "parameter", "estimate", "null.value", "conf.int", "stderr"), function(field) {
      vector <- fit[[field]]
      if (!length(vector)) return(NULL)
      labels <- if (is.null(names(vector))) rep("UNNAMED", length(vector)) else names(vector)
      data.frame(field = field, index = seq_along(vector), label = labels,
                 value_kind = vapply(as.numeric(vector), value_kind, character(1)),
                 value = vapply(as.numeric(vector), function(value) format(value, digits = 17, trim = TRUE), character(1)))
    })
    parameters <- do.call(rbind, parameters)
    summary <- data.frame(test_id = required("test_id"),
       statistic = finite_slot(fit$statistic), p_value = finite_slot(fit$p.value),
       dof1 = finite_slot(fit$parameter), dof2 = finite_slot(fit$parameter[2]),
       estimate1 = finite_slot(fit$estimate), estimate2 = finite_slot(fit$estimate[2]),
       null_value = finite_slot(fit$null.value), stderr = finite_slot(fit$stderr),
       conf_low = finite_slot(bounds[1]), conf_high = finite_slot(bounds[2]),
       conf_low_type = value_kind(bounds[1]), conf_high_type = value_kind(bounds[2]),
       achieved_conf_level = finite_slot(attr(fit$conf.int, "conf.level")),
       alternative = fit$alternative, method = fit$method,
       status = if (is.finite(fit$p.value) && fit$p.value >= 0 && fit$p.value <= 1) "ESTIMABLE" else "NOT_ESTIMABLE",
       check.names = FALSE)
  }
  saveRDS(list(fit = fit, arguments = args, contract = contract, row_id = data$row_id,
               warnings = warnings, R_version = R.version.string), port("OUTPUT", 2))
  write_tsv(summary, port("OUTPUT", 0))
  write_tsv(parameters, port("OUTPUT", 1))
  facts <- c(status = "COMPLETED", operation = operation, R_version = R.version.string,
             stats_version = as.character(packageVersion("stats")), input_sha256 = checksum(port("INPUT", 0)),
             contract_sha256 = checksum(port("INPUT", 1)), raw_rows = nrow(data),
             not_estimable_rows = sum(summary$status == "NOT_ESTIMABLE"), warning_count = length(warnings),
             requested_alternative = if (operation == "adjust") "NOT_APPLICABLE" else required("alternative"),
             effective_alternative = if (operation == "adjust") "NOT_APPLICABLE" else fit$alternative,
             scientific_G0_granted = "false")
  for (index in 0:2) facts[paste0("output", index, "_sha256")] <- checksum(port("OUTPUT", index))
  write_tsv(data.frame(key = names(facts), value = unname(facts)), port("OUTPUT", 4))
  print(summary)
  print(sessionInfo())
}

for (index in 0:4) {
  filename <- port("OUTPUT", index)
  if (!nzchar(filename)) stop("Every declared output port must be bound")
  dir.create(dirname(filename), recursive = TRUE, showWarnings = FALSE)
}
connection <- file(port("OUTPUT", 3), "wt")
sink(connection)
sink(connection, type = "message")
failed <- tryCatch({ run_statistics(); FALSE }, error = function(condition) {
  message("BLOCKED: ", conditionMessage(condition))
  for (index in 0:2) unlink(port("OUTPUT", index))
  write_tsv(data.frame(key = c("status", "message"), value = c("BLOCKED", conditionMessage(condition))), port("OUTPUT", 4))
  TRUE
})
sink(type = "message")
sink()
close(connection)
if (failed) quit(status = 1)
