need <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

h5_exists <- function(path, key) {
  handle <- rhdf5::H5Fopen(path, flags = "H5F_ACC_RDONLY")
  on.exit(rhdf5::H5Fclose(handle))
  rhdf5::H5Lexists(handle, key)
}

h5_axis <- function(path, axis) {
  key <- rhdf5::h5readAttributes(path, axis)[["_index"]]
  need(is.character(key) && length(key) == 1L && !is.na(key) && nzchar(key) && !grepl("/", key), "Invalid H5AD index attribute")
  need(h5_exists(path, paste0(axis, "/", key)), "Missing H5AD index")
  values <- rhdf5::h5read(path, paste0(axis, "/", key))
  need(is.character(values) && !anyNA(values) && all(nzchar(values)) && !anyDuplicated(values) &&
       !any(grepl("[\t\r\n]", values)), "Invalid or duplicate H5AD axis")
  as.vector(values, mode = "character")
}

h5_labels <- function(path, key, count) {
  need(is.character(key) && length(key) == 1L && !is.na(key) && nzchar(key) && !grepl("/", key), "Invalid metadata column")
  key <- paste0("obs/", key)
  need(h5_exists(path, key), "Missing metadata column")
  encoding <- rhdf5::h5readAttributes(path, key)[["encoding-type"]]
  if (identical(encoding, "categorical")) {
    categories <- rhdf5::h5read(path, paste0(key, "/categories"))
    codes <- rhdf5::h5read(path, paste0(key, "/codes"))
    need(is.character(categories) && !anyNA(categories) && all(nzchar(categories)) && !anyDuplicated(categories), "Invalid metadata categories")
    need(is.numeric(codes) && length(codes) == count && all(is.finite(codes)) && all(codes == floor(codes)) &&
         all(codes >= 0 & codes < length(categories)), "Missing or invalid metadata codes")
    values <- categories[codes + 1L]
  } else if (identical(encoding, "nullable-string-array")) {
    values <- rhdf5::h5read(path, paste0(key, "/values"))
    mask <- rhdf5::h5read(path, paste0(key, "/mask"))
    need(is.logical(mask) && length(mask) == count && !anyNA(mask) && !any(mask), "Missing or invalid nullable metadata")
  } else {
    need(identical(encoding, "string-array"), "Unsupported metadata encoding")
    values <- rhdf5::h5read(path, key)
  }
  need(is.character(values) && length(values) == count && !anyNA(values) && all(nzchar(values)) &&
       !any(grepl("[\t\r\n]", values)), "Missing or invalid metadata labels")
  as.vector(values, mode = "character")
}

h5_matrix <- function(path, cells, genes) {
  attributes <- rhdf5::h5readAttributes(path, "X")
  encoding <- attributes[["encoding-type"]]
  need(length(cells) * length(genes) <= 2000000, "Small-proof matrix budget exceeded")
  if (encoding %in% c("csr_matrix", "csc_matrix")) {
    need(identical(as.numeric(attributes$shape), c(as.numeric(length(cells)), as.numeric(length(genes)))), "Sparse shape mismatch")
    values <- as.numeric(rhdf5::h5read(path, "X/data"))
    indices <- as.numeric(rhdf5::h5read(path, "X/indices"))
    pointers <- as.numeric(rhdf5::h5read(path, "X/indptr"))
    major <- if (encoding == "csr_matrix") length(cells) else length(genes)
    minor <- if (encoding == "csr_matrix") length(genes) else length(cells)
    need(length(pointers) == major + 1L && all(is.finite(pointers)) && all(pointers == floor(pointers)) &&
         pointers[1L] == 0 && all(diff(pointers) >= 0) && tail(pointers, 1L) == length(values), "Invalid sparse pointers")
    need(length(indices) == length(values) && all(is.finite(indices)) && all(indices == floor(indices)) &&
         all(indices >= 0 & indices < minor), "Invalid sparse indices")
    need(all(is.finite(values)) && all(values >= 0), "Invalid expression values")
    coordinates <- rep(seq_len(major), diff(pointers))
    matrix <- if (encoding == "csr_matrix")
      Matrix::sparseMatrix(i = indices + 1L, j = coordinates, x = values, dims = c(length(genes), length(cells))) else
      Matrix::sparseMatrix(i = coordinates, j = indices + 1L, x = values, dims = c(length(genes), length(cells)))
  } else {
    need(identical(encoding, "array"), "Unsupported H5AD expression encoding")
    values <- rhdf5::h5read(path, "X")
    need(is.numeric(values) && identical(dim(values), c(length(genes), length(cells))), "Dense standard H5AD shape mismatch")
    need(all(is.finite(values)) && all(values >= 0), "Invalid expression values")
    matrix <- Matrix::Matrix(values, sparse = TRUE)
  }
  matrix <- Matrix::drop0(methods::as(matrix, "dgCMatrix"))
  dimnames(matrix) <- list(genes, cells)
  need(all(Matrix::colSums(matrix) > 0), "Zero-library cell")
  matrix
}

