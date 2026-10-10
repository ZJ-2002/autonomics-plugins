#!/usr/bin/env Rscript
# SPDX-License-Identifier: GPL-3.0-only
#
# Fixture generator, R half. Runs INSIDE the built nichenetr image (it needs
# the baked priors and the official package). It seeds the planted signal
# FROM THE OFFICIAL PRIOR ITSELF: pick a ligand L whose top-50 prior targets
# give L rank 1 by aupr_corrected under the EXACT filtering the driver will
# apply, then emit the planted gene lists for the python half.
#
# Usage (inside the image, /io mounted):
#   Rscript /io/make_fixture.R            # writes /io/fixture_spec.json,
#                                        #        /io/geneset.txt,
#                                        #        /io/expected.json
# Deterministic: fixed seeds, no RNG in the acceptance loop.

suppressPackageStartupMessages({
  library(nichenetr)
  library(dplyr)
  library(jsonlite)
})

PRIORS_DIR <- "/opt/nichenetr/priors"
OUT_DIR <- "/io"

message("fixture: loading priors")
ltm <- readRDS(file.path(PRIORS_DIR, "ligand_target_matrix_nsga2r_final.rds"))
weighted_networks <- readRDS(file.path(PRIORS_DIR, "weighted_networks_nsga2r_final.rds"))
lr_network <- readRDS(file.path(PRIORS_DIR, "lr_network_human_21122021.rds"))
lr_sig <- weighted_networks$lr_sig

# Deterministic background: 500 prior targets planted at low level in every
# cluster (the receiver's expressed-gene background the driver will compute).
set.seed(2024)
bg <- sample(rownames(ltm), 500)

# Candidate ligands: real lr_network ligands with broad, strong prior
# profiles (>= 300 positive target weights), strongest top-50 mass first.
ligand_mass <- apply(ltm, 2, function(w) sum(head(sort(w, decreasing = TRUE), 50)))
ligand_npos <- apply(ltm, 2, function(w) sum(w > 0))
candidates <- intersect(colnames(ltm), unique(lr_network$from))
candidates <- candidates[ligand_npos[candidates] >= 300]
candidates <- candidates[order(-ligand_mass[candidates], candidates)]
message("fixture: ", length(candidates), " candidate ligands")

# The receiver also gets one real receptor of L planted, so L's ligand-
# receptor pair passes the driver's pairwise filter.
pick_receptor <- function(ligand) {
  recs <- lr_network %>% filter(.data$from == ligand) %>% pull(.data$to)
  if (length(recs) == 0L) return(NA_character_)
  w <- lr_sig %>% filter(.data$from == ligand, .data$to %in% recs)
  if (nrow(w) > 0) {
    w <- w %>% arrange(dplyr::desc(.data$weight), .data$to)
    return(w$to[1])
  }
  sort(recs)[1]
}

prescreen <- function(ligand) {
  geneset <- head(names(sort(ltm[, ligand], decreasing = TRUE)[
    sort(ltm[, ligand], decreasing = TRUE) > 0]), 50)
  receptor <- pick_receptor(ligand)
  if (is.na(receptor)) return(list(ok = FALSE, why = "no receptor"))
  sender_set <- union(ligand, bg)
  receiver_set <- union(union(geneset, bg), receptor)
  pairs <- lr_network %>%
    filter(.data$from %in% sender_set, .data$to %in% receiver_set) %>%
    distinct(.data$from, .data$to)
  potential <- intersect(unique(pairs$from), colnames(ltm))
  if (!(ligand %in% potential)) {
    return(list(ok = FALSE, why = "ligand not in potential set"))
  }
  background <- intersect(receiver_set, rownames(ltm))
  act <- predict_ligand_activities(
    geneset = geneset,
    background_expressed_genes = background,
    ligand_target_matrix = ltm,
    potential_ligands = potential
  )
  act <- act %>% arrange(dplyr::desc(.data$aupr_corrected), .data$test_ligand)
  rank_lig <- which(act$test_ligand == ligand)
  margin <- act$aupr_corrected[1] - act$aupr_corrected[
    min(4L, nrow(act))]  # gap rank1 -> rank4 (assertion threshold is top-3)
  list(
    # rank 1 AND a margin big enough that the Poisson tail (a background gene
    # randomly missing the 10% expression cutoff, p ~ 1e-8) cannot flip the
    # driver-side top-3 assertion.
    ok = length(rank_lig) == 1L && rank_lig == 1L && margin >= 0.02,
    rank = rank_lig,
    margin = margin,
    geneset = geneset,
    receptor = receptor,
    n_potential = length(potential),
    n_background = length(background),
    aupr_corrected = act$aupr_corrected[rank_lig],
    runner_up = act$test_ligand[1]
  )
}

chosen <- NULL
tries <- 0
for (cand in head(candidates, 40)) {
  tries <- tries + 1
  res <- prescreen(cand)
  message("fixture: candidate ", cand, " rank=", res$rank %||% "NA",
          " potential=", res$n_potential %||% "NA")
  if (isTRUE(res$ok)) {
    chosen <- c(list(ligand = cand), res)
    break
  }
}
if (is.null(chosen)) stop("fixture: no candidate reached rank 1 in 40 tries")

message("fixture: chose ligand ", chosen$ligand, " (rank ", chosen$rank,
        ", aupr_corrected ", round(chosen$aupr_corrected, 4),
        ", potential ligands ", chosen$n_potential, ")")

spec <- list(
  ligand = chosen$ligand,
  receptor = chosen$receptor,
  geneset = chosen$geneset,
  background = bg,
  sender_cluster = "Sender",
  receiver_cluster = "Receiver",
  bystander_cluster = "Bystander",
  n_cells_per_cluster = 120
)
write_json(spec, file.path(OUT_DIR, "fixture_spec.json"),
           auto_unbox = TRUE, pretty = TRUE)

writeLines(chosen$geneset, file.path(OUT_DIR, "geneset.txt"))

expected <- list(
  ligand = chosen$ligand,
  metric = "aupr_corrected",
  expect_rank_le = 3,
  prescreen_rank = chosen$rank,
  prescreen_margin_to_rank4 = chosen$margin,
  prescreen_aupr_corrected = chosen$aupr_corrected,
  prescreen_runner_up = chosen$runner_up,
  prescreen_potential_ligands = chosen$n_potential,
  prescreen_background = chosen$n_background
)
write_json(expected, file.path(OUT_DIR, "expected.json"),
           auto_unbox = TRUE, pretty = TRUE, digits = NA)
message("fixture: spec/geneset/expected written to ", OUT_DIR)
