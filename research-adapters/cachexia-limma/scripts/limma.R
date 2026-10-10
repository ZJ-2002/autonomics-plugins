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

.counts_contract <- counts_preflight("limma")
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

split_csv <- function(value) {
  if (!nzchar(value)) return(character())
  values <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  values[nzchar(values)]
}

required_env("AUTONOMICS_INPUT0")
required_env("AUTONOMICS_INPUT1")

count_path <- Sys.getenv("AUTONOMICS_INPUT0")
metadata_path <- Sys.getenv("AUTONOMICS_INPUT1")
results_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
weights_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
normalized_path <- Sys.getenv("AUTONOMICS_OUTPUT2")
contrast_summary_path <- Sys.getenv("AUTONOMICS_OUTPUT3")
report_path <- Sys.getenv("AUTONOMICS_OUTPUT4")

outcome_var <- required_env("AUTONOMICS_LIMMA_OUTCOME")
covariates <- split_csv(Sys.getenv("AUTONOMICS_LIMMA_COVARIATES"))
contrast_var <- required_env("AUTONOMICS_LIMMA_CONTRAST_VAR")
contrast_levels <- split_csv(Sys.getenv("AUTONOMICS_LIMMA_CONTRAST_LEVELS"))
outcome_mode <- Sys.getenv("AUTONOMICS_LIMMA_OUTCOME_MODE", "categorical")
normalization <- Sys.getenv("AUTONOMICS_LIMMA_NORMALIZATION", "tmm")
alpha <- as.numeric(Sys.getenv("AUTONOMICS_LIMMA_ALPHA", "0.05"))
threads <- as.integer(Sys.getenv("AUTONOMICS_LIMMA_THREADS", "1"))

if (!outcome_mode %in% c("categorical", "continuous")) {
  stop("outcome_mode must be 'categorical' or 'continuous'", call. = FALSE)
}
if (!normalization %in% c("tmm", "quantile", "none")) {
  stop("normalization must be tmm, quantile, or none", call. = FALSE)
}
if (is.na(alpha) || !is.finite(alpha) || alpha <= 0 || alpha >= 1) {
  stop("alpha must lie strictly between 0 and 1", call. = FALSE)
}
if (is.na(threads) || threads < 1) {
  stop("threads must be a positive integer", call. = FALSE)
}

if (identical(outcome_mode, "categorical") && length(contrast_levels) != 2) {
  stop("contrast_levels must contain exactly two entries for categorical outcome", call. = FALSE)
}
if (anyDuplicated(covariates)) {
  stop("covariates cannot contain duplicates", call. = FALSE)
}
for (cov in covariates) {
  if (identical(cov, outcome_var) || identical(cov, "sample_id")) {
    stop(sprintf("covariate `%s` is reserved", cov), call. = FALSE)
  }
  if (!grepl("^[.A-Za-z][.A-Za-z0-9_]*$", cov)) {
    stop(sprintf("covariate `%s` must be a simple R identifier", cov), call. = FALSE)
  }
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
counts <- suppressWarnings(matrix(
  as.numeric(as.matrix(counts_frame[, -1])),
  nrow = nrow(counts_frame)
))
rownames(counts) <- gene_ids
colnames(counts) <- count_samples
if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0)) {
  stop("all count values must be finite nonnegatives", call. = FALSE)
}

if (ncol(metadata_frame) < 2 || !identical(colnames(metadata_frame)[[1]], "sample_id")) {
  stop("sample metadata must start with sample_id", call. = FALSE)
}
if (anyDuplicated(colnames(metadata_frame))) {
  stop("sample metadata column names must be unique", call. = FALSE)
}
if (anyDuplicated(metadata_frame[[1]])) {
  stop("sample_id values must be unique", call. = FALSE)
}
rownames(metadata_frame) <- metadata_frame[[1]]
if (!setequal(count_samples, metadata_frame[[1]])) {
  stop("count matrix and metadata sample sets differ", call. = FALSE)
}
metadata_frame <- metadata_frame[count_samples, , drop = FALSE]

