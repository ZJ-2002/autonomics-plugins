options(stringsAsFactors = FALSE, digits = 15)

required_env <- function(name) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) {
    stop(sprintf("missing required environment variable: %s", name), call. = FALSE)
  }
  value
}

read_literal_tsv <- function(filename) {
  if (!file.exists(filename) || dir.exists(filename) ||
      system2("/usr/bin/test", c("-f", shQuote(filename)), stdout = FALSE, stderr = FALSE) != 0L) {
    stop("input must be an existing regular file", call. = FALSE)
  }
  connection <- file(filename, open = "rb")
  on.exit(close(connection), add = TRUE)
  repeat {
    block <- readBin(connection, what = "raw", n = 1024L * 1024L)
    if (!length(block)) break
    if (any(block == as.raw(0))) {
      stop("input must not contain embedded NUL bytes", call. = FALSE)
    }
  }
  lines <- readLines(filename, warn = FALSE)
  lines <- sub("\r$", "", lines)
  if (length(lines) < 2L || any(!nzchar(lines))) {
    stop("input must contain a header and nonempty data rows", call. = FALSE)
  }
  fields <- lapply(lines, function(line) {
    tokens <- strsplit(paste0(line, "\t__END__"), "\t", fixed = TRUE)[[1]]
    tokens[-length(tokens)]
  })
  header <- fields[[1]]
  if (any(grepl("[[:cntrl:]]", unlist(fields, use.names = FALSE)))) {
    stop("input fields must not contain control characters", call. = FALSE)
  }
  if (any(!nzchar(header)) || anyDuplicated(header)) {
    stop("input headers must be nonempty and unique", call. = FALSE)
  }
  if (any(lengths(fields) != length(header))) {
    stop("input rows must match the header width", call. = FALSE)
  }
  frame <- as.data.frame(do.call(rbind, fields[-1]), check.names = FALSE, stringsAsFactors = FALSE)
  colnames(frame) <- header
  frame
}

exact_integer_token <- function(token) {
  token <- trimws(token)
  match <- regmatches(token, regexec(
    "^([+-]?)([0-9]*)(?:[.]([0-9]*))?(?:[eE]([+-]?[0-9]+))?$", token, perl = TRUE
  ))[[1]]
  if (length(match) != 5L || !nzchar(paste0(match[[3]], match[[4]]))) return(FALSE)
  digits <- sub("^0+", "", paste0(match[[3]], match[[4]]))
  if (!nzchar(digits)) return(TRUE)
  if (match[[2]] == "-") return(FALSE)
  exponent <- if (nzchar(match[[5]])) suppressWarnings(as.numeric(match[[5]])) else 0
  if (!is.finite(exponent)) return(FALSE)
  decimal_places <- nchar(match[[4]]) - exponent
  if (decimal_places > 0) {
    if (decimal_places >= nchar(digits)) return(FALSE)
    tail <- substr(digits, nchar(digits) - decimal_places + 1, nchar(digits))
    if (grepl("[1-9]", tail)) return(FALSE)
    digits <- substr(digits, 1, nchar(digits) - decimal_places)
  } else {
    if (nchar(digits) - decimal_places > 10L) return(FALSE)
    digits <- paste0(digits, strrep("0", -decimal_places))
  }
  nchar(digits) < 10L || (nchar(digits) == 10L && digits <= "2147483647")
}

parse_covariates <- function(value) {
  if (!nzchar(value)) {
    return(character())
  }
  values <- strsplit(paste0(value, ",__END__"), ",", fixed = TRUE)[[1]]
  values <- trimws(values[-length(values)])
  if (any(!nzchar(values))) {
    stop("covariates must not contain empty entries", call. = FALSE)
  }
  if (anyDuplicated(values)) {
    stop("covariates cannot contain duplicates", call. = FALSE)
  }
  values
}

