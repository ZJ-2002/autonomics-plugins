suppressPackageStartupMessages({
  library(CellChat)
  library(rhdf5)
  library(jsonlite)
  library(Matrix)
})

root <- Sys.getenv("AUTONOMICS_WORKDIR", getwd())
dir.create(root, recursive = TRUE, showWarnings = FALSE)
output <- function(name) file.path(root, name)
hash <- function(path) digest::digest(file = path, algo = "sha256")
need <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}
log_message <- function(message) {
  cat(message, "\n", file = output("cellchat.log"), append = TRUE)
}
scalar <- function(value, mode, name) {
  need(length(value) == 1L && !is.null(value) && !is.na(value) && typeof(value) %in% mode,
       paste("Invalid scalar", name))
  value
}
integer_value <- function(value, lower, upper, name) {
  scalar(value, c("integer", "double"), name)
  need(is.finite(value) && value == floor(value) && value >= lower && value <= upper,
       paste("Invalid integer", name))
  as.integer(value)
}
identities <- function(value, name) {
  need(is.list(value) && length(value) > 0L && all(vapply(value, function(item)
    is.character(item) && length(item) == 1L && !is.na(item) && nzchar(item) &&
      !grepl("[\t\r\n]", item), logical(1))), paste("Invalid identities", name))
  result <- unlist(value, use.names = FALSE)
  need(!anyDuplicated(result), paste("Duplicate identities", name))
  result
}
exists_h5 <- function(path, name) {
  handle <- H5Fopen(path, flags = "H5F_ACC_RDONLY")
  on.exit(H5Fclose(handle))
  H5Lexists(handle, name)
}
axis_names <- function(path, axis) {
  index <- h5readAttributes(path, axis)[["_index"]]
  need(is.character(index) && length(index) == 1L && !grepl("/", index),
       paste("Missing or invalid H5AD index attribute", axis))
  need(exists_h5(path, paste0(axis, "/", index)), paste("Missing H5AD index", axis))
  values <- h5read(path, paste0(axis, "/", index))
  need(is.character(values) && !anyNA(values) && all(nzchar(values)) &&
       !anyDuplicated(values) && !any(grepl("[\t\r\n]", values)), paste("Invalid H5AD axis", axis))
  as.vector(values, mode = "character")
}
obs_column <- function(path, column, count) {
  need(is.character(column) && length(column) == 1L && nzchar(column) && !grepl("/", column),
       "Invalid obs column name")
  key <- paste0("obs/", column)
  need(exists_h5(path, key), paste("Missing obs column", column))
  encoding <- h5readAttributes(path, key)[["encoding-type"]]
  if (identical(encoding, "categorical")) {
    categories <- h5read(path, paste0(key, "/categories"))
    codes <- h5read(path, paste0(key, "/codes"))
    need(is.character(categories) && length(categories) > 0L && !anyNA(categories) &&
         all(nzchar(categories)) && !anyDuplicated(categories), "Invalid categorical categories")
    need(is.numeric(codes) && length(codes) == count && all(is.finite(codes)) &&
         all(codes == floor(codes)) && all(codes >= 0L & codes < length(categories)),
         "Invalid or missing categorical codes")
    values <- categories[codes + 1L]
  } else {
    need(identical(encoding, "string-array"), "Unsupported obs encoding")
    values <- h5read(path, key)
  }
  need(is.character(values) && length(values) == count && !anyNA(values) &&
       all(nzchar(values)) && !any(grepl("[\t\r\n]", values)), "Invalid obs labels")
  as.vector(values, mode = "character")
}
read_expression <- function(path, cells, genes) {
  encoding <- h5readAttributes(path, "X")[["encoding-type"]]
  if (encoding %in% c("csr_matrix", "csc_matrix")) {
    shape <- h5readAttributes(path, "X")$shape
    need(identical(as.numeric(shape), as.numeric(c(length(cells), length(genes)))), "Sparse shape mismatch")
    values <- h5read(path, "X/data")
    indices <- h5read(path, "X/indices")
    pointers <- h5read(path, "X/indptr")
    major <- if (encoding == "csr_matrix") length(cells) else length(genes)
    minor <- if (encoding == "csr_matrix") length(genes) else length(cells)
    need(is.numeric(values) && length(values) == length(indices) && all(is.finite(values)) &&
         all(values >= 0), "Invalid expression values")
    need(is.numeric(pointers) && length(pointers) == major + 1L && all(is.finite(pointers)) &&
         all(pointers == floor(pointers)) && pointers[1] == 0 && all(diff(pointers) >= 0) &&
         tail(pointers, 1) == length(values), "Invalid sparse pointers")
    need(is.numeric(indices) && all(is.finite(indices)) && all(indices == floor(indices)) &&
         all(indices >= 0 & indices < minor), "Invalid sparse indices")
    for (position in seq_len(major)) {
      start <- pointers[position] + 1L
      end <- pointers[position + 1L]
      if (start <= end) need(!anyDuplicated(indices[start:end]), "Duplicate sparse coordinates")
    }
    values <- as.numeric(values)
    indices <- as.numeric(indices)
    pointers <- as.numeric(pointers)
    coordinates <- rep(seq_len(major), diff(pointers))
    matrix <- if (encoding == "csr_matrix")
      sparseMatrix(i = indices + 1L, j = coordinates, x = values, dims = c(length(genes), length(cells))) else
      sparseMatrix(i = coordinates, j = indices + 1L, x = values, dims = c(length(genes), length(cells)))
  } else {
    need(identical(encoding, "array"), "Unsupported X encoding")
    values <- h5read(path, "X")
    need(is.numeric(values) && identical(dim(values), c(length(genes), length(cells))),
         "Dense HDF5 orientation or shape mismatch")
    need(all(is.finite(values)) && all(values >= 0), "Invalid expression values")
    matrix <- Matrix(values, sparse = TRUE)
  }
  matrix <- as(matrix, "dgCMatrix")
  dimnames(matrix) <- list(genes, cells)
  need(all(Matrix::colSums(matrix) > 0), "Zero-library cell")
  matrix
}
write_table <- function(table, name) write.table(table, output(name), sep = "\t", quote = FALSE,
                                                row.names = FALSE, na = "NA")
