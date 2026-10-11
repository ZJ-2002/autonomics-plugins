# coloc_abf - official R coloc::coloc.abf() on two GWAS summary-statistic
# datasets merged on SNP into one tab-separated file.
#
# Adapted from the legacy Rust wrapper (nodes-io coloc_abf_container.rs).
# Every parameter arrives as a COLOC_-prefixed environment value; optional
# parameters resolve to empty strings and are gated with nzchar(), numbers
# are parsed with as.numeric(). The coloc.abf() call structure, the dataset
# list construction and the RDS + log epilogues match the legacy script
# template.

input <- Sys.getenv("AUTONOMICS_INPUT0")
result_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
stopifnot(as.character(utils::packageVersion("coloc")) == "5.2.3")
if (!all(nzchar(c(input, result_path, log_path)))) stop("All declared input/output ports are required")
output_paths <- vapply(c(result_path, log_path), normalizePath, character(1), mustWork = FALSE)
if (anyDuplicated(output_paths)) stop("Output paths must be distinct")
link_targets <- Sys.readlink(output_paths)
if (any(file.exists(output_paths)) || any(!is.na(link_targets) & nzchar(link_targets))) stop("Existing output must not be overwritten")
field_counts <- count.fields(input, sep = "\t", quote = "", comment.char = "", blank.lines.skip = FALSE)
if (length(field_counts) < 2L || any(field_counts != field_counts[1L])) stop("TSV rows must be nonempty and rectangular")
data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE,
                   colClasses = "character", na.strings = character(), quote = "",
                   comment.char = "", fill = FALSE, blank.lines.skip = FALSE, row.names = NULL)
if (anyDuplicated(names(data))) stop("Duplicate TSV headers are ambiguous")
if (any(!nzchar(trimws(names(data))))) stop("Empty TSV headers are invalid")
for (index in c(1L, 2L)) {
  for (field in c("snp", "beta", "varbeta", "pvalues", "maf")) {
    column <- Sys.getenv(paste0("COLOC_DATASET", index, "_", toupper(field)))
    if (!nzchar(column)) next
    if (!(column %in% names(data))) stop("Missing mapped column: ", column)
  }
  snp_column <- Sys.getenv(paste0("COLOC_DATASET", index, "_SNP"))
  if (nzchar(snp_column)) {
    identifiers <- data[[snp_column]]
    if (any(!nzchar(identifiers)) || any(grepl("[[:space:][:cntrl:]]", identifiers))) stop("Invalid SNP identifiers")
  }
}
numeric_columns <- unique(Sys.getenv(unlist(lapply(c(1L, 2L), function(index) {
  paste0("COLOC_DATASET", index, "_", c("BETA", "VARBETA", "PVALUES", "MAF"))
}))))
numeric_columns <- numeric_columns[nzchar(numeric_columns)]
identifier_columns <- Sys.getenv(c("COLOC_DATASET1_SNP", "COLOC_DATASET2_SNP"))
if (any(numeric_columns %in% identifier_columns)) stop("SNP identifier and numeric mappings must not alias")
for (column in numeric_columns) {
  values <- suppressWarnings(as.numeric(data[[column]]))
  if (any(!is.finite(values))) stop("Mapped numeric columns must contain finite numbers: ", column)
  data[[column]] <- values
}

# -- dataset 1: cross-field validation -----------------------------------
# Mirrors the legacy wrapper validate(), which the manifest param DSL
# cannot express: exactly one of (beta+varbeta) or pvalues, and the
# pvalues path requires maf, n and (for cc traits) s.
if (!(Sys.getenv("COLOC_DATASET1_TYPE") %in% c("quant", "cc"))) {
  stop("dataset1.type must be quant or cc", call. = FALSE)
}
if (trimws(Sys.getenv("COLOC_DATASET1_SNP")) == "") {
  stop("dataset1.snp cannot be empty", call. = FALSE)
}
if (nzchar(Sys.getenv("COLOC_DATASET1_BETA")) &&
    nzchar(Sys.getenv("COLOC_DATASET1_VARBETA")) &&
    !nzchar(Sys.getenv("COLOC_DATASET1_PVALUES"))) {
  if (trimws(Sys.getenv("COLOC_DATASET1_BETA")) == "" ||
      trimws(Sys.getenv("COLOC_DATASET1_VARBETA")) == "") {
    stop("dataset1.beta and dataset1.varbeta cannot be empty", call. = FALSE)
  }
} else if (!nzchar(Sys.getenv("COLOC_DATASET1_BETA")) &&
           !nzchar(Sys.getenv("COLOC_DATASET1_VARBETA")) &&
           nzchar(Sys.getenv("COLOC_DATASET1_PVALUES"))) {
  if (trimws(Sys.getenv("COLOC_DATASET1_PVALUES")) == "") {
    stop("dataset1.pvalues cannot be empty", call. = FALSE)
  }
  if (!nzchar(Sys.getenv("COLOC_DATASET1_MAF"))) {
    stop("dataset1.maf is required when using dataset1.pvalues", call. = FALSE)
  }
  if (!nzchar(Sys.getenv("COLOC_DATASET1_N"))) {
    stop("dataset1.n is required when using dataset1.pvalues", call. = FALSE)
  }
  if (Sys.getenv("COLOC_DATASET1_TYPE") == "cc" &&
      !nzchar(Sys.getenv("COLOC_DATASET1_S"))) {
    stop("dataset1.s is required for cc + pvalues", call. = FALSE)
  }
} else {
  stop("dataset1 must supply exactly one of (beta+varbeta) or pvalues", call. = FALSE)
}

