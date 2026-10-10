# SPDX-License-Identifier: GPL-3.0-only
#
# Pinned dependency install for the CellChat tier-1 image. Two stages, run
# as separate Docker layers so the slow Bioconductor compile layer survives
# changes to the fast CellChat layer:
#
#   Rscript install-deps.R bioc      # Bioc 3.20 source packages (HDF5!)
#   Rscript install-deps.R cellchat  # CRAN binaries + CellChat from tarball
#
# - CRAN deps come from the dated Posit Package Manager jammy snapshot
#   (precompiled binaries, no per-package compilation).
# - Bioconductor 3.20 (the release matching R 4.4.x) has no PPM binaries on
#   the public Posit repo; these packages compile from source once at build
#   time. Biobase is here because NMF (CRAN, CellChat Imports) Imports it —
#   the CRAN-only PPM repo cannot serve Bioconductor packages.
# - CellChat itself installs from the vendored upstream tarball at the
#   pinned commit (remotes::install_local), so the build never depends on
#   the GitHub API being reachable. Pinned commit:
#   jinworks/CellChat@75253cd0c9e68410e6e721a6d3a0419a1d7e358f
#   (official main HEAD 2026-03-04, includes the PR #438 bootstrap parallel
#   fix; the v2.1.2 tag predates it and carries the >=40k-cell parallel
#   performance bug — NEVER install the v2.1.2 tag).

options(warn = 1)
options(HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(),
        paste(getRversion(), R.version$platform, R.version$arch, R.version$os)))

stopifnot(getRversion() >= "4.4.1", getRversion() < "4.5.0")

# Dated binary snapshot of CRAN for jammy (pinned for reproducibility).
options(repos = c(CRAN = "https://packagemanager.posit.co/cran/__linux__/jammy/2026-10-01"))

TARBALL <- "/opt/src/cellchat-75253cd0.tar.gz"
# presto (GPL-3, immunogenomics/presto@b5df6ee6, v1.1.0): NOT the CRAN
# "presto" (that is a PrestoDB DBI connector). CellChat's official default
# identifyOverExpressedGenes path (do.fast=TRUE) hard-requires it, and per
# upstream docs the presto vs stats wilcoxon paths produce DIFFERENT logFC
# values — presto is the official default, so it is vendored and pinned too.
PRESTO_TARBALL <- "/opt/src/presto-b5df6ee6.tar.gz"

stage <- commandArgs(trailingOnly = TRUE)[[1]]

if (stage == "bioc") {
  BiocManager <- NULL
  install.packages("BiocManager")
  BiocManager::install(
    c("BiocGenerics", "Biobase", "BiocNeighbors", "rhdf5", "ComplexHeatmap"),
    update = FALSE, ask = FALSE, version = "3.20"
  )
  quit(save = "no", status = 0L)
}

if (stage == "cellchat") {
  stopifnot(file.exists(TARBALL))
  install.packages("remotes")

  # dependencies = NA installs ONLY Depends/Imports/LinkingTo — TRUE would
  # pull CellChat's Suggests (tidyverse, Seurat, SingleCellExperiment, ...),
  # which the tier-1 contract explicitly forbids in the image.
  remotes::install_local(TARBALL, dependencies = NA, upgrade = "never")
  stopifnot(file.exists(PRESTO_TARBALL))
  remotes::install_local(PRESTO_TARBALL, dependencies = NA, upgrade = "never")

  cat("presto version:", as.character(packageVersion("presto")), "\n")
  stopifnot(as.character(packageVersion("presto")) == "1.1.0")

  # Tier-1 exclusions: no Seurat / SingleCellExperiment may end up in the image.
  for (b in c("Seurat", "SeuratObject", "SingleCellExperiment", "SummarizedExperiment")) {
    if (requireNamespace(b, quietly = TRUE)) {
      stop("forbidden package installed: ", b)
    }
  }

  cat("CellChat version:", as.character(packageVersion("CellChat")), "\n")
  stopifnot(as.character(packageVersion("CellChat")) == "2.2.0.9001")

  # Lock-equivalent record: full installed-package table baked into the image.
  ip <- installed.packages()[, c("Package", "Version", "LibPath", "Built")]
  ip <- ip[order(rownames(ip)), ]
  write.table(ip, "/opt/autonomics/r-pkg-versions.tsv",
              sep = "\t", quote = FALSE, col.names = NA)
  cat("wrote /opt/autonomics/r-pkg-versions.tsv (", nrow(ip), "packages )\n")
  quit(save = "no", status = 0L)
}

stop("usage: Rscript install-deps.R bioc|cellchat")
