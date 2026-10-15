#!/usr/bin/env Rscript
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
  values <- strsplit(paste0(value, ",__END__"), ",", fixed = TRUE)[[1]]
  values <- trimws(values[-length(values)])
  if (any(!nzchar(values))) {
    stop("comma-separated parameters must not contain empty entries", call. = FALSE)
  }
  values
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
  parse_record <- function(line) {
    quote_character <- intToUtf8(34L)
    if (!grepl(quote_character, line, fixed = TRUE)) {
      tokens <- strsplit(paste0(line, "\t__END__"), "\t", fixed = TRUE)[[1]]
      return(tokens[-length(tokens)])
    }
    characters <- strsplit(line, "", fixed = TRUE)[[1]]
    buffer <- character(length(characters))
    size <- 0L
    tokens <- character()
    state <- "start"
    position <- 1L
    while (position <= length(characters)) {
      character <- characters[[position]]
      if (state == "quoted") {
        if (character == quote_character) {
          if (position < length(characters) && characters[[position + 1L]] == quote_character) {
            size <- size + 1L
            buffer[[size]] <- character
            position <- position + 1L
          } else {
            state <- "closed"
          }
        } else {
          size <- size + 1L
          buffer[[size]] <- character
        }
      } else if (character == "\t") {
        tokens <- c(tokens, paste0(buffer[seq_len(size)], collapse = ""))
        size <- 0L
        state <- "start"
      } else if (state == "closed") {
        stop("quoted TSV has characters after a closing quote", call. = FALSE)
      } else if (character == quote_character) {
        if (state != "start") stop("quoted TSV has a bare quote inside an unquoted field", call. = FALSE)
        state <- "quoted"
      } else {
        size <- size + 1L
        buffer[[size]] <- character
        state <- "unquoted"
      }
      position <- position + 1L
    }
    if (state == "quoted") stop("quoted TSV has an unclosed quote or multiline field", call. = FALSE)
    c(tokens, paste0(buffer[seq_len(size)], collapse = ""))
  }
  fields <- lapply(lines, parse_record)
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
    if (nchar(digits) - decimal_places > 16L) return(FALSE)
    digits <- paste0(digits, strrep("0", -decimal_places))
  }
  nchar(digits) < 16L || (nchar(digits) == 16L && digits <= "9007199254740991")
}

publication_identity <- function(filename) {
  identity <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
  status <- attr(identity, "status")
  if ((!is.null(status) && status != 0L) || length(identity) != 1L || !grepl("^[0-9]+:[0-9]+$", identity)) return(NA_character_)
  unname(identity)
}

publication_file_identity <- function(filename) {
  link <- Sys.readlink(filename)
  if (!is.na(link) && nzchar(link)) return(NA_character_)
  metadata <- function() {
    result <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i:%f:%u:%g:%s:%y"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
    status <- attr(result, "status")
    if ((!is.null(status) && status != 0L) || length(result) != 1L) return(NA_character_)
    fields <- strsplit(result, ":", fixed = TRUE)[[1]]
    if (length(fields) < 7L || is.na(strtoi(fields[[3]], base = 16L)) ||
        bitwAnd(strtoi(fields[[3]], base = 16L), 61440L) != 32768L) return(NA_character_)
    unname(result)
  }
  before <- metadata()
  if (is.na(before)) return(NA_character_)
  checksum <- tryCatch(suppressWarnings(system2("/usr/bin/sha256sum", stdin = filename, stdout = TRUE, stderr = FALSE)), error = function(condition) character())
  status <- attr(checksum, "status")
  after <- metadata()
  link <- Sys.readlink(filename)
  if ((!is.null(status) && status != 0L) || length(checksum) != 1L ||
      !grepl("^[0-9a-f]{64}  -$", checksum) || is.na(after) || !identical(before, after) ||
      (!is.na(link) && nzchar(link))) return(NA_character_)
  paste0(before, ":", substr(checksum, 1L, 64L))
}

publication_remove_owned_file <- function(filename, expected) {
  if (is.na(expected)) return(invisible(FALSE))
  current <- publication_file_identity(filename)
  if (is.na(current) || !identical(current, expected)) return(invisible(FALSE))
  invisible(unlink(filename) == 0L)
}

