options(width = 200, digits = 17)

output_file <- function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port))
input_file <- function(port) Sys.getenv(paste0("AUTONOMICS_INPUT", port))
write_tsv <- function(value, filename) {
  write.table(value, filename, sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
}
read_lexical <- function(filename) {
  widths <- count.fields(filename, sep = "\t", quote = "", comment.char = "", blank.lines.skip = FALSE)
  if (!length(widths) || anyNA(widths) || any(widths != widths[1])) stop("Ragged TSV rows are not permitted")
  value <- read.delim(filename, check.names = FALSE, stringsAsFactors = FALSE,
                      colClasses = "character", na.strings = NULL, quote = "",
                      comment.char = "", blank.lines.skip = FALSE, fill = FALSE)
  if (anyDuplicated(names(value))) stop("Duplicate column names")
  value
}
check_ids <- function(value) {
  if (!length(value) || anyNA(value) || any(!nzchar(value)) ||
      any(value != trimws(value)) || any(!grepl("^[A-Za-z0-9_.:+-]+$", value)) ||
      anyDuplicated(value)) stop("Variant identity must be lexical, nonempty and unique")
}
finite_number <- function(value) {
  result <- suppressWarnings(as.numeric(value))
  if (!length(result) || any(!is.finite(result))) stop("Numeric input must be finite")
  result
}
checksum <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status")) || length(result) != 1L ||
      !grepl("^[0-9a-f]{64} ", result)) stop("Content hash could not be verified")
  substr(result, 1, 64)
}
run_regional <- function() {
  operation <- Sys.getenv("REGIONAL_OPERATION")
  if (!operation %in% c("susie", "abf")) stop("Unknown regional operation")
  if (as.character(packageVersion("coloc")) != "5.2.3" ||
      as.character(packageVersion("susieR")) != "0.14.2") stop("Official package version mismatch")
  lock <- read_lexical(input_file(2))
  if (!identical(names(lock), c("key", "value")) || !nrow(lock) ||
      anyDuplicated(lock$key)) stop("Contract needs unique key/value rows")
  contract <- setNames(as.list(lock$value), lock$key)
  required <- function(key) {
    value <- contract[[key]]
    if (is.null(value) || length(value) != 1L || !nzchar(trimws(value))) stop("Missing contract key: ", key)
    value
  }
  numeric_key <- function(key, minimum = -Inf, maximum = Inf) {
    value <- finite_number(required(key))
    if (value < minimum || value > maximum) stop("Contract value outside bounds: ", key)
    value
  }
  integer_key <- function(key, minimum = 1, maximum = .Machine$integer.max) {
    raw <- required(key)
    if (!grepl("^[0-9]+$", raw)) stop("Contract integer required: ", key)
    as.integer(numeric_key(key, minimum, maximum))
  }
  logical_key <- function(key) {
    value <- required(key)
    if (!value %in% c("true", "false")) stop("Contract boolean required: ", key)
    value == "true"
  }
  if (required("operation") != operation || required("scope") != "TECHNICAL_ONLY_NOT_G0") stop("Contract operation or scope mismatch")
  common_keys <- c("operation", "scope", "input0_sha256", "input1_sha256", "alignment_evidence")
  method_keys <- if (operation == "susie") {
    c("mode", "effect_scale", "n", "L", "coverage", "ld_source", "estimate_residual_variance",
      "scaled_prior_variance", "estimate_prior_variance", "min_abs_corr", "max_iter", "tol",
      "n_purity", "seed", "var_y")
  } else c("n1", "n2", "type1", "type2", "sd_y1", "sd_y2", "case_fraction1", "case_fraction2", "p1", "p2", "p12")
  if (length(setdiff(names(contract), c(common_keys, method_keys)))) stop("Unknown or unsupported method contract key")
  for (port in 0:1) {
    if (required(paste0("input", port, "_sha256")) != checksum(input_file(port))) stop("Input SHA256 mismatch")
  }
  alignment <- required("alignment_evidence")
  first <- read_lexical(input_file(0))
  if (!"snp" %in% names(first) || nrow(first) < 2L || nrow(first) > 2000L) stop("Bounded region needs 2..2000 variants")
  check_ids(first$snp)
  if (operation == "susie") {
    mode <- required("mode")
    if (!mode %in% c("z", "beta_se")) stop("RSS mode must be z or beta_se")
    sample_size <- integer_key("n", 3)
    component_count <- integer_key("L", 10, 20)
    if (!component_count %in% c(10L, 20L) || numeric_key("coverage") != .95) stop("Plan L/coverage contract violated")
    source <- required("ld_source")
    if (!source %in% c("reference", "in_sample")) stop("LD source must be explicit")
    estimate_residual <- logical_key("estimate_residual_variance")
    if (source == "reference" && estimate_residual) stop("Reference LD cannot estimate residual variance in this route")
    matrix_table <- read_lexical(input_file(1))
    if (!identical(names(matrix_table), c("snp", first$snp)) ||
        !identical(matrix_table$snp, first$snp)) stop("LD row/column variant identity mismatch")
    correlation <- matrix(finite_number(as.matrix(matrix_table[, -1, drop = FALSE])),
                          nrow = nrow(first), dimnames = list(first$snp, first$snp))
    if (max(abs(correlation - t(correlation))) > 1e-8 ||
        max(abs(diag(correlation) - 1)) > 1e-8 ||
        min(eigen(correlation, symmetric = TRUE, only.values = TRUE)$values) < -1e-8) stop("Signed LD must be symmetric PSD with unit diagonal")
    args <- list(R = correlation, n = sample_size, L = component_count, coverage = .95,
                 estimate_residual_variance = estimate_residual,
                 scaled_prior_variance = numeric_key("scaled_prior_variance", 1e-12, 1),
                 estimate_prior_variance = logical_key("estimate_prior_variance"),
                 estimate_prior_method = "optim", min_abs_corr = numeric_key("min_abs_corr", 0, 1),
                 max_iter = integer_key("max_iter", 1, 10000), tol = numeric_key("tol", 1e-12, 1),
                 n_purity = integer_key("n_purity", 1, 2000), refine = FALSE)
    if (mode == "z") {
      if (!is.null(contract$var_y)) stop("var_y is not used in this z route")
      if (!"z" %in% names(first) || required("effect_scale") != "STANDARDIZED_Z_WALD") stop("Frozen Wald z scale required")
      args$z <- finite_number(first$z)
    } else {
      if (!all(c("beta", "se") %in% names(first)) || required("effect_scale") != "QUANTITATIVE_BETA_SE") stop("Frozen quantitative beta/se scale required")
      args$bhat <- finite_number(first$beta)
      args$shat <- finite_number(first$se)
      if (any(args$shat <= 0) || any(!is.finite(args$shat^2)) || any(args$shat^2 == 0)) stop("SE must have finite positive square")
      args$var_y <- numeric_key("var_y", 1e-12)
    }
    set.seed(integer_key("seed", 0))
    fit <- do.call(susieR::susie_rss, args)
    saveRDS(list(fit = fit, arguments = args, snp = first$snp, contract = contract), output_file(2))
    if (!isTRUE(fit$converged)) stop("RSS did not converge; fit retained as diagnostics")
    pip <- susieR::susie_get_pip(fit)
    if (length(pip) != nrow(first) || any(!is.finite(pip)) || any(pip < 0 | pip > 1)) stop("Official PIP invalid")
    membership <- vapply(seq_len(nrow(first)), function(index) {
      matching <- names(fit$sets$cs)[vapply(fit$sets$cs, function(indices) index %in% indices, logical(1))]
      if (!length(matching)) "NONE" else paste(matching, collapse = ";")
    }, character(1))
    credible <- data.frame(cs_id = character(), members = character(), coverage = numeric(),
                           min_abs_corr = numeric(), mean_abs_corr = numeric(), median_abs_corr = numeric())
    if (length(fit$sets$cs)) {
      credible <- data.frame(cs_id = names(fit$sets$cs),
                            members = vapply(fit$sets$cs, function(indices) paste(first$snp[indices], collapse = ";"), character(1)),
                            coverage = as.numeric(fit$sets$coverage),
                            min_abs_corr = fit$sets$purity[, 1], mean_abs_corr = fit$sets$purity[, 2],
                            median_abs_corr = fit$sets$purity[, 3], check.names = FALSE)
    }
    write_tsv(data.frame(snp = first$snp, pip = pip, credible_sets = membership), output_file(0))
    write_tsv(credible, output_file(1))
    facts <- c(status = "COMPLETED", method = "susieR::susie_rss", version = "0.14.2",
               converged = "true", niter = fit$niter, credible_set_count = nrow(credible),
               no_credible_sets = if (nrow(credible)) "false" else "true")
  } else {
    second <- read_lexical(input_file(1))
    if (!"snp" %in% names(second)) stop("Trait 2 SNP column required")
    check_ids(second$snp)
    if (!identical(first$snp, second$snp)) stop("Traits must have exactly the same frozen variant order")
    dataset <- function(value, suffix) {
      if (!all(c("beta", "se") %in% names(value))) stop("beta/se input required")
      beta <- finite_number(value$beta)
      standard_error <- finite_number(value$se)
      if (any(standard_error <= 0)) stop("SE must be positive")
      trait_type <- required(paste0("type", suffix))
      if (!trait_type %in% c("quant", "cc")) stop("Trait type must be quant or cc")
      variance <- standard_error^2
      if (any(!is.finite(variance)) || any(variance == 0)) stop("SE square outside finite positive range")
      result <- list(snp = value$snp, beta = beta, varbeta = variance,
                     N = integer_key(paste0("n", suffix), 3), type = trait_type)
      if (trait_type == "quant") {
        if (!is.null(contract[[paste0("case_fraction", suffix)]])) stop("Case fraction is not used for quant trait")
        result$sdY <- numeric_key(paste0("sd_y", suffix), 1e-12)
      } else {
        if (!is.null(contract[[paste0("sd_y", suffix)]])) stop("Quant phenotype SD is not used for cc trait")
        result$s <- numeric_key(paste0("case_fraction", suffix), 1e-12, 1 - 1e-12)
      }
      result
    }
    p12 <- numeric_key("p12")
    if (!p12 %in% c(1e-6, 1e-5, 1e-4) || numeric_key("p1") != 1e-4 || numeric_key("p2") != 1e-4) stop("Frozen coloc prior contract violated")
    result <- coloc::coloc.abf(dataset(first, "1"), dataset(second, "2"), p1 = 1e-4, p2 = 1e-4, p12 = p12)
    posterior <- result$summary[paste0("PP.H", 0:4, ".abf")]
    if (any(!is.finite(posterior)) || any(posterior < 0 | posterior > 1) || abs(sum(posterior) - 1) > 1e-8) stop("Official posterior invalid")
    write_tsv(as.data.frame(as.list(result$summary)), output_file(0))
    write_tsv(result$results, output_file(1))
    saveRDS(list(result = result, contract = contract, assumption = "SINGLE_CAUSAL_VARIANT_PER_TRAIT"), output_file(2))
    facts <- c(status = "COMPLETED", method = "coloc::coloc.abf", version = "5.2.3",
               assumption = "SINGLE_CAUSAL_VARIANT_PER_TRAIT")
  }
  facts <- c(facts, scientific_G0_granted = "false", alignment_evidence = alignment,
             input0_sha256 = checksum(input_file(0)), input1_sha256 = checksum(input_file(1)),
             contract_sha256 = checksum(input_file(2)), output0_sha256 = checksum(output_file(0)),
             output1_sha256 = checksum(output_file(1)), output2_sha256 = checksum(output_file(2)))
  write_tsv(data.frame(key = names(facts), value = as.character(facts)), output_file(4))
  print(facts)
  print(sessionInfo())
}

tryCatch({
  sink(output_file(3), split = TRUE)
  run_regional()
  sink()
}, error = function(error) {
  while (sink.number() > 0) sink()
  retained <- ""
  if (file.exists(output_file(2))) {
    retained <- paste0(output_file(2), ".diagnostic")
    file.rename(output_file(2), retained)
  }
  unlink(vapply(c(0, 1, 2, 4), output_file, character(1)))
  cat("BLOCKED:", conditionMessage(error), "\n", file = output_file(3), append = TRUE)
  write_tsv(data.frame(key = c("status", "error", "retained_fit", "scientific_G0_granted"),
                       value = c("BLOCKED", gsub("[\t\r\n]", " ", conditionMessage(error)), retained, "false")), output_file(4))
  quit(status = 2)
})
