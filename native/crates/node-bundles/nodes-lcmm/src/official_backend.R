library(jsonlite)
arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 2L)
request <- fromJSON(arguments[[1]], simplifyVector = FALSE)
output_directory <- arguments[[2]]
if (file.exists(output_directory) || dir.exists(output_directory)) stop("output directory already exists; refusing overwrite")
if (!dir.create(output_directory, recursive = FALSE)) stop("cannot create private output directory")
sha256 <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status"))) stop("cannot verify runtime/input content identity")
  substr(result[[1]], 1L, 64L)
}
write_manifest <- function(value, filename) {
  write_json(value, file.path(output_directory, filename), auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null", null = "null")
}
read_f64 <- function(filename, length_expected) {
  if (file.info(filename)$size != length_expected * 8) stop("binary Float64 input length mismatch")
  values <- readBin(filename, "double", n = length_expected, size = 8L, endian = "little")
  if (length(values) != length_expected || any(!is.finite(values))) stop("nonfinite or incomplete numeric input")
  values
}
formula_from_roles <- function(aliases, selected, outcome = NULL) {
  intercept <- any(aliases == "intercept" & selected)
  terms <- aliases[which(selected & aliases != "intercept")]
  as.formula(paste(if (is.null(outcome)) "" else outcome, if (intercept) "~ 1" else "~ -1", if (length(terms)) paste("+", paste(terms, collapse = " + ")) else ""))
}
parameter_keys <- function(aliases, indicators, classes, idiag, nwg) {
  keys <- character()
  if (classes > 1L) {
    for (name in aliases[indicators$idprob == 1L]) {
      keys <- c(keys, paste("class_membership", name, seq_len(classes - 1L), sep = "|"))
    }
  }
  for (index in which(indicators$idg != 0L)) {
    roles <- if (indicators$idg[[index]] == 1L || classes == 1L) "common" else as.character(seq_len(classes))
    keys <- c(keys, paste("fixed_effect", aliases[[index]], roles, sep = "|"))
  }
  random_aliases <- aliases[indicators$idea == 1L]
  for (row_index in seq_along(random_aliases)) {
    columns <- if (idiag) row_index else seq_len(row_index)
    for (column_index in columns) {
      pair <- sort(c(random_aliases[[row_index]], random_aliases[[column_index]]))
      keys <- c(keys, paste("varcov", pair[[1]], pair[[2]], sep = "|"))
    }
  }
  if (classes > 1L && nwg) keys <- c(keys, paste("nwg", seq_len(classes - 1L), sep = "|"))
  c(keys, "stderr")
}
write_table <- function(port, columns, kinds, nullable = rep(FALSE, length(columns))) {
  sizes <- vapply(columns, length, integer(1))
  if (length(unique(sizes)) != 1L) stop("output column cardinality mismatch")
  metadata <- list()
  for (index in seq_along(columns)) {
    values <- columns[[index]]
    entry <- list(name = names(columns)[[index]], kind = kinds[[index]], nullable = nullable[[index]])
    if (!nullable[[index]] && anyNA(values)) stop("missing value violates nonnullable output")
    if (kinds[[index]] == "Float64") {
      if (any(!is.finite(values) & !is.na(values))) stop("nonfinite output cannot be published")
      validity <- !is.na(values)
      values[!validity] <- 0
      filename <- paste0("port-", port, "-column-", index, ".f64le")
      mask <- paste0("port-", port, "-column-", index, ".validity-u8")
      writeBin(as.double(values), file.path(output_directory, filename), size = 8L, endian = "little")
      writeBin(as.raw(validity), file.path(output_directory, mask))
      entry$binary <- filename
      entry$validity <- mask
    } else {
      entry$values <- as.list(values)
    }
    metadata[[index]] <- entry
  }
  list(port = port, rows = sizes[[1]], columns = metadata)
}
run <- function() {
  prefixes <- unlist(request$runtime$library_paths)
  .libPaths(c(prefixes, .libPaths()))
  library(lcmm)
  if (as.character(packageVersion("lcmm")) != "2.2.2" || as.character(packageVersion("marqLevAlg")) != "2.0.8") stop("official lcmm/marqLevAlg version mismatch")
  runtime <- list(R = R.version.string, lcmm = as.character(packageVersion("lcmm")), marqLevAlg = as.character(packageVersion("marqLevAlg")), lcmm_library = getLoadedDLLs()[["lcmm"]][["path"]], marq_library = getLoadedDLLs()[["marqLevAlg"]][["path"]], BLAS = extSoftVersion()[["BLAS"]])
  if (!identical(runtime$R, request$runtime$R)) stop("R runtime identity mismatch")
  runtime$BLAS_sha256 <- sha256(runtime$BLAS)
  if (!identical(runtime$BLAS_sha256, request$runtime$BLAS_sha256)) stop("BLAS runtime identity mismatch")
  runtime$lcmm_sha256 <- sha256(runtime$lcmm_library)
  runtime$marq_sha256 <- sha256(runtime$marq_library)
  runtime$lcmm_rdb_sha256 <- sha256(file.path(find.package("lcmm"), "R/lcmm.rdb"))
  runtime$lcmm_rdx_sha256 <- sha256(file.path(find.package("lcmm"), "R/lcmm.rdx"))
  runtime$marq_rdb_sha256 <- sha256(file.path(find.package("marqLevAlg"), "R/marqLevAlg.rdb"))
  runtime$marq_rdx_sha256 <- sha256(file.path(find.package("marqLevAlg"), "R/marqLevAlg.rdx"))
  for (name in c("lcmm_sha256", "marq_sha256", "lcmm_rdb_sha256", "lcmm_rdx_sha256", "marq_rdb_sha256", "marq_rdx_sha256")) {
    if (!identical(runtime[[name]], request$runtime[[name]])) stop(paste("official native/namespace fingerprint mismatch", name))
  }
  write_manifest(runtime, "ACTUAL_AUTHOR_RUNTIME.json")
  operation <- request$operation
  input_files <- unique(unlist(list(request$design$binary, request$outcome_binary, request$initial_binary, request$best_binary)))
  input_identities <- lapply(input_files, function(filename) list(path = filename, sha256 = sha256(filename)))
  write_manifest(input_identities, "ACTUAL_INPUT_IDENTITIES.json")
  if (operation %in% c("fit", "predict")) {
    model <- request$model
    rows <- as.integer(request$design$rows)
    indicators <- lapply(c("idg", "idea", "idprob", "idcor"), function(name) as.integer(unlist(model[[name]])))
    names(indicators) <- c("idg", "idea", "idprob", "idcor")
    width <- length(indicators$idg)
    classes <- as.integer(model$ng)
    if (rows < 1L || classes < 1L || any(lengths(indicators) != width) || any(indicators$idg < 0L | indicators$idg > 2L) || any(unlist(indicators[-1]) < 0L | unlist(indicators[-1]) > 1L)) stop("invalid model/design dimensions or indicator values")
    if (any(indicators$idcor != 0L)) stop("correlation is outside the original hlme fit node's interface")
    aliases <- if (width) paste0("design", seq_len(width)) else character()
    matrix_values <- read_f64(request$design$binary, rows * width)
    design <- as.data.frame(matrix(matrix_values, nrow = rows, ncol = width, byrow = TRUE))
    if (!is.null(request$design$intercept_column)) {
      index <- as.integer(request$design$intercept_column) + 1L
      if (is.na(index) || index != 1L || any(design[[index]] != 1)) stop("the explicit canonical intercept must be first and identically one")
      aliases[[index]] <- "intercept"
    }
    names(design) <- aliases
    original_indicators <- indicators
    one_class_normalized <- classes == 1L && (any(indicators$idg == 2L) || any(indicators$idprob == 1L) || isTRUE(model$nwg))
    if (classes == 1L) {
      indicators$idg[indicators$idg == 2L] <- 1L
      indicators$idprob[] <- 0L
      model$nwg <- FALSE
    }
    input_before <- sha256(request$design$binary)
    class_membership_parameters <- if (classes > 1L) sum(indicators$idprob) * (classes - 1L) else 0L
    fixed_parameters <- sum(indicators$idg == 1L) + classes * sum(indicators$idg == 2L)
    random_count <- sum(indicators$idea)
    random_parameters <- if (isTRUE(model$idiag)) random_count else random_count * (random_count + 1L) / 2L
    scaling_parameters <- if (classes > 1L && isTRUE(model$nwg)) classes - 1L else 0L
    parameters <- class_membership_parameters + fixed_parameters + random_parameters + scaling_parameters + 1L
    zero_mean_model <- !any(indicators$idg != 0L)
    fixed_formula <- if (zero_mean_model) as.formula(".outcome ~ 1") else formula_from_roles(aliases, indicators$idg != 0L, ".outcome")
    mixture_formula <- formula_from_roles(aliases, indicators$idg == 2L)
    random_formula <- formula_from_roles(aliases, indicators$idea == 1L)
    membership_formula <- if (classes > 1L && !any(indicators$idprob == 1L)) as.formula("~ 1") else formula_from_roles(aliases, indicators$idprob == 1L)
    canonical_keys <- parameter_keys(aliases, indicators, classes, isTRUE(model$idiag), isTRUE(model$nwg))
    author_membership_aliases <- if (classes > 1L) c("intercept", aliases[indicators$idprob == 1L & aliases != "intercept"]) else character()
    author_fixed_aliases <- if (zero_mean_model) "intercept" else aliases[indicators$idg != 0L]
    author_aliases <- unique(c(author_fixed_aliases, aliases[indicators$idea == 1L], author_membership_aliases))
    author_indices <- match(author_aliases, aliases)
    author_indicators <- lapply(indicators, function(values) {
      result <- values[author_indices]
      result[is.na(author_indices)] <- 0L
      result
    })
    author_indicators$idprob <- as.integer(author_aliases %in% author_membership_aliases)
    if (zero_mean_model) author_indicators$idg[author_aliases == "intercept"] <- 1L
    author_keys <- parameter_keys(author_aliases, author_indicators, classes, isTRUE(model$idiag), isTRUE(model$nwg))
    canonical_positions <- match(canonical_keys, author_keys)
    if (anyNA(canonical_positions) || anyDuplicated(canonical_positions) || length(canonical_keys) != parameters) stop("cannot map original parameter model to complete author model")
    fixed_positions <- setdiff(seq_along(author_keys), canonical_positions)
    allowed_fixed <- startsWith(author_keys[fixed_positions], "class_membership|intercept|") | (zero_mean_model & author_keys[fixed_positions] == "fixed_effect|intercept|common")
    if (length(fixed_positions) && any(!allowed_fixed)) stop("unexpected extra author coefficient cannot be silently fixed")
    constrained_classmb_intercept <- any(startsWith(author_keys[fixed_positions], "class_membership|intercept|"))
  }
  if (operation == "fit") {
    subjects <- unlist(request$subject_labels)
    counts <- as.integer(unlist(request$nmes))
    if (!length(subjects) || anyNA(subjects) || anyDuplicated(subjects) || length(counts) != length(subjects) || any(counts < 1L) || sum(counts) != rows) stop("invalid subject identity/grouping contract")
    aliases_subject <- seq_along(subjects)
    design$.subject <- rep(aliases_subject, counts)
    design$.outcome <- read_f64(request$outcome_binary, rows)
    call <- list(fixed = fixed_formula, subject = ".subject", ng = classes, data = design, random = random_formula, idiag = isTRUE(model$idiag), nwg = isTRUE(model$nwg), maxiter = as.integer(model$maxiter), na.action = 2L, nproc = 1L, verbose = FALSE, returndata = TRUE)
    if (classes > 1L) {
      call$mixture <- mixture_formula
      call$classmb <- membership_formula
    }
    if (length(fixed_positions)) call$posfix <- fixed_positions
    if (!is.null(request$initial_binary)) {
      initial <- read_f64(request$initial_binary, parameters)
      if (is.null(request$initial_parameterization)) stop("explicit initialization requires r_covariance or legacy_cholesky")
      if (request$initial_parameterization == "legacy_cholesky" && random_parameters > 0L) {
        start <- class_membership_parameters + fixed_parameters
        factor <- matrix(0, random_count, random_count)
        if (isTRUE(model$idiag)) diag(factor) <- initial[start + seq_len(random_parameters)] else factor[upper.tri(factor, diag = TRUE)] <- initial[start + seq_len(random_parameters)]
        covariance <- t(factor) %*% factor
        initial[start + seq_len(random_parameters)] <- if (isTRUE(model$idiag)) diag(covariance) else covariance[upper.tri(covariance, diag = TRUE)]
      } else if (!(request$initial_parameterization %in% c("r_covariance", "legacy_cholesky"))) stop("unknown initial parameterization")
      author_initial <- rep(0, length(author_keys))
      author_initial[canonical_positions] <- initial
      call$B <- author_initial
    } else if (classes > 1L) stop("ng > 1 requires explicit author initialization; no class-count/initial-value selection")
    fit <- do.call(lcmm::hlme, call)
    saveRDS(fit, file.path(output_directory, "complete-author-fit.rds"))
    if (!(fit$conv %in% 1:3)) stop(paste("author optimizer failed with conv", fit$conv))
    if (!identical(fit$Xnames, author_aliases) || !identical(as.integer(fit$idg0), author_indicators$idg) || !identical(as.integer(fit$idea0), author_indicators$idea) || !identical(as.integer(fit$idprob0), author_indicators$idprob)) stop("author design roles differ from the canonical prepared model")
    canonical_best <- fit$best[canonical_positions]
    if (length(canonical_best) != parameters || (length(fixed_positions) && any(fit$best[fixed_positions] != 0))) stop("fixed-zero compatibility mapping does not preserve the original parameter model")
    write_manifest(list(canonical_to_author_positions_1based = canonical_positions, canonical_parameter_keys = canonical_keys, author_parameter_keys = author_keys, author_design_aliases = author_aliases, author_extra_compatibility_coefficients_fixed_zero = fixed_positions, author_extra_classmb_intercept_positions_fixed_zero = fixed_positions[startsWith(author_keys[fixed_positions], "class_membership|intercept|")], author_full_parameters = length(fit$best), canonical_free_parameters = length(canonical_best), one_class_inactive_roles_normalized = one_class_normalized, zero_mean_model_preserved_by_fixed_zero_intercept = zero_mean_model, original_role_indicators = original_indicators, classmb_intercept_is_zero_constraint_preserving_original_model_not_a_new_free_coefficient = constrained_classmb_intercept), "CANONICAL_PARAMETER_MAPPING.json")
    sections <- rep(c("class_membership", "fixed_effect", "varcov", "nwg", "stderr"), c(class_membership_parameters, fixed_parameters, random_parameters, scaling_parameters, 1L))
    indices <- unlist(lapply(c(class_membership_parameters, fixed_parameters, random_parameters, scaling_parameters, 1L), function(size) if (size) seq_len(size) - 1L else integer()))
    errors <- rep(NA_real_, length(canonical_best))
    if (fit$conv %in% c(1L, 3L)) {
      diagonal <- fit$V[cumsum(seq_along(fit$best))][canonical_positions]
      errors[is.finite(diagonal) & diagonal >= 0] <- sqrt(diagonal[is.finite(diagonal) & diagonal >= 0])
      errors[sections == "varcov"] <- NA_real_
    }
    summary <- list(loglik = fit$loglik, aic = fit$AIC, bic = fit$BIC, niter = as.integer(fit$niter), conv = c("Converged", "MaxIter", "PartialH")[[fit$conv]], ng = as.integer(fit$ng), npm = as.integer(length(canonical_best)), ns = as.integer(fit$ns), nobs = rows, n_param_eff = as.integer(length(canonical_best)))
    ports <- list(write_table(0L, summary, c("Float64", "Float64", "Float64", "Int32", "Utf8", rep("Int32", 5L))), write_table(1L, list(section = sections, index = as.integer(indices), estimate = as.double(canonical_best), std_error = errors), c("Utf8", "Int32", "Float64", "Float64"), c(FALSE, FALSE, FALSE, TRUE)))
    posterior <- list(subject = subjects[match(as.character(fit$pprob[[1]]), aliases_subject)], class = as.integer(fit$pprob[[2]]))
    for (index in seq_len(classes)) posterior[[paste0("ppi_", index)]] <- as.double(fit$pprob[[index + 2L]])
    fitted <- list(subject = subjects[match(as.character(fit$pred[[1]]), aliases_subject)], outcome = as.double(fit$pred$obs), pred_marginal = as.double(fit$pred$pred_m), pred_subject = as.double(fit$pred$pred_ss), resid_marginal = as.double(fit$pred$resid_m), resid_subject = as.double(fit$pred$resid_ss))
    if (model$maxiter == 0L) {
      posterior <- lapply(posterior, function(values) values[FALSE])
      fitted <- lapply(fitted, function(values) values[FALSE])
    }
    ports[[3]] <- write_table(2L, posterior, c("Int64", "Int32", rep("Float64", classes)))
    ports[[4]] <- write_table(3L, fitted, c("Int64", rep("Float64", 5L)), c(FALSE, FALSE, rep(TRUE, 4L)))
  } else if (operation == "predict") {
    best <- read_f64(request$best_binary, as.integer(request$best_length))
    if (length(best) < class_membership_parameters + fixed_parameters) stop("best omits required class-membership/fixed effects")
    shell <- structure(list(best = best, ng = classes, conv = 2L, idg0 = indicators$idg, idea0 = indicators$idea, idprob0 = indicators$idprob, idcor0 = indicators$idcor, N = c(class_membership_parameters, fixed_parameters, random_parameters, scaling_parameters, 0L), Xnames = aliases, Xnames2 = aliases, call = list(fixed = fixed_formula, random = random_formula, mixture = mixture_formula, classmb = membership_formula), levels = list()), class = "hlme")
    prediction <- lcmm::predictY(shell, newdata = design, draws = FALSE, na.action = 2L)
    if (!identical(dim(prediction$pred), c(rows, classes))) stop("author prediction dimension mismatch")
    saveRDS(shell, file.path(output_directory, "reconstructed-mean-only-author-object.rds"))
    ports <- list(write_table(0L, list(row = rep(seq_len(rows) - 1L, each = classes), class = rep(seq_len(classes), rows), predicted = as.double(t(prediction$pred))), c("Int32", "Int32", "Float64")))
  } else if (operation == "compare") {
    models <- request$models
    if (!length(models)) stop("empty comparison list")
    names <- vapply(models, function(model) model$name, character(1))
    if (any(!nzchar(trimws(names))) || anyDuplicated(names)) stop("model names must be unique/nonblank")
    counts <- lapply(c("ng", "npm", "ns"), function(name) vapply(models, function(model) as.integer(model[[name]]), integer(1)))
    if (any(unlist(counts) < 1L) || anyNA(unlist(counts))) stop("comparison counts must be positive Int32")
    likelihoods <- vapply(models, function(model) as.double(model$loglik), double(1))
    aic <- -2 * likelihoods + 2 * counts[[2]]
    bic <- -2 * likelihoods + log(counts[[3]]) * counts[[2]]
    differences <- bic - min(bic)
    if (any(!is.finite(c(likelihoods, aic, bic, differences)))) stop("nonfinite comparison values")
    weights <- exp(-0.5 * differences)
    ports <- list(write_table(0L, list(model = names, ng = counts[[1]], npm = counts[[2]], loglik = likelihoods, aic = aic, bic = bic, bic_delta = differences, bic_prob = weights / sum(weights)), c("Utf8", "Int32", "Int32", rep("Float64", 5L)), c(rep(FALSE, 6L), TRUE, TRUE)))
  } else stop("unknown operation")
  if (operation %in% c("fit", "predict") && !identical(input_before, sha256(request$design$binary))) stop("design content changed during execution")
  for (identity in input_identities) if (!identical(identity$sha256, sha256(identity$path))) stop("input content changed during execution")
  write_manifest(list(protocol = "lcmm-author-dataframe-adapter-candidate-v1", operation = operation, ports = ports, actual_author_namespace = operation %in% c("fit", "predict"), compare_is_arithmetic_extension_not_model_qualification = operation == "compare", prediction_is_mean_only_reconstructed_object = operation == "predict", canonical_maxiter_zero_suppresses_prediction_ports = operation == "fit" && model$maxiter == 0L, deployment_status = "NOT_ASSERTED_BY_METHOD_ADAPTER", G0 = FALSE), "PORTS.json")
}
tryCatch(run(), error = function(error) {
  write_manifest(list(status = "FAILED_NOT_PASS", message = conditionMessage(error), no_committed_PORTS_manifest = !file.exists(file.path(output_directory, "PORTS.json")), deployment_status = "NOT_ASSERTED_BY_METHOD_ADAPTER", G0 = FALSE), "FAILED.json")
  message(conditionMessage(error))
  quit(status = 1L)
})
