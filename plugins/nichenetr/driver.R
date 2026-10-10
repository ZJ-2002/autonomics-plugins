#!/usr/bin/env Rscript
# SPDX-License-Identifier: GPL-3.0-only
#
# Tier-1 driver for NicheNet ligand activity analysis.
#
# I/O translation only: reads the engine-mounted h5ad + geneset file and
# env-rendered params, runs the OFFICIAL nichenetr manual pipeline with a
# FROZEN parameterization (matrix + metadata path, no Seurat wrappers, no
# visualization), and writes the official tables plus provenance to the
# workdir root. Every analytical decision is made by the official package
# pinned in the image; this script only feeds inputs and renames outputs.
#
# Frozen steps (do not change without re-freezing the node contract):
#   1. convert_alias_to_symbols() on gene names (skipping silently drops
#      ~35 ligand interactions that are known under aliases)
#   2. get_expressed_genes(sender/receiver, pct = 0.10)
#   3. background = receiver expressed genes INTERSECT prior targets
#   4. potential ligands = lr_network pairs with ligand expressed in the
#      sender AND receptor expressed in the receiver
#   5. predict_ligand_activities() ranked by aupr_corrected (v2 convention)
#   6. top N ligands (default 30)
#   7. get_weighted_ligand_target_links(n = 200) per top ligand
#   8. get_weighted_ligand_receptor_links(weighted_networks$lr_sig)
# There is NO nnls/PPR algorithm parameter on this path: the NSGA2R
# ligand-target matrix is baked in the image and read as-is, and there is
# no prioritize_ligands export upstream.

suppressPackageStartupMessages({
  library(nichenetr)
  library(magrittr)  # %>% used below; nichenetr v2 no longer re-exports it
  library(Matrix)
  library(rhdf5)
  library(jsonlite)
})

PRIORS_DIR <- "/opt/nichenetr/priors"
PRIOR_LTM <- "ligand_target_matrix_nsga2r_final.rds"
PRIOR_WN <- "weighted_networks_nsga2r_final.rds"
PRIOR_LR <- "lr_network_human_21122021.rds"

env_str <- function(name, default = "") {
  value <- Sys.getenv(name, "")
  if (nzchar(value)) value else default
}
env_int <- function(name, default) {
  value <- Sys.getenv(name, "")
  if (nzchar(value)) as.integer(value) else as.integer(default)
}
env_num <- function(name, default) {
  value <- Sys.getenv(name, "")
  if (nzchar(value)) as.numeric(value) else as.numeric(default)
}
die <- function(...) {
  message("driver: ERROR: ", paste0(...))
  quit(save = "no", status = 1L)
}

