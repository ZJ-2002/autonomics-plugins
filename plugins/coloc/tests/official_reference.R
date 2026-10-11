arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 3L)
reference_library <- arguments[1L]
directory <- arguments[2L]
.libPaths(c(reference_library, .libPaths()))
stopifnot(normalizePath(find.package("coloc")) == normalizePath(file.path(reference_library, "coloc")),
          normalizePath(find.package("susieR")) == normalizePath(file.path(reference_library, "susieR")),
          as.character(packageVersion("coloc")) == "5.2.3",
          as.character(packageVersion("susieR")) == "0.14.2")
settings <- dget(arguments[3L])
inputs <- lapply(0:3, function(index) read.delim(file.path(directory, paste0("input", index, ".tsv")),
                  check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character",
                  quote = "", comment.char = "", na.strings = character()))
datasets <- lapply(1:2, function(index) {
  variants <- inputs[[index]]
  raw_ld <- matrix(as.numeric(as.matrix(inputs[[index + 2L]][, -1L, drop = FALSE])),
                   nrow = nrow(variants), ncol = nrow(variants))
  changes <- ifelse(variants$effect_allele == variants$ld_a1, 1, -1)
  oriented <- diag(changes) %*% raw_ld %*% diag(changes)
  dimnames(oriented) <- list(variants$snp, variants$snp)
  dataset <- list(beta = as.numeric(variants$beta), varbeta = as.numeric(variants$se)^2,
                  snp = variants$snp, LD = oriented, N = settings[[paste0("n", index)]],
                  type = settings[[paste0("type", index)]])
  if (dataset$type == "quant") dataset$sdY <- settings[[paste0("sd_y", index)]]
  if (dataset$type == "cc") dataset$s <- settings[[paste0("case_fraction", index)]]
  dataset
})
set.seed(settings$seed)
first <- coloc::runsusie(datasets[[1L]], L = settings$l, coverage = settings$coverage,
                         min_abs_corr = settings$min_abs_corr, maxit = settings$max_iter,
                         repeat_until_convergence = FALSE, estimate_residual_variance = FALSE)
second <- coloc::runsusie(datasets[[2L]], L = settings$l, coverage = settings$coverage,
                          min_abs_corr = settings$min_abs_corr, maxit = settings$max_iter,
                          repeat_until_convergence = FALSE, estimate_residual_variance = FALSE)
reference <- coloc::coloc.susie(first, second, p1 = settings$p1, p2 = settings$p2, p12 = settings$p12)
saveRDS(list(dataset1 = datasets[[1L]], dataset2 = datasets[[2L]], fit1 = first, fit2 = second,
             coloc = reference), file.path(directory, "official-reference.RDS"))
actual <- readRDS(file.path(directory, "output/coloc.RDS"))
stopifnot(identical(actual$metadata1, inputs[[1L]]), identical(actual$metadata2, inputs[[2L]]),
          identical(actual$alignment_evidence, settings$alignment_evidence),
          identical(actual$priors, c(p1 = settings$p1, p2 = settings$p2, p12 = settings$p12)))
for (name in c("dataset1", "dataset2", "fit1", "fit2", "coloc")) {
  if (name != "coloc") {
    expected <- switch(name, dataset1 = datasets[[1L]], dataset2 = datasets[[2L]], fit1 = first, fit2 = second)
    comparison <- all.equal(actual[[name]], expected, tolerance = 1e-12, check.attributes = TRUE)
  } else comparison <- all.equal(actual$coloc, reference, tolerance = 1e-12, check.attributes = TRUE)
  if (!isTRUE(comparison)) stop(paste(name, paste(comparison, collapse = ";")))
}
summary <- read.delim(file.path(directory, "output/coloc_summary.tsv"), check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
variants <- read.delim(file.path(directory, "output/coloc_variants.tsv"), check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
if (is.null(reference$summary)) {
  stopifnot(identical(summary$status, "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS"),
            identical(variants$status, "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS"),
            !any(startsWith(names(summary), "PP.H")))
} else {
  expected_summary <- as.data.frame(reference$summary)
  expected_variants <- as.data.frame(reference$results)
  stopifnot(identical(names(summary), c(names(expected_summary), "status")),
            identical(names(variants), c(names(expected_variants), "status")))
  for (name in names(expected_summary)) {
    stopifnot(isTRUE(all.equal(summary[[name]], expected_summary[[name]], tolerance = 1e-12, check.attributes = TRUE)))
  }
  for (name in names(expected_variants)) {
    stopifnot(isTRUE(all.equal(variants[[name]], expected_variants[[name]], tolerance = 1e-12, check.attributes = TRUE)))
  }
  stopifnot(all(summary$status == "ESTIMATED_SUPPORT_ONLY"),
            all(variants$status == "CONDITIONAL_ON_H4_NOT_UNCONDITIONAL_PROBABILITY"))
}
cat("Whole official datasets, fits and coloc result; every TSV field PASS at frozen tolerance 1e-12\n")
