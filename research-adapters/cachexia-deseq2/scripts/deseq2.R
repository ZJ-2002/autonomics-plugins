tryCatch({
counts_preflight <- function(method) {
  contract <- jsonlite::fromJSON(Sys.getenv("AUTONOMICS_INPUT2"), simplifyVector = FALSE)
  if (!identical(contract$expression_scale, "raw_integer_counts")) stop("only declared raw_integer_counts are supported; normalized arrays are forbidden")
  if (!is.character(contract$count_source) || length(contract$count_source) != 1 || !nzchar(contract$count_source)) stop("count source attestation is required")
  matrix_frame <- read.delim(Sys.getenv("AUTONOMICS_INPUT0"), check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character")
  metadata <- read.delim(Sys.getenv("AUTONOMICS_INPUT1"), check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character")
  if (ncol(matrix_frame) < 2 || names(matrix_frame)[1] != "gene_id" || anyDuplicated(names(matrix_frame))) stop("count matrix shape/columns invalid")
  genes <- as.character(matrix_frame[[1]])
  if (!length(genes) || anyNA(genes) || any(!nzchar(genes)) || anyDuplicated(genes)) stop("count gene identities invalid")
  counts <- suppressWarnings(matrix(as.numeric(as.matrix(matrix_frame[, -1, drop = FALSE])), nrow = nrow(matrix_frame)))
  if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0) || any(counts != floor(counts)) || any(counts > .Machine$integer.max)) stop("counts must be finite nonnegative 32-bit integers")
  if (any(colSums(counts) <= 0)) stop("empty count library")
  samples <- names(matrix_frame)[-1]
  if (names(metadata)[1] != "sample_id" || anyDuplicated(names(metadata)) || anyNA(metadata$sample_id) || any(!nzchar(metadata$sample_id)) || anyDuplicated(metadata$sample_id)) stop("metadata sample identities invalid")
  if (!setequal(samples, metadata$sample_id)) stop("matrix/metadata sample sets differ")
  metadata <- metadata[match(samples, metadata$sample_id), , drop = FALSE]
  unit <- contract$unit_column
  if (!is.character(unit) || length(unit) != 1 || !unit %in% names(metadata)) stop("independent-unit column must be supplied")
  units <- as.character(metadata[[unit]])
  if (anyNA(units) || any(!nzchar(units)) || anyDuplicated(units)) stop("repeated/missing independent units need another model; cells are not donors")
  prefix <- if (method == "deseq2") "AUTONOMICS_DESEQ2_" else "AUTONOMICS_LIMMA_"
  covariates <- strsplit(Sys.getenv(paste0(prefix, "COVARIATES")), ",", fixed = TRUE)[[1]]
  covariates <- trimws(covariates[nzchar(covariates)])
  if (anyDuplicated(covariates) || any(!grepl("^[A-Za-z.][A-Za-z0-9_.]*$", covariates))) stop("covariate identities invalid")
  types <- contract$covariate_types
  if (!setequal(names(types), covariates) || any(!unlist(types) %in% c("numeric", "categorical"))) stop("every covariate requires an explicit numeric/categorical type")
  for (covariate in covariates) {
    if (!covariate %in% names(metadata)) stop("covariate missing")
    values <- metadata[[covariate]]
    if (anyNA(values) || any(!nzchar(as.character(values)))) stop("covariate missing values are forbidden")
    if (types[[covariate]] == "numeric") {
      numeric_values <- suppressWarnings(as.numeric(values))
      if (anyNA(numeric_values) || any(!is.finite(numeric_values))) stop("numeric covariate must remain finite numeric; no silent factor conversion")
      metadata[[covariate]] <- numeric_values
    } else metadata[[covariate]] <- factor(as.character(values))
  }
  if (method == "deseq2") {
    outcome <- "condition"
    levels <- c(Sys.getenv("AUTONOMICS_DESEQ2_CONDITION_REFERENCE"), Sys.getenv("AUTONOMICS_DESEQ2_CONDITION_TEST"))
    categorical <- TRUE
  } else {
    outcome <- Sys.getenv("AUTONOMICS_LIMMA_OUTCOME")
    categorical <- Sys.getenv("AUTONOMICS_LIMMA_OUTCOME_MODE", "categorical") == "categorical"
    levels <- strsplit(Sys.getenv("AUTONOMICS_LIMMA_CONTRAST_LEVELS"), ",", fixed = TRUE)[[1]]
  }
  if (!grepl("^[A-Za-z.][A-Za-z0-9_.]*$", outcome) || !outcome %in% names(metadata) || outcome %in% covariates || "sample_id" %in% covariates) stop("outcome/covariate roles invalid")
  if (categorical) {
    values <- as.character(metadata[[outcome]])
    if (length(levels) != 2 || any(!nzchar(levels)) || anyDuplicated(levels) || anyNA(values) || !setequal(unique(values), levels)) stop("outcome must contain exactly the two declared levels")
    observed <- table(factor(values, levels = levels))
    expected <- contract$expected_arm_counts
    if (!setequal(names(expected), levels) || any(vapply(levels, function(level) !isTRUE(unname(observed[level]) == expected[[level]]), logical(1)))) stop("independent arm counts differ from the declared contract")
    if (any(observed < 3)) stop("at least three declared independent units per arm required in this scoped contract")
    metadata[[outcome]] <- factor(values, levels = levels)
  } else {
    metadata[[outcome]] <- suppressWarnings(as.numeric(metadata[[outcome]]))
    if (anyNA(metadata[[outcome]]) || any(!is.finite(metadata[[outcome]]))) stop("continuous outcome must be finite numeric")
    if (!isTRUE(contract$expected_n == nrow(metadata)) || nrow(metadata) < 6) stop("continuous independent-unit count mismatch")
  }
  terms <- if (method == "deseq2") c(covariates, outcome) else c(outcome, covariates)
  formula_text <- paste(if (method == "limma" && categorical) "~ 0 +" else "~", paste(terms, collapse = " + "))
  if (!identical(contract$design_formula, formula_text)) stop("design formula differs from explicit contract")
  design <- model.matrix(as.formula(formula_text), metadata)
  if (nrow(design) != nrow(metadata) || any(!is.finite(design)) || qr(design)$rank != ncol(design)) stop("rank deficient or incomplete count design")
  if (nrow(design) <= ncol(design)) stop("nonpositive count residual degrees of freedom")
  list(covariate_types = types, audit = list(expression_scale = contract$expression_scale,
    count_source = contract$count_source, unit_column = unit, design_formula = formula_text,
    independent_unit_identity_is_attestation_not_biological_validation = TRUE,
    genes_total = length(genes), sample_ids = samples, residual_df = nrow(design) - ncol(design),
    method_proof_only = TRUE, scientific_release = FALSE, g0_granted = FALSE,
    contract_md5 = unname(tools::md5sum(Sys.getenv("AUTONOMICS_INPUT2")))))
}

.counts_contract <- counts_preflight("deseq2")
if (!requireNamespace("DESeq2", quietly = TRUE)) stop("official DESeq2 package is unavailable")
.counts_seed <- as.integer(Sys.getenv("AUTONOMICS_COUNTS_SEED", "1"))
if (is.na(.counts_seed) || .counts_seed < 0) stop("invalid count seed")
set.seed(.counts_seed)
options(stringsAsFactors = FALSE, digits = 15)

required_env <- function(name) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) {
    stop(sprintf("missing required environment variable: %s", name), call. = FALSE)
  }
  value
}