# ---------------------------------------------------------------------------
# h5ad reader (rhdf5, sparse-preserving; no reticulate/python in the image).
# Handles BOTH on-disk generations:
#   legacy (anndata <= 0.12 / h5sparse): _index string dataset, categorical
#     column = codes dataset + "categories" attr, X attrs h5sparse_format /
#     h5sparse_shape
#   current (anndata 0.13 encoding): nullable-string-array groups
#     (values+mask), categorical groups (codes+categories datasets),
#     X attrs encoding-type csr_matrix/csc_matrix + "shape"
# X accepted as CSR group, CSC group or dense dataset, in either orientation.
# ---------------------------------------------------------------------------
read_h5ad_exprs <- function(path, cluster_column) {
  if (!file.exists(path)) die("h5ad not found: ", path)
  layout <- h5ls(path, recursive = TRUE)
  at <- function(group, name) which(layout$group == group & layout$name == name)
  is_group <- function(group, name) {
    i <- at(group, name)
    length(i) == 1L && layout$otype[i] == "H5I_GROUP"
  }
  is_dataset <- function(group, name) {
    i <- at(group, name)
    length(i) == 1L && layout$otype[i] == "H5I_DATASET"
  }

  # String vector: plain string dataset, or nullable-string-array group
  # (values + mask). Masked entries become NA.
  read_strings <- function(where) {
    where <- paste0("/", sub("^/+", "", where))  # h5ls paths are absolute
    if (is_group(dirname(where), basename(where)) &&
        is_dataset(where, "values")) {
      vals <- as.character(h5read(path, paste0(where, "/values")))
      mask <- tryCatch(as.logical(h5read(path, paste0(where, "/mask"))),
                       error = function(e) NULL)
      if (!is.null(mask) && length(mask) == length(vals)) {
        vals[mask] <- NA_character_
      }
      vals
    } else {
      as.character(h5read(path, where))
    }
  }

  # Categorical column: group with codes+categories, or legacy codes dataset
  # + categories attribute, or plain strings.
  read_cluster_col <- function(where) {
    where <- paste0("/", sub("^/+", "", where))  # h5ls paths are absolute
    if (is_group(dirname(where), basename(where)) &&
        is_dataset(where, "codes")) {
      codes <- as.integer(h5read(path, paste0(where, "/codes")))
      cats <- read_strings(paste0(where, "/categories"))
      out <- rep(NA_character_, length(codes))
      ok <- !is.na(codes) & codes >= 0 & codes < length(cats)
      out[ok] <- cats[codes[ok] + 1L]
      out
    } else {
      raw <- h5read(path, where)
      attrs <- h5readAttributes(path, where)
      if (is.numeric(raw) && !is.null(attrs$categories)) {
        cats <- as.character(attrs$categories)
        out <- rep(NA_character_, length(raw))
        ok <- !is.na(raw) & raw >= 0 & raw < length(cats)
        out[ok] <- cats[raw[ok] + 1L]
        out
      } else {
        as.character(raw)
      }
    }
  }

  obs_names <- tryCatch(read_strings("obs/_index"),
                        error = function(e) die("obs/_index unreadable"))
  var_names <- tryCatch(read_strings("var/_index"),
                        error = function(e) die("var/_index unreadable"))
  n_obs <- length(obs_names)
  n_var <- length(var_names)

  col_path <- paste0("obs/", cluster_column)
  cluster <- tryCatch(
    read_cluster_col(col_path),
    error = function(e) {
      cols <- layout$name[layout$group == "/obs" & layout$name != "_index"]
      die("obs column '", cluster_column, "' not readable (available: ",
          paste(cols, collapse = ", "), ")")
    }
  )
  if (length(cluster) != n_obs) die("cluster column length mismatch")
  names(cluster) <- obs_names

  x_attrs <- h5readAttributes(path, "X")
  if ("h5sparse_format" %in% names(x_attrs)) {
    fmt <- tolower(x_attrs$h5sparse_format)
    shape <- as.integer(x_attrs$h5sparse_shape)
  } else if (!is.null(x_attrs[["encoding-type"]]) &&
             grepl("^(csr|csc)_matrix$", x_attrs[["encoding-type"]])) {
    fmt <- sub("_matrix.*", "", x_attrs[["encoding-type"]])
    shape <- as.integer(x_attrs$shape)
  } else {
    fmt <- NULL
    shape <- NULL
  }

  if (!is.null(fmt)) {
    data <- as.numeric(h5read(path, "X/data"))
    indices <- as.integer(h5read(path, "X/indices"))
    indptr <- as.integer(h5read(path, "X/indptr"))
    nr <- shape[1]
    nc <- shape[2]
    if (identical(fmt, "csr")) {
      if (length(indptr) != nr + 1L) die("CSR indptr length mismatch")
      rows <- rep(seq_len(nr), times = diff(indptr))
      x <- sparseMatrix(i = rows, j = indices + 1L, x = data,
                        dims = c(nr, nc), index1 = TRUE)
    } else if (identical(fmt, "csc")) {
      if (length(indptr) != nc + 1L) die("CSC indptr length mismatch")
      cols <- rep(seq_len(nc), times = diff(indptr))
      x <- sparseMatrix(i = indices + 1L, j = cols, x = data,
                        dims = c(nr, nc), index1 = TRUE)
    } else {
      die("unsupported sparse encoding: ", fmt)
    }
  } else {
    dense <- as.matrix(h5read(path, "X"))
    storage.mode(dense) <- "double"
    x <- Matrix(dense, sparse = TRUE)
    nr <- nrow(x)
    nc <- ncol(x)
  }

  # Orient to genes x cells (nichenetr convention). Standard scanpy/anndata
  # stores cells x genes; transposed storage (rows asserted = genes) is also
  # accepted when the dims identify it unambiguously.
  if (nr == n_obs && nc == n_var) {
    exprs <- t(x)
  } else if (nr == n_var && nc == n_obs) {
    exprs <- x
  } else {
    die("X dims (", nr, "x", nc, ") match neither obs (", n_obs,
        ") nor var (", n_var, ") on either axis")
  }
  rownames(exprs) <- var_names
  colnames(exprs) <- obs_names
  list(exprs = exprs, cluster = cluster)
}