main <- function() {
required_env("AUTONOMICS_INPUT0")
required_env("AUTONOMICS_INPUT1")

count_path <- Sys.getenv("AUTONOMICS_INPUT0")
metadata_path <- Sys.getenv("AUTONOMICS_INPUT1")
results_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
weights_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
normalized_path <- Sys.getenv("AUTONOMICS_OUTPUT2")
contrast_summary_path <- Sys.getenv("AUTONOMICS_OUTPUT3")
report_path <- Sys.getenv("AUTONOMICS_OUTPUT4")

outputs <- c(results_path, weights_path, normalized_path, contrast_summary_path, report_path)
if (any(!nzchar(outputs))) {
  stop("all five declared output ports are required", call. = FALSE)
}
output_links <- Sys.readlink(outputs)
if (any(file.exists(outputs)) || any(!is.na(output_links) & nzchar(output_links))) {
  stop("existing outputs must not be overwritten", call. = FALSE)
}
output_identities <- vapply(outputs, function(filename) {
  if (!dir.exists(dirname(filename))) {
    stop("output parent must be an existing directory", call. = FALSE)
  }
  file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename))
}, character(1))
if (anyDuplicated(output_identities)) {
  stop("output paths must be distinct", call. = FALSE)
}
if (any(file.access(dirname(outputs), 2L) != 0L)) {
  stop("output parent directories must be writable", call. = FALSE)
}
output_targets <- outputs
if (!all(file.exists(c("/usr/bin/stat", "/usr/bin/sha256sum", "/usr/bin/rmdir")))) {
  stop("GNU stat, sha256sum and rmdir are required for publication identity checks", call. = FALSE)
}
stages <- character()
stage_identities <- character()
staged_identities <- rep(NA_character_, length(output_targets))
staged_outputs <- character()
published <- integer()
complete <- FALSE
on.exit({
  if (!complete && length(published)) {
    for (index in published) {
      publication_remove_owned_file(output_targets[[index]], staged_identities[[index]])
    }
  }
  for (index in seq_along(stages)) {
    identity <- publication_identity(stages[[index]])
    if (!is.na(identity) && identical(identity, stage_identities[[index]])) {
      if (length(staged_outputs) >= index) publication_remove_owned_file(staged_outputs[[index]], staged_identities[[index]])
      suppressWarnings(system2("/usr/bin/rmdir", c("--", shQuote(stages[[index]])), stdout = FALSE, stderr = FALSE))
    }
  }
}, add = TRUE)
for (index in seq_along(output_targets)) {
  stage <- tempfile(pattern = ".limma-voom-publication-", tmpdir = normalizePath(dirname(output_targets[[index]]), mustWork = TRUE))
  if (!dir.create(stage, mode = "0700")) stop("cannot create private publication staging", call. = FALSE)
  stages <- c(stages, stage)
  stage_identities <- c(stage_identities, publication_identity(stage))
  if (is.na(stage_identities[[index]])) stop("cannot verify private staging identity", call. = FALSE)
}
staged_outputs <- file.path(stages, paste0("port", seq_along(output_targets)))
results_path <- staged_outputs[[1]]
weights_path <- staged_outputs[[2]]
normalized_path <- staged_outputs[[3]]
contrast_summary_path <- staged_outputs[[4]]
report_path <- staged_outputs[[5]]

outcome_var <- required_env("AUTONOMICS_LIMMA_OUTCOME")
covariates <- split_csv(Sys.getenv("AUTONOMICS_LIMMA_COVARIATES"))
contrast_var <- required_env("AUTONOMICS_LIMMA_CONTRAST_VAR")
contrast_levels <- split_csv(Sys.getenv("AUTONOMICS_LIMMA_CONTRAST_LEVELS"))
outcome_mode <- Sys.getenv("AUTONOMICS_LIMMA_OUTCOME_MODE", "categorical")
normalization <- Sys.getenv("AUTONOMICS_LIMMA_NORMALIZATION", "tmm")
alpha <- as.numeric(Sys.getenv("AUTONOMICS_LIMMA_ALPHA", "0.05"))
threads_text <- Sys.getenv("AUTONOMICS_LIMMA_THREADS", "1")
threads <- suppressWarnings(as.integer(threads_text))