parse_covariates <- function(value) {
  if (!nzchar(value)) {
    return(character())
  }
  values <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  values <- values[nzchar(values)]
  if (anyDuplicated(values)) {
    stop("covariates cannot contain duplicates", call. = FALSE)
  }
  values
}

count_path <- required_env("AUTONOMICS_INPUT0")
metadata_path <- required_env("AUTONOMICS_INPUT1")
results_path <- required_env("AUTONOMICS_OUTPUT0")
normalized_path <- required_env("AUTONOMICS_OUTPUT1")
size_factors_path <- required_env("AUTONOMICS_OUTPUT2")
dataset_path <- required_env("AUTONOMICS_OUTPUT3")
report_path <- required_env("AUTONOMICS_OUTPUT4")

condition_reference <- required_env("AUTONOMICS_DESEQ2_CONDITION_REFERENCE")
condition_test <- required_env("AUTONOMICS_DESEQ2_CONDITION_TEST")
covariates <- parse_covariates(Sys.getenv("AUTONOMICS_DESEQ2_COVARIATES"))
fit_type <- Sys.getenv("AUTONOMICS_DESEQ2_FIT_TYPE", "parametric")
alpha <- as.numeric(Sys.getenv("AUTONOMICS_DESEQ2_ALPHA", "0.1"))
threads <- as.integer(Sys.getenv("AUTONOMICS_DESEQ2_THREADS", "1"))
lfc_shrink <- Sys.getenv("AUTONOMICS_DESEQ2_LFC_SHRINK", "apeglm")

