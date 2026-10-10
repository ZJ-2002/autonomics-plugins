#!/usr/bin/env Rscript
# SPDX-License-Identifier: GPL-3.0-only
#
# Tier-1 driver for CellChat (official stack, digest-pinned image).
# I/O translation ONLY: reads the engine-mounted h5ad and env-rendered
# params, runs the FROZEN official CellChat pipeline with official defaults
# (no analysis decisions of our own), and leaves official result tables
# plus a provenance record in the workdir.
#
# Frozen pipeline (do not reorder / retune):
#   createCellChat -> @DB <- CellChatDB[.human|.mouse] (subsetDB when
#   db_scope="secreted") -> subsetData -> identifyOverExpressedGenes ->
#   identifyOverExpressedInteractions -> computeCommunProb(triMean,
#   raw.use=TRUE, seed.use=1L) -> filterCommunication(min.cells=10) ->
#   computeCommunProbPathway(thresh=0.05) -> aggregateNet ->
#   netAnalysis_computeCentrality(slot.name="netP")
#
# h5ad is read with rhdf5 only (no reticulate/Python): X stays SPARSE from
# disk to CellChat (the official tutorial's t(as.matrix()) bridge would
# densify 50k cells into OOM — never used here). CSR and CSC encodings of
# the cells-x-genes matrix are both handled; the genes-x-cells orientation
# is asserted, not assumed.

suppressPackageStartupMessages({
  library(rhdf5)
  library(CellChat)
  library(jsonlite)
})

CELLCHAT_COMMIT <- "75253cd0c9e68410e6e721a6d3a0419a1d7e358f"
PRESTO_COMMIT <- "b5df6ee6097eb62522f2e557aa93ac21bab2d05f"

env_str <- function(name, default) {
  v <- Sys.getenv(name, "")
  if (nzchar(v)) v else default
}
env_int <- function(name, default) {
  v <- Sys.getenv(name, "")
  if (nzchar(v)) as.integer(v) else default
}
die <- function(...) {
  cat("driver: FATAL:", ..., "\n", sep = " ", file = stderr())
  quit(save = "no", status = 1L)
}

say <- function(...) cat("driver:", ..., "\n", sep = " ")

# ---------------------------------------------------------------------------
# Inputs and parameters
# ---------------------------------------------------------------------------
input0 <- env_str("AUTONOMICS_INPUT0", "")
if (!nzchar(input0) || !file.exists(input0)) {
  die("AUTONOMICS_INPUT0 missing or not a file:", input0)
}
out_dir <- env_str("AUTONOMICS_WORKDIR", getwd())
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

cluster_column <- env_str("CCHAT_CLUSTER_COLUMN", "cluster")
species <- tolower(env_str("CCHAT_SPECIES", "human"))
db_scope <- env_str("CCHAT_DB_SCOPE", "full")
normalized <- env_str("CCHAT_NORMALIZED", "auto")
nboot <- env_int("CCHAT_NBOOT", 100L)
workers <- env_int("CCHAT_WORKERS", 4L)

if (!species %in% c("human", "mouse")) {
  die("CCHAT_SPECIES must be 'human' or 'mouse', got:", species)
}
if (!db_scope %in% c("full", "secreted")) {
  die("CCHAT_DB_SCOPE must be 'full' or 'secreted', got:", db_scope)
}
if (!normalized %in% c("auto", "raw", "lognorm")) {
  die("CCHAT_NORMALIZED must be 'auto', 'raw' or 'lognorm', got:", normalized)
}
if (is.na(nboot) || nboot < 10 || nboot > 500) {
  die("CCHAT_NBOOT must be an integer in [10, 500], got:", Sys.getenv("CCHAT_NBOOT"))
}
if (is.na(workers) || workers < 1 || workers > 32) {
  die("CCHAT_WORKERS must be an integer in [1, 32], got:", Sys.getenv("CCHAT_WORKERS"))
}

# ---------------------------------------------------------------------------
# h5ad reading (sparse-preserving, rhdf5 only)
# ---------------------------------------------------------------------------
read_index_names <- function(h5path, axis) {
  # h5ad >= 0.2: axis/_index dataset; h5ad 0.1: "index" attribute on the group.
  if (h5_exists(h5path, paste0(axis, "/_index"))) {
    as.character(h5read(h5path, paste0(axis, "/_index")))
  } else {
    idx <- h5readAttributes(h5path, axis)$index
    if (is.null(idx)) die("h5ad ", axis, " has neither _index dataset nor index attribute")
    as.character(idx)
  }
}