required_columns <- unique(c(outcome_var, covariates, contrast_var))
missing <- setdiff(required_columns, colnames(metadata_frame))
if (length(missing) > 0) {
  stop(sprintf("metadata is missing required columns: %s", paste(missing, collapse = ", ")), call. = FALSE)
}

design_terms <- character()
for (column in unique(c(outcome_var, covariates))) {
  original_values <- metadata_frame[[column]]
  if (anyNA(original_values)) {
    stop(sprintf("metadata column `%s` contains NA", column), call. = FALSE)
  }
  if (column == outcome_var && outcome_mode == "categorical") {
    values <- as.character(original_values)
    if (length(contrast_levels) >= 2) {
      values <- factor(values, levels = contrast_levels)
    } else {
      values <- factor(values)
    }
    metadata_frame[[column]] <- values
    design_terms <- c(design_terms, column)
  } else {
    if (column == outcome_var || .counts_contract$covariate_types[[column]] == "numeric") {
      metadata_frame[[column]] <- as.numeric(original_values)
    } else metadata_frame[[column]] <- factor(as.character(original_values))
    design_terms <- c(design_terms, column)
  }
}

if (!identical(contrast_var, outcome_var)) {
  stop("contrast_var must equal outcome_var in the first contract", call. = FALSE)
}
if (identical(outcome_mode, "categorical")) {
  formula <- paste("~ 0 +", paste(design_terms, collapse = " + "))
} else {
  formula <- paste("~", paste(design_terms, collapse = " + "))
}
design_matrix <- model.matrix(as.formula(formula), data = metadata_frame)
colnames(design_matrix) <- make.names(colnames(design_matrix))

if (identical(outcome_mode, "categorical")) {
  test_coefficient <- make.names(paste0(contrast_var, contrast_levels[2]))
  reference_coefficient <- make.names(paste0(contrast_var, contrast_levels[1]))
  contrast <- limma::makeContrasts(
    contrasts = sprintf("%s - %s", test_coefficient, reference_coefficient),
    levels = design_matrix
  )
  contrast_label <- sprintf("%s_%s_vs_%s", contrast_var, contrast_levels[2], contrast_levels[1])
} else {
  if (length(contrast_levels) > 0) {
    stop("CONTRAST_LEVELS only applies to categorical outcome", call. = FALSE)
  }
  if (!nzchar(contrast_var)) {
    contrast_var <- outcome_var
  }
  contrast <- NULL
  contrast_label <- sprintf("%s_continuous", contrast_var)
}

dge <- edgeR::DGEList(counts = counts)
keep <- edgeR::filterByExpr(dge, design = design_matrix)
dge <- dge[keep, , keep.lib.sizes = FALSE]
if (identical(normalization, "tmm")) {
  dge <- edgeR::calcNormFactors(dge, method = "TMM")
}

v <- limma::voom(dge, design = design_matrix,
                 normalize.method = if (normalization == "quantile") "quantile" else "none", plot = FALSE)
colnames(v$weights) <- colnames(v$E)

fit <- limma::lmFit(v, design_matrix)

if (is.null(contrast)) {
  fit <- limma::eBayes(fit)
  coef_idx <- which(colnames(design_matrix) == contrast_var)
  if (length(coef_idx) != 1L) {
    stop(sprintf("unable to locate coefficient for `%s`", contrast_var), call. = FALSE)
  }
  top <- limma::topTable(
    fit,
    coef = coef_idx,
    number = Inf,
    sort.by = "none",
    confint = FALSE,
    adjust.method = "BH"
  )
} else {
  fit <- limma::contrasts.fit(fit, contrast)
  fit <- limma::eBayes(fit)
  top <- limma::topTable(
    fit,
    number = Inf,
    sort.by = "none",
    confint = FALSE,
    adjust.method = "BH"
  )
}