read_standard_h5ad <- function(path, group_column, donor_column = NULL, tissue_column = NULL) {
  cells <- h5_axis(path, "obs")
  genes <- h5_axis(path, "var")
  result <- list(exprs = h5_matrix(path, cells, genes), cluster = h5_labels(path, group_column, length(cells)))
  names(result$cluster) <- cells
  if (!is.null(donor_column)) result$donor <- h5_labels(path, donor_column, length(cells))
  if (!is.null(tissue_column)) result$tissue <- h5_labels(path, tissue_column, length(cells))
  result
}

file_hash <- function(path) {
  result <- system2("sha256sum", shQuote(path), stdout = TRUE, stderr = TRUE)
  need(is.null(attr(result, "status")), "SHA256 read failed")
  substr(result[[1L]], 1L, 64L)
}

frozen_ids <- function(value, label) {
  need(is.list(value) && length(value) > 0L && all(vapply(value, function(item)
    is.character(item) && length(item) == 1L && !is.na(item) && nzchar(item) &&
      trimws(item) == item && !grepl("[\t\r\n]", item), logical(1))), paste("Invalid identities", label))
  result <- unlist(value, use.names = FALSE)
  need(!anyDuplicated(result), paste("Duplicate identities", label))
  result
}

frozen_integer <- function(value, lower, upper, name) {
  need(is.numeric(value) && length(value) == 1L && is.finite(value) && value == floor(value) &&
       value >= lower && value <= upper, paste("Invalid integer", name))
  as.integer(value)
}

table_scalars <- function(tables, test_id) {
  records <- list()
  for (name in names(tables)) {
    table <- tables[[name]]
    need(is.data.frame(table) && !anyDuplicated(names(table)), "Unsupported official table")
    for (row_position in seq_len(nrow(table))) for (column_position in seq_len(ncol(table))) {
      value <- table[[column_position]][[row_position]]
      missing <- is.na(value)
      need(length(missing) == 1L, "Unsupported official scalar")
      kind <- if (missing) "MISSING" else if (is.logical(value)) "BOOLEAN" else if (is.numeric(value)) "NUMERIC" else "TEXT"
      if (kind == "NUMERIC") need(is.finite(value), "Nonfinite official numeric scalar")
      records[[length(records) + 1L]] <- data.frame(test_id = test_id, table = name,
        row_position = row_position - 1L, column_position = column_position - 1L,
        row_label_json = as.character(jsonlite::toJSON(rownames(table)[row_position], auto_unbox = TRUE)),
        column_label_json = as.character(jsonlite::toJSON(names(table)[column_position], auto_unbox = TRUE)), value_kind = kind,
        numeric_value = if (kind == "NUMERIC") sprintf("%.17g", value) else "NA",
        text_json = if (kind %in% c("TEXT", "BOOLEAN")) as.character(jsonlite::toJSON(value, auto_unbox = TRUE)) else "null",
        missing_kind = if (missing) if (is.nan(value)) "R_NAN" else typeof(value) else "",
        source_position = length(records), stringsAsFactors = FALSE)
    }
  }
  need(length(records) > 0L, "Empty official table collection")
  do.call(rbind, records)
}

