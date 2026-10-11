number_setting <- function(name, default = NULL, lower = -Inf, upper = Inf, integer = FALSE) {
  text <- Sys.getenv(name)
  if (!nzchar(text) && !is.null(default)) text <- as.character(default)
  value <- suppressWarnings(as.numeric(text))
  if (length(value) != 1L || !is.finite(value) || value < lower || value > upper ||
      (integer && value != floor(value))) stop(paste("Invalid setting", name))
  value
}

numeric_values <- function(text, name) {
  values <- suppressWarnings(as.numeric(text))
  if (length(values) != length(text) || any(!is.finite(values))) stop(paste("Nonfinite or nonnumeric", name))
  values
}

read_literal_table <- function(path) {
  data <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE,
                     colClasses = "character", na.strings = character(), quote = "", comment.char = "")
  if (anyDuplicated(names(data))) stop("Duplicate table column names")
  data
}

read_dataset <- function(data_path, ld_path, sample_size, trait_type, trait_index) {
  data <- read_literal_table(data_path)
  required <- c("snp", "beta", "se", "effect_allele", "other_allele", "ld_a1", "ld_a2", "ld_n")
  if (!all(required %in% names(data))) stop("Variant table lacks declared SNP/effect/LD metadata")
  if (nrow(data) < 2L || any(!nzchar(data$snp)) || anyDuplicated(data$snp) ||
      any(grepl("[[:space:][:cntrl:]]", data$snp))) stop("Invalid or duplicate SNP identity")
  for (name in c("effect_allele", "other_allele", "ld_a1", "ld_a2")) {
    if (any(!grepl("^[ACGT]+$", data[[name]]))) stop("Alleles must be explicit uppercase DNA sequences")
  }
  if (any(data$effect_allele == data$other_allele) || any(data$ld_a1 == data$ld_a2)) stop("Identical allele pair")
  aligned <- data$effect_allele == data$ld_a1 & data$other_allele == data$ld_a2
  reversed <- data$effect_allele == data$ld_a2 & data$other_allele == data$ld_a1
  if (any(!aligned & !reversed)) stop("LD counting alleles disagree with the exact effect allele pair")
  beta <- numeric_values(data$beta, "beta")
  standard_error <- numeric_values(data$se, "se")
  if (any(standard_error <= 0) || any(!is.finite(standard_error^2)) || any(standard_error^2 == 0)) stop("SE and its variance must be finite and positive")
  ld_count <- numeric_values(data$ld_n, "ld_n")
  if (length(unique(ld_count)) != 1L || any(ld_count <= 1) || any(ld_count != floor(ld_count))) stop("ld_n must be a constant integer greater than one")
  table_ld <- read_literal_table(ld_path)
  if (names(table_ld)[1L] != "snp" || !identical(table_ld$snp, data$snp) ||
      !identical(names(table_ld)[-1L], data$snp)) stop("LD row/column identity or order mismatch")
  matrix_ld <- do.call(cbind, lapply(names(table_ld)[-1L], function(name) numeric_values(table_ld[[name]], "signed LD")))
  if (nrow(matrix_ld) != nrow(data) || ncol(matrix_ld) != nrow(data) ||
      any(abs(matrix_ld) > 1) || max(abs(diag(matrix_ld) - 1)) > 1e-10 ||
      max(abs(matrix_ld - t(matrix_ld))) > 1e-10) stop("Signed LD must be square, symmetric, bounded and have unit diagonal")
  if (min(eigen(matrix_ld, symmetric = TRUE, only.values = TRUE)$values) < -1e-10 * nrow(data)) stop("Signed LD is not positive semidefinite; repair is not performed")
  orientation <- ifelse(aligned, 1, -1)
  matrix_ld <- matrix_ld * tcrossprod(orientation)
  dimnames(matrix_ld) <- list(data$snp, data$snp)
  dataset <- list(beta = beta, varbeta = standard_error^2, snp = data$snp,
                  LD = matrix_ld, N = sample_size, type = trait_type)
  if (trait_type == "quant") {
    dataset$sdY <- number_setting(paste0("COLOC_SD_Y", trait_index))
    if (dataset$sdY <= 0) stop("Known quantitative phenotype SD must be positive")
  } else {
    dataset$s <- number_setting(paste0("COLOC_CASE_FRACTION", trait_index))
    if (dataset$s <= 0 || dataset$s >= 1) stop("Known case fraction must lie strictly between zero and one")
  }
  list(dataset = dataset, metadata = data)
}

