arguments <- commandArgs(trailingOnly = TRUE)
collect <- function(filename) {
  definitions <- list()
  walk <- function(expression) {
    if (!is.call(expression) && !is.expression(expression)) return(invisible(NULL))
    if (is.call(expression) && identical(expression[[1L]], as.name("<-")) && length(expression) == 3L &&
        is.symbol(expression[[2L]]) && is.call(expression[[3L]]) &&
        identical(expression[[3L]][[1L]], as.name("function"))) {
      definitions[[as.character(expression[[2L]])]] <<- expression[[3L]]
    }
    invisible(lapply(as.list(expression), function(element) {
      if (!missing(element)) walk(element)
    }))
  }
  walk(parse(filename, keep.source = FALSE))
  definitions
}
previous <- collect(arguments[[1L]])
current <- collect(arguments[[2L]])
names <- c("require_value", "exact", "unique_json", "text", "strings", "number", "boolean",
           "checksum", "read_json", "read_data", "formula_terms", "validate_request", "validate_bundle",
           "fit_model", "predict_model", "compare_models", "numeric_summary", "run")
checks <- vapply(names, function(name) !is.null(previous[[name]]) &&
  !is.null(current[[name]]) && identical(previous[[name]], current[[name]]), logical(1))
write.table(data.frame(name = names, identical_AST = checks), arguments[[3L]],
            sep = "\t", row.names = FALSE, quote = FALSE)
stopifnot(length(checks) == 18L, all(checks))
