#!/usr/bin/env Rscript
options(stringsAsFactors = FALSE, digits = 17)

required_env <- function(name) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) stop(paste("missing required environment variable:", name), call. = FALSE)
  value
}

scalar_number <- function(name, default, lower, upper, integer = FALSE, exclusive = FALSE) {
  token <- Sys.getenv(name, default)
  pattern <- "^[+]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?$"
  value <- suppressWarnings(as.numeric(token))
  if (!grepl(pattern, token, perl = TRUE) || !is.finite(value) ||
      value < lower || value > upper || (exclusive && (value == lower || value == upper)) ||
      (integer && (value != floor(value) || !grepl("^[+]?[0-9]+$", token)))) {
    stop(paste("invalid scalar parameter:", name), call. = FALSE)
  }
  if (integer) as.integer(value) else value
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
    if (any(block == as.raw(0))) stop("input must not contain embedded NUL bytes", call. = FALSE)
  }
  lines <- sub("\r$", "", readLines(filename, warn = FALSE))
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
  if (any(!nzchar(header)) || anyDuplicated(header)) stop("input headers must be nonempty and unique", call. = FALSE)
  if (any(lengths(fields) != length(header))) stop("input rows must match the header width", call. = FALSE)
  frame <- as.data.frame(do.call(rbind, fields[-1]), check.names = FALSE, stringsAsFactors = FALSE)
  colnames(frame) <- header
  frame
}

summary_values <- function(values) {
  if (any(!is.finite(values))) stop("official network contains nonfinite similarities", call. = FALSE)
  list(edges = length(values), nonzero_edges = sum(values != 0),
       mean = if (length(values)) mean(values) else NA_real_,
       median = if (length(values)) median(values) else NA_real_,
       minimum = if (length(values)) min(values) else NA_real_,
       maximum = if (length(values)) max(values) else NA_real_)
}