h5_exists <- function(h5path, name) {
  # RDONLY: inputs arrive on read-only mounts, and rhdf5's H5Fopen defaults
  # to RDWR which fails there (h5read/h5ls open read-only internally).
  fid <- H5Fopen(h5path, flags = "H5F_ACC_RDONLY")
  on.exit(H5Fclose(fid))
  H5Lexists(fid, name)
}

read_obs_labels <- function(h5path, column) {
  col_path <- paste0("obs/", column)
  # rhdf5's h5ls has no path= argument: list recursively, take direct /obs children
  obs_direct <- h5ls(h5path, recursive = TRUE)
  obs_direct <- obs_direct[obs_direct$group == "/obs", , drop = FALSE]
  if (!column %in% obs_direct$name) {
    die("cluster column '", column, "' not in h5ad obs (available:",
        paste(setdiff(obs_direct$name, "_index"), collapse = ", "), ")")
  }
  attrs <- h5readAttributes(h5path, col_path)
  enc <- attrs[["encoding-type"]]
  is_group <- obs_direct$otype[obs_direct$name == column] == "H5I_GROUP"
  if (is_group && !is.null(enc) && enc == "categorical") {
    # anndata >= 0.11: categorical is a group with codes/categories datasets
    cats <- as.character(h5read(h5path, paste0(col_path, "/categories")))
    codes <- as.integer(h5read(h5path, paste0(col_path, "/codes")))
    cats[codes + 1L]
  } else {
    vals <- h5read(h5path, col_path)
    if (!is.null(enc) && enc == "categorical") {
      # older anndata: codes dataset + categories attribute
      cats <- attrs[["categories"]]
      if (is.null(cats)) die("categorical obs column '", column, "' lacks categories")
      as.character(cats)[as.integer(vals) + 1L]
    } else {
      as.character(vals)
    }
  }
}

read_h5ad_x <- function(h5path) {
  cell_names <- read_index_names(h5path, "obs")
  gene_names <- read_index_names(h5path, "var")
  n_obs <- length(cell_names)
  n_vars <- length(gene_names)
  if (anyDuplicated(cell_names)) die("duplicate cell names in h5ad obs index")
  if (anyDuplicated(gene_names)) die("duplicate gene names in h5ad var index")

  x_otype <- h5ls(h5path, recursive = FALSE)
  x_otype <- x_otype$otype[x_otype$name == "X"]
  if (length(x_otype) == 0) die("h5ad has no /X")

  if (x_otype == "H5I_GROUP") {
    enc <- h5readAttributes(h5path, "X")[["encoding-type"]]
    if (is.null(enc)) die("sparse /X group lacks encoding-type attribute")
    x <- as.numeric(h5read(h5path, "X/data"))
    idx <- as.numeric(h5read(h5path, "X/indices"))
    ptr <- as.numeric(h5read(h5path, "X/indptr"))
    if (length(x) != length(idx)) die("X/data and X/indices lengths differ")
    if (length(ptr) < 1 || tail(ptr, 1) != length(idx)) die("X/indptr is inconsistent with X/indices")
    if (any(idx < 0)) die("negative index in sparse X")

    if (enc == "csr_matrix") {
      # cells are rows: entry k of row i is (cell i, gene idx[k]+1)
      if (length(ptr) != n_obs + 1L) die("CSR indptr length != n_cells + 1 (orientation mismatch?)")
      if (any(idx >= n_vars)) die("CSR index exceeds n_genes")
      i_cell <- rep(seq_len(n_obs), diff(ptr))
      j_gene <- idx + 1
    } else if (enc == "csc_matrix") {
      # genes are columns: entry k of column j is (cell idx[k]+1, gene j)
      if (length(ptr) != n_vars + 1L) die("CSC indptr length != n_genes + 1 (orientation mismatch?)")
      if (any(idx >= n_obs)) die("CSC index exceeds n_cells")
      j_gene <- rep(seq_len(n_vars), diff(ptr))
      i_cell <- idx + 1
    } else {
      die("unsupported sparse X encoding-type:", enc)
    }
    m <- Matrix::sparseMatrix(i = as.integer(j_gene), j = as.integer(i_cell),
                              x = x, dims = c(n_vars, n_obs))
  } else {
    say("WARNING: /X is DENSE — densifying to read; large inputs should ship sparse h5ad")
    d <- h5read(h5path, "X")
    # rhdf5 returns 2D datasets transposed relative to the h5py view, so an
    # h5ad (n_obs, n_vars) dense X normally arrives here as (n_vars, n_obs).
    if (identical(dim(d), c(n_vars, n_obs))) {
      m <- Matrix::Matrix(d, sparse = TRUE)
    } else if (identical(dim(d), c(n_obs, n_vars))) {
      m <- Matrix::t(Matrix::Matrix(d, sparse = TRUE))
    } else {
      die("dense X dim is", paste(dim(d), collapse = "x"),
          "but obs/var imply", n_obs, "x", n_vars, "or", n_vars, "x", n_obs)
    }
  }

  dimnames(m) <- list(gene_names, cell_names)
  # Orientation assertion: rows = genes, cols = cells.
  stopifnot(identical(dim(m), c(n_vars, n_obs)))
  if (min(m@x) < 0) die("expression matrix contains negative values")
  list(matrix = m, n_cells = n_obs, n_genes = n_vars,
       n_nonzero = length(m@x), dense_warned = x_otype != "H5I_GROUP")
}