run_nichenet <- function(outputs, audit) {
  suppressPackageStartupMessages({library(nichenetr); library(Matrix); library(rhdf5); library(jsonlite); library(dplyr)})
  inputs <- vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), character(1))
  need(identical(Sys.getenv("AUTONOMICS_INPUT_COUNT"), "3") && all(file.exists(inputs)), "Three declared File inputs required")
  request <- jsonlite::fromJSON(inputs[[3L]], simplifyVector = FALSE)
  keys <- c("schema_version", "input0_sha256", "input1_sha256", "scale", "species", "group_column", "donor_column", "tissue_column",
            "expected_genes", "expected_cells", "expected_groups", "expected_donors", "expected_tissue", "sender", "receiver", "pct",
            "top_n_ligands", "n_targets", "ranking_metric", "tie_policy", "alias_policy", "expected_geneset", "geneset_policy",
            "minimum_geneset_coverage", "family_id", "test_id", "scope", "null_unit", "input_origin", "seed", "prior_sha256")
  need(is.list(request) && !anyDuplicated(names(request)) && setequal(names(request), keys) && length(request) == length(keys), "Missing, duplicate or unknown frozen key")
  need(identical(request$schema_version, 1L), "Unsupported contract schema")
  for (key in c("scale", "species", "group_column", "donor_column", "tissue_column", "expected_tissue", "sender", "receiver",
                "ranking_metric", "tie_policy", "alias_policy", "geneset_policy", "family_id", "test_id", "scope", "null_unit", "input_origin"))
    need(is.character(request[[key]]) && length(request[[key]]) == 1L && !is.na(request[[key]]) && nzchar(request[[key]]) &&
         trimws(request[[key]]) == request[[key]] && !grepl("[\t\r\n]", request[[key]]), paste("Invalid contract scalar", key))
  for (index in 0:1) {
    key <- paste0("input", index, "_sha256")
    need(is.character(request[[key]]) && length(request[[key]]) == 1L && grepl("^[a-f0-9]{64}$", request[[key]]) &&
         file_hash(inputs[[index + 1L]]) == request[[key]], "Input byte identity mismatch")
  }
  need(request$species == "human" && request$scale %in% c("raw_counts", "log1p_cp10k"), "Unsupported species or explicit scale")
  need(request$scope == "within_tissue_candidate_only" && request$null_unit == "prior_based_prediction_not_donor_inference", "Unsupported inference scope or null unit")
  need(request$input_origin %in% c("SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"), "Research qualification not granted")
  need(request$ranking_metric == "aupr_corrected" && request$tie_policy == "official_average_rank_keep_boundary_ties" &&
       request$alias_policy == "official_unique_no_merge" && request$geneset_policy == "frozen_background_intersection", "Unsupported frozen method policy")
  seed <- frozen_integer(request$seed, 0, .Machine$integer.max, "seed")
  top_n <- frozen_integer(request$top_n_ligands, 1, 200, "top_n_ligands")
  n_targets <- frozen_integer(request$n_targets, 1, 1000, "n_targets")
  for (key in c("pct", "minimum_geneset_coverage")) need(is.numeric(request[[key]]) && length(request[[key]]) == 1L &&
    is.finite(request[[key]]) && request[[key]] > 0 && request[[key]] <= 1, paste("Invalid numeric", key))
  cells <- frozen_ids(request$expected_cells, "cells")
  genes <- frozen_ids(request$expected_genes, "genes")
  groups <- frozen_ids(request$expected_groups, "groups")
  donors <- frozen_ids(request$expected_donors, "donors")
  geneset_input <- frozen_ids(request$expected_geneset, "geneset")
  need(identical(as.character(packageVersion("nichenetr")), "2.2.0"), "Official package version mismatch")
  prior_names <- c("ligand_target_matrix_nsga2r_final.rds", "weighted_networks_nsga2r_final.rds", "lr_network_human_21122021.rds")
  need(is.list(request$prior_sha256) && !anyDuplicated(names(request$prior_sha256)) && setequal(names(request$prior_sha256), prior_names), "Missing or unknown prior identity")
  prior_paths <- file.path("/opt/nichenetr/priors", prior_names)
  actual_hashes <- setNames(lapply(prior_paths, file_hash), prior_names)
  need(identical(request$prior_sha256[prior_names], actual_hashes), "Frozen official prior identity mismatch")
  parsed <- read_standard_h5ad(inputs[[1L]], request$group_column, request$donor_column, request$tissue_column)
  original <- parsed$exprs
  need(identical(colnames(original), cells) && identical(rownames(original), genes), "Frozen source axes mismatch")
  need(setequal(unique(parsed$cluster), groups) && setequal(unique(parsed$donor), donors), "Frozen group or donor universe mismatch")
  need(identical(unique(parsed$tissue), request$expected_tissue), "Pooled or unexpected tissues blocked")
  need(request$sender %in% groups && request$receiver %in% groups, "Sender or receiver not in frozen group universe")
  if (request$scale == "raw_counts") need(all(original@x == floor(original@x)), "Raw counts must be integral")
  file_geneset <- readLines(inputs[[2L]], warn = FALSE)
  need(identical(file_geneset, geneset_input), "Frozen geneset identity or format mismatch")
  mapped <- nichenetr::convert_alias_to_symbols(aliases = genes, organism = "human", verbose = FALSE)
  need(is.character(mapped) && length(mapped) == length(genes) && !anyNA(mapped) && !anyDuplicated(mapped), "Unresolved or colliding official aliases blocked; no silent expression merge")
  exprs <- original
  rownames(exprs) <- unname(mapped)
  priors <- setNames(lapply(prior_paths, readRDS), c("ltm", "weighted_networks", "lr_network"))
  set.seed(seed)
  rng_before <- .Random.seed
  collected_warnings <- character()
  method <- withCallingHandlers({
    sender <- nichenetr::get_expressed_genes(celltype_oi = request$sender, object = exprs, celltype_annot = parsed$cluster, pct = request$pct)
    receiver <- nichenetr::get_expressed_genes(celltype_oi = request$receiver, object = exprs, celltype_annot = parsed$cluster, pct = request$pct)
    background <- intersect(receiver, rownames(priors$ltm))
    geneset <- intersect(geneset_input, background)
    need(length(geneset) >= 1L && length(background) > length(geneset) && length(geneset)/length(geneset_input) >= request$minimum_geneset_coverage,
         "Frozen geneset coverage or positive/negative background not estimable")
    lr_pairs <- priors$lr_network %>% dplyr::filter(.data$from %in% sender, .data$to %in% receiver) %>% dplyr::distinct(.data$from, .data$to)
    potential <- intersect(unique(lr_pairs$from), colnames(priors$ltm))
    need(length(potential) > 0L, "No potential official ligands")
    activities <- nichenetr::predict_ligand_activities(geneset = geneset, background_expressed_genes = background,
                                                     ligand_target_matrix = priors$ltm, potential_ligands = potential, single = TRUE)
    need(nrow(activities) == length(potential) && !anyDuplicated(activities$test_ligand) &&
         all(is.finite(as.matrix(activities[, c("auroc", "aupr", "aupr_corrected", "pearson")]))), "Official activity not estimable")
    ranked <- activities %>% dplyr::arrange(dplyr::desc(.data$aupr_corrected), .data$test_ligand) %>%
      dplyr::mutate(rank = rank(-.data$aupr_corrected, ties.method = "average"))
    top <- ranked %>% dplyr::slice_max(.data$aupr_corrected, n = top_n, with_ties = TRUE) %>%
      dplyr::arrange(dplyr::desc(.data$aupr_corrected), .data$test_ligand)
    lt <- lapply(top$test_ligand, nichenetr::get_weighted_ligand_target_links, geneset = geneset,
                 ligand_target_matrix = priors$ltm, n = n_targets) %>% dplyr::bind_rows()
    receptors <- intersect(priors$lr_network$to, receiver)
    lr <- nichenetr::get_weighted_ligand_receptor_links(best_upstream_ligands = top$test_ligand, expressed_receptors = receptors,
                                                      lr_network = priors$lr_network, weighted_networks_lr_sig = priors$weighted_networks$lr_sig)
    list(sender = sender, receiver = receiver, background = background, geneset = geneset, lr_pairs = lr_pairs,
         potential = potential, receptors = receptors, result = list(activities = activities, ranked = ranked, top = top, target_links = lt, receptor_links = lr))
  }, warning = function(warning) {
    collected_warnings <<- c(collected_warnings, conditionMessage(warning))
    invokeRestart("muffleWarning")
  })
  payload <- list(original_exprs = original, mapped_exprs = exprs, parsed = parsed, alias_map = mapped, priors = priors,
                  method = method, rng_before = rng_before, rng_after = .Random.seed, warnings = collected_warnings, request = request)
  saveRDS(payload, outputs[[2L]], compress = TRUE)
  write_tsv <- function(table, path) write.table(table, path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE, na = "NA")
  values <- table_scalars(method$result, request$test_id)
  write_tsv(values, outputs[[1L]])
  write_tsv(data.frame(cell = cells, group = unname(parsed$cluster), donor = parsed$donor, tissue = parsed$tissue, source_position = seq_along(cells) - 1L), outputs[[5L]])
  write_tsv(data.frame(gene = genes, official_symbol = unname(mapped), source_position = seq_along(genes) - 1L,
                       in_prior_targets = unname(mapped) %in% rownames(priors$ltm), in_sender = unname(mapped) %in% method$sender,
                       in_receiver = unname(mapped) %in% method$receiver, in_background = unname(mapped) %in% method$background), outputs[[6L]])
  write_tsv(data.frame(gene = geneset_input, source_position = seq_along(geneset_input) - 1L,
                       status = ifelse(geneset_input %in% method$geneset, "ELIGIBLE_FROZEN_BACKGROUND", "NOT_IN_FROZEN_BACKGROUND")), outputs[[7L]])
  universe <- union(colnames(priors$ltm), unique(priors$lr_network$from))
  family <- data.frame(family_id = request$family_id, ligand = universe, source_position = seq_along(universe) - 1L,
    sender = request$sender, receiver = request$receiver, status = ifelse(universe %in% method$potential, "ESTIMATED_OFFICIAL",
    ifelse(!universe %in% colnames(priors$ltm), "NO_PRIOR_TARGET_PROFILE", ifelse(!universe %in% method$sender, "NOT_EXPRESSED_SENDER", "NO_EXPRESSED_RECEIVER_RECEPTOR"))))
  write_tsv(family, outputs[[8L]])
  audit$request <- request
  audit$status <- "TECHNICAL_PASS_NOT_SCIENTIFIC"
  audit$prior_sha256 <- actual_hashes
  audit$input_sha256 <- vapply(inputs, file_hash, character(1))
  audit$outputs <- setNames(lapply(outputs[c(1L,2L,5L,6L,7L,8L)], file_hash), as.character(c(0L,1L,4L,5L,6L,7L)))
  audit$typed_fields <- nrow(values)
  audit$full_family_rows <- nrow(family)
  audit$eligible_geneset <- length(method$geneset)
  audit$frozen_geneset <- length(geneset_input)
  message("PASS official NicheNet manual profile; NOT donor inference, cross-organ transport or G0")
  audit
}