if (identical(condition_reference, condition_test)) {
  stop("condition_test and condition_reference must differ", call. = FALSE)
}
if (!fit_type %in% c("parametric", "local", "mean")) {
  stop("fit_type must be parametric, local, or mean", call. = FALSE)
}
if (!lfc_shrink %in% c("apeglm", "none")) {
  stop("lfc_shrink must be apeglm or none", call. = FALSE)
}
if (lfc_shrink == "apeglm" && !requireNamespace("apeglm", quietly = TRUE)) {
  stop("lfc_shrink=apeglm requires the apeglm package in the runtime image", call. = FALSE)
}
if (is.na(alpha) || !is.finite(alpha) || alpha <= 0 || alpha >= 1) {
  stop("alpha must be finite and lie strictly between 0 and 1", call. = FALSE)
}
if (is.na(threads) || threads != 1) {
  stop("threads must be 1 in the deterministic first contract", call. = FALSE)
}

counts_frame <- read.delim(
  count_path,
  check.names = FALSE,
  stringsAsFactors = FALSE,
  na.strings = "NA",
  colClasses = "character"
)
metadata_frame <- read.delim(
  metadata_path,
  check.names = FALSE,
  stringsAsFactors = FALSE,
  na.strings = "NA",
  colClasses = "character"
)

if (ncol(counts_frame) < 2 || !identical(colnames(counts_frame)[[1]], "gene_id")) {
  stop("count matrix must start with gene_id followed by sample columns", call. = FALSE)
}
if (anyDuplicated(colnames(counts_frame))) {
  stop("count matrix column names must be unique", call. = FALSE)
}
gene_ids <- counts_frame[[1]]
if (anyNA(gene_ids) || !all(nzchar(gene_ids))) {
  stop("gene_id cannot be empty", call. = FALSE)
}
if (anyDuplicated(gene_ids)) {
  stop("gene_id values must be unique", call. = FALSE)
}

count_samples <- colnames(counts_frame)[-1]
counts <- suppressWarnings(matrix(as.numeric(as.matrix(counts_frame[, -1])), nrow = nrow(counts_frame)))
rownames(counts) <- gene_ids
colnames(counts) <- count_samples
if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0) || any(counts != floor(counts))) {
  stop("all count values must be finite nonnegative integers", call. = FALSE)
}

if (ncol(metadata_frame) < 2 || !identical(colnames(metadata_frame)[[1]], "sample_id")) {
  stop("sample metadata must start with sample_id", call. = FALSE)
}
if (anyDuplicated(colnames(metadata_frame))) {
  stop("sample metadata column names must be unique", call. = FALSE)
}
metadata_samples <- metadata_frame[[1]]
if (anyNA(metadata_samples) || !all(nzchar(metadata_samples))) {
  stop("sample_id cannot be empty", call. = FALSE)
}
if (anyDuplicated(metadata_samples)) {
  stop("sample_id values must be unique", call. = FALSE)
}
if (!setequal(metadata_samples, count_samples)) {
  stop("count matrix and metadata sample sets must match exactly", call. = FALSE)
}

