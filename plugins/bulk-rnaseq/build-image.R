options(repos = c(
  CRAN = "https://packagemanager.posit.co/cran/__linux__/noble/2026-09-13",
  BioCsoft = "https://bioconductor.org/packages/3.22/bioc",
  BioCann = "https://bioconductor.org/packages/3.22/data/annotation",
  BioCexp = "https://bioconductor.org/packages/3.22/data/experiment"
))
stopifnot(getRversion() == "4.5.3")
phase <- commandArgs(trailingOnly = TRUE)
stopifnot(length(phase) == 1L, phase %in% c("core", "dependencies", "WGCNA", "verify"))
archives <- file.path("/tmp/method-sources", c(
  "statmod_1.5.2.tar.gz", "limma_3.66.0.tar.gz", "edgeR_4.8.2.tar.gz"
))
if (phase == "core") {
  for (archive in archives) {
    install.packages(archive, repos = NULL, type = "source", Ncpus = 1)
  }
}
if (phase == "dependencies") {
  install.packages(c(
    "dynamicTreeCut", "preprocessCore", "impute", "fastcluster", "matrixStats",
    "doParallel", "foreach", "Rcpp", "Hmisc"
  ), Ncpus = 1)
}
if (phase == "WGCNA") {
  install.packages("/tmp/method-sources/WGCNA_1.74.tar.gz", repos = NULL, type = "source", Ncpus = 1)
}
if (phase != "verify") {
  quit(save = "no", status = 0)
}
expected <- c(limma = "3.66.0", edgeR = "4.8.2", statmod = "1.5.2", WGCNA = "1.74")
for (package in names(expected)) {
  stopifnot(as.character(packageVersion(package)) == expected[[package]])
}
packages <- as.data.frame(installed.packages()[, c("Package", "Version", "Built")], stringsAsFactors = FALSE)
packages <- packages[order(packages$Package), ]
dir.create("/opt/autonomics", recursive = TRUE, showWarnings = FALSE)
write.table(packages, "/opt/autonomics/installed-packages.tsv", sep = "\t", quote = FALSE, row.names = FALSE)
writeLines(capture.output(sessionInfo()), "/opt/autonomics/build-session-info.txt")