main <- function() {
count_path <- required_env("AUTONOMICS_INPUT0")
metadata_path <- required_env("AUTONOMICS_INPUT1")
results_path <- required_env("AUTONOMICS_OUTPUT0")
normalized_path <- required_env("AUTONOMICS_OUTPUT1")
size_factors_path <- required_env("AUTONOMICS_OUTPUT2")
dataset_path <- required_env("AUTONOMICS_OUTPUT3")
report_path <- required_env("AUTONOMICS_OUTPUT4")

output_targets <- c(results_path, normalized_path, size_factors_path, dataset_path, report_path)
links <- Sys.readlink(output_targets)
if (any(file.exists(output_targets)) || any(!is.na(links) & nzchar(links))) {
  stop("existing outputs must not be overwritten", call. = FALSE)
}
identities <- vapply(output_targets, function(filename) {
  if (!dir.exists(dirname(filename))) stop("output parent must exist", call. = FALSE)
  file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename))
}, character(1))
if (anyDuplicated(identities)) stop("output paths must be distinct", call. = FALSE)
if (any(file.access(dirname(output_targets), 2L) != 0L)) {
  stop("output parent directories must be writable", call. = FALSE)
}
stage <- tempfile(pattern = "deseq2-publication-")
if (!dir.create(stage)) stop("cannot create private publication staging", call. = FALSE)
published <- character()
complete <- FALSE
on.exit({
  if (!complete && length(published)) unlink(published)
  unlink(stage, recursive = TRUE)
}, add = TRUE)
staged_outputs <- file.path(stage, paste0("port", seq_along(output_targets)))
results_path <- staged_outputs[[1]]
normalized_path <- staged_outputs[[2]]
size_factors_path <- staged_outputs[[3]]
dataset_path <- staged_outputs[[4]]
report_path <- staged_outputs[[5]]

condition_reference <- required_env("AUTONOMICS_DESEQ2_CONDITION_REFERENCE")
condition_test <- required_env("AUTONOMICS_DESEQ2_CONDITION_TEST")
covariates <- parse_covariates(Sys.getenv("AUTONOMICS_DESEQ2_COVARIATES"))
fit_type <- Sys.getenv("AUTONOMICS_DESEQ2_FIT_TYPE", "parametric")
alpha <- as.numeric(Sys.getenv("AUTONOMICS_DESEQ2_ALPHA", "0.1"))
threads_text <- Sys.getenv("AUTONOMICS_DESEQ2_THREADS", "1")
threads <- suppressWarnings(as.integer(threads_text))
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
if (is.na(alpha) || !is.finite(alpha) || alpha <= 0 || alpha >= 1) {
  stop("alpha must be finite and lie strictly between 0 and 1", call. = FALSE)
}
if (!identical(threads_text, "1")) {
  stop("threads must be 1 in the deterministic first contract", call. = FALSE)
}