results_frame <- data.frame(
  gene_id = rownames(top),
  top,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(results_frame, results_path, sep = "\t", quote = FALSE, row.names = FALSE)

weights_frame <- data.frame(
  gene_id = rownames(v$E),
  v$weights,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(weights_frame, weights_path, sep = "\t", quote = FALSE, row.names = FALSE)

normalized_frame <- data.frame(
  gene_id = rownames(v$E),
  v$E,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(normalized_frame, normalized_path, sep = "\t", quote = FALSE, row.names = FALSE)

contrast_summary <- data.frame(
  outcome_mode = outcome_mode,
  outcome_var = outcome_var,
  contrast_var = contrast_var,
  contrast_label = contrast_label,
  normalization = normalization,
  covariates = if (length(covariates)) paste(covariates, collapse = ",") else "",
  design = paste(design_terms, collapse = " + "),
  genes_kept = nrow(v$E),
  samples = ncol(v$E),
  alpha = alpha,
  threads = threads,
  stringsAsFactors = FALSE
)
write.table(contrast_summary, contrast_summary_path, sep = "\t", quote = FALSE, row.names = FALSE)

file_checksum <- function(path) unname(tools::md5sum(path))

report <- list(
  schema_version = "1.0",
  node = "limma_voom_container",
  analysis = list(
    outcome_mode = outcome_mode,
    outcome_var = outcome_var,
    contrast_var = contrast_var,
    contrast_levels = contrast_levels,
    normalization = normalization,
    covariates = covariates,
    design = paste(design_terms, collapse = " + "),
    alpha = alpha,
    threads = threads,
    formula = formula
  ),
  engine = list(
    package = c("limma", "edgeR"),
    versions = list(
      limma = as.character(packageVersion("limma")),
      edgeR = as.character(packageVersion("edgeR"))
    ),
    bioconductor_release = Sys.getenv("BIOCONDUCTOR_RELEASE"),
    r_version = paste(R.version$major, R.version$minor, sep = ".")
  ),
  inputs = list(
    count_matrix = list(path = basename(count_path), md5 = file_checksum(count_path)),
    sample_metadata = list(path = basename(metadata_path), md5 = file_checksum(metadata_path))
  ),
  dimensions = list(
    genes_total = nrow(counts),
    genes_after_filter = nrow(v$E),
    samples = ncol(counts),
    design_columns = ncol(design_matrix),
    design_colnames = colnames(design_matrix)
  ),
  outputs = list(
    results = list(path = basename(results_path), md5 = file_checksum(results_path)),
    weights = list(path = basename(weights_path), md5 = file_checksum(weights_path)),
    normalized = list(path = basename(normalized_path), md5 = file_checksum(normalized_path)),
    contrast_summary = list(path = basename(contrast_summary_path), md5 = file_checksum(contrast_summary_path))
  )
)
report$study_contract <- .counts_contract$audit
report$analysis$seed <- .counts_seed
report$filter_ledger <- list(kept_gene_ids = rownames(v$E), excluded_gene_ids = setdiff(gene_ids, rownames(v$E)), excluded_raw_p = "NA; no study-family denominator inferred")
jsonlite::write_json(
  report,
  report_path,
  pretty = TRUE,
  auto_unbox = TRUE,
  digits = 15,
  na = "null"
)

cat("limma_voom complete: ", nrow(v$E), " genes x ", ncol(v$E), " samples\n", sep = "")
}, error = function(error) {
  for (port in 0:3) unlink(Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)))
  report_path <- Sys.getenv("AUTONOMICS_OUTPUT4")
  if (nzchar(report_path)) jsonlite::write_json(list(status = "BLOCKED", error = conditionMessage(error), scientific_release = FALSE, g0_granted = FALSE), report_path, auto_unbox = TRUE, pretty = TRUE)
  message(conditionMessage(error))
  quit(status = 2)
})
