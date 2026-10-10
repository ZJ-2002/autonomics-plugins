stopifnot(as.character(utils::packageVersion("coloc")) == "5.2.3",
          as.character(utils::packageVersion("susieR")) == "0.14.2")
alignment_evidence <- trimws(Sys.getenv("COLOC_ALIGNMENT_EVIDENCE"))
component_count <- as.integer(Sys.getenv("COLOC_L"))
p12 <- as.numeric(Sys.getenv("COLOC_P12"))
sample_sizes <- as.numeric(c(Sys.getenv("COLOC_N1"), Sys.getenv("COLOC_N2")))
trait_types <- c(Sys.getenv("COLOC_TYPE1"), Sys.getenv("COLOC_TYPE2"))
if (!nzchar(alignment_evidence) || !component_count %in% c(10L, 20L) ||
    !p12 %in% c(1e-6, 1e-5, 1e-4) || any(!is.finite(sample_sizes)) ||
    any(sample_sizes < 3) || any(sample_sizes != floor(sample_sizes)) ||
    !all(trait_types %in% c("quant", "cc"))) stop("Frozen coloc settings invalid")
read_dataset <- function(data_port, ld_port, sample_size, trait_type, trait_index) {
  data <- read.delim(Sys.getenv(paste0("AUTONOMICS_INPUT", data_port)), check.names = FALSE, stringsAsFactors = FALSE)
  ld_table <- read.delim(Sys.getenv(paste0("AUTONOMICS_INPUT", ld_port)), check.names = FALSE, stringsAsFactors = FALSE)
  if (!all(c("snp", "beta", "se") %in% names(data)) || anyDuplicated(names(data)) ||
      nrow(data) < 3 || anyNA(data$snp) || any(!nzchar(data$snp)) || anyDuplicated(data$snp) ||
      !is.numeric(data$beta) || !is.numeric(data$se) || any(!is.finite(data$beta)) ||
      any(!is.finite(data$se)) || any(data$se <= 0)) stop("Variant table invalid")
  if (names(ld_table)[1] != "snp" || !identical(as.character(ld_table$snp), as.character(data$snp)) ||
      !identical(names(ld_table)[-1], as.character(data$snp))) stop("LD row/column variant identity mismatch")
  ld <- as.matrix(ld_table[, -1, drop = FALSE])
  if (!is.numeric(ld) || nrow(ld) != ncol(ld) || any(!is.finite(ld)) ||
      max(abs(ld - t(ld))) > 1e-8 || max(abs(diag(ld) - 1)) > 1e-8 ||
      min(eigen(ld, symmetric = TRUE, only.values = TRUE)$values) < -1e-8) stop("LD must be finite, symmetric PSD with unit diagonal")
  dimnames(ld) <- list(as.character(data$snp), as.character(data$snp))
  result <- list(beta = data$beta, varbeta = data$se^2, snp = as.character(data$snp), LD = ld,
                 N = sample_size, type = trait_type)
  if (trait_type == "quant") {
    sd_y <- as.numeric(Sys.getenv(paste0("COLOC_SD_Y", trait_index)))
    if (!is.finite(sd_y) || sd_y <= 0) stop("Known quantitative phenotype SD required")
    result$sdY <- sd_y
  } else {
    case_fraction <- as.numeric(Sys.getenv(paste0("COLOC_CASE_FRACTION", trait_index)))
    if (!is.finite(case_fraction) || case_fraction <= 0 || case_fraction >= 1) stop("Known case fraction required")
    result$s <- case_fraction
  }
  result
}
dataset1 <- read_dataset(0, 2, sample_sizes[1], trait_types[1], 1)
dataset2 <- read_dataset(1, 3, sample_sizes[2], trait_types[2], 2)
if (!identical(dataset1$snp, dataset2$snp)) stop("Both traits must have exactly the frozen common variant order")
sink(Sys.getenv("AUTONOMICS_OUTPUT2"), split = TRUE)
cat("coloc 5.2.3; susieR 0.14.2; alignment evidence", alignment_evidence, "\n")
fit1 <- coloc::runsusie(dataset1, L = component_count, coverage = .95, maxit = 1000,
                        repeat_until_convergence = FALSE)
fit2 <- coloc::runsusie(dataset2, L = component_count, coverage = .95, maxit = 1000,
                        repeat_until_convergence = FALSE)
result <- coloc::coloc.susie(fit1, fit2, p1 = 1e-4, p2 = 1e-4, p12 = p12)
summary <- as.data.frame(result$summary)
if (nrow(summary) == 0 || !all(paste0("PP.H", 0:4, ".abf") %in% names(summary))) {
  summary <- data.frame(status = "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS")
} else {
  probabilities <- as.matrix(summary[, paste0("PP.H", 0:4, ".abf")])
  if (any(!is.finite(probabilities)) || any(probabilities < 0) || any(probabilities > 1) ||
      any(abs(rowSums(probabilities) - 1) > 1e-8)) stop("Official posterior output invalid")
  summary$status <- "ESTIMATED_SUPPORT_ONLY"
}
write.table(summary, Sys.getenv("AUTONOMICS_OUTPUT0"), sep = "\t", quote = FALSE, row.names = FALSE)
saveRDS(list(dataset1 = dataset1, dataset2 = dataset2, fit1 = fit1, fit2 = fit2,
             coloc = result, p1 = 1e-4, p2 = 1e-4, p12 = p12, L = component_count,
             alignment_evidence = alignment_evidence), Sys.getenv("AUTONOMICS_OUTPUT1"))
print(summary)
print(sessionInfo())
sink()
