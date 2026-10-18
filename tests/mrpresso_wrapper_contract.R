arguments <- commandArgs(TRUE)
wrapper <- arguments[[1L]]
output <- arguments[[2L]]
baseline <- identical(arguments[[3L]], "baseline")
dir.create(output, recursive = TRUE, showWarnings = FALSE)

run_tests <- function() {
  original <- MRPRESSO::mr_presso
  on.exit(assignInNamespace("mr_presso", original, ns = "MRPRESSO"), add = TRUE)
  observations <- list()
  run_case <- function(name, beta = c("bX"), standard_error = c("sX"), setup = NULL,
                       expect_error = FALSE, expected_message = NULL, after = NULL,
                       array_literal = NULL, fail_author = FALSE, link_hook = NULL) {
    directory <- file.path(output, name)
    dir.create(directory)
    input <- file.path(directory, "input.tsv")
    result_path <- file.path(directory, "result.rds")
    log_path <- file.path(directory, "result.log")
    data <- data.frame(bX = c(0.1, 0.2, 0.3, 0.4), bX2 = c(0.2, 0.1, 0.4, 0.3),
                       bY = c(0.03, 0.07, 0.08, 0.13), sX = rep(0.01, 4),
                       sX2 = rep(0.02, 4), sY = rep(0.03, 4), a = 1:4, b = 2:5)
    write.table(data, input, sep = "\t", row.names = FALSE, quote = FALSE)
    called <- FALSE
    recorded <- NULL
    assignInNamespace("mr_presso", function(...) {
      called <<- TRUE
      if (fail_author) stop("AUTHOR_FAILURE", call. = FALSE)
      recorded <<- list(...)
      structure(list(captured = recorded), class = "recorded_author_call")
    }, ns = "MRPRESSO")
    literal <- function(values) paste0("c(", paste(vapply(values, function(value) encodeString(value, quote = '"'), character(1)), collapse = ","), ")")
    environment <- c(AUTONOMICS_INPUT0 = input, AUTONOMICS_OUTPUT0 = result_path,
      AUTONOMICS_OUTPUT1 = log_path, MRPRESSO_BETA_OUTCOME = "bY", MRPRESSO_SD_OUTCOME = "sY",
      MRPRESSO_BETA_EXPOSURE = paste(beta, collapse = " "), MRPRESSO_SD_EXPOSURE = paste(standard_error, collapse = " "),
      MRPRESSO_BETA_EXPOSURE_R = if (is.null(array_literal)) literal(beta) else array_literal,
      MRPRESSO_SD_EXPOSURE_R = literal(standard_error), MRPRESSO_OUTLIER_TEST = "false",
      MRPRESSO_DISTORTION_TEST = "false", MRPRESSO_SIGNIF_THRESHOLD = "0.05",
      MRPRESSO_NB_DISTRIBUTION = "1000", MRPRESSO_SEED = "123")
    if (!is.null(setup)) {
      changed <- setup(directory, input, result_path, log_path, environment)
      if (!is.null(changed)) environment <- changed
    }
    do.call(Sys.setenv, as.list(environment))
    local_environment <- new.env(parent = globalenv())
    if (!is.null(link_hook)) local_environment$file.link <- link_hook(directory, result_path, log_path)
    observed_error <- tryCatch({ sys.source(wrapper, envir = local_environment); NULL }, error = function(error) error)
    passed <- if (expect_error) !is.null(observed_error) else is.null(observed_error)
    if (passed && !is.null(expected_message)) passed <- grepl(expected_message, conditionMessage(observed_error), fixed = TRUE)
    if (passed && !expect_error) {
      observed <- readRDS(result_path)
      passed <- called && inherits(observed, "recorded_author_call") &&
        identical(observed$captured$BetaExposure, beta) && identical(observed$captured$SdExposure, standard_error) &&
        identical(observed$captured$data, data) && identical(observed$captured$OUTLIERtest, FALSE) &&
        identical(observed$captured$DISTORTIONtest, FALSE) && observed$captured$NbDistribution == 1000
    }
    if (passed && !is.null(after)) passed <- isTRUE(after(directory, input, result_path, log_path, called))
    if (passed) passed <- length(list.files(directory, pattern = "^\\.mrpresso-owned-", all.files = TRUE)) == 0L
    observations[[length(observations) + 1L]] <<- data.frame(name = name, pass = passed,
      author_stub_called = called, error = if (is.null(observed_error)) "" else conditionMessage(observed_error))
  }
  unchanged <- function(marker, target) function(directory, input, result_path, log_path, called) {
    destination <- if (target == "result") result_path else log_path
    !called && identical(readLines(destination, warn = FALSE), marker)
  }
  prior <- function(marker, target) function(directory, input, result_path, log_path, environment) {
    writeLines(marker, if (target == "result") result_path else log_path)
    environment
  }
  run_case("array-boundary-mismatch", beta = "a b", standard_error = c("sX", "sX2"),
    expect_error = TRUE, expected_message = "equal lengths")
  run_case("existing-result", setup = prior("FOREIGN_RESULT", "result"), expect_error = TRUE,
    expected_message = "overwrite", after = unchanged("FOREIGN_RESULT", "result"))
  run_case("existing-log", setup = prior("FOREIGN_LOG", "log"), expect_error = TRUE,
    expected_message = "overwrite", after = unchanged("FOREIGN_LOG", "log"))
  if (!baseline) {
    run_case("univariate")
    run_case("multivariate", beta = c("bX", "bX2"), standard_error = c("sX", "sX2"))
    run_case("array-expression-not-evaluated", array_literal = 'c(stop("INJECTED"))',
      expect_error = TRUE, expected_message = "character literals")
    run_case("no-lossy-fallback", setup = function(directory, input, result_path, log_path, environment) {
      environment[["MRPRESSO_BETA_EXPOSURE_R"]] <- ""
      environment
    }, expect_error = TRUE, expected_message = "Lossless")
    run_case("dangling-result", setup = function(directory, input, result_path, log_path, environment) {
      stopifnot(file.symlink(file.path(directory, "missing"), result_path))
      environment
    }, expect_error = TRUE, expected_message = "overwrite",
      after = function(directory, input, result_path, log_path, called) !called && nzchar(Sys.readlink(result_path)))
    run_case("output-alias", setup = function(directory, input, result_path, log_path, environment) {
      environment[["AUTONOMICS_OUTPUT1"]] <- result_path
      environment
    }, expect_error = TRUE, expected_message = "distinct")
    run_case("author-failure", fail_author = TRUE, expect_error = TRUE, expected_message = "AUTHOR_FAILURE",
      after = function(directory, input, result_path, log_path, called) called && !file.exists(result_path) && !file.exists(log_path))
    run_case("second-link-failure", link_hook = function(directory, result_path, log_path) {
      count <- 0L
      function(from, to) { count <<- count + 1L; if (count == 2L) return(FALSE); base::file.link(from, to) }
    }, expect_error = TRUE, expected_message = "publication",
      after = function(directory, input, result_path, log_path, called) !file.exists(result_path) && !file.exists(log_path))
    run_case("foreign-replacement", link_hook = function(directory, result_path, log_path) {
      count <- 0L
      function(from, to) {
        count <<- count + 1L
        if (count == 2L) { unlink(result_path); writeLines("FOREIGN_REPLACEMENT", result_path); return(FALSE) }
        base::file.link(from, to)
      }
    }, expect_error = TRUE, expected_message = "publication",
      after = function(directory, input, result_path, log_path, called) identical(readLines(result_path), "FOREIGN_REPLACEMENT") && !file.exists(log_path))
    run_case("foreign-publication-race", link_hook = function(directory, result_path, log_path) {
      function(from, to) { writeLines("FOREIGN_RACE", to); suppressWarnings(base::file.link(from, to)) }
    }, expect_error = TRUE, expected_message = "publication",
      after = function(directory, input, result_path, log_path, called) identical(readLines(result_path), "FOREIGN_RACE"))
  }
  result <- do.call(rbind, observations)
  write.table(result, file.path(output, "checks.tsv"), sep = "\t", row.names = FALSE, quote = TRUE)
  if (baseline) stopifnot(nrow(result) == 3L, all(!result$pass), all(result$author_stub_called)) else
    stopifnot(nrow(result) == 13L, all(result$pass))
}
run_tests()