run_nichenet_entry <- function(outputs) {
  need(all(nzchar(outputs)) && !anyDuplicated(outputs) && !any(file.exists(outputs)), "Eight distinct non-overwritten declared ports required")
  log_connection <- file(outputs[[4L]], "wt")
  sink(log_connection)
  sink(log_connection, type = "message")
  audit <- list(status = "RUNNING", G0_granted = FALSE, donor_inference_granted = FALSE, resident_deployment_granted = FALSE)
  audit <- tryCatch(run_nichenet(outputs, audit), error = function(error) {
    unlink(outputs[c(1L,2L,5L,6L,7L,8L)])
    audit$status <- "BLOCKED"
    audit$error <- conditionMessage(error)
    message("BLOCKED ", audit$error)
    audit
  })
  jsonlite::write_json(audit, outputs[[3L]], auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null")
  sink(type = "message")
  sink()
  close(log_connection)
  if (audit$status == "TECHNICAL_PASS_NOT_SCIENTIFIC") 0L else 1L
}

publish_nichenet_outputs <- function(writer) {
  destinations <- vapply(0:7, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), "")
  need(all(nzchar(destinations)), "Every declared output path is required")
  destinations <- vapply(destinations, function(filename)
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename)), character(1))
  need(!anyDuplicated(destinations) && !anyDuplicated(basename(destinations)), "Distinct output paths required")
  inputs <- vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), "")
  need(all(nzchar(inputs)), "Three declared inputs are required")
  input_paths <- vapply(inputs, normalizePath, character(1), mustWork = TRUE)
  need(!any(destinations %in% input_paths), "Input and output paths must be distinct")
  path_present <- function(filename) {
    target <- Sys.readlink(filename)
    file.exists(filename) || (!is.na(target) && nzchar(target))
  }
  need(!any(vapply(destinations, path_present, logical(1))), "Refusing to overwrite existing output")
  stage <- tempfile(pattern = ".nichenet-owned-", tmpdir = dirname(destinations[[1L]]))
  need(dir.create(stage, mode = "0700"), "Private output staging could not be created")
  created <- list()
  completed <- FALSE
  file_identity <- function(filename) {
    value <- system2("stat", c("-c", shQuote("%d:%i"), shQuote(filename)), stdout = TRUE, stderr = TRUE)
    need(is.null(attr(value, "status")) && length(value) == 1L && grepl("^[0-9]+:[0-9]+$", value), "Output file identity unavailable")
    value[[1L]]
  }
  on.exit({
    if (!completed) {
      for (owned in rev(created)) {
        tryCatch({
          if (path_present(owned$path) && identical(file_identity(owned$path), owned$identity)) unlink(owned$path)
        }, error = function(error) warning(paste("Output rollback retained an unverified path:", conditionMessage(error))))
      }
    }
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  private_outputs <- file.path(stage, basename(destinations))
  status <- writer(private_outputs)
  need(length(status) == 1L && status %in% c(0L, 1L), "Invalid wrapper exit status")
  positions <- if (status == 0L) seq_along(destinations) else c(3L, 4L)
  for (position in positions) {
    identity <- file_identity(private_outputs[[position]])
    need(file.link(private_outputs[[position]], destinations[[position]]), "Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(path = destinations[[position]], identity = identity)
  }
  completed <- TRUE
  status
}

if (nzchar(Sys.getenv("AUTONOMICS_INPUT_COUNT"))) {
  exit_status <- publish_nichenet_outputs(run_nichenet_entry)
  if (exit_status != 0L) quit(save = "no", status = exit_status)
}
