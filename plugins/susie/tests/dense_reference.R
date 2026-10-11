arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) %in% c(3L, 4L))
reference_library <- arguments[1L]
case_root <- arguments[2L]
configuration <- arguments[3L]
.libPaths(c(reference_library, .libPaths()))
stopifnot(normalizePath(find.package("susieR")) == normalizePath(file.path(reference_library, "susieR")))
stopifnot(as.character(packageVersion("susieR")) == "0.16.6")
input <- read.delim(file.path(case_root, "input.tsv"), colClasses = "character", check.names = FALSE)
effect_allele <- if ("a1" %in% names(input)) input$a1 else vapply(strsplit(input$snp, ":"), `[[`, "", 3L)
signs <- ifelse(effect_allele == input$ld_a1, 1, -1)
reference_ld <- matrix(as.numeric(as.matrix(input[, paste0("ld:", input$snp), drop = FALSE])), nrow = nrow(input))
reference_ld <- diag(signs, nrow(input)) %*% reference_ld %*% diag(signs, nrow(input))
dimnames(reference_ld) <- list(input$snp, input$snp)
settings <- dget(configuration)
sample_size <- if ("n" %in% names(input)) as.numeric(input$n[1L]) else NULL
set.seed(settings$seed)
reference <- susieR::susie_rss(z = as.numeric(input$z), R = reference_ld, n = sample_size,
                              L = settings$effects, scaled_prior_variance = settings$scaled_prior_variance,
                              estimate_residual_variance = settings$estimate_residual_variance, estimate_prior_variance = settings$estimate_prior_variance,
                              estimate_prior_method = settings$prior_method, z_method = settings$z_method,
                              check_null_threshold = settings$null_threshold, coverage = settings$coverage,
                              min_abs_corr = settings$min_abs_corr, max_iter = settings$max_iter)
if (length(arguments) == 4L) {
  stopifnot(arguments[4L] == "nonconverged", !isTRUE(reference$converged),
            !file.exists(file.path(case_root, "output/fit.RDS")),
            !file.exists(file.path(case_root, "output/fit.tsv")))
  saveRDS(reference, file.path(case_root, "official-nonconverged-reference.RDS"))
  cat("OFFICIAL_NONCONVERGENCE_MATCH_NO_RESULT_PUBLICATION\n")
  quit(save = "no", status = 0L)
}
actual <- readRDS(file.path(case_root, "output/fit.RDS"))
comparison <- all.equal(actual, reference, tolerance = 1e-12, check.attributes = TRUE)
if (!isTRUE(comparison)) stop(paste(comparison, collapse = "\n"))
saveRDS(reference, file.path(case_root, "official-reference.RDS"))
actual_table <- read.delim(file.path(case_root, "output/fit.tsv"), na.strings = character(),
                          colClasses = c(cs_all = "character"), check.names = FALSE)
stopifnot(identical(actual_table$snp, input$snp))
stopifnot(isTRUE(all.equal(actual_table$pip, susieR::susie_get_pip(reference), tolerance = 1e-12)))
best <- apply(reference$alpha, 2, which.max)
coordinates <- cbind(best, seq_len(nrow(input)))
for (field in c("mu", "mu2", "lbf")) {
  stopifnot(isTRUE(all.equal(actual_table[[field]], reference[[if (field == "lbf") "lbf_variable" else field]][coordinates],
                            tolerance = 1e-12, check.attributes = FALSE)))
}
stopifnot(isTRUE(all.equal(actual_table$alpha, apply(reference$alpha, 2, max), tolerance = 1e-12, check.attributes = FALSE)))
membership <- integer(nrow(input))
membership_all <- rep("", nrow(input))
for (set_index in seq_along(reference$sets$cs)) {
  members <- reference$sets$cs[[set_index]]
  membership[members] <- set_index
  membership_all[members] <- ifelse(nzchar(membership_all[members]),
                                   paste(membership_all[members], set_index, sep = ";"), as.character(set_index))
}
stopifnot(identical(as.integer(actual_table$cs), membership))
stopifnot(identical(as.character(actual_table$cs_all), membership_all))
cat("FULL_OFFICIAL_OBJECT_AND_EVERY_TSV_COLUMN_MATCH tolerance=1e-12\n")