run <- function(output_paths) {
  if (as.character(packageVersion("coloc")) != "5.2.3" ||
      as.character(packageVersion("susieR")) != "0.14.2") stop("Pinned coloc/susieR package versions required")
  alignment <- trimws(Sys.getenv("COLOC_ALIGNMENT_EVIDENCE"))
  if (!nzchar(alignment)) stop("alignment_evidence must identify declared provenance")
  sample_sizes <- c(number_setting("COLOC_N1", lower = 3, integer = TRUE),
                    number_setting("COLOC_N2", lower = 3, integer = TRUE))
  trait_types <- c(Sys.getenv("COLOC_TYPE1"), Sys.getenv("COLOC_TYPE2"))
  if (!all(trait_types %in% c("quant", "cc"))) stop("Trait types must be explicitly quant or cc")
  effects <- number_setting("COLOC_L", 10, lower = 1, integer = TRUE)
  coverage <- number_setting("COLOC_COVERAGE", .95, lower = 0, upper = 1)
  purity <- number_setting("COLOC_MIN_ABS_CORR", .5, lower = 0, upper = 1)
  priors <- c(p1 = number_setting("COLOC_P1", 1e-4, lower = 0, upper = 1),
              p2 = number_setting("COLOC_P2", 1e-4, lower = 0, upper = 1),
              p12 = number_setting("COLOC_P12", 5e-6, lower = 0, upper = 1))
  if (any(priors <= 0) || any(priors >= 1) || priors["p12"] > min(priors[c("p1", "p2")])) stop("Priors must be in (0,1) with p12 no larger than p1 or p2")
  iterations <- number_setting("COLOC_MAX_ITER", 100, lower = 1, integer = TRUE)
  seed <- number_setting("COLOC_SEED", 1, lower = 0, upper = .Machine$integer.max, integer = TRUE)
  first <- read_dataset(Sys.getenv("AUTONOMICS_INPUT0"), Sys.getenv("AUTONOMICS_INPUT2"), sample_sizes[1L], trait_types[1L], 1L)
  second <- read_dataset(Sys.getenv("AUTONOMICS_INPUT1"), Sys.getenv("AUTONOMICS_INPUT3"), sample_sizes[2L], trait_types[2L], 2L)
  if (!identical(first$dataset$snp, second$dataset$snp)) stop("Both traits require exactly the same ordered SNP identities; no intersection is performed")
  same <- first$metadata$effect_allele == second$metadata$effect_allele & first$metadata$other_allele == second$metadata$other_allele
  reversed <- first$metadata$effect_allele == second$metadata$other_allele & first$metadata$other_allele == second$metadata$effect_allele
  if (any(!same & !reversed)) stop("Trait allele pairs disagree; strand inference is not performed")
  cat("coloc 5.2.3; susieR 0.14.2; alignment declaration:", alignment,
      "\nExternal signed LD; no automatic iteration extension; seed:", seed, "\n")
  set.seed(seed)
  fit1 <- coloc::runsusie(first$dataset, L = effects, coverage = coverage, min_abs_corr = purity,
                         maxit = iterations, repeat_until_convergence = FALSE, estimate_residual_variance = FALSE)
  fit2 <- coloc::runsusie(second$dataset, L = effects, coverage = coverage, min_abs_corr = purity,
                         maxit = iterations, repeat_until_convergence = FALSE, estimate_residual_variance = FALSE)
  result <- coloc::coloc.susie(fit1, fit2, p1 = unname(priors["p1"]), p2 = unname(priors["p2"]), p12 = unname(priors["p12"]))
  no_sets <- is.null(fit1$sets$cs) || is.null(fit2$sets$cs) || !length(fit1$sets$cs) || !length(fit2$sets$cs)
  if (no_sets) {
    summary <- data.frame(status = "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS")
    variants <- data.frame(status = "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS")
  } else {
    if (!is.list(result) || is.null(result$summary) || is.null(result$results)) stop("Unexpected official result structure")
    summary <- as.data.frame(result$summary)
    variants <- as.data.frame(result$results)
    fields <- paste0("PP.H", 0:4, ".abf")
    if (!nrow(summary) || !all(fields %in% names(summary))) stop("Official signal summary incomplete")
    probabilities <- as.matrix(summary[, fields, drop = FALSE])
    if (any(!is.finite(probabilities)) || any(probabilities < 0) || any(probabilities > 1) ||
        any(abs(rowSums(probabilities) - 1) > 1e-8)) stop("Official posterior output invalid")
    summary$status <- "ESTIMATED_SUPPORT_ONLY"
    variants$status <- "CONDITIONAL_ON_H4_NOT_UNCONDITIONAL_PROBABILITY"
  }
  temporaries <- vapply(output_paths[1:3], function(path) tempfile(".coloc-", tmpdir = dirname(path)), character(1))
  published <- character()
  complete <- FALSE
  on.exit({
    unlink(temporaries)
    if (!complete) unlink(published)
  }, add = TRUE)
  write.table(summary, temporaries[1L], sep = "\t", quote = FALSE, row.names = FALSE)
  write.table(variants, temporaries[2L], sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(list(dataset1 = first$dataset, dataset2 = second$dataset, fit1 = fit1, fit2 = fit2,
               coloc = result, priors = priors, metadata1 = first$metadata, metadata2 = second$metadata,
               alignment_evidence = alignment), temporaries[3L])
  for (index in seq_along(temporaries)) {
    if (!file.link(temporaries[index], output_paths[index])) stop("Refused output publication; existing paths are never overwritten")
    published <- c(published, output_paths[index])
  }
  complete <- TRUE
  print(summary)
  print(sessionInfo())
}

main <- function() {
  output_paths <- vapply(0:3, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1))
  if (any(!nzchar(output_paths)) || anyDuplicated(output_paths) || any(file.exists(output_paths)) ||
      any(!dir.exists(dirname(output_paths)))) stop("Four distinct existing-parent output paths required; overwrite refused")
  log_temporary <- tempfile(".coloc-log-", tmpdir = dirname(output_paths[4L]))
  on.exit(unlink(log_temporary), add = TRUE)
  sink(log_temporary, split = TRUE)
  failed <- NULL
  tryCatch(run(output_paths), error = function(error) {
    failed <<- conditionMessage(error)
    cat("ERROR:", failed, "\n")
  })
  sink()
  if (!file.link(log_temporary, output_paths[4L])) stop("Log publication refused; no overwrite")
  if (!is.null(failed)) stop(failed)
}

main()
