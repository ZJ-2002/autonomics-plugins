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
checks <- list()
publishers <- list()
for (name in c("survey.R", "bind_contract.R")) {
  previous <- collect(file.path(arguments[[1L]], name))
  current <- collect(file.path(arguments[[2L]], "scripts", name))
  expected <- setdiff(names(previous), "main")
  stopifnot(all(expected %in% names(current)))
  same <- vapply(expected, function(key) identical(previous[[key]], current[[key]]), logical(1))
  checks[[name]] <- data.frame(script = name, name = expected, identical_AST = same)
  publishers[[name]] <- current$publish_outputs
  stopifnot(all(same))
}
stopifnot(!is.null(publishers[[1L]]), identical(publishers[[1L]], publishers[[2L]]))
result <- do.call(rbind, checks)
write.table(result, arguments[[3L]], sep = "\t", row.names = FALSE, quote = FALSE)
cat("UNCHANGED_FUNCTION_AST_COUNT=", nrow(result), "\n", sep = "")