# Aggregate alias rows onto official symbols (sums expression across rows
# mapping to the same official symbol; no-op when names are already unique
# official symbols, which is the common case).
aggregate_onto_symbols <- function(exprs, symbols) {
  dup <- unique(symbols[duplicated(symbols)])
  if (length(dup) == 0L) {
    rownames(exprs) <- symbols
    return(exprs)
  }
  is_dup <- symbols %in% dup
  singles <- exprs[!is_dup, , drop = FALSE]
  rownames(singles) <- symbols[!is_dup]
  groups <- split(which(is_dup), symbols[is_dup])
  dup_rows <- lapply(groups, function(idx) {
    Matrix(colSums(exprs[idx, , drop = FALSE]), nrow = 1L, sparse = TRUE)
  })
  dup_mat <- do.call(rbind, dup_rows)
  rownames(dup_mat) <- names(groups)
  out <- rbind(singles, dup_mat)
  out[order(rownames(out)), , drop = FALSE]
}

read_geneset_file <- function(path) {
  if (!file.exists(path)) die("geneset file not found: ", path)
  lines <- readLines(path, warn = FALSE)
  lines <- trimws(lines)
  lines <- lines[nzchar(lines) & !startsWith(lines, "#")]
  if (length(lines) == 0L) die("geneset file is empty: ", path)
  # One gene per line; tolerate two/multi-column files by taking column 1.
  first <- sub("[\t,;].*$", "", lines)
  unique(first)
}

