suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
  library(broom.mixed)
  library(data.table)
})

publish <- function(path, writer) {
  if (file.exists(path)) stop(paste("output already exists:", path))
  temporary <- tempfile(".lme4-", tmpdir = dirname(path))
  on.exit(unlink(temporary))
  writer(temporary)
  if (!file.link(temporary, path)) stop(paste("cannot publish output:", path))
}

model_path <- Sys.getenv("AUTONOMICS_OUTPUT2")
fail <- function(message_text) {
  if (nzchar(model_path) && dir.exists(dirname(model_path)) && !file.exists(model_path)) {
    try(publish(model_path, function(path) writeLines(c("status: failed", message_text), path)), silent = TRUE)
  }
  message(message_text)
  quit(status = 2)
}

integer_setting <- function(name, default) {
  value <- suppressWarnings(as.numeric(Sys.getenv(name, default)))
  if (length(value) != 1L || !is.finite(value) || value < 0 ||
      value > .Machine$integer.max || value != floor(value)) {
    stop(paste(name, "must be a nonnegative integer"))
  }
  as.integer(value)
}

logical_setting <- function(name, default) {
  value <- tolower(Sys.getenv(name, default))
  if (!value %in% c("true", "false")) stop(paste(name, "must be true or false"))
  value == "true"
}