metadata_frame <- metadata_frame[match(count_samples, metadata_samples), , drop = FALSE]
rownames(metadata_frame) <- metadata_frame$sample_id

if (!"condition" %in% colnames(metadata_frame)) {
  stop("sample metadata requires a condition column", call. = FALSE)
}
condition_values <- as.character(metadata_frame$condition)
if (anyNA(condition_values) || !all(nzchar(condition_values))) {
  stop("condition cannot contain missing values", call. = FALSE)
}
observed_conditions <- unique(condition_values)
if (!setequal(observed_conditions, c(condition_reference, condition_test))) {
  stop(
    sprintf(
      "condition must contain exactly %s and %s",
      condition_reference,
      condition_test
    ),
    call. = FALSE
  )
}
metadata_frame$condition <- factor(
  condition_values,
  levels = c(condition_reference, condition_test)
)

if (any(c("sample_id", "condition") %in% covariates)) {
  stop("sample_id and condition cannot be listed as covariates", call. = FALSE)
}
missing_covariates <- setdiff(covariates, colnames(metadata_frame))
if (length(missing_covariates) > 0) {
  stop(
    sprintf("missing covariate columns: %s", paste(missing_covariates, collapse = ", ")),
    call. = FALSE
  )
}
identifier_pattern <- "^[A-Za-z.][A-Za-z0-9_.]*$"
if (!all(grepl(identifier_pattern, covariates))) {
  stop("covariate names must be simple R identifiers", call. = FALSE)
}

for (covariate in covariates) {
  values <- metadata_frame[[covariate]]
  if (.counts_contract$covariate_types[[covariate]] == "numeric") {
    metadata_frame[[covariate]] <- as.numeric(values)
  } else metadata_frame[[covariate]] <- factor(as.character(values))
}

design_terms <- c(covariates, "condition")
design <- as.formula(paste("~", paste(design_terms, collapse = " + ")))
design_string <- paste("~", paste(design_terms, collapse = " + "))
model_matrix <- model.matrix(design, data = metadata_frame)
if (qr(model_matrix)$rank < ncol(model_matrix)) {
  stop(
    "design matrix is rank deficient; remove collinear covariates or add samples",
    call. = FALSE
  )
}

col_data <- metadata_frame[, design_terms, drop = FALSE]
rownames(col_data) <- metadata_frame$sample_id

cat("DESeq2:", as.character(packageVersion("DESeq2")), "\n")
cat("Genes:", nrow(counts), "Samples:", ncol(counts), "\n")
cat("Design:", paste(deparse(design), collapse = " "), "\n")

dds <- DESeq2::DESeqDataSetFromMatrix(
  countData = counts,
  colData = col_data,
  design = design
)
dds <- DESeq2::DESeq(
  dds,
  fitType = fit_type,
  quiet = TRUE,
  parallel = FALSE
)
effective_fit_type <- attr(DESeq2::dispersionFunction(dds), "fitType")
if (!identical(effective_fit_type, fit_type)) stop("DESeq2 dispersion fit fallback differs from frozen requested method")
result <- DESeq2::results(
  dds,
  contrast = c("condition", condition_test, condition_reference),
  alpha = alpha,
  independentFiltering = TRUE,
  cooksCutoff = TRUE
)

if (lfc_shrink == "apeglm") {
  shrink_coef <- sprintf("condition_%s_vs_%s", condition_test, condition_reference)
  if (!shrink_coef %in% DESeq2::resultsNames(dds)) {
    stop(
      sprintf(
        "shrinkage coefficient %s not found among design terms: %s",
        shrink_coef,
        paste(DESeq2::resultsNames(dds), collapse = ", ")
      ),
      call. = FALSE
    )
  }
  shrunk <- DESeq2::lfcShrink(
    dds,
    coef = shrink_coef,
    type = "apeglm",
    quiet = TRUE
  )
  result$log2FoldChange <- shrunk$log2FoldChange
  result$lfcSE <- shrunk$lfcSE
}