counts_frame <- read_literal_tsv(count_path)
metadata_frame <- read_literal_tsv(metadata_path)

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
if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0) || any(counts != floor(counts)) || any(counts > .Machine$integer.max)) {
  stop("all count values must be finite nonnegative integers within R integer range", call. = FALSE)
}
count_tokens <- as.vector(as.matrix(counts_frame[, -1]))
nonliteral_integers <- !grepl("^[+]?[0-9]+$", trimws(count_tokens))
if (any(!vapply(count_tokens[nonliteral_integers], exact_integer_token, logical(1)))) {
  stop("all count values must be finite nonnegative integers within R integer range", call. = FALSE)
}
if (any(colSums(counts) <= 0)) {
  stop("every sample library must have positive total counts", call. = FALSE)
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
if (anyNA(condition_values) || !all(nzchar(condition_values)) || any(condition_values == "NA")) {
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
if (any(make.names(covariates) != covariates)) {
  stop("covariate names must be simple R identifiers", call. = FALSE)
}

for (covariate in covariates) {
  values <- metadata_frame[[covariate]]
  if (any(values == "NA") || any(!nzchar(values))) {
    stop(sprintf("covariate %s cannot contain missing values", covariate), call. = FALSE)
  }
  numeric_values <- suppressWarnings(as.numeric(values))
  if (any(is.nan(numeric_values)) || (!anyNA(numeric_values) && any(!is.finite(numeric_values)))) {
    stop(sprintf("numeric covariate %s must be finite", covariate), call. = FALSE)
  }
  if (!anyNA(numeric_values) && all(is.finite(numeric_values))) {
    metadata_frame[[covariate]] <- numeric_values
  } else {
    if (anyNA(values) || !all(nzchar(as.character(values)))) {
      stop(sprintf("covariate %s cannot contain missing values", covariate), call. = FALSE)
    }
    metadata_frame[[covariate]] <- factor(as.character(values))
  }
}

design_terms <- c(covariates, "condition")
design <- as.formula(paste("~", paste(design_terms, collapse = " + ")))
design_string <- paste("~", paste(design_terms, collapse = " + "))
model_matrix <- model.matrix(design, data = metadata_frame)
if (nrow(model_matrix) != ncol(counts) || qr(model_matrix)$rank < ncol(model_matrix) || nrow(model_matrix) <= ncol(model_matrix)) {
  stop(
    "design must retain every sample, be full rank and have positive residual degrees of freedom",
    call. = FALSE
  )
}

if (lfc_shrink == "apeglm" && !requireNamespace("apeglm", quietly = TRUE)) {
  stop("lfc_shrink=apeglm requires the apeglm package in the runtime image", call. = FALSE)
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
result <- DESeq2::results(
  dds,
  contrast = c("condition", condition_test, condition_reference),
  alpha = alpha,
  independentFiltering = TRUE,
  cooksCutoff = TRUE
)

if (lfc_shrink == "apeglm") {
  shrink_coef <- make.names(sprintf("condition_%s_vs_%s", condition_test, condition_reference))
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
    node = "deseq2_de",
    contrast = list(
      variable = "condition",
      test = condition_test,
      reference = condition_reference
    ),
    design = design_string,
    fit_type = fit_type,
    actual_dispersion_fit_type = attr(DESeq2::dispersionFunction(dds), "fitType"),
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
  sample_ids = unname(as.list(colnames(counts))),
  gene_ledger = list(
    all_gene_ids = unname(as.list(gene_ids)),
    all_zero_gene_ids = unname(as.list(gene_ids[rowSums(counts) == 0])),
    pvalue_unavailable_gene_ids = unname(as.list(gene_ids[is.na(result$pvalue)])),
    independent_filter_only_gene_ids = unname(as.list(gene_ids[!is.na(result$pvalue) & is.na(padj)])),
    adjusted_pvalue_available_gene_ids = unname(as.list(gene_ids[!is.na(padj)])),
    family_scope = "Official DESeq2 independent filtering; not a frozen study hypothesis family",
    pvalue_unavailable_scope = "Official missing pvalue retained; not silently reclassified as independent filtering"
  ),
  column_semantics = list(
    log2FoldChange = if (lfc_shrink == "apeglm") "apeglm posterior estimate" else "DESeq2 MLE",
    lfcSE = if (lfc_shrink == "apeglm") "apeglm posterior uncertainty" else "DESeq2 MLE standard error",
    stat = "Unshrunk DESeq2 Wald statistic",
    pvalue = "Unshrunk DESeq2 Wald pvalue",
    padj = "Official independently filtered DESeq2 adjusted pvalue"
  ),
  factor_levels = lapply(col_data, levels),
  result = list(
    genes = nrow(result_frame),
    independent_filtering_retained = sum(tested),
    significant_at_alpha = sum(tested & padj < alpha),
    up_at_alpha = sum(tested & padj < alpha & log2_fold_change > 0),
    down_at_alpha = sum(tested & padj < alpha & log2_fold_change < 0)
  ),
  outputs = list(
    results = list(path = basename(output_targets[[1]]), md5 = file_checksum(results_path)),
    normalized_counts = list(path = basename(output_targets[[2]]), md5 = file_checksum(normalized_path)),
    size_factors = list(path = basename(output_targets[[3]]), md5 = file_checksum(size_factors_path)),
    dataset = list(path = basename(output_targets[[4]]), md5 = file_checksum(dataset_path))
  )
)
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

links <- Sys.readlink(output_targets)
if (any(file.exists(output_targets)) || any(!is.na(links) & nzchar(links))) {
  stop("output appeared during execution; publication refused", call. = FALSE)
}
for (index in seq_along(staged_outputs)) {
  if (!file.copy(staged_outputs[[index]], output_targets[[index]], overwrite = FALSE)) {
    stop("output publication failed", call. = FALSE)
  }
  published <- c(published, output_targets[[index]])
}
complete <- TRUE
}
main()