run <- function() {
  request_path <- Sys.getenv("AUTONOMICS_INPUT1")
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  need(file.exists(input) && file.exists(request_path), "Missing declared input file")
  request <- fromJSON(request_path, simplifyVector = FALSE)
  keys <- c("schema_version", "input0_sha256", "scale", "species", "db_scope", "seed", "nboot",
            "group_column", "donor_column", "tissue_column", "expected_genes", "expected_cells",
            "expected_groups", "expected_donors", "expected_tissue", "scope", "null_unit", "family_id",
            "test_id", "input_origin")
  need(is.list(request) && !anyDuplicated(names(request)) && setequal(names(request), keys) &&
       length(request) == length(keys), "Missing, duplicate or unknown frozen contract key")
  need(identical(request$schema_version, 1L), "Unsupported contract schema")
  for (key in setdiff(keys, c("schema_version", "seed", "nboot", "expected_genes", "expected_cells",
                              "expected_groups", "expected_donors"))) scalar(request[[key]], "character", key)
  need(grepl("^[a-f0-9]{64}$", request$input0_sha256) && hash(input) == request$input0_sha256,
       "Input byte identity mismatch")
  need(request$scale %in% c("raw_counts", "log1p_cp10k"), "Explicit supported scale required; no auto normalization")
  need(request$species %in% c("human", "mouse") && request$db_scope %in% c("full", "secreted"),
       "Unsupported species or DB scope")
  need(request$scope == "within_tissue_candidate_only" &&
       request$null_unit == "official_cell_labels_not_donor_inference", "Unsupported inference scope or null unit")
  need(request$input_origin %in% c("SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"),
       "Research qualification not granted by this technical adapter")
  need(all(vapply(request[c("family_id", "test_id", "expected_tissue")], function(value)
    nzchar(value) && !grepl("[\t\r\n]", value), logical(1))), "Invalid contract identity")
  seed <- integer_value(request$seed, 0, .Machine$integer.max, "seed")
  nboot <- integer_value(request$nboot, 10, 500, "nboot")
  expected_cells <- identities(request$expected_cells, "expected_cells")
  expected_genes <- identities(request$expected_genes, "expected_genes")
  groups <- identities(request$expected_groups, "expected_groups")
  donors <- identities(request$expected_donors, "expected_donors")
  need(identical(as.character(packageVersion("CellChat")), "2.2.0.9001") &&
       identical(as.character(packageVersion("presto")), "1.1.0"), "Official package version mismatch")
  cells <- axis_names(input, "obs")
  genes <- axis_names(input, "var")
  need(identical(cells, expected_cells) && identical(genes, expected_genes), "Frozen cell or gene order mismatch")
  labels <- obs_column(input, request$group_column, length(cells))
  donor_labels <- obs_column(input, request$donor_column, length(cells))
  tissues <- obs_column(input, request$tissue_column, length(cells))
  need(length(groups) >= 2L && setequal(unique(labels), groups), "Frozen groups mismatch")
  need(setequal(unique(donor_labels), donors) && length(donors) >= 2L, "Frozen donors mismatch")
  need(all(tissues == request$expected_tissue), "Pooled or unexpected tissues blocked")
  need(all(table(factor(labels, levels = groups)) >= 10L), "Group below official min.cells")
  matrix <- read_expression(input, cells, genes)
  if (request$scale == "raw_counts") {
    need(all(matrix@x == floor(matrix@x)), "Raw counts must be integral")
    matrix@x <- log1p(matrix@x / rep(unname(Matrix::colSums(matrix)), diff(matrix@p)) * 10000)
  }
  metadata <- data.frame(labels = factor(labels, levels = groups), row.names = cells)
  future::plan("sequential")
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  set.seed(seed)
  before <- .Random.seed
  warnings <- character()
  result <- withCallingHandlers({
    object <- createCellChat(object = matrix, meta = metadata, group.by = "labels")
    database <- if (request$species == "human") CellChatDB.human else CellChatDB.mouse
    if (request$db_scope == "secreted") database <- subsetDB(database, search = "Secreted Signaling", key = "annotation")
    object@DB <- database
    object <- subsetData(object)
    object <- identifyOverExpressedGenes(object)
    object <- identifyOverExpressedInteractions(object)
    object <- computeCommunProb(object, type = "triMean", trim = 0.1, raw.use = TRUE,
                               population.size = FALSE, nboot = nboot, seed.use = seed)
    object <- filterCommunication(object, min.cells = 10)
    object <- computeCommunProbPathway(object, thresh = 0.05)
    object <- aggregateNet(object)
    netAnalysis_computeCentrality(object, slot.name = "netP")
  }, warning = function(warning) {
    warnings <<- c(warnings, conditionMessage(warning))
    invokeRestart("muffleWarning")
  })
  state <- list(before = before, after = .Random.seed, warnings = warnings, request = request)
  need(validObject(result) && length(dim(result@net$prob)) == 3L &&
       identical(dim(result@net$prob), dim(result@net$pval)) &&
       all(is.finite(result@net$prob)) && all(is.finite(result@net$pval)) &&
       all(result@net$prob >= 0) && all(result@net$pval >= 0 & result@net$pval <= 1),
       "Official output not usable")
  dimensions <- dimnames(result@net$prob)
  need(identical(dimensions[[1]], groups) && identical(dimensions[[2]], groups) &&
       !anyDuplicated(dimensions[[3]]) && length(dimensions[[3]]) > 0L, "Official axes mismatch or no estimable LR")
  rows <- expand.grid(source = dimensions[[1]], target = dimensions[[2]], interaction = dimensions[[3]],
                      KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
  rows$test_id <- request$test_id
  rows$prob <- as.numeric(result@net$prob)
  rows$pval <- as.numeric(result@net$pval)
  rows$row_id <- seq_len(nrow(rows))
  family <- expand.grid(source = groups, target = groups, interaction = as.character(result@DB$interaction$interaction_name),
                        KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
  family$family_id <- request$family_id
  family$status <- ifelse(family$interaction %in% dimensions[[3]], "ESTIMATED_OFFICIAL", "NOT_ESTIMATED_OFFICIAL_SELECTION")
  need(!anyDuplicated(result@DB$interaction$interaction_name), "Duplicate official DB interaction IDs")
  write_table(rows, "values.tsv")
  saveRDS(result, output("cellchat.rds"), version = 3)
  saveRDS(state, output("state.rds"), version = 3)
  write_table(data.frame(cell = cells, group = labels, donor = donor_labels, tissue = tissues,
                         source_position = seq_along(cells)), "cells.tsv")
  write_table(data.frame(gene = genes, source_position = seq_along(genes)), "genes.tsv")
  write_table(family, "family.tsv")
  products <- c("values.tsv", "cellchat.rds", "state.rds", "cells.tsv", "genes.tsv", "family.tsv")
  audit <- list(status = "TECHNICAL_PASS_NOT_SCIENTIFIC", G0_granted = FALSE, resident_deployment_granted = FALSE,
                request = request, input0_sha256 = hash(input), input1_sha256 = hash(request_path),
                full_DB_pair_family_rows = nrow(family), estimated_rows = nrow(rows),
                not_estimated_rows = sum(family$status != "ESTIMATED_OFFICIAL"), workers = 1L,
                official_bootstrap_unit = "cell labels, NOT donor inference", outputs =
                  as.list(setNames(vapply(products, function(name) hash(output(name)), character(1)), products)))
  writeLines(toJSON(audit, auto_unbox = TRUE, pretty = TRUE), output("audit.json"))
  log_message("PASS technical CellChat candidate inference; NOT G0, donor inference or cross-organ transport")
}
tryCatch(run(), error = function(error) {
  for (name in c("values.tsv", "cellchat.rds", "cells.tsv", "genes.tsv", "state.rds", "family.tsv")) {
    if (file.exists(output(name))) unlink(output(name))
  }
  log_message(paste("BLOCKED", conditionMessage(error)))
  writeLines(toJSON(list(status = "BLOCKED", error = conditionMessage(error), G0_granted = FALSE,
                         resident_deployment_granted = FALSE), auto_unbox = TRUE, pretty = TRUE), output("audit.json"))
  quit(save = "no", status = 1L)
})