run_model <- function() {
  formula_text <- Sys.getenv("LME4_FORMULA")
  family_text <- Sys.getenv("LME4_FAMILY", "gaussian")
  reml <- logical_setting("LME4_REML", "true")
  reliable_only <- logical_setting("LME4_RELIABLE_ONLY", "true")
  ddf <- tolower(Sys.getenv("LME4_DDF", "satterthwaite"))
  nagq <- integer_setting("LME4_NAGQ", "1")
  n_boot <- integer_setting("LME4_NBOOT", "0")
  seed <- integer_setting("LME4_SEED", "42")
  input_path <- Sys.getenv("AUTONOMICS_INPUT0")
  output_paths <- c(Sys.getenv("AUTONOMICS_OUTPUT0"), Sys.getenv("AUTONOMICS_OUTPUT1"), model_path)
  if (any(!nzchar(output_paths)) || anyDuplicated(output_paths) ||
      any(!dir.exists(dirname(output_paths)))) stop("three distinct output paths with existing parents are required")
  if (any(file.exists(output_paths))) stop("output already exists; overwrite is forbidden")
  if (!nzchar(formula_text)) stop("LME4_FORMULA is empty")
  if (!family_text %in% c("gaussian", "binomial", "poisson")) stop("unsupported family")
  if (!ddf %in% c("satterthwaite", "kenward")) stop("unsupported ddf")
  if (family_text == "gaussian" && ddf == "kenward" && !reml) {
    stop("Kenward-Roger's method is only available for REML model fits")
  }
  frame <- withCallingHandlers(
    fread(input_path, sep = "\t", na.strings = c("NA", ""), keepLeadingZeros = TRUE),
    warning = function(warning_value) stop(conditionMessage(warning_value))
  )
  if (!nrow(frame) || anyDuplicated(names(frame))) stop("input must have rows and unique column names")
  parsed <- as.formula(formula_text)
  needed <- all.vars(parsed)
  if (length(setdiff(needed, names(frame)))) stop("columns missing from input")
  if (anyNA(frame[, needed, with = FALSE])) stop("missing model values; silent row omission is forbidden")
  for (column in needed) {
    if (is.numeric(frame[[column]]) && any(!is.finite(frame[[column]]))) stop("nonfinite model values")
  }
  set.seed(seed)
  fit_warnings <- character()
  fitted <- withCallingHandlers({
    if (family_text == "gaussian") {
      lmerTest::lmer(parsed, data = frame, REML = reml, na.action = na.fail,
                    control = lmerControl(check.rankX = "stop.deficient"))
    } else {
      glmer(parsed, data = frame, family = family_text, nAGQ = nagq, na.action = na.fail,
            control = glmerControl(optimizer = "bobyqa", check.rankX = "stop.deficient"))
    }
  }, warning = function(warning_value) {
    fit_warnings <<- c(fit_warnings, conditionMessage(warning_value))
    invokeRestart("muffleWarning")
  })
  if (nobs(fitted) != nrow(frame)) stop("observation count changed during fitting")
  optimizer_code <- as.integer(fitted@optinfo$conv$opt)
  optimizer_messages <- fitted@optinfo$conv$lme4$messages
  if (is.null(optimizer_messages)) optimizer_messages <- character()
  convergence_messages <- c(optimizer_messages, fit_warnings)
  convergence_messages <- convergence_messages[!grepl("boundary \\(singular\\) fit", convergence_messages)]
  singular <- isSingular(fitted)
  converged <- identical(optimizer_code, 0L) && !length(convergence_messages)
  status <- if (!converged && singular) "not-converged+singular" else if (!converged) {
    "not-converged"
  } else if (singular) "singular" else "ok"
  ddf_argument <- if (family_text != "gaussian") "wald-z" else if (ddf == "kenward") {
    "Kenward-Roger"
  } else "Satterthwaite"
  fit_summary <- if (family_text == "gaussian") summary(fitted, ddf = ddf_argument) else summary(fitted)
  model_text <- c(
    capture.output(fit_summary), "", paste("formula:", formula_text),
    sprintf("family: %s | ddf: %s (applied: %s) | REML: %s | nAGQ: %d | seed: %d",
            family_text, ddf, ddf_argument, reml, nagq, seed),
    sprintf("input_rows: %d", nrow(frame)), sprintf("n_obs: %d", nobs(fitted)),
    paste("status:", status), paste("converged:", tolower(as.character(converged))),
    paste("singular_fit:", tolower(as.character(singular))),
    paste("optimizer_code:", paste(optimizer_code, collapse = ",")),
    paste("lme4_messages:", if (length(optimizer_messages)) paste(optimizer_messages, collapse = " | ") else "none"),
    paste("fit_warnings:", if (length(fit_warnings)) paste(fit_warnings, collapse = " | ") else "none"),
    "random_effects_scale: sdcor",
    if (singular) "NOTE singular fit: random-effect covariance is on a boundary; individual variances need not be zero. This does not prove biological absence of variation." else character(),
    if (!converged) "NOTE not converged: estimates are diagnostic only, not a trustworthy optimum." else character()
  )
  if (reliable_only && status != "ok") {
    publish(model_path, function(path) writeLines(c(model_text, "estimates_published: false"), path))
    stop(paste("fit status:", status, "- estimate outputs refused"))
  }
  if (status != "ok") message(paste("fit status:", status, "- diagnostic outputs only"))
  fixed <- if (family_text == "gaussian") {
    broom.mixed::tidy(fitted, effects = "fixed", conf.int = TRUE, ddf.method = ddf_argument)
  } else broom.mixed::tidy(fitted, effects = "fixed", conf.int = TRUE)
  bootstrap <- NULL
  if (n_boot > 0L) {
    bootstrap <- lme4::bootMer(fitted, FUN = lme4::fixef, nsim = n_boot, seed = seed,
                         type = "parametric", use.u = FALSE, parallel = "no", .progress = "none")
    if (!identical(nrow(bootstrap$t), n_boot) || any(!is.finite(bootstrap$t)) ||
        !isTRUE(attr(bootstrap, "bootFail") == 0L)) stop("bootstrap replicates failed; no incomplete interval published")
    intervals <- t(apply(bootstrap$t, 2, quantile, probs = c(0.025, 0.975), type = 7))
    term_indices <- match(fixed$term, names(bootstrap$t0))
    if (anyNA(term_indices)) stop("bootstrap coefficient axes do not match fixed effects")
    fixed$boot_low <- intervals[term_indices, 1]
    fixed$boot_high <- intervals[term_indices, 2]
    model_text <- c(model_text, sprintf("bootstrap_replicates: %d", n_boot),
                    "bootstrap_method: parametric; use.u=false; percentile quantile type=7")
  }
  random <- broom.mixed::tidy(fitted, effects = "ran_pars", scales = "sdcor")
  if (reliable_only && (any(!is.finite(unlist(fixed[vapply(fixed, is.numeric, logical(1))]))) ||
                       any(!is.finite(random$estimate)))) stop("nonfinite estimate output refused")
  published <- character()
  completed <- FALSE
  on.exit(if (!completed) unlink(published))
  publish(output_paths[1], function(path) fwrite(fixed, path, sep = "\t"))
  published <- c(published, output_paths[1])
  publish(output_paths[2], function(path) fwrite(random, path, sep = "\t"))
  published <- c(published, output_paths[2])
  publish(output_paths[3], function(path) writeLines(c(model_text, "estimates_published: true",
          paste("diagnostic_only:", tolower(as.character(status != "ok")))), path))
  published <- c(published, output_paths[3])
  completed <- TRUE
  invisible(list(fit = fitted, fixed = fixed, random = random, bootstrap = bootstrap, frame = frame))
}

.lme4_result <- tryCatch(run_model(), error = function(error_value) fail(conditionMessage(error_value)))