# -- dataset 1: column extraction -----------------------------------------
# Legacy equivalent: snp_1 <- data$<column>; the plugin resolves the
# column name from the environment instead of Rust string interpolation.
snp_1 <- data[[Sys.getenv("COLOC_DATASET1_SNP")]]
type_1 <- Sys.getenv("COLOC_DATASET1_TYPE")
if (nzchar(Sys.getenv("COLOC_DATASET1_BETA"))) {
  beta_1 <- data[[Sys.getenv("COLOC_DATASET1_BETA")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET1_VARBETA"))) {
  varbeta_1 <- data[[Sys.getenv("COLOC_DATASET1_VARBETA")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET1_PVALUES"))) {
  pvalues_1 <- data[[Sys.getenv("COLOC_DATASET1_PVALUES")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET1_MAF"))) {
  MAF_1 <- data[[Sys.getenv("COLOC_DATASET1_MAF")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET1_N"))) {
  N_1 <- as.numeric(Sys.getenv("COLOC_DATASET1_N"))
}
if (nzchar(Sys.getenv("COLOC_DATASET1_S"))) {
  s_1 <- as.numeric(Sys.getenv("COLOC_DATASET1_S"))
}
if (nzchar(Sys.getenv("COLOC_DATASET1_SD_Y"))) {
  sdY_1 <- as.numeric(Sys.getenv("COLOC_DATASET1_SD_Y"))
}

# Absent optional fields stay absent from the dataset list, exactly like
# the legacy list_args assembly (coloc dispatches on element presence).
dataset_1 <- list(snp = snp_1, type = type_1)
if (nzchar(Sys.getenv("COLOC_DATASET1_BETA"))) {
  dataset_1$beta <- beta_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_VARBETA"))) {
  dataset_1$varbeta <- varbeta_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_PVALUES"))) {
  dataset_1$pvalues <- pvalues_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_MAF"))) {
  dataset_1$MAF <- MAF_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_N"))) {
  dataset_1$N <- N_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_S"))) {
  dataset_1$s <- s_1
}
if (nzchar(Sys.getenv("COLOC_DATASET1_SD_Y"))) {
  dataset_1$sdY <- sdY_1
}

# -- dataset 2: cross-field validation -----------------------------------
if (!(Sys.getenv("COLOC_DATASET2_TYPE") %in% c("quant", "cc"))) {
  stop("dataset2.type must be quant or cc", call. = FALSE)
}
if (trimws(Sys.getenv("COLOC_DATASET2_SNP")) == "") {
  stop("dataset2.snp cannot be empty", call. = FALSE)
}
if (nzchar(Sys.getenv("COLOC_DATASET2_BETA")) &&
    nzchar(Sys.getenv("COLOC_DATASET2_VARBETA")) &&
    !nzchar(Sys.getenv("COLOC_DATASET2_PVALUES"))) {
  if (trimws(Sys.getenv("COLOC_DATASET2_BETA")) == "" ||
      trimws(Sys.getenv("COLOC_DATASET2_VARBETA")) == "") {
    stop("dataset2.beta and dataset2.varbeta cannot be empty", call. = FALSE)
  }
} else if (!nzchar(Sys.getenv("COLOC_DATASET2_BETA")) &&
           !nzchar(Sys.getenv("COLOC_DATASET2_VARBETA")) &&
           nzchar(Sys.getenv("COLOC_DATASET2_PVALUES"))) {
  if (trimws(Sys.getenv("COLOC_DATASET2_PVALUES")) == "") {
    stop("dataset2.pvalues cannot be empty", call. = FALSE)
  }
  if (!nzchar(Sys.getenv("COLOC_DATASET2_MAF"))) {
    stop("dataset2.maf is required when using dataset2.pvalues", call. = FALSE)
  }
  if (!nzchar(Sys.getenv("COLOC_DATASET2_N"))) {
    stop("dataset2.n is required when using dataset2.pvalues", call. = FALSE)
  }
  if (Sys.getenv("COLOC_DATASET2_TYPE") == "cc" &&
      !nzchar(Sys.getenv("COLOC_DATASET2_S"))) {
    stop("dataset2.s is required for cc + pvalues", call. = FALSE)
  }
} else {
  stop("dataset2 must supply exactly one of (beta+varbeta) or pvalues", call. = FALSE)
}

# -- dataset 2: column extraction -----------------------------------------
snp_2 <- data[[Sys.getenv("COLOC_DATASET2_SNP")]]
type_2 <- Sys.getenv("COLOC_DATASET2_TYPE")
if (nzchar(Sys.getenv("COLOC_DATASET2_BETA"))) {
  beta_2 <- data[[Sys.getenv("COLOC_DATASET2_BETA")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET2_VARBETA"))) {
  varbeta_2 <- data[[Sys.getenv("COLOC_DATASET2_VARBETA")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET2_PVALUES"))) {
  pvalues_2 <- data[[Sys.getenv("COLOC_DATASET2_PVALUES")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET2_MAF"))) {
  MAF_2 <- data[[Sys.getenv("COLOC_DATASET2_MAF")]]
}
if (nzchar(Sys.getenv("COLOC_DATASET2_N"))) {
  N_2 <- as.numeric(Sys.getenv("COLOC_DATASET2_N"))
}
if (nzchar(Sys.getenv("COLOC_DATASET2_S"))) {
  s_2 <- as.numeric(Sys.getenv("COLOC_DATASET2_S"))
}
if (nzchar(Sys.getenv("COLOC_DATASET2_SD_Y"))) {
  sdY_2 <- as.numeric(Sys.getenv("COLOC_DATASET2_SD_Y"))
}

dataset_2 <- list(snp = snp_2, type = type_2)
if (nzchar(Sys.getenv("COLOC_DATASET2_BETA"))) {
  dataset_2$beta <- beta_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_VARBETA"))) {
  dataset_2$varbeta <- varbeta_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_PVALUES"))) {
  dataset_2$pvalues <- pvalues_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_MAF"))) {
  dataset_2$MAF <- MAF_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_N"))) {
  dataset_2$N <- N_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_S"))) {
  dataset_2$s <- s_2
}
if (nzchar(Sys.getenv("COLOC_DATASET2_SD_Y"))) {
  dataset_2$sdY <- sdY_2
}

p1 <- as.numeric(Sys.getenv("COLOC_P1"))
p2 <- as.numeric(Sys.getenv("COLOC_P2"))
p12 <- as.numeric(Sys.getenv("COLOC_P12"))

for (dataset in list(dataset_1, dataset_2)) {
  if (!is.null(dataset[["varbeta"]]) && any(dataset[["varbeta"]] <= 0)) stop("varbeta must be positive")
  if (!is.null(dataset[["pvalues"]]) && any(dataset[["pvalues"]] <= 0 | dataset[["pvalues"]] > 1)) stop("pvalues must be in (0,1]")
  if (!is.null(dataset[["MAF"]]) && any(dataset[["MAF"]] <= 0 | dataset[["MAF"]] >= 1)) stop("MAF must be strictly between zero and one")
  if (!is.null(dataset[["sdY"]]) && (!is.finite(dataset[["sdY"]]) || dataset[["sdY"]] <= 0)) stop("sdY must be positive and finite")
  if (!is.null(dataset[["N"]]) && (!is.finite(dataset[["N"]]) || dataset[["N"]] <= 0)) stop("N must be positive and finite")
  if (!is.null(dataset[["s"]]) && (!is.finite(dataset[["s"]]) || dataset[["s"]] <= 0 || dataset[["s"]] >= 1)) stop("s must be between zero and one")
}
if (any(!is.finite(c(p1, p2, p12))) || any(c(p1, p2, p12) < 0 | c(p1, p2, p12) > 1)) {
  stop("Priors must be finite probabilities in [0,1]")
}

result <- coloc::coloc.abf(
  dataset1 = dataset_1,
  dataset2 = dataset_2,
  p1 = p1,
  p2 = p2,
  p12 = p12
)

numeric_results <- result$results[vapply(result$results, is.numeric, logical(1))]
if (any(!is.finite(result$summary)) || any(!is.finite(unlist(numeric_results)))) {
  stop("Official result contains non-finite inference; no analytic output published")
}

sink(log_path, split = TRUE)
cat("## coloc.abf (official R package 5.2.3)\n")
print(result$summary)
cat("\n## top SNPs by SNP.PP.H4\n")
ord <- order(result$results$SNP.PP.H4, decreasing = TRUE)
top <- head(result$results[ord, c("snp", "SNP.PP.H4")], 10)
print(top)
sink()

saveRDS(result, result_path)