result_data <- as.data.frame(result)
result_frame <- data.frame(
  gene_id = rownames(result_data),
  result_data,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(
  result_frame,
  results_path,
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)

normalized_counts <- DESeq2::counts(dds, normalized = TRUE)
normalized_data <- as.data.frame(normalized_counts)
normalized_frame <- data.frame(
  gene_id = rownames(normalized_data),
  normalized_data,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(
  normalized_frame,
  normalized_path,
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)

size_factors <- DESeq2::sizeFactors(dds)
size_factor_frame <- data.frame(
  sample_id = names(size_factors),
  size_factor = unname(size_factors),
  stringsAsFactors = FALSE
)
write.table(
  size_factor_frame,
  size_factors_path,
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)

saveRDS(dds, dataset_path)

file_checksum <- function(path) {
  unname(tools::md5sum(path))
}

padj <- result$padj
log2_fold_change <- result$log2FoldChange
tested <- !is.na(padj)
report <- list(
  schema_version = "1.0",
  analysis = list(
    node = "deseq2_de_container",
    contrast = list(
      variable = "condition",
      test = condition_test,
      reference = condition_reference
    ),
    design = design_string,
    fit_type = fit_type,
    lfc_shrink = lfc_shrink,
    alpha = alpha,
    independent_filtering = TRUE,
    cooks_cutoff = TRUE,
    threads = threads
  ),
  engine = list(
    package = "DESeq2",
    version = as.character(packageVersion("DESeq2")),
    apeglm_version = if (lfc_shrink == "apeglm") as.character(packageVersion("apeglm")) else NULL,
    bioconductor_release = Sys.getenv("BIOCONDUCTOR_RELEASE"),
    r_version = paste(R.version$major, R.version$minor, sep = ".")
  ),
  inputs = list(
    count_matrix = list(path = basename(count_path), md5 = file_checksum(count_path)),
    sample_metadata = list(path = basename(metadata_path), md5 = file_checksum(metadata_path))
  ),
  dimensions = list(genes = nrow(counts), samples = ncol(counts)),
  sample_ids = colnames(counts),
  factor_levels = lapply(col_data, levels),
  result = list(
    genes = nrow(result_frame),
    independent_filtering_retained = sum(tested),
    significant_at_alpha = sum(tested & padj < alpha),
    up_at_alpha = sum(tested & padj < alpha & log2_fold_change > 0),
    down_at_alpha = sum(tested & padj < alpha & log2_fold_change < 0)
  ),
  outputs = list(
    results = list(path = basename(results_path), md5 = file_checksum(results_path)),
    normalized_counts = list(path = basename(normalized_path), md5 = file_checksum(normalized_path)),
    size_factors = list(path = basename(size_factors_path), md5 = file_checksum(size_factors_path)),
    dataset = list(path = basename(dataset_path), md5 = file_checksum(dataset_path))
  )
)
report$study_contract <- .counts_contract$audit
report$analysis$seed <- .counts_seed
report$analysis$effective_fit_type <- effective_fit_type
report$analysis$coefficient_semantics <- if (lfc_shrink == "apeglm") "log2FoldChange/lfcSE=posterior; stat/pvalue/padj=MLE Wald" else "MLE Wald"
jsonlite::write_json(
  report,
  report_path,
  pretty = TRUE,
  auto_unbox = TRUE,
  digits = 15,
  na = "null"
)

cat("Retained by independent filtering:", sum(tested), "\n")
cat("Significant at alpha", alpha, ":", sum(tested & padj < alpha), "\n")
cat("log2FC shrinkage:", lfc_shrink, "\n")
}, error = function(error) {
  for (port in 0:3) unlink(Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)))
  report_path <- Sys.getenv("AUTONOMICS_OUTPUT4")
  if (nzchar(report_path)) jsonlite::write_json(list(status = "BLOCKED", error = conditionMessage(error), scientific_release = FALSE, g0_granted = FALSE), report_path, auto_unbox = TRUE, pretty = TRUE)
  message(conditionMessage(error))
  quit(status = 2)
})