main <- function() {
  expr_path <- required_env("AUTONOMICS_INPUT0")
  metadata_path <- Sys.getenv("AUTONOMICS_INPUT1")
  outputs <- vapply(0:5, function(port) required_env(paste0("AUTONOMICS_OUTPUT", port)), character(1))
  output_links <- Sys.readlink(outputs)
  if (any(file.exists(outputs)) || any(!is.na(output_links) & nzchar(output_links))) {
    stop("existing outputs must not be overwritten", call. = FALSE)
  }
  identities <- vapply(outputs, function(filename) {
    if (!dir.exists(dirname(filename))) stop("output parent must be an existing directory", call. = FALSE)
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename))
  }, character(1))
  if (anyDuplicated(identities)) stop("output paths must be distinct", call. = FALSE)
  if (any(file.access(dirname(outputs), 2L) != 0L)) stop("output parents must be writable", call. = FALSE)

  network_type <- Sys.getenv("AUTONOMICS_WGCNA_NETWORK_TYPE", "signed")
  cor_type <- Sys.getenv("AUTONOMICS_WGCNA_COR", "pearson")
  if (!network_type %in% c("signed", "unsigned")) stop("network_type must be signed or unsigned", call. = FALSE)
  if (!cor_type %in% c("pearson", "bicor")) stop("cor must be pearson or bicor", call. = FALSE)
  min_module_size <- scalar_number("AUTONOMICS_WGCNA_MIN_MODULE_SIZE", "30", 5, .Machine$integer.max, TRUE)
  deep_split <- scalar_number("AUTONOMICS_WGCNA_DEEP_SPLIT", "2", 0, 4, TRUE)
  merge_threshold <- scalar_number("AUTONOMICS_WGCNA_MERGE_THRESHOLD", "0.25", 0, 1, exclusive = TRUE)
  max_block_size <- scalar_number("AUTONOMICS_WGCNA_MAX_BLOCK_SIZE", "5000", 500, .Machine$integer.max, TRUE)
  threads <- scalar_number("AUTONOMICS_WGCNA_THREADS", "1", 1, .Machine$integer.max, TRUE)
  fixed_power <- scalar_number("AUTONOMICS_WGCNA_POWER", "0", 0, 30)
  power_cutoff <- scalar_number("AUTONOMICS_WGCNA_POWER_CUTOFF", "0.85", 0, 1, exclusive = TRUE)
  max_p_outliers <- scalar_number("AUTONOMICS_WGCNA_MAX_P_OUTLIERS", "1", 0, 1)
  seed <- scalar_number("AUTONOMICS_WGCNA_SEED", "54321", 0, .Machine$integer.max, TRUE)

  raw <- read_literal_tsv(expr_path)
  if (ncol(raw) < 2L || names(raw)[[1]] != "gene_id") {
    stop("expression matrix must start with gene_id followed by sample columns", call. = FALSE)
  }
  gene_ids <- raw[[1]]
  sample_ids <- names(raw)[-1]
  if (any(!nzchar(gene_ids)) || anyDuplicated(gene_ids)) stop("gene_id must be nonempty and unique", call. = FALSE)
  tokens <- as.matrix(raw[, -1, drop = FALSE])
  pattern <- "^[+-]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?$"
  if (any(!grepl(pattern, tokens, perl = TRUE))) stop("expression values must be finite numeric tokens", call. = FALSE)
  expression <- matrix(suppressWarnings(as.numeric(tokens)), nrow = nrow(raw))
  if (any(!is.finite(expression))) stop("expression values must be finite", call. = FALSE)
  dimnames(expression) <- list(gene_ids, sample_ids)
  datExpr <- t(expression)

  metadata <- NULL
  if (nzchar(metadata_path)) {
    metadata <- read_literal_tsv(metadata_path)
    if (names(metadata)[[1]] != "sample_id" || any(!nzchar(metadata[[1]])) ||
        anyDuplicated(metadata[[1]]) || !setequal(metadata[[1]], sample_ids)) {
      stop("metadata must start with unique sample_id covering exactly the expression samples", call. = FALSE)
    }
    metadata <- metadata[match(sample_ids, metadata[[1]]), , drop = FALSE]
  }

  suppressPackageStartupMessages(library(WGCNA))
  if (threads > 1L) WGCNA::enableWGCNAThreads(nThreads = threads) else WGCNA::disableWGCNAThreads()
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  set.seed(seed)
  rng_before <- .Random.seed
  stage <- tempfile(pattern = "wgcna-publication-")
  if (!dir.create(stage, mode = "0700")) stop("cannot create private staging", call. = FALSE)
  staged_outputs <- file.path(stage, paste0("port", 0:5))
  published <- character()
  complete <- FALSE
  on.exit({
    if (!complete && length(published)) unlink(published)
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  state <- new.env(parent = emptyenv())
  state$warnings <- character()
  state$analysis <- list(network_type = network_type, cor = cor_type, min_module_size = min_module_size,
    deep_split = deep_split, merge_threshold = merge_threshold, max_block_size = max_block_size,
    threads = threads, requested_power = fixed_power, power_cutoff = power_cutoff,
    max_p_outliers = max_p_outliers, seed = seed)
  tryCatch(withCallingHandlers({
    quality <- WGCNA::goodSamplesGenes(datExpr, verbose = 0)
    state$quality <- quality
    filtered <- datExpr[quality$goodSamples, quality$goodGenes, drop = FALSE]
    cor_function <- if (cor_type == "bicor") "bicor" else "cor"
    cor_options <- list(use = "p")
    cor_options_text <- "use = 'p'"
    if (cor_type == "bicor") {
      cor_options <- c(cor_options, list(maxPOutliers = max_p_outliers, pearsonFallback = "individual"))
      cor_options_text <- paste0("use = 'p', maxPOutliers = ", sprintf("%.17g", max_p_outliers),
                                ", pearsonFallback = 'individual'")
    }
    powers <- c(1:10, seq(12, 30, by = 2))
    scan <- WGCNA::pickSoftThreshold(filtered, powerVector = powers, RsquaredCut = power_cutoff,
      networkType = network_type, corFnc = cor_function, corOptions = cor_options, verbose = 0)
    state$soft_threshold <- scan
    chosen_power <- if (fixed_power > 0) fixed_power else scan$powerEstimate
    if (length(chosen_power) != 1L || !is.finite(chosen_power)) {
      stop("official powerEstimate is unavailable; no automatic fallback is permitted", call. = FALSE)
    }
    state$analysis$chosen_power <- chosen_power
    state$analysis$power_source <- if (fixed_power > 0) "EXPLICIT_FIXED_POWER" else "OFFICIAL_PICK_SOFT_THRESHOLD"
    fit <- scan$fitIndices
    if (is.null(fit) || !nrow(fit)) stop("official power scan returned no fit indices", call. = FALSE)
    soft <- data.frame(power = fit$Power, scale_free_R2 = fit$SFT.R.sq, slope = fit$slope,
      truncated_R2 = fit$truncated.R.sq, mean_connectivity = fit$mean.k,
      median_connectivity = fit$median.k, max_connectivity = fit$max.k,
      chosen_power = chosen_power, network_type = network_type, cor = cor_type)
    write.table(soft, staged_outputs[[1]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    network <- WGCNA::blockwiseModules(datExpr, power = chosen_power, networkType = network_type,
      corType = cor_type, maxPOutliers = max_p_outliers, pearsonFallback = "individual",
      TOMType = network_type, TOMDenom = "min", deepSplit = deep_split, minModuleSize = min_module_size,
      mergeCutHeight = merge_threshold, maxBlockSize = max_block_size, pamRespectsDendro = FALSE,
      numericLabels = TRUE, saveTOMs = TRUE, saveTOMFileBase = file.path(stage, "actual-TOM"),
      randomSeed = seed, nThreads = threads, verbose = 0, checkMissingData = TRUE)
    if (!identical(network$goodGenes, quality$goodGenes) || !identical(network$goodSamples, quality$goodSamples) ||
        length(network$colors) != length(gene_ids) || !length(network$blockGenes) ||
        length(network$TOMFiles) != length(network$blockGenes) || !isTRUE(network$MEsOK)) {
      stop("official network axes, QC or TOM outputs are inconsistent", call. = FALSE)
    }
    state$network <- network[setdiff(names(network), "TOMFiles")]
    adjacency_rows <- list()
    tom_rows <- list()
    block_identities <- list()
    for (block_index in seq_along(network$blockGenes)) {
      positions <- network$blockGenes[[block_index]]
      block_expr <- datExpr[quality$goodSamples, positions, drop = FALSE]
      adjacency <- WGCNA::adjacency(block_expr, type = network_type, power = chosen_power,
        corFnc = cor_function, corOptions = cor_options)
      adjacent_summary <- summary_values(adjacency[lower.tri(adjacency)])
      adjacency_rows[[block_index]] <- data.frame(block = block_index, genes = length(positions),
        as.data.frame(adjacent_summary), diagonal_min = min(diag(adjacency)),
        diagonal_max = max(diag(adjacency)), mean_connectivity = mean(rowSums(adjacency) - diag(adjacency)),
        values_sha256 = digest::digest(as.numeric(adjacency), algo = "sha256"),
        network_type = network_type, cor = cor_type, power = chosen_power)
      tom_environment <- new.env(parent = emptyenv())
      objects <- load(network$TOMFiles[[block_index]], envir = tom_environment)
      if (!identical(objects, "TOM") || !inherits(tom_environment$TOM, "dist") ||
          attr(tom_environment$TOM, "Size") != length(positions)) {
        stop("actual official TOM is absent or has the wrong block dimension", call. = FALSE)
      }
      tom_values <- as.numeric(tom_environment$TOM)
      if (length(tom_values) != length(positions) * (length(positions) - 1) / 2) {
        stop("actual official TOM has an inconsistent edge count", call. = FALSE)
      }
      tom_rows[[block_index]] <- data.frame(block = block_index, genes = length(positions),
        as.data.frame(summary_values(tom_values)), serialized_bytes = file.info(network$TOMFiles[[block_index]])$size,
        values_sha256 = digest::digest(tom_values, algo = "sha256"),
        network_type = network_type, cor = cor_type, power = chosen_power)
      block_identities[[block_index]] <- list(block = block_index, original_gene_positions = positions,
                                             gene_ids = gene_ids[positions])
    }
    write.table(do.call(rbind, adjacency_rows), staged_outputs[[2]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    write.table(do.call(rbind, tom_rows), staged_outputs[[3]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    eigengenes <- network$MEs
    if (is.null(rownames(eigengenes)) || !identical(rownames(eigengenes), sample_ids)) {
      stop("official eigengene sample axis differs from the original input", call. = FALSE)
    }
    kme <- WGCNA::signedKME(filtered, eigengenes[quality$goodSamples, , drop = FALSE],
      outputColumnName = "kME", corFnc = cor_function, corOptions = cor_options_text)
    all_kme <- matrix(NA_real_, nrow = length(gene_ids), ncol = ncol(kme),
                      dimnames = list(gene_ids, names(kme)))
    all_kme[quality$goodGenes, ] <- as.matrix(kme)
    labels <- network$colors
    assignments <- data.frame(gene_id = gene_ids, module_label = labels,
      module_color = WGCNA::labels2colors(labels),
      gene_status = ifelse(!quality$goodGenes, "OFFICIAL_QC_EXCLUDED",
                           ifelse(labels == 0, "UNASSIGNED_GREY", "ASSIGNED_MODULE")),
      all_kme, check.names = FALSE)
    write.table(assignments, staged_outputs[[4]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    eigengene_frame <- data.frame(sample_id = sample_ids, eigengenes, check.names = FALSE)
    if (!is.null(metadata)) {
      columns <- setdiff(names(metadata), "sample_id")
      if (any(columns %in% names(eigengene_frame))) stop("metadata columns collide with eigengenes", call. = FALSE)
      eigengene_frame <- cbind(eigengene_frame, metadata[, columns, drop = FALSE])
    }
    write.table(eigengene_frame, staged_outputs[[5]], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
    packages <- c("WGCNA", "dynamicTreeCut", "fastcluster", "impute", "preprocessCore")
    report <- list(schema_version = "2.0", node = "wgcna", technical_execution = "COMPLETE",
      scientific_release = "NOT_GRANTED", analysis = state$analysis,
      engine = list(versions = as.list(setNames(vapply(packages, function(package) as.character(packageVersion(package)),
                                                   character(1)), packages)), r_version = as.character(getRversion())),
      method = list(powers = powers, checkMissingData = TRUE, pamRespectsDendro = FALSE, numericLabels = TRUE,
                    TOMType = network_type, TOMDenom = "min", pearsonFallback = "individual",
                    blockwiseOtherArguments = "official WGCNA 1.74 defaults"),
      rng = list(kind = RNGkind(), before = rng_before, after = .Random.seed), warnings = state$warnings,
      inputs = list(expression_matrix = list(path = basename(expr_path), md5 = unname(tools::md5sum(expr_path))),
        sample_metadata = if (nzchar(metadata_path)) list(path = basename(metadata_path),
          md5 = unname(tools::md5sum(metadata_path)), contract = "LEGACY_DIRECT_SCRIPT_ONLY_NOT_A_DECLARED_DAG_PORT") else NULL),
      qc = list(all_original_gene_ids = gene_ids, all_original_sample_ids = sample_ids,
        goodGenes = quality$goodGenes, goodSamples = quality$goodSamples,
        excluded_gene_ids = gene_ids[!quality$goodGenes], excluded_sample_ids = sample_ids[!quality$goodSamples]),
      blocks = block_identities, network_semantics_sha256 = digest::digest(state$network, algo = "sha256"),
      dimensions = list(genes = length(gene_ids), samples = length(sample_ids), good_genes = sum(quality$goodGenes),
        good_samples = sum(quality$goodSamples), blocks = length(network$blockGenes),
        assigned_modules = length(setdiff(unique(labels), 0L)), grey_genes = sum(labels == 0)),
      output_semantics = list(adjacency = "WITHIN_ACTUAL_BLOCK_OFFDIAGONAL_ADJACENCY_NOT_MODULE_SIZE",
        TOM = "ACTUAL_TOM_USED_BY_OFFICIAL_BLOCKWISE_CLUSTERING_OFFDIAGONAL_DIST",
        scope = "COEXPRESSION_NOT_CAUSALITY_OR_TRAIT_ASSOCIATION", input_scale = "NOT_INFERRED_FROM_NUMBERS",
        publication = "ORDINARY_FAILURE_ROLLBACK_NOT_MULTI_FILE_ATOMIC_OR_CONCURRENT_WRITER_CERTIFICATION"),
      outputs = lapply(seq_len(5), function(index) list(port = index - 1L,
        path = basename(outputs[[index]]), md5 = unname(tools::md5sum(staged_outputs[[index]])))))
    jsonlite::write_json(report, staged_outputs[[6]], auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null", null = "null")
    for (index in seq_along(outputs)) {
      link <- Sys.readlink(outputs[[index]])
      if (file.exists(outputs[[index]]) || (!is.na(link) && nzchar(link)) ||
          !file.copy(staged_outputs[[index]], outputs[[index]], overwrite = FALSE)) {
        stop("cannot publish without overwriting an existing output", call. = FALSE)
      }
      published <- c(published, outputs[[index]])
    }
    complete <- TRUE
  }, warning = function(condition) {
    state$warnings <- c(state$warnings, conditionMessage(condition))
  }), error = function(condition) {
    diagnostic <- tempfile("wgcna-failure-", tmpdir = dirname(outputs[[6]]), fileext = ".rds")
    saveRDS(list(error = conditionMessage(condition), state = as.list(state), scientific_release = "NOT_GRANTED"),
            diagnostic, version = 3)
    message("failed official computation retained in ", diagnostic)
    stop(condition)
  })
  cat("wgcna complete; technical execution is not scientific release\n")
}

main()
