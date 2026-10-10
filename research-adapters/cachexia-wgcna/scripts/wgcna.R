need <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

scalar_text <- function(value, name) {
  need(is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
       trimws(value) == value && !grepl("[\t\r\n]", value), paste("Invalid text", name))
  value
}

ids <- function(value, name, unique = TRUE) {
  need(is.list(value) && length(value) > 0L, paste("Invalid identities", name))
  result <- vapply(value, scalar_text, "", name = name)
  need(!unique || !anyDuplicated(result), paste("Duplicate identities", name))
  unname(result)
}

number <- function(value, lower, upper, name, integer = FALSE) {
  need(is.numeric(value) && length(value) == 1L && is.finite(value) && value >= lower && value <= upper &&
       (!integer || value == floor(value)), paste("Invalid numeric", name))
  if (integer) as.integer(value) else value
}

file_hash <- function(path) {
  need(file.exists(path) && !dir.exists(path), "File identity unavailable")
  digest::digest(path, algo = "sha256", file = TRUE)
}

write_audit <- function(audit, path) {
  if (audit$status == "TECHNICAL_PASS_NOT_SCIENTIFIC") {
    need(is.list(audit$output_sha256) && identical(names(audit$output_sha256), c("0", "1", "4", "5", "6", "7")),
         "Audit output identities must be a declared port map")
  }
  jsonlite::write_json(audit, path, auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null", null = "null")
}

lexical_tsv <- function(path) {
  lines <- readLines(path, warn = FALSE)
  need(length(lines) >= 2L && all(nzchar(lines)) && !any(grepl('["\r]', lines)), "Invalid lexical TSV")
  counts <- lengths(strsplit(paste0(lines, "\tEND"), "\t", fixed = TRUE)) - 1L
  need(all(counts == counts[1L]) && counts[1L] >= 2L, "Ragged lexical TSV")
  result <- utils::read.delim(path, colClasses = "character", check.names = FALSE, quote = "", comment.char = "",
                             na.strings = character(), strip.white = FALSE, fill = FALSE)
  need(nrow(result) == length(lines) - 1L && !anyDuplicated(names(result)) && all(nzchar(names(result))), "Invalid TSV header or rows")
  result
}

validate_request <- function(request) {
  keys <- c("schema_version", "official_source_sha256", "input0_sha256", "input1_sha256", "expected_genes", "expected_samples",
            "expected_donors", "expected_groups", "expected_tissue", "scale", "input_origin", "scope", "null_unit",
            "test_id", "family_id", "seed", "power_policy", "fixed_power", "powers", "rsquared_cut", "qc_policy", "cor_type",
            "network_type", "tom_type", "tom_denom", "max_p_outliers", "min_module_size", "deep_split", "merge_cut_height",
            "max_block_size", "block_assignments", "min_kme_to_stay", "min_core_kme", "min_core_kme_size", "reassign_threshold")
  need(is.list(request) && !anyDuplicated(names(request)) && setequal(names(request), keys) && length(request) == length(keys),
       "Missing, duplicate or unknown frozen key")
  need(identical(request$schema_version, 1L), "Unsupported contract schema")
  for (name in c("official_source_sha256", "input0_sha256", "input1_sha256", "expected_tissue", "scale", "input_origin",
                 "scope", "null_unit", "test_id", "family_id", "power_policy", "qc_policy", "cor_type", "network_type", "tom_type", "tom_denom")) {
    scalar_text(request[[name]], name)
  }
  for (name in c("official_source_sha256", "input0_sha256", "input1_sha256")) {
    need(grepl("^[a-f0-9]{64}$", request[[name]]), paste("Invalid SHA256", name))
  }
  need(request$official_source_sha256 == "4f61e117b82287f01b61bf936d5c5ea3814c9c4b0d0b90d5016dda77f1f955d6", "Official WGCNA source mismatch")
  need(request$scale %in% c("log2_normalized_donor_expression", "continuous_normalized_donor_expression"), "Unsupported explicit expression scale")
  need(request$input_origin %in% c("SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"), "Research qualification not granted")
  need(request$scope == "within_tissue_coexpression_not_causality" && request$null_unit == "independent_donor_profile_not_cell",
       "Unsupported inference scope or unit")
  genes <- ids(request$expected_genes, "genes")
  samples <- ids(request$expected_samples, "samples")
  donors <- ids(request$expected_donors, "donors")
  groups <- ids(request$expected_groups, "groups", unique = FALSE)
  need(length(samples) >= 20L && length(samples) <= 128L && length(genes) >= 10L && length(genes) <= 1500L &&
       length(donors) == length(samples) && length(groups) == length(samples), "Frozen donor or gene proof budget mismatch")
  number(request$seed, 0, .Machine$integer.max, "seed", TRUE)
  need(request$power_policy %in% c("frozen_fixed", "official_pickSoftThreshold") &&
       request$qc_policy %in% c("reject_any_exclusion", "official_goodSamplesGenes_record_exclusion"), "Unsupported frozen power or QC policy")
  need(is.list(request$powers) && length(request$powers) >= 1L && length(request$powers) <= 30L, "Invalid frozen power scan")
  powers <- vapply(request$powers, number, 0, lower = 1, upper = 30, name = "powers", integer = FALSE)
  need(!anyDuplicated(powers) && all(diff(powers) > 0), "Frozen powers must be unique and increasing")
  number(request$rsquared_cut, 0, 1, "rsquared_cut")
  if (request$power_policy == "frozen_fixed") number(request$fixed_power, 1, 30, "fixed_power") else
    need(is.null(request$fixed_power), "Official scan cannot accept fixed-power fallback")
  need(request$cor_type %in% c("pearson", "bicor") && request$network_type %in% c("unsigned", "signed", "signed hybrid") &&
       request$tom_type %in% c("unsigned", "signed", "signed Nowick") && request$tom_denom %in% c("min", "mean"), "Unsupported correlation or network profile")
  for (name in c("max_p_outliers", "merge_cut_height", "min_kme_to_stay", "min_core_kme", "reassign_threshold")) {
    number(request[[name]], 0, 1, name)
  }
  number(request$min_module_size, 2, length(genes), "min_module_size", TRUE)
  number(request$deep_split, 0, 4, "deep_split", TRUE)
  number(request$max_block_size, 20, 1500, "max_block_size", TRUE)
  number(request$min_core_kme_size, 1, length(genes), "min_core_kme_size", TRUE)
  if (!is.null(request$block_assignments)) {
    need(is.list(request$block_assignments) && length(request$block_assignments) == length(genes), "Frozen blocks do not cover gene axis")
    vapply(request$block_assignments, number, 0L, lower = 1, upper = 1500, name = "block_assignments", integer = TRUE)
  }
  invisible(request)
}

typed_tables <- function(tables, test_id) {
  pieces <- lapply(names(tables), function(name) {
    table <- as.data.frame(tables[[name]], stringsAsFactors = FALSE, check.names = FALSE)
    if (nrow(table) == 0L || ncol(table) == 0L) return(NULL)
    coordinates <- expand.grid(column = seq_len(ncol(table)), row = seq_len(nrow(table)))
    values <- lapply(seq_len(nrow(coordinates)), function(position) table[[coordinates$column[position]]][coordinates$row[position]])
    kind <- vapply(values, function(value) if (is.na(value)) "MISSING" else if (is.numeric(value))
      if (is.finite(value)) "NUMERIC" else "NONFINITE" else if (is.logical(value)) "BOOLEAN" else "TEXT", "")
    data.frame(test_id = test_id, table = name, row_position = coordinates$row - 1L, column_position = coordinates$column - 1L,
      row_label_json = vapply(rownames(table)[coordinates$row], function(value) as.character(jsonlite::toJSON(value, auto_unbox = TRUE)), ""),
      column_label_json = vapply(names(table)[coordinates$column], function(value) as.character(jsonlite::toJSON(value, auto_unbox = TRUE)), ""),
      value_kind = kind,
      numeric_value = vapply(seq_along(values), function(position) if (kind[position] == "NUMERIC") sprintf("%.17g", values[[position]]) else "", ""),
      text_json = vapply(seq_along(values), function(position) if (kind[position] %in% c("TEXT", "BOOLEAN"))
        as.character(jsonlite::toJSON(values[[position]], auto_unbox = TRUE)) else "null", ""),
      missing_kind = vapply(seq_along(values), function(position) if (kind[position] == "MISSING")
        if (is.nan(values[[position]])) "R_NAN" else typeof(values[[position]]) else if (kind[position] == "NONFINITE")
          if (values[[position]] > 0) "POSINF" else "NEGINF" else "", ""), stringsAsFactors = FALSE)
  })
  result <- do.call(rbind, pieces)
  need(!is.null(result) && nrow(result) > 0L, "Empty typed official projection")
  result$source_position <- seq_len(nrow(result)) - 1L
  result
}

read_expression <- function(inputs, request) {
  raw <- lexical_tsv(inputs[1L])
  metadata <- lexical_tsv(inputs[2L])
  genes <- ids(request$expected_genes, "genes")
  samples <- ids(request$expected_samples, "samples")
  need(identical(names(raw), c("gene_id", samples)) && identical(raw$gene_id, genes), "Frozen expression axes mismatch")
  need(identical(names(metadata), c("sample_id", "donor_id", "tissue", "group")) && identical(metadata$sample_id, samples) &&
       identical(metadata$donor_id, ids(request$expected_donors, "donors")) &&
       identical(metadata$group, ids(request$expected_groups, "groups", unique = FALSE)) &&
       identical(unique(metadata$tissue), request$expected_tissue), "Frozen donor metadata mismatch")
  tokens <- as.matrix(raw[, -1L, drop = FALSE])
  pattern <- "^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
  need(all(tokens == "NA" | grepl(pattern, tokens, perl = TRUE)), "Invalid expression numeric token")
  values <- suppressWarnings(matrix(as.numeric(tokens), nrow = nrow(tokens), ncol = ncol(tokens)))
  need(all(is.na(values) | is.finite(values)), "Nonfinite expression values")
  dimnames(values) <- list(genes, samples)
  list(raw = raw, metadata = metadata, data = t(values))
}

run_wgcna <- function(outputs, audit) {
  suppressPackageStartupMessages(library(WGCNA))
  need(identical(utils::packageDescription("WGCNA", fields = "Version"), "1.74") &&
       identical(as.character(getRversion()), "4.5.3"), "Official runtime version differs")
  plan <- jsonlite::fromJSON("/opt/cachexia-wgcna-source-plan.json", simplifyVector = FALSE)
  for (entry in plan$archives) {
    need(file_hash(file.path("/opt/cachexia-wgcna-sources", entry$filename)) == entry$sha256 &&
         identical(utils::packageDescription(entry$package, fields = "Version"), entry$version), "Frozen official dependency differs")
  }
  inputs <- vapply(0:2, function(position) Sys.getenv(paste0("AUTONOMICS_INPUT", position)), "")
  need(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "3" && all(file.exists(inputs)), "Three declared File inputs required")
  request <- jsonlite::fromJSON(inputs[3L], simplifyVector = FALSE)
  audit$test_id <- request$test_id
  audit$family_id <- request$family_id
  validate_request(request)
  initial_hashes <- vapply(inputs, file_hash, "")
  need(identical(unname(initial_hashes[1:2]), c(request$input0_sha256, request$input1_sha256)), "Input byte identity mismatch")
  parsed <- read_expression(inputs, request)
  datExpr <- parsed$data
  WGCNA::disableWGCNAThreads()
  set.seed(request$seed)
  rng_before <- .Random.seed
  collected <- character()
  state <- withCallingHandlers({
    quality <- WGCNA::goodSamplesGenes(datExpr, verbose = 0)
    if (request$qc_policy == "reject_any_exclusion") need(quality$allOK, "Frozen QC forbids sample or gene exclusion")
    filtered <- datExpr[quality$goodSamples, quality$goodGenes, drop = FALSE]
    need(nrow(filtered) >= 20L && ncol(filtered) >= 10L, "Official QC leaves insufficient technical proof universe")
    cor_options <- list(use = "p")
    if (request$cor_type == "bicor") cor_options <- c(cor_options, list(maxPOutliers = request$max_p_outliers, pearsonFallback = "individual"))
    cor_function <- if (request$cor_type == "bicor") WGCNA::bicor else WGCNA::cor
    scan <- WGCNA::pickSoftThreshold(filtered, RsquaredCut = request$rsquared_cut, powerVector = unlist(request$powers, use.names = FALSE),
                                    networkType = request$network_type, corFnc = cor_function, corOptions = cor_options, verbose = 0)
    power <- if (request$power_policy == "frozen_fixed") request$fixed_power else scan$powerEstimate
    audit$official_power_estimate <- scan$powerEstimate
    if (length(power) != 1L || !is.finite(power)) {
      saveRDS(list(request = request, scan = scan, quality = quality, input_sha256 = initial_hashes,
                   rng_before = rng_before, rng_after = .Random.seed, warnings = collected, G0_granted = FALSE),
              file.path(dirname(outputs[3L]), "nonestimable-power-scan.rds"))
    }
    need(length(power) == 1L && is.finite(power), "Official powerEstimate not estimable; no fallback permitted")
    blocks <- if (is.null(request$block_assignments)) NULL else unlist(request$block_assignments, use.names = FALSE)
    net <- WGCNA::blockwiseModules(datExpr, checkMissingData = TRUE, blocks = blocks, maxBlockSize = request$max_block_size,
      randomSeed = request$seed, corType = request$cor_type, maxPOutliers = request$max_p_outliers, quickCor = 0,
      pearsonFallback = "individual", cosineCorrelation = FALSE, power = power, networkType = request$network_type,
      replaceMissingAdjacencies = FALSE, TOMType = request$tom_type, TOMDenom = request$tom_denom,
      suppressTOMForZeroAdjacencies = FALSE, suppressNegativeTOM = FALSE, saveTOMs = TRUE, saveTOMFileBase = "official-TOM",
      deepSplit = request$deep_split, detectCutHeight = 0.995, minModuleSize = request$min_module_size,
      pamStage = TRUE, pamRespectsDendro = FALSE, reassignThreshold = request$reassign_threshold, minCoreKME = request$min_core_kme,
      minCoreKMESize = request$min_core_kme_size, minKMEtoStay = request$min_kme_to_stay, mergeCutHeight = request$merge_cut_height,
      impute = TRUE, trapErrors = FALSE, numericLabels = TRUE, nThreads = 1, useInternalMatrixAlgebra = FALSE,
      useCorOptionsThroughout = TRUE, verbose = 0)
    need(identical(net$goodSamples, quality$goodSamples) && identical(net$goodGenes, quality$goodGenes), "Official QC masks disagree")
    need(length(net$TOMFiles) == length(net$blockGenes) && all(file.exists(net$TOMFiles)) && net$MEsOK, "Official TOM or eigengenes missing")
    toms <- lapply(net$TOMFiles, function(path) {
      environment <- new.env(parent = emptyenv())
      need(identical(load(path, envir = environment), "TOM"), "Unexpected official TOM object")
      environment$TOM
    })
    adjacency <- WGCNA::adjacency(filtered, type = request$network_type, power = power, corFnc = cor_function, corOptions = cor_options)
    kme_options <- if (request$cor_type == "bicor") paste0("use = 'p', maxPOutliers = ", sprintf("%.17g", request$max_p_outliers),
                                                                        ", pearsonFallback = 'individual'") else "use = 'p'"
    kme <- WGCNA::signedKME(filtered, net$MEs[quality$goodSamples, , drop = FALSE], corFnc = if (request$cor_type == "bicor") "bicor" else "cor",
                           corOptions = kme_options)
    list(quality = quality, scan = scan, selected_power = power, net = net, toms = toms, adjacency = adjacency, kme = kme,
         color_names = WGCNA::labels2colors(net$colors), filtered = filtered)
  }, warning = function(warning) {
    collected <<- c(collected, conditionMessage(warning))
    invokeRestart("muffleWarning")
  })
  gene_block <- rep(NA_integer_, ncol(datExpr))
  for (position in seq_along(state$net$blockGenes)) gene_block[state$net$blockGenes[[position]]] <- position
  genes <- data.frame(gene_id = colnames(datExpr), source_position = seq_len(ncol(datExpr)) - 1L,
                      official_good_gene = state$quality$goodGenes, official_block = gene_block,
                      official_module = unname(state$net$colors), official_color = state$color_names,
                      status = ifelse(!state$quality$goodGenes, "EXCLUDED_OFFICIAL_QC", ifelse(state$net$colors == 0L, "OFFICIAL_GREY_UNASSIGNED", "ASSIGNED_OFFICIAL_MODULE")))
  samples <- cbind(parsed$metadata, source_position = seq_len(nrow(datExpr)) - 1L, official_good_sample = state$quality$goodSamples,
                   status = ifelse(state$quality$goodSamples, "USED_OFFICIAL", "EXCLUDED_OFFICIAL_QC"))
  products <- data.frame(block_position = seq_along(state$net$blockGenes) - 1L,
    genes = lengths(state$net$blockGenes), filename = basename(state$net$TOMFiles), bytes = file.info(state$net$TOMFiles)$size,
    sha256 = vapply(state$net$TOMFiles, file_hash, ""))
  need(all(vapply(seq_along(state$toms), function(position) {
    is.numeric(state$toms[[position]]) && length(state$toms[[position]]) == products$genes[position] * (products$genes[position] - 1L)/2
  }, logical(1))), "Official TOM object does not match actual block gene axis")
  module_sizes <- as.data.frame(table(state$net$colors), stringsAsFactors = FALSE)
  names(module_sizes) <- c("official_module", "module_size")
  statistics <- data.frame(selected_power = state$selected_power, actual_blocks = length(state$net$blockGenes),
    actual_TOM_files = length(state$net$TOMFiles), adjacency_rows = nrow(state$adjacency), adjacency_columns = ncol(state$adjacency),
    adjacency_offdiagonal_mean = mean(state$adjacency[row(state$adjacency) != col(state$adjacency)]))
  projection <- list(soft_threshold = state$scan$fitIndices, statistics = statistics, eigengenes = state$net$MEs,
                     membership = state$kme, module_sizes = module_sizes, TOM_products = products)
  payload <- list(parsed = parsed, request = request, method = state, projection = projection,
                  genes = genes, samples = samples, products = products, rng_before = rng_before, rng_after = .Random.seed, warnings = collected)
  saveRDS(payload, outputs[2L], compress = TRUE)
  write_tsv <- function(table, path) write.table(table, path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE, na = "NA")
  values <- typed_tables(projection, request$test_id)
  write_tsv(values, outputs[1L])
  write_tsv(genes, outputs[5L])
  write_tsv(samples, outputs[6L])
  archive <- normalizePath(outputs[7L], mustWork = FALSE)
  utils::tar(archive, files = state$net$TOMFiles, compression = "gzip", tar = "internal")
  family <- data.frame(family_id = request$family_id, test_id = request$test_id, status = "ESTIMATED_OFFICIAL_TECHNICAL_ONLY", G0_granted = FALSE)
  write_tsv(family, outputs[8L])
  need(identical(initial_hashes, vapply(inputs, file_hash, "")), "Source inputs changed during execution")
  need(identical(readRDS(outputs[2L]), payload), "Complete official state failed readback")
  need(setequal(utils::untar(archive, list = TRUE), state$net$TOMFiles), "Actual TOM archive incomplete")
  audit$status <- "TECHNICAL_PASS_NOT_SCIENTIFIC"
  audit$input_sha256 <- initial_hashes
  audit$output_sha256 <- setNames(as.list(vapply(outputs[c(1L, 2L, 5L, 6L, 7L, 8L)], file_hash, "")), c("0", "1", "4", "5", "6", "7"))
  audit$request <- request
  audit$actual_blocks <- length(state$net$blockGenes)
  audit$complete_original_genes <- nrow(genes)
  audit$complete_original_donors <- nrow(samples)
  audit$warnings <- as.list(collected)
  message("PASS official WGCNA technical profile; no scientific release or G0")
  audit
}

if (nzchar(Sys.getenv("AUTONOMICS_INPUT_COUNT"))) {
  suppressPackageStartupMessages({library(jsonlite); library(digest)})
  outputs <- vapply(0:7, function(position) Sys.getenv(paste0("AUTONOMICS_OUTPUT", position)), "")
  need(all(nzchar(outputs)) && !anyDuplicated(outputs) && !any(file.exists(outputs)), "Eight distinct non-overwritten declared ports required")
  log_connection <- file(outputs[4L], "wt")
  sink(log_connection)
  sink(log_connection, type = "message")
  audit <- list(status = "RUNNING", G0_granted = FALSE, scientific_release_granted = FALSE, resident_deployment_granted = FALSE)
  audit <- tryCatch({
    request_path <- Sys.getenv("AUTONOMICS_INPUT2")
    if (nzchar(request_path) && file.exists(request_path)) {
      preflight <- jsonlite::fromJSON(request_path, simplifyVector = FALSE)
      for (key in c("test_id", "family_id")) {
        value <- preflight[[key]]
        if (is.character(value) && length(value) == 1L && !is.na(value)) audit[[key]] <- value
      }
      audit$request_sha256 <- file_hash(request_path)
    }
    run_wgcna(outputs, audit)
  }, error = function(error) {
    unlink(outputs[c(1L, 2L, 5L, 6L, 7L, 8L)])
    audit$status <- "BLOCKED"
    audit$error <- conditionMessage(error)
    valid_id <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
      trimws(value) == value && !grepl("[\t\r\n]", value)
    if (valid_id(audit$test_id) && valid_id(audit$family_id)) {
      blocked_family <- file.path(dirname(outputs[3L]), "blocked-family.tsv")
      write.table(data.frame(family_id = audit$family_id, test_id = audit$test_id, status = "BLOCKED_NOT_ESTIMATED", G0_granted = FALSE),
                  blocked_family, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
      audit$blocked_family_diagnostic <- list(filename = basename(blocked_family), sha256 = file_hash(blocked_family))
    }
    diagnostic <- file.path(dirname(outputs[3L]), "nonestimable-power-scan.rds")
    if (file.exists(diagnostic)) {
      audit$nonestimable_official_power_diagnostic <- list(filename = basename(diagnostic), sha256 = file_hash(diagnostic))
    }
    message("BLOCKED ", audit$error)
    audit
  })
  write_audit(audit, outputs[3L])
  sink(type = "message")
  sink()
  close(log_connection)
  quit(save = "no", status = if (audit$status == "TECHNICAL_PASS_NOT_SCIENTIFIC") 0L else 1L)
}