# Official normalization formula applied sparsely (identical arithmetic to
# log1p(t(t(X)/colSums(X))*10000) without densifying): each nonzero entry in
# CSC column j is divided by that column's sum, scaled by 1e4, then log1p.
lognorm_sparse <- function(m) {
  cs <- Matrix::colSums(m)
  if (any(cs <= 0)) die("cells with zero total expression cannot be normalized")
  m@x <- log1p(m@x / rep(cs, diff(m@p)) * 10000)
  m
}

say("reading", input0)
h5 <- read_h5ad_x(input0)
mat <- h5$matrix
labels <- read_obs_labels(input0, cluster_column)

# ---------------------------------------------------------------------------
# Normalization decision (recorded in provenance; official formula only)
# ---------------------------------------------------------------------------
norm_decision <- NA_character_
if (normalized == "lognorm") {
  norm_decision <- "lognorm_passed_through"
} else if (normalized == "raw") {
  mat <- lognorm_sparse(mat)
  norm_decision <- "raw_explicit_log1p_applied"
} else {
  x <- mat@x
  looks_raw <- all(x == round(x)) && min(x) >= 0
  if (looks_raw) {
    mat <- lognorm_sparse(mat)
    norm_decision <- "auto_detected_raw_log1p_applied"
  } else {
    norm_decision <- "auto_detected_lognorm_passed_through"
  }
}
say("normalization:", norm_decision)

meta <- data.frame(labels = factor(labels), row.names = colnames(mat))
stopifnot(identical(rownames(meta), colnames(mat)))
say("cells:", h5$n_cells, "genes:", h5$n_genes, "clusters:",
    paste(levels(meta$labels), collapse = ", "))

# ---------------------------------------------------------------------------
# FROZEN official pipeline
# ---------------------------------------------------------------------------
if (workers > 1) {
  future::plan("multisession", workers = workers)
} else {
  future::plan("sequential")
}
say("future workers:", future::nbrOfWorkers())

t0 <- proc.time()

cellchat <- createCellChat(object = mat, meta = meta, group.by = "labels")

db_name <- if (species == "human") "CellChatDB.human" else "CellChatDB.mouse"
db <- get(db_name)
db_versions <- sort(unique(as.character(db$interaction$version)))
n_db_before <- nrow(db$interaction)
if (db_scope == "secreted") {
  db <- subsetDB(db, search = "Secreted Signaling", key = "annotation")
}
n_db_after <- nrow(db$interaction)
cellchat@DB <- db

cellchat <- subsetData(cellchat)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)
cellchat <- computeCommunProb(cellchat, type = "triMean", trim = 0.1,
                              raw.use = TRUE, population.size = FALSE,
                              nboot = nboot, seed.use = 1L)
cellchat <- filterCommunication(cellchat, min.cells = 10)
cellchat <- computeCommunProbPathway(cellchat, thresh = 0.05)
cellchat <- aggregateNet(cellchat)
cellchat <- netAnalysis_computeCentrality(cellchat, slot.name = "netP")