main <- function() {
  h5ad_path <- env_str("AUTONOMICS_INPUT0")
  geneset_path <- env_str("AUTONOMICS_INPUT1")
  if (!nzchar(h5ad_path)) die("AUTONOMICS_INPUT0 (h5ad) not set")
  if (!nzchar(geneset_path)) die("AUTONOMICS_INPUT1 (geneset file) not set")

  sender <- env_str("NNET_SENDER")
  receiver <- env_str("NNET_RECEIVER")
  if (!nzchar(sender)) die("NNET_SENDER is required (no default)")
  if (!nzchar(receiver)) die("NNET_RECEIVER is required (no default)")

  cluster_column <- env_str("NNET_CLUSTER_COLUMN", "cluster")
  top_n_ligands <- env_int("NNET_TOP_N_LIGANDS", 30L)
  n_targets <- env_int("NNET_N_TARGETS", 200L)
  pct <- env_num("NNET_PCT", 0.10)

  out_dir <- env_str("AUTONOMICS_WORKDIR", getwd())
  dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

  message("driver: inputs h5ad=", h5ad_path, " geneset=", geneset_path)
  message("driver: sender=", sender, " receiver=", receiver,
          " cluster_column=", cluster_column,
          " top_n_ligands=", top_n_ligands,
          " n_targets=", n_targets, " pct=", pct)

  # ---- input ---------------------------------------------------------------
  parsed <- read_h5ad_exprs(h5ad_path, cluster_column)
  exprs <- parsed$exprs
  cluster <- parsed$cluster
  message("driver: h5ad read: ", nrow(exprs), " genes x ", ncol(exprs),
          " cells; clusters: ",
          paste(sort(unique(cluster)), collapse = ", "))

  if (!sender %in% cluster) {
    die("sender '", sender, "' not among clusters; available: ",
        paste(sort(unique(cluster)), collapse = ", "))
  }
  if (!receiver %in% cluster) {
    die("receiver '", receiver, "' not among clusters; available: ",
        paste(sort(unique(cluster)), collapse = ", "))
  }

  # ---- frozen step 1: aliases -> official symbols ---------------------------
  alias_map <- nichenetr::convert_alias_to_symbols(
    aliases = rownames(exprs), organism = "human", verbose = FALSE
  )
  n_alias_fixed <- sum(!is.na(alias_map) & alias_map != rownames(exprs))
  n_dropped <- sum(is.na(alias_map))
  if (n_dropped > 0L) {
    message("driver: WARNING ", n_dropped,
            " gene names not in the alias table were dropped")
  }
  keep <- !is.na(alias_map)
  exprs <- aggregate_onto_symbols(exprs[keep, , drop = FALSE], alias_map[keep])
  message("driver: alias conversion: ", n_alias_fixed, " renamed, ",
          n_dropped, " dropped, ", nrow(exprs), " official symbols remain")

  # ---- frozen step 2: expressed genes in sender and receiver ----------------
  expressed_genes_sender <- nichenetr::get_expressed_genes(
    celltype_oi = sender, object = exprs, celltype_annot = cluster, pct = pct
  )
  expressed_genes_receiver <- nichenetr::get_expressed_genes(
    celltype_oi = receiver, object = exprs, celltype_annot = cluster, pct = pct
  )
  message("driver: expressed genes sender=", length(expressed_genes_sender),
          " receiver=", length(expressed_genes_receiver))

  # ---- priors (baked in, MD5-gated at build time) ---------------------------
  ltm <- readRDS(file.path(PRIORS_DIR, PRIOR_LTM))
  weighted_networks <- readRDS(file.path(PRIORS_DIR, PRIOR_WN))
  lr_network <- readRDS(file.path(PRIORS_DIR, PRIOR_LR))

  # ---- frozen step 3: geneset + background ----------------------------------
  geneset <- read_geneset_file(geneset_path)
  background <- intersect(expressed_genes_receiver, rownames(ltm))
  message("driver: geneset n=", length(geneset), " background n=",
          length(background))
  if (length(geneset) == 0L) die("empty geneset after reading file")
  if (length(background) == 0L) {
    die("background empty: no receiver expressed gene is a prior target")
  }

  # ---- frozen step 4: potential ligands (pairwise filter) -------------------
  lr_pairs <- lr_network %>%
    dplyr::filter(.data$from %in% expressed_genes_sender,
                  .data$to %in% expressed_genes_receiver) %>%
    dplyr::distinct(.data$from, .data$to)
  potential_ligands <- intersect(unique(lr_pairs$from), colnames(ltm))
  message("driver: lr pairs passing expression filter: ", nrow(lr_pairs),
          "; potential ligands: ", length(potential_ligands))
  if (length(potential_ligands) == 0L) {
    die("no potential ligands: no lr_network pair with ligand expressed in '",
        sender, "' and receptor expressed in '", receiver, "'")
  }

  # ---- frozen step 5: official ligand activity prediction -------------------
  ligand_activities <- nichenetr::predict_ligand_activities(
    geneset = geneset,
    background_expressed_genes = background,
    ligand_target_matrix = ltm,
    potential_ligands = potential_ligands
  )
  ligand_activities <- ligand_activities %>%
    dplyr::arrange(dplyr::desc(.data$aupr_corrected), .data$test_ligand) %>%
    dplyr::mutate(rank = dplyr::row_number())
  message("driver: top 5 ligands: ",
          paste(head(ligand_activities$test_ligand, 5), collapse = ", "))

  # ---- frozen step 6: top-N ligands -----------------------------------------
  n_top <- min(top_n_ligands, nrow(ligand_activities))
  best_upstream_ligands <- ligand_activities %>%
    dplyr::slice_head(n = n_top) %>%
    dplyr::pull(.data$test_ligand)

  # ---- frozen step 7: ligand-target links (official idiom: per ligand) ------
  ligand_target_links <- best_upstream_ligands %>%
    lapply(nichenetr::get_weighted_ligand_target_links,
           geneset = geneset, ligand_target_matrix = ltm, n = n_targets) %>%
    dplyr::bind_rows()

  # ---- frozen step 8: ligand-receptor links ---------------------------------
  expressed_receptors <- intersect(lr_network$to, expressed_genes_receiver)
  ligand_receptor_links <- nichenetr::get_weighted_ligand_receptor_links(
    best_upstream_ligands = best_upstream_ligands,
    expressed_receptors = expressed_receptors,
    lr_network = lr_network,
    weighted_networks_lr_sig = weighted_networks$lr_sig
  )

  # ---- outputs (workdir root, fixed names) ----------------------------------
  out_activities <- "nichenetr_ligand_activities.csv"
  out_lt <- "nichenetr_ligand_target_links.csv"
  out_lr <- "nichenetr_ligand_receptor_links.csv"
  out_top <- "nichenetr_top_ligands.csv"
  out_prov <- "nichenetr_provenance.json"

  utils::write.csv(ligand_activities, file.path(out_dir, out_activities),
                   row.names = FALSE, quote = TRUE)
  utils::write.csv(ligand_target_links, file.path(out_dir, out_lt),
                   row.names = FALSE, quote = TRUE)
  utils::write.csv(ligand_receptor_links, file.path(out_dir, out_lr),
                   row.names = FALSE, quote = TRUE)
  utils::write.csv(
    ligand_activities %>%
      dplyr::select(.data$rank, .data$test_ligand, .data$aupr_corrected,
                    .data$aupr, .data$auroc, .data$pearson) %>%
      dplyr::slice_head(n = n_top),
    file.path(out_dir, out_top), row.names = FALSE, quote = TRUE
  )

  prior_files <- c(PRIOR_LTM, PRIOR_WN, PRIOR_LR)
  prior_md5 <- vapply(prior_files, function(f) {
    unname(tools::md5sum(file.path(PRIORS_DIR, f)))
  }, character(1))
  provenance <- list(
    package = "nichenetr",
    package_version = as.character(utils::packageVersion("nichenetr")),
    nichenetr_commit = "f9906f3a51ddc09405a04ece9de375688e03facb",
    nichenetr_tag = "v2.2.0",
    r_version = paste(R.version$major, R.version$minor, sep = "."),
    priors = lapply(seq_along(prior_files), function(i) {
      list(file = prior_files[[i]], md5 = unname(prior_md5[[i]]))
    }),
    priors_source = "Zenodo record 7074291 (human nsga2r set)",
    organism = "human",
    params = list(
      sender = sender,
      receiver = receiver,
      cluster_column = cluster_column,
      top_n_ligands = top_n_ligands,
      n_targets = n_targets,
      pct = pct,
      ranking_metric = "aupr_corrected"
    ),
    frozen_pipeline = c(
      "convert_alias_to_symbols",
      "get_expressed_genes",
      "background = receiver expressed INTERSECT prior targets",
      "pairwise potential-ligand filter",
      "predict_ligand_activities (aupr_corrected)",
      "top-N ligands",
      "get_weighted_ligand_target_links",
      "get_weighted_ligand_receptor_links"
    ),
    geneset_source = basename(geneset_path),
    geneset_n = length(geneset),
    background_n = length(background),
    potential_ligands_n = length(potential_ligands),
    expressed_genes_sender_n = length(expressed_genes_sender),
    expressed_genes_receiver_n = length(expressed_genes_receiver),
    expressed_receptors_n = length(expressed_receptors),
    alias_genes_renamed = n_alias_fixed,
    alias_genes_dropped = n_dropped,
    inputs = list(
      h5ad = basename(h5ad_path),
      geneset = basename(geneset_path)
    ),
    outputs = c(out_activities, out_lt, out_lr, out_top, out_prov)
  )
  jsonlite::write_json(provenance, file.path(out_dir, out_prov),
                       auto_unbox = TRUE, pretty = TRUE, digits = NA)

  message("driver: outputs written to ", out_dir)
  for (f in list.files(out_dir)) {
    message("driver: output ", f, " (",
            file.size(file.path(out_dir, f)), " bytes)")
  }
}

# Sourcing guard: fixtures/tests source this file to reuse the reader.
if (identical(Sys.getenv("NNET_SOURCE_ONLY"), "")) main()
