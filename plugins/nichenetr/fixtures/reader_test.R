#!/usr/bin/env Rscript
# SPDX-License-Identifier: GPL-3.0-only
#
# Unit test for the driver's h5ad reader, run inside the built image:
#   Rscript /io/reader_test.R /inputs
# Exercises every supported on-disk shape (all encode the same data:
# cells c0..c3, genes G1..G3, clusters A,A,B,B):
#   current.h5ad    anndata 0.13 encoding, CSR, cells x genes
#   legacy.h5ad     h5sparse attrs, vlen-str datasets, codes + categories attr
#   transposed.h5ad 0.13 encoding, CSC, genes x cells storage
#   dense.h5ad      0.13 dense dataset

Sys.setenv(NNET_SOURCE_ONLY = "1")
source("/opt/autonomics/driver.R")

args <- commandArgs(trailingOnly = TRUE)
indir <- if (length(args) >= 1) args[[1]] else "/inputs"

fails <- 0L
expect <- function(name, cond, detail = "") {
  cat(if (cond) "[PASS] " else "[FAIL] ", name, " ", detail, "\n", sep = "")
  if (!cond) fails <<- fails + 1L
}

# G1: c0=1,c2=4 ; G2: c1=3,c3=6 ; G3: c0=2,c2=5
ref <- matrix(0, 3, 4,
              dimnames = list(c("G1", "G2", "G3"), c("c0", "c1", "c2", "c3")))
ref["G1", c("c0", "c2")] <- c(1, 4)
ref["G2", c("c1", "c3")] <- c(3, 6)
ref["G3", c("c0", "c2")] <- c(2, 5)

cases <- c("current.h5ad", "legacy.h5ad", "transposed.h5ad", "dense.h5ad")
for (f in cases) {
  r <- read_h5ad_exprs(file.path(indir, f), "cluster")
  expect(paste(f, "dims 3x4"), identical(dim(r$exprs), c(3L, 4L)),
         paste(dim(r$exprs), collapse = "x"))
  expect(paste(f, "rownames"),
         identical(rownames(r$exprs), c("G1", "G2", "G3")))
  expect(paste(f, "colnames"),
         identical(colnames(r$exprs), c("c0", "c1", "c2", "c3")))
  expect(paste(f, "values"),
         isTRUE(all.equal(as.matrix(r$exprs), ref, check.attributes = FALSE)))
  expect(paste(f, "cluster"),
         identical(as.character(r$cluster), c("A", "A", "B", "B")))
}

# Error path: die() quits the process with status 1 -> subprocess check.
out <- system2(
  "Rscript", c("-e", shQuote(sprintf(
    paste0('Sys.setenv(NNET_SOURCE_ONLY="1"); ',
           'source("/opt/autonomics/driver.R"); ',
           'read_h5ad_exprs("%s", "nope")'),
    file.path(indir, "dense.h5ad")))),
  stdout = TRUE, stderr = TRUE
)
expect("missing column exits 1", identical(attr(out, "status"), 1L),
       paste(tail(out, 1), collapse = " "))

if (fails > 0L) {
  cat("READER TESTS FAILED: ", fails, "\n", sep = "")
  quit(save = "no", status = 1L)
}
cat("READER TESTS PASSED\n")