elapsed <- (proc.time() - t0)[["elapsed"]]
say("pipeline finished in", round(elapsed, 1), "s")

future::plan("sequential")  # reap multisession workers before exit

# ---------------------------------------------------------------------------
# Outputs (workdir root, fixed names)
# ---------------------------------------------------------------------------
p_out <- function(name) file.path(out_dir, name)

lr <- subsetCommunication(cellchat)
write.csv(lr, p_out("cellchat_lr_pairs.csv"), row.names = FALSE)

pw <- subsetCommunication(cellchat, slot.name = "netP")
write.csv(pw, p_out("cellchat_pathway_probs.csv"), row.names = FALSE)

write.csv(cellchat@net$count, p_out("cellchat_net_count.csv"))
write.csv(cellchat@net$weight, p_out("cellchat_net_weight.csv"))

centr <- cellchat@netP$centr
centr_long <- do.call(rbind, unname(lapply(names(centr), function(p) {
  ms <- centr[[p]]
  do.call(rbind, unname(lapply(names(ms), function(mn) {
    v <- ms[[mn]]
    if (is.numeric(v) && !is.null(names(v))) {
      data.frame(pathway = p, measure = mn, cluster = names(v),
                 value = as.numeric(v), stringsAsFactors = FALSE)
    } else NULL
  })))
})))
if (is.null(centr_long)) {
  centr_long <- data.frame(pathway = character(), measure = character(),
                           cluster = character(), value = numeric())
}
write.csv(centr_long, p_out("cellchat_centrality.csv"), row.names = FALSE)

saveRDS(cellchat, p_out("cellchat_object.rds"))

outputs <- c("cellchat_lr_pairs.csv", "cellchat_pathway_probs.csv",
             "cellchat_net_count.csv", "cellchat_net_weight.csv",
             "cellchat_centrality.csv", "cellchat_object.rds")

src_sha <- NA_character_
if (file.exists("/opt/autonomics/source.sha256")) {
  src_sha <- strsplit(readLines("/opt/autonomics/source.sha256", n = 1), "[[:space:]]+")[[1]][1]
}

provenance <- list(
  package = "CellChat",
  package_version = as.character(packageVersion("CellChat")),
  upstream = list(
    repo = "jinworks/CellChat",
    commit = CELLCHAT_COMMIT,
    source_tarball_sha256 = src_sha
  ),
  presto = list(
    repo = "immunogenomics/presto",
    commit = PRESTO_COMMIT,
    version = as.character(packageVersion("presto")),
    role = "official do.fast=TRUE Wilcoxon backend for identifyOverExpressedGenes"
  ),
  r_version = R.version.string,
  bioconductor_version = "3.20",
  cellchatdb = list(
    name = db_name,
    versions = db_versions,
    interactions_before_scope_subset = n_db_before,
    interactions_after_scope_subset = n_db_after
  ),
  params = list(
    cluster_column = cluster_column,
    species = species,
    db_scope = db_scope,
    normalized = normalized,
    nboot = nboot,
    seed.use = 1L,
    type = "triMean",
    trim = 0.1,
    raw.use = TRUE,
    population.size = FALSE,
    min.cells = 10L,
    pathway.thresh = 0.05
  ),
  normalization = list(
    decision = norm_decision,
    formula = "log1p(t(t(X)/colSums(X))*10000) (sparse CSC arithmetic)"
  ),
  input = list(
    file = basename(input0),
    n_cells = h5$n_cells,
    n_genes = h5$n_genes,
    n_nonzero = h5$n_nonzero,
    x_dense = h5$dense_warned
  ),
  future = list(plan = "multisession-or-sequential", workers = workers),
  runtime_secs = round(elapsed, 3),
  outputs = as.list(stats::setNames(
    vapply(outputs, function(f) as.numeric(file.size(p_out(f))), numeric(1)),
    outputs
  ))
)
writeLines(toJSON(provenance, auto_unbox = TRUE, pretty = TRUE, na = "null"),
           p_out("cellchat_provenance.json"))

outputs <- c(outputs, "cellchat_provenance.json")
say("pipeline rows: lr_pairs =", nrow(lr), " pathway_probs =", nrow(pw),
    " centrality =", nrow(centr_long))
for (f in outputs) {
  say("output", f, "(", file.size(p_out(f)), "bytes )")
}
say("done")