if (!outcome_mode %in% c("categorical", "continuous")) {
  stop("outcome_mode must be 'categorical' or 'continuous'", call. = FALSE)
}
if (!normalization %in% c("tmm", "quantile", "none")) {
  stop("normalization must be tmm, quantile, or none", call. = FALSE)
}
if (is.na(alpha) || !is.finite(alpha) || alpha <= 0 || alpha >= 1) {
  stop("alpha must lie strictly between 0 and 1", call. = FALSE)
}
if (!identical(threads_text, "1")) {
  stop("threads must be fixed at 1", call. = FALSE)
}
if (!identical(make.names(outcome_var), outcome_var) || outcome_var == "sample_id" ||
    !identical(make.names(contrast_var), contrast_var)) {
  stop("outcome_var and contrast_var must be simple nonreserved R identifiers", call. = FALSE)
}

# Contract rules the manifest DSL cannot express, carried over from the
# legacy Rust wrapper's validate() so the failure point (container start)
# keeps the legacy error messages.
if (identical(outcome_mode, "categorical") && length(contrast_levels) != 2) {
  stop("contrast_levels must contain exactly two entries for categorical outcome", call. = FALSE)
}
if (anyDuplicated(contrast_levels)) {
  stop("contrast_levels must be distinct", call. = FALSE)
}
if (anyDuplicated(covariates)) {
  stop("covariates cannot contain duplicates", call. = FALSE)
}
for (cov in covariates) {
  if (identical(cov, outcome_var) || identical(cov, "sample_id")) {
    stop(sprintf("covariate `%s` is reserved", cov), call. = FALSE)
  }
  if (!identical(make.names(cov), cov)) {
    stop(sprintf("covariate `%s` must be a simple R identifier", cov), call. = FALSE)
  }
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
counts <- suppressWarnings(matrix(
  as.numeric(as.matrix(counts_frame[, -1])),
  nrow = nrow(counts_frame)
))
rownames(counts) <- gene_ids
colnames(counts) <- count_samples
if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0)) {
  stop("all count values must be finite nonnegatives", call. = FALSE)
}
if (any(counts != floor(counts)) || any(counts > 2^53 - 1)) {
  stop("count values must be exactly representable nonnegative integers", call. = FALSE)
}
count_tokens <- as.vector(as.matrix(counts_frame[, -1]))
nonliteral_integers <- !grepl("^[+]?[0-9]+$", trimws(count_tokens))
if (any(!vapply(count_tokens[nonliteral_integers], exact_integer_token, logical(1)))) {
  stop("count values must be exactly representable nonnegative integers", call. = FALSE)
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
if (anyDuplicated(metadata_frame[[1]])) {
  stop("sample_id values must be unique", call. = FALSE)
}
if (any(!nzchar(metadata_frame[[1]]))) {
  stop("sample_id cannot be empty", call. = FALSE)
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

# Convert categorical outcome / contrast columns to factors with explicit
# reference level ordering when supplied via CONTRAST_LEVELS. Limma's
# makeContrasts consumes the resulting model matrix deterministically.
design_terms <- character()
for (column in unique(c(outcome_var, covariates))) {
  original_values <- metadata_frame[[column]]
  if (anyNA(original_values) || any(!nzchar(original_values)) || any(original_values == "NA")) {
    stop(sprintf("metadata column `%s` contains missing values", column), call. = FALSE)
  }
  if (column == outcome_var && outcome_mode == "categorical") {
    values <- as.character(original_values)
    if (length(contrast_levels) >= 2) {
      values <- factor(values, levels = contrast_levels)
    } else {
      values <- factor(values)
    }
    metadata_frame[[column]] <- values
    if (anyNA(values)) {
      stop("categorical outcome values must belong to contrast_levels", call. = FALSE)
    }
    design_terms <- c(design_terms, column)
  } else {
    if (any(!nzchar(original_values)) || any(original_values == "NA")) {
      stop(sprintf("metadata column `%s` contains missing values", column), call. = FALSE)
    }
    numeric_values <- suppressWarnings(as.numeric(original_values))
    if (all(!is.na(numeric_values)) && any(!is.finite(numeric_values))) {
      stop(sprintf("numeric metadata column `%s` must be finite", column), call. = FALSE)
    }
    if (column == outcome_var && outcome_mode == "continuous") {
      if (any(!is.finite(numeric_values))) {
        stop("continuous outcome values must be finite numbers", call. = FALSE)
      }
      metadata_frame[[column]] <- numeric_values
    } else if (all(is.finite(numeric_values))) {
      metadata_frame[[column]] <- numeric_values
    }
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
# Limma contrasts require syntactically valid coefficient names even when a
# metadata factor contains values such as "single-read".
colnames(design_matrix) <- make.names(colnames(design_matrix))
if (anyDuplicated(colnames(design_matrix))) {
  stop("design coefficient names collide after R name normalization", call. = FALSE)
}
if (nrow(design_matrix) != ncol(counts) || qr(design_matrix)$rank != ncol(design_matrix) ||
    nrow(design_matrix) <= ncol(design_matrix)) {
  stop("design must retain every sample, be full rank and have positive residual degrees of freedom", call. = FALSE)
}

if (identical(outcome_mode, "categorical")) {
  # contrast_levels is [reference, test]; report test-versus-reference logFC.
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
if (!any(keep)) {
  stop("no genes remain after official filterByExpr", call. = FALSE)
}
dge <- dge[keep, , keep.lib.sizes = FALSE]
if (identical(normalization, "tmm")) {
  dge <- edgeR::calcNormFactors(dge, method = "TMM")
}

if (identical(normalization, "quantile")) {
  v <- limma::voom(dge, design = design_matrix, normalize.method = "quantile", plot = FALSE)
} else if (identical(normalization, "none")) {
  v <- limma::voom(dge, design = design_matrix, normalize.method = "none", plot = FALSE)
} else {
  v <- limma::voom(dge, design = design_matrix, plot = FALSE)
}

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
write.table(results_frame, results_path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)

weights_frame <- data.frame(
  gene_id = rownames(v$E),
  v$weights,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
colnames(weights_frame)[-1] <- colnames(v$E)
write.table(weights_frame, weights_path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)

normalized_frame <- data.frame(
  gene_id = rownames(v$E),
  v$E,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(normalized_frame, normalized_path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)

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
write.table(contrast_summary, contrast_summary_path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)

file_checksum <- function(path) unname(tools::md5sum(path))

report <- list(
  schema_version = "1.0",
  node = "limma_voom",
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
  gene_filter = list(
    method = "edgeR::filterByExpr",
    all_gene_ids = unname(as.list(gene_ids)),
    retained_gene_ids = unname(as.list(gene_ids[keep])),
    excluded_gene_ids = unname(as.list(gene_ids[!keep])),
    BH_family = "retained genes only; not the study hypothesis ledger"
  ),
  outputs = list(
    results = list(path = basename(output_targets[[1]]), md5 = file_checksum(results_path)),
    weights = list(path = basename(output_targets[[2]]), md5 = file_checksum(weights_path)),
    normalized = list(path = basename(output_targets[[3]]), md5 = file_checksum(normalized_path)),
    contrast_summary = list(path = basename(output_targets[[4]]), md5 = file_checksum(contrast_summary_path))
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
if (any(file.exists(output_targets)) || any(!is.na(Sys.readlink(output_targets)) & nzchar(Sys.readlink(output_targets)))) {
  stop("output appeared during execution; publication refused", call. = FALSE)
}
for (index in seq_along(staged_outputs)) {
  staged_identities[[index]] <- publication_file_identity(staged_outputs[[index]])
  if (is.na(staged_identities[[index]])) stop("cannot verify staged output identity", call. = FALSE)
}
for (index in seq_along(staged_outputs)) {
  if (!identical(publication_identity(stages[[index]]), stage_identities[[index]]) ||
      !identical(publication_file_identity(staged_outputs[[index]]), staged_identities[[index]])) {
    stop("staged output changed before publication", call. = FALSE)
  }
  if (!file.link(staged_outputs[[index]], output_targets[[index]])) {
    stop("output publication failed", call. = FALSE)
  }
  published <- c(published, index)
  if (!identical(publication_file_identity(output_targets[[index]]), staged_identities[[index]])) {
    stop("published output identity or contents changed", call. = FALSE)
  }
}
for (index in seq_along(staged_outputs)) {
  if (!identical(publication_identity(stages[[index]]), stage_identities[[index]]) ||
      !identical(publication_file_identity(staged_outputs[[index]]), staged_identities[[index]]) ||
      !identical(publication_file_identity(output_targets[[index]]), staged_identities[[index]])) {
    stop("output changed before publication completed", call. = FALSE)
  }
}
complete <- TRUE

cat("limma_voom complete: ", nrow(v$E), " genes x ", ncol(v$E), " samples\n", sep = "")
}
main()
